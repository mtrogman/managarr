# modules/discordFunctions.py

import logging, math, discord, asyncio
from typing import Set
from modules.globalBot import bot
from discord.ui import Select, View, Button
from plexapi.server import PlexServer
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from modules import configFunctions, dbFunctions, emailFunctions, mathFunctions
from modules.promotions import referral_reward_for_new_user_first_purchase

# ---------------------- Config ----------------------
config_location = "./config/config.yml"
config = configFunctions.get_config(config_location)
dcfg = config.get("discord", {}) or {}

# ---------------------- Helpers ----------------------
_NEWUSER_LOCK = asyncio.Lock()
_PROCESSED_NEWUSER_KEYS: Set[str] = set()

def _newuser_op_key(info: dict) -> str:
    return f"{str(info.get('primaryEmail','')).strip().lower()}|{info.get('startDate')}|{info.get('endDate')}"

def _parse_date_yyyy_mm_dd(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None

async def send_discord_message(to_user, subject, body):
    if bot is None:
        logging.error("The bot instance in globalBot is None!")
        return
    if not bot.is_ready():
        logging.error("The bot is not ready yet!")
        return
    try:
        user = await bot.fetch_user(int(to_user))
        embed = discord.Embed(title=f"**{subject}**", description=body, color=discord.Colour.blue())
        await user.send(embed=embed)
    except discord.errors.Forbidden as e:
        logging.warning(f"Failed to send message to {to_user}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred sending DM: {e}")

async def add_role(user_id: int | str, role_name: str | None):
    """Best-effort role add. Requires discord.guildId in config and a matching role in guild."""
    if not role_name:
        return
    try:
        guild_id = int(dcfg.get("guildId") or config["discord"]["guildId"])
    except Exception as e:
        logging.error(f"discord.guildId missing/invalid in config: {e}")
        return
    guild = bot.get_guild(guild_id)
    if not guild:
        logging.error(f"Guild with ID {guild_id} not found.")
        return
    try:
        member = await guild.fetch_member(int(user_id))
    except Exception as e:
        logging.error(f"Could not fetch member {user_id}: {e}")
        return
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        logging.error(f"Role '{role_name}' not found in guild {guild_id}")
        return
    try:
        await member.add_roles(role, reason="New user confirmation")
    except Exception as e:
        logging.error(f"Failed to add role '{role_name}' to {user_id}: {e}")

# ---------------------- Message editing utility ----------------------
async def _edit_same_message(interaction: discord.Interaction, *, content: str, view=None) -> bool:
    """
    Always try to edit the SAME anchor message without creating new bubbles.
    Returns True if any edit succeeded.
    """
    # 1) Component message
    try:
        if getattr(interaction, "message", None):
            await interaction.message.edit(content=content, view=view)
            return True
    except Exception:
        pass
    # 2) Response (if still open)
    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=content, view=view)
            return True
    except Exception:
        pass
    # 3) Fallback to original response (if available)
    try:
        await interaction.edit_original_response(content=content, view=view)
        return True
    except Exception:
        pass
    return False

# ---------------------- (Aux) Server & Library selection (single-anchor) ----------------------
class ServerSelect(Select):
    def __init__(self, interaction, servers):
        servers_filtered = []
        for server in servers:
            if 'server' in getattr(server, 'provides', []) and getattr(server, 'owned', False):
                servers_filtered.append(server)

        options = [discord.SelectOption(label=server.name, value=server.name) for server in servers_filtered] \
                  if servers_filtered else [discord.SelectOption(label="No servers available", value="none")]

        super().__init__(placeholder="Choose a server", min_values=1, max_values=1, options=options)
        self.interaction = interaction  # original command interaction
        self.servers_filtered = servers_filtered

    async def callback(self, interaction: discord.Interaction):
        # Ack without changing text
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        selected_server_name = self.values[0]
        if selected_server_name == "none":
            await _edit_same_message(interaction, content="No servers available.", view=None)
            return

        # Load libraries
        try:
            base_url = config.get(f"PLEX-{selected_server_name}", {}).get('baseUrl')
            token = config.get(f"PLEX-{selected_server_name}", {}).get('token')
            plex = PlexServer(base_url, token)
            libraries = [section.title for section in plex.library.sections()]
        except Exception as e:
            logging.error(f"Error connecting to Plex server '{selected_server_name}': {e}")
            await _edit_same_message(
                interaction,
                content=f"Error connecting to server '{selected_server_name}'. Please try again later.",
                view=None
            )
            return

        view = View()
        view.add_item(StandardLibrarySelect(selected_server_name, libraries))
        await _edit_same_message(
            interaction,
            content=f"Server: **{selected_server_name}**\nChoose standard libraries:",
            view=view
        )

class StandardLibrarySelect(Select):
    def __init__(self, selected_server_name, libraries):
        super().__init__(placeholder="Choose standard libraries", min_values=1, max_values=len(libraries))
        self.selected_server_name = selected_server_name
        self.libraries = libraries
        self.options = [discord.SelectOption(label=lib, value=lib) for lib in libraries]

    async def callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        selected_libraries = self.values
        optional_library_options = [lib for lib in self.libraries if lib not in selected_libraries]
        view = View()
        view.add_item(OptionalLibrarySelect(self.selected_server_name, selected_libraries, optional_library_options))
        await _edit_same_message(
            interaction,
            content=(
                "Standard libraries selected: " + ", ".join(selected_libraries) +
                "\nChoose optional libraries (or skip):"
            ),
            view=view
        )

class OptionalLibrarySelect(Select):
    def __init__(self, selected_server_name, standard_library_titles, optional_library_options):
        super().__init__(placeholder="Choose optional libraries", min_values=0, max_values=max(1, len(optional_library_options)))
        self.selected_server_name = selected_server_name
        self.standard_library_titles = standard_library_titles
        self.optional_library_options = optional_library_options
        self.options = [discord.SelectOption(label=lib, value=lib) for lib in optional_library_options] or [
            discord.SelectOption(label="(None)", value="__none__")
        ]

    async def callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        selected_optional_libraries = [] if self.values == ["__none__"] else self.values
        section_names = self.standard_library_titles + selected_optional_libraries

        plex_cfg = (config.get(f"PLEX-{self.selected_server_name}", {}) or {})
        base_url = plex_cfg.get('baseUrl')
        token = plex_cfg.get('token')

        if not base_url or not token:
            await _edit_same_message(
                interaction,
                content=f"Invalid configuration for Plex server '{self.selected_server_name}'",
                view=None
            )
            return

        # Invite to Plex or produce preview (admin flow – just show summary)
        summary_lines = []
        try:
            PlexServer(base_url, token)  # just validate connectivity
            libraries_str = ", ".join(section_names) if section_names else "(none)"
            summary_lines.append(f"Server: {self.selected_server_name}")
            summary_lines.append(f"Libraries: {libraries_str}")
        except Exception as e:
            logging.error(f"Error authenticating to Plex at {base_url}: {e}")
            summary_lines.append("Failed to connect to Plex server.")

        await _edit_same_message(interaction, content="\n".join(summary_lines) or "Done.", view=None)

# ======================================================================
#                            PAYMENT RECEIVED (renewal)
# ======================================================================
class RenewConfirmView(View):
    """Shows confirmation for a renewal, then applies on Correct (single anchor; no interim texts)."""
    def __init__(self, base_message_interaction: discord.Interaction, summary_text: str, context: dict):
        super().__init__(timeout=180.0)
        self.anchor_interaction = base_message_interaction
        self.summary_text = summary_text
        self.ctx = context

        import asyncio
        self._processing = False
        self._lock = asyncio.Lock()

        btn_ok = Button(style=discord.ButtonStyle.primary, label="Correct")
        btn_ok.callback = self.on_confirm
        self.add_item(btn_ok)

        btn_cancel = Button(style=discord.ButtonStyle.danger, label="Cancel")
        btn_cancel.callback = self.on_cancel
        self.add_item(btn_cancel)

    async def _edit_anchor(self, interaction: discord.Interaction, *, content: str, view=None):
        ok = await _edit_same_message(interaction, content=content, view=view)
        if not ok:
            # Last fallback to the stored base interaction
            try:
                await self.anchor_interaction.edit_original_response(content=content, view=view)
            except Exception:
                pass

    async def on_confirm(self, interaction: discord.Interaction):
        # Ack immediately — prevents "This interaction failed"
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        # Idempotency
        if self._processing or self.ctx.get('_renew_done'):
            return
        if self._lock.locked():
            return
        async with self._lock:
            if self._processing or self.ctx.get('_renew_done'):
                return
            self._processing = True
            self.ctx['_renew_done'] = True

            # Disable buttons right away (same bubble)
            try:
                for child in self.children:
                    try: child.disabled = True
                    except Exception: pass
                if getattr(interaction, "message", None):
                    await interaction.message.edit(view=self)
            except Exception:
                try:
                    if getattr(interaction, "message", None):
                        await interaction.message.edit(view=None)
                except Exception:
                    pass

            try:
                user_to_update = self.ctx["user_to_update"]
                paid_amount = float(self.ctx["paid_amount"])
                term_length = int(self.ctx["term_length"])
                new_end_date = self.ctx["new_end_date"]
                start_date = self.ctx["start_date"]
                align_line = self.ctx["align_line"]

                user_id = user_to_update.get('id')
                server = user_to_update.get('server')
                is_4k = user_to_update.get('4k')

                # Update DB
                dbFunctions.update_database(user_id, "startDate", start_date.strftime('%Y-%m-%d'))
                dbFunctions.update_database(user_id, "endDate", new_end_date.strftime('%Y-%m-%d'))
                dbFunctions.update_database(user_id, "status", "Active")

                # Log (quiet fail)
                info = dict(self.ctx.get("information") or {})
                info.setdefault('primaryEmail', user_to_update.get('primaryEmail') or "")
                info.setdefault('server', server)
                info.setdefault('4k', is_4k)
                info.setdefault('paidAmount', paid_amount)
                info.setdefault('term_length', term_length)
                info.setdefault('termLength', term_length)
                try:
                    dbFunctions.log_transaction(information=info)
                except Exception as e:
                    logging.info(f"log_transaction skipped due to internal error: {e}")

                # Notify user (best-effort)
                user_email = user_to_update.get('primaryEmail')
                discord_user_id = user_to_update.get('primaryDiscordId')
                try:
                    subject = dcfg.get('paymentSubject', "Subscription Updated")
                    body_tmpl = dcfg.get('paymentBody', "Your subscription for {primaryEmail} now ends on {newEndDate}.")
                    body = body_tmpl.format(
                        primaryEmail=user_email,
                        server=server,
                        section_names=("4k" if (is_4k == "Yes") else "1080p"),
                        newEndDate=new_end_date.strftime('%Y-%m-%d')
                    )
                    if discord_user_id:
                        await send_discord_message(to_user=discord_user_id, subject=subject, body=body)
                    emailFunctions.send_email(config_location, subject, body, user_email)
                except Exception as e:
                    logging.warning(f"Renewal notify failed: {e}")

                # Final moderator summary (overwrite same message)
                old_end = self.ctx["old_end_date"]
                old_end_str = old_end.strftime('%Y-%m-%d') if hasattr(old_end, "strftime") else str(old_end)
                followup = (
                    "---------------------\n"
                    f"Discord: {user_to_update.get('primaryDiscord')}\n"
                    f"Email: {user_to_update.get('primaryEmail')}\n"
                    f"Server: {server}\n"
                    f"4k: {is_4k}\n"
                    "---------------------\n"
                    f"Old End: {old_end_str}\n"
                    f"New End: {new_end_date.strftime('%Y-%m-%d')}\n"
                    f"Months Added: {term_length}\n"
                    f"{align_line}\n"
                    "---------------------\n"
                    f"Status: Active\n"
                    f"Paid Amount: {paid_amount}\n"
                )

                await self._edit_anchor(interaction, content=followup, view=None)

            except Exception as e:
                logging.exception(e)
                await self._edit_anchor(interaction, content=f"Error applying renewal: {e}", view=None)

    async def on_cancel(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass
        await self._edit_anchor(interaction, content="Cancelled the request.", view=None)

class UpdateSelector(Select):
    def __init__(self, data, information):
        self.information = information
        options = []
        for row in data or []:
            email = (row or {}).get('primaryEmail')
            discord_name = (row or {}).get('primaryDiscord')
            status = (row or {}).get('status')
            payment_person = (row or {}).get('paymentPerson')
            if not email:
                continue
            label = f"{email} - {discord_name} - {status} - {payment_person}"
            options.append(discord.SelectOption(label=label, value=email))

        super().__init__(placeholder="Please select the user", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Ack, but do not modify text; we'll overwrite with the preview once ready
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        picked_email = self.values[0]
        await self.view.render_confirmation(interaction, picked_email, self.information)

class UpdateSelectorView(View):
    def __init__(self, search_results, information):
        super().__init__(timeout=180.0)
        self.information = information
        self.add_item(UpdateSelector(search_results, information))

    async def render_confirmation(self, interaction: discord.Interaction, picked_email: str, info: dict):
        # Find the selected user
        matches = dbFunctions.find_user(picked_email) or []
        user_to_update = next(
            (r for r in matches
             if (r.get('primaryEmail') or '').strip().lower() == picked_email.strip().lower()
             or (r.get('secondaryEmail') or '').strip().lower() == picked_email.strip().lower()),
            matches[0] if matches else None
        )

        if not user_to_update:
            await _edit_same_message(interaction, content=f"The person for {picked_email} does not exist in DB.", view=None)
            return

        # Build preview
        paid_amount = info.get('paidAmount')
        if paid_amount is None:
            await _edit_same_message(interaction, content="Paid amount information is missing.", view=None)
            return

        # Normalize current end date
        old_end_val = user_to_update.get('endDate')
        if isinstance(old_end_val, datetime):
            old_end = old_end_val.date()
        elif isinstance(old_end_val, str):
            old_end = datetime.strptime(old_end_val, '%Y-%m-%d').date()
        else:
            old_end = old_end_val  # date or None

        start_date = datetime.now().date()
        server = user_to_update.get('server')
        is_4k = user_to_update.get('4k')

        paid_amount = math.floor(float(paid_amount) * 100) / 100.0
        term_length = mathFunctions.calculate_term_length(server, paid_amount, is_4k)
        new_end = max(start_date, old_end) + relativedelta(months=term_length)

        # Price alignment
        def _std_prices(_server: str, _is_4k: str):
            plan = (config.get(f"PLEX-{_server}", {}) or {}).get("4k" if _is_4k == "Yes" else "1080p", {}) or {}
            return {
                12: float(plan.get("12Month") or 0),
                6:  float(plan.get("6Month") or 0),
                3:  float(plan.get("3Month") or 0),
                1:  float(plan.get("1Month") or 0),
            }
        prices = _std_prices(server, is_4k)
        remaining = round(float(paid_amount), 2)
        pack = []
        for m in (12, 6, 3, 1):
            tier = round(float(prices.get(m, 0) or 0), 2)
            while tier > 0 and remaining + 1e-9 >= tier:
                pack.append(m)
                remaining = round(remaining - tier, 2)
        aligned = (len(pack) > 0 and abs(remaining) < 0.01)
        align_line = (f"Aligned Price: {'+'.join(str(x) for x in pack)} month(s) (total {sum(pack)})"
                      if aligned else f"Non-standard amount: ${paid_amount:.2f} (leftover ${remaining:.2f})")

        # Summary text
        old_end_str = old_end.strftime('%Y-%m-%d') if isinstance(old_end, (date, datetime)) else str(old_end)
        preview = (
            "Confirm renewal details:\n"
            "---------------------\n"
            f"Discord: {user_to_update.get('primaryDiscord')}\n"
            f"Email: {user_to_update.get('primaryEmail')}\n"
            f"Server: {server}\n"
            f"4k: {is_4k}\n"
            "---------------------\n"
            f"Old End: {old_end_str}\n"
            f"New End: {new_end.strftime('%Y-%m-%d')}\n"
            f"Months Added: {term_length}\n"
            f"{align_line}\n"
            "---------------------\n"
            f"Paid Amount: {paid_amount}\n"
            "Press **Correct** to apply or **Cancel** to abort."
        )

        ctx = {
            "user_to_update": user_to_update,
            "paid_amount": paid_amount,
            "term_length": term_length,
            "new_end_date": new_end,
            "old_end_date": old_end,
            "start_date": start_date,
            "align_line": align_line,
            "information": info or {},
        }
        confirm_view = RenewConfirmView(interaction, preview, ctx)
        await _edit_same_message(interaction, content=preview, view=confirm_view)

# ======================================================================
#                              NEW USER WIZARD
# ======================================================================
class DiscordUserView(View):
    """
    Single ephemeral anchor message for the whole wizard.
    """
    def __init__(self, information, interaction, discorduser):
        super().__init__(timeout=180.0)
        self.information = information
        self.interaction = interaction
        self.discorduser = discorduser

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    async def on_timeout(self) -> None:
        pass

    async def start(self):
        """
        If launched from referrer-picker, self.interaction is the component interaction
        tied to the previous prompt — we EDIT that message.
        If launched straight from the modal, there is no anchor message; we SEND one (done by caller).
        """
        view = await self._build_confirm_discord_view()

        # Case 1: We have a message to edit (preferred — no new messages).
        msg_obj = getattr(self.interaction, "message", None)
        if msg_obj is not None:
            try:
                await msg_obj.edit(content="Confirm Discord user (or skip):", view=view)
                return
            except Exception as e:
                logging.debug(f"start(): msg_obj.edit failed, will try response/followup: {e}")

            try:
                if not self.interaction.response.is_done():
                    await self.interaction.response.edit_message(content="Confirm Discord user (or skip):", view=view)
                    return
            except Exception as e:
                logging.debug(f"start(): response.edit_message failed: {e}")

        # Case 2: No anchor message available (e.g., launched from modal) — send one.
        try:
            if not self.interaction.response.is_done():
                await self.interaction.response.send_message("Confirm Discord user (or skip):", view=view, ephemeral=True)
            else:
                await self.interaction.followup.send("Confirm Discord user (or skip):", view=view, ephemeral=True)
        except Exception as e:
            logging.debug(f"start(): send fallback failed: {e}")
            await self.interaction.followup.send("Confirm Discord user (or skip):", view=view, ephemeral=True)

    async def _build_confirm_discord_view(self):
        options = []
        if self.discorduser and str(self.discorduser).lower() not in ("none", "na"):
            options.append(discord.SelectOption(label=f"Use: {self.discorduser}", value="use_found"))
        options.append(discord.SelectOption(label="Not on Discord / Skip", value="skip"))
        options.append(discord.SelectOption(label="Cancel", value="cancel"))

        sel = discord.ui.Select(placeholder="Confirm Discord user", min_values=1, max_values=1, options=options)
        view = View(); view.add_item(sel)

        async def on_pick(inter: discord.Interaction):
            try:
                if not inter.response.is_done():
                    await inter.response.defer_update()
            except Exception:
                pass
            choice = sel.values[0]
            if choice == "use_found":
                self.information['primaryDiscord'] = self.discorduser
                await self._render_payment_method(inter)
                return
            if choice == "skip":
                self.information['primaryDiscord'] = None
                self.information['primaryDiscordId'] = None
                await self._render_payment_method(inter)
                return
            await _edit_same_message(inter, content="Cancelled the request.", view=None)

        sel.callback = on_pick
        return view

    async def _render_payment_method(self, interaction: discord.Interaction):
        pms = config.get('PaymentMethod', [])
        pm = discord.ui.Select(
            placeholder="Select payment method",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=x, value=x) for x in pms]
        )
        view = View(); view.add_item(pm)

        async def on_pm(inter: discord.Interaction):
            try:
                if not inter.response.is_done():
                    await inter.response.defer_update()
            except Exception:
                pass
            self.information['paymentMethod'] = pm.values[0]
            await _edit_same_message(
                inter,
                content=f"Payment method selected: {pm.values[0]}\n\nPick a Plex server:",
                view=await self._build_server_view()
            )
        pm.callback = on_pm

        await _edit_same_message(interaction, content="Pick a payment method:", view=view)

    async def _build_server_view(self):
        servers = [k.replace("PLEX-","") for k in config.keys() if isinstance(k, str) and k.startswith("PLEX-")]
        sel = discord.ui.Select(
            placeholder="Select a server",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=s, value=s) for s in servers]
        )
        view = View(); view.add_item(sel)

        async def on_srv(inter: discord.Interaction):
            try:
                if not inter.response.is_done():
                    await inter.response.defer_update()
            except Exception:
                pass
            self.information['server'] = sel.values[0]
            await _edit_same_message(
                inter,
                content=f"Server selected: {sel.values[0]}\n\nChoose resolution plan:",
                view=await self._build_resolution_view()
            )
        sel.callback = on_srv
        return view

    async def _build_resolution_view(self):
        res = discord.ui.Select(
            placeholder="4k access?",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label="Yes (4K plan)", value="Yes"),
                     discord.SelectOption(label="No (1080p only)", value="No")]
        )
        view = View(); view.add_item(res)

        async def on_res(inter: discord.Interaction):
            try:
                if not inter.response.is_done():
                    await inter.response.defer_update()
            except Exception:
                pass
            self.information['4k'] = "Yes" if res.values[0] == "Yes" else "No"
            await self._show_confirmation(inter)
        res.callback = on_res
        return view

    async def _show_confirmation(self, interaction: discord.Interaction):
        server = self.information.get('server', '')
        term_length = mathFunctions.calculate_term_length(server, self.information['paidAmount'], self.information.get('4k'))
        today = datetime.now().date()
        self.information['startDate'] = today.strftime('%Y-%m-%d')
        self.information['endDate'] = (today + relativedelta(months=term_length)).strftime('%Y-%m-%d')
        self.information['termLength'] = term_length

        # --- Referrer extension preview ---
        ref_lines = ""
        try:
            ref_id = self.information.get('referrerUserId')
            if ref_id:
                ref_row = dbFunctions.get_user_by_id(int(ref_id))
                if ref_row and (ref_row.get('status') or '').strip().lower() == 'active':
                    reward = referral_reward_for_new_user_first_purchase(months=int(term_length or 0), config=config)
                    days = int(getattr(reward, 'days_to_extend', 0) or 0)
                    before_end = _parse_date_yyyy_mm_dd(ref_row.get('endDate')) or today
                    after_end = before_end + timedelta(days=days)
                    label = ref_row.get('paymentPerson') or ref_row.get('primaryDiscord') or ref_row.get('primaryEmail') or f"ID {ref_row.get('id')}"
                    ref_lines = (
                        "\n--- Referral Extension Preview ---\n"
                        f"Referrer: {label}\n"
                        f"Before:  {before_end.strftime('%Y-%m-%d')}\n"
                        f"After:   {after_end.strftime('%Y-%m-%d')} (+{days} days)\n"
                    )
                    self.information['_ref_preview'] = {
                        "label": label,
                        "before": before_end.strftime('%Y-%m-%d'),
                        "after": after_end.strftime('%Y-%m-%d'),
                        "days": days,
                    }
        except Exception as e:
            logging.warning(f"Referrer preview failed: {e}")

        confirmation_message = (
            f"Discord: {self.information.get('primaryDiscord')}\n"
            f"Email: {self.information.get('primaryEmail')}\n"
            f"Payment Method: {self.information.get('paymentMethod')}\n"
            f"Paid Amount: {self.information.get('paidAmount')}\n"
            f"Server: {self.information.get('server')}\n"
            f"4k: {self.information.get('4k')}\n"
            f"Start Date: {self.information.get('startDate')}\n"
            f"End Date: {self.information.get('endDate')}\n"
            f"Term Length: {self.information.get('termLength')}\n"
            f"{ref_lines}"
        )

        confirmation_view = ConfirmButtonsNewUser(self.information, anchor_message=getattr(interaction, "message", None))
        await interaction.response.edit_message(content=confirmation_message, view=confirmation_view)


class ConfirmButtonsNewUser(View):
    def __init__(self, information: dict, anchor_message: discord.Message | None = None):
        super().__init__(timeout=180.0)
        self.information = information
        self.anchor_message = anchor_message  # message to overwrite for final summary

        ok = Button(style=discord.ButtonStyle.primary, label="Correct")
        ok.callback = self.correct_callback
        self.add_item(ok)

        cancel = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel.callback = self.cancel_callback
        self.add_item(cancel)

    async def _ack_and_freeze(self, interaction: discord.Interaction):
        # 1) Ack first to avoid "This interaction failed"
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        # 2) Disable buttons immediately (prevents double clicks)
        try:
            for child in self.children:
                try:
                    child.disabled = True
                except Exception:
                    pass
            msg = self.anchor_message or getattr(interaction, "message", None)
            if msg:
                await msg.edit(view=self)
        except Exception:
            # Best-effort removal if editing with a view fails
            try:
                msg = self.anchor_message or getattr(interaction, "message", None)
                if msg:
                    await msg.edit(view=None)
            except Exception:
                pass

    async def correct_callback(self, interaction: discord.Interaction):
        # --- 0) ACK FAST: strip the buttons on the same message so users can't double-click ---
        # Using edit_message() here counts as the interaction response and avoids "This interaction failed".
        try:
            await interaction.response.edit_message(view=None)
        except Exception:
            try:
                if getattr(interaction, "message", None):
                    await interaction.message.edit(view=None)
            except Exception:
                pass  # if the message is gone, just continue silently

        # --- 1) Idempotency: prevent duplicate processing / logs for the same new-user op ---
        op_key = _newuser_op_key(self.information)
        async with _NEWUSER_LOCK:
            if op_key in _PROCESSED_NEWUSER_KEYS:
                return  # already handled
            _PROCESSED_NEWUSER_KEYS.add(op_key)

        errors: list[str] = []

        try:
            server = self.information.get('server')
            email = self.information.get('primaryEmail')
            discord_user = self.information.get('primaryDiscord')
            discord_user_id = self.information.get('primaryDiscordId')
            discord_role = (config.get(f"PLEX-{server}", {}) or {}).get('role')

            std_libs = (config.get(f"PLEX-{server}", {}) or {}).get('standardLibraries') or []
            opt_libs = (config.get(f"PLEX-{server}", {}) or {}).get('optionalLibraries') or []
            section_names = (std_libs + opt_libs) if (self.information.get('4k') == "Yes") else std_libs

            start_date = self.information.get('startDate')
            end_date = self.information.get('endDate')

            # 2) Add Discord role (best-effort)
            try:
                if discord_user and discord_user_id and discord_role:
                    await add_role(discord_user_id, discord_role)
            except Exception as e:
                logging.warning(f"add_role failed: {e}")
                errors.append("Could not add Discord role")

            # 3) Plex invite (best-effort)
            try:
                plex_cfg = (config.get(f"PLEX-{server}", {}) or {})
                base_url = plex_cfg.get('baseUrl')
                token = plex_cfg.get('token')
                if not base_url or not token:
                    errors.append(f"Invalid Plex config for '{server}'")
                else:
                    plex = PlexServer(base_url, token)
                    try:
                        plex.myPlexAccount().inviteFriend(
                            user=email, server=plex, sections=section_names, allowSync=True
                        )
                    except Exception as e:
                        logging.error(f"Plex invite failed for {email} on {server}: {e}")
                        errors.append("Plex invite failed")
            except Exception as e:
                logging.error(f"Plex auth/invite error: {e}")
                errors.append("Plex connection error")

            # 4) DB create + transaction log
            try:
                dbFunctions.create_user(self.information)
                logging.info(f"Created new user with primary email: {email}")
            except Exception as e:
                logging.error(f"DB create_user failed: {e}")
                errors.append("DB create_user failed")

            try:
                self.information.setdefault('term_length', int(self.information.get('termLength') or 0))
                dbFunctions.log_transaction(information=self.information)
                logging.info(f"Logged transaction for {email} with amount: {self.information.get('paidAmount')}")
            except Exception as e:
                logging.info(f"log_transaction error: {e}")
                errors.append("log_transaction failed")

            # 5) Referral reward (best-effort)
            try:
                referrer_id = self.information.get('referrerUserId')
                if referrer_id:
                    try:
                        ref_row = dbFunctions.get_user_by_id(int(referrer_id))
                    except Exception as e:
                        ref_row = None
                        logging.error(f"Failed to load referrer id={referrer_id}: {e}")

                    if ref_row and (ref_row.get('status') or "").strip().lower() == "active":
                        preview = self.information.get('_ref_preview') or {}
                        before_str = preview.get("before")
                        after_str = preview.get("after")
                        days = preview.get("days")

                        if not (before_str and after_str and (days is not None)):
                            reward = referral_reward_for_new_user_first_purchase(
                                months=int(self.information.get('termLength') or 0), config=config
                            )
                            days = int(getattr(reward, 'days_to_extend', 0) or 0)
                            before_date = _parse_date_yyyy_mm_dd(ref_row.get('endDate')) or date.today()
                            after_date = before_date + timedelta(days=days)
                            before_str = before_date.strftime("%Y-%m-%d")
                            after_str = after_date.strftime("%Y-%m-%d")

                        try:
                            dbFunctions.update_database(ref_row['id'], 'endDate', after_str)
                        except Exception as e:
                            logging.error(f"Referral DB update failed: {e}")
                            errors.append("Referral DB update failed")

                        # Optional: notify referrer (best-effort, non-fatal)
                        try:
                            ref_subject = dcfg.get("referralSubject", "Referral bonus applied")
                            ref_body_tmpl = dcfg.get(
                                "referralBody",
                                "Thanks for referring {referredEmail}.\n"
                                "We extended your subscription from {beforeEnd} to {afterEnd} (+{daysExtended} days)."
                            )
                            ref_body = ref_body_tmpl.format(
                                referredEmail=email, beforeEnd=before_str, afterEnd=after_str, daysExtended=days
                            )
                            ref_discord_id = ref_row.get('primaryDiscordId')
                            ref_email = ref_row.get('primaryEmail')
                            if ref_discord_id:
                                try:
                                    user_obj = await interaction.client.fetch_user(int(ref_discord_id))
                                    await user_obj.send(ref_body)
                                except Exception as e:
                                    logging.warning(f"Could not DM referrer: {e}")
                            if ref_email:
                                try:
                                    emailFunctions.send_email(config_location, ref_subject, ref_body, ref_email)
                                except Exception as e:
                                    logging.warning(f"Could not email referrer: {e}")
                        except Exception as e:
                            logging.warning(f"Notify referrer failed: {e}")
                    # if inactive or not found: silently skip per your preference
            except Exception as e:
                logging.error(f"Referral handling error: {e}")
                errors.append("Referral handling error")

            # 6) Notify the new user (best-effort, non-fatal)
            try:
                subject = dcfg.get('paymentSubject', "Subscription Created")
                body_tmpl = dcfg.get(
                    'paymentBody',
                    "Your subscription for {primaryEmail} has been created.\n"
                    "Server: {server}\n"
                    "Libraries: {section_names}\n"
                    "End: {newEndDate}"
                )
                body = body_tmpl.format(
                    primaryEmail=email,
                    server=server,
                    section_names=("4k" if self.information.get('4k') == "Yes" else "1080p"),
                    newEndDate=end_date
                )
                if discord_user_id:
                    await send_discord_message(to_user=discord_user_id, subject=subject, body=body)
                emailFunctions.send_email(config_location, subject, body, email)
            except Exception as e:
                logging.warning(f"Notify new user failed: {e}")
                errors.append("User notification failed")

        except Exception as e:
            logging.exception(e)
            errors.append(f"Unexpected error: {e}")

        # 7) Only if anything went wrong, show a single ephemeral follow-up
        if errors:
            try:
                await interaction.followup.send(
                    "Some steps completed with issues:\n- " + "\n- ".join(errors),
                    ephemeral=True
                )
            except Exception:
                pass

    async def cancel_callback(self, interaction: discord.Interaction):
        # Ack and overwrite same message
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass
        try:
            msg = self.anchor_message or getattr(interaction, "message", None)
            if msg:
                await msg.edit(content="Cancelled the request.", view=None)
            else:
                await interaction.edit_original_response(content="Cancelled the request.", view=None)
        except Exception:
            pass


# ======================================================================
#                                MOVE USER
# ======================================================================
class ConfirmButtonsMoveUser(View):
    def __init__(self, information):
        super().__init__(timeout=180.0)
        self.information = information

        import asyncio
        self._processing = False
        self._lock = asyncio.Lock()

        ok = Button(style=discord.ButtonStyle.primary, label="Correct")
        ok.callback = self.correct_callback
        self.add_item(ok)

        cancel = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel.callback = self.cancel_callback
        self.add_item(cancel)

    async def correct_callback(self, interaction: discord.Interaction):
        # Ack immediately
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass

        # Idempotency
        if self._processing or self.information.get('_move_done'):
            return
        if self._lock.locked():
            return
        async with self._lock:
            if self._processing or self.information.get('_move_done'):
                return
            self._processing = True
            self.information['_move_done'] = True

            # Disable buttons
            try:
                for child in self.children:
                    try: child.disabled = True
                    except Exception: pass
                if getattr(interaction, "message", None):
                    await interaction.message.edit(view=self)
            except Exception:
                try:
                    if getattr(interaction, "message", None):
                        await interaction.message.edit(view=None)
                except Exception:
                    pass

            followup_message = ""
            new_server = self.information.get('server')
            new_4k = self.information.get('4k')
            email = self.information.get('primaryEmail')

            std_libs = (config.get(f"PLEX-{new_server}", {}) or {}).get('standardLibraries') or []
            opt_libs = (config.get(f"PLEX-{new_server}", {}) or {}).get('optionalLibraries') or []
            section_names = (std_libs + opt_libs) if (self.information.get('4k') == "Yes") else std_libs
            old_section_names = (std_libs + opt_libs) if (self.information.get('old_4k') == "Yes") else std_libs

            plex_config = (config.get(f'PLEX-{new_server}', {}) or {})
            base_url = plex_config.get('baseUrl')
            token = plex_config.get('token')
            if not base_url or not token:
                logging.error(f"No/invalid configuration for Plex server '{new_server}'")
            else:
                try:
                    plex = PlexServer(base_url, token)
                    try:
                        update_user = plex.myPlexAccount().updateFriend(
                            user=email,
                            server=plex,
                            sections=section_names,
                            removeSections=old_section_names
                        )
                        if update_user:
                            logging.info(f"User '{email}' updated in Plex server '{new_server}'")
                    except Exception as e:
                        logging.error(f"Error updating user {email} to {new_server} with sections {section_names}: {e}")
                except Exception as e:
                    logging.error(f"Error authenticating to Plex at {base_url}: {e}")

            try:
                dbFunctions.update_database(self.information.get('id'), "server", new_server)
                dbFunctions.update_database(self.information.get('id'), "4k", new_4k)
                try:
                    dbFunctions.log_transaction(information=self.information)
                except Exception as e:
                    logging.info(f"log_transaction skipped due to internal error: {e}")
            except Exception as e:
                logging.error(f"DB update/log failed in move flow: {e}")

            followup_message += (
                "---------------------\n"
                f"Email: {self.information.get('primaryEmail')}\n"
                f"Old Server: {self.information.get('old_server')}\n"
                f"Old 4k: {self.information.get('old_4k')}\n"
                "---------------------\n"
                f"Server: {self.information.get('server')}\n"
                f"4k: {self.information.get('4k')}\n"
                f"Paid Amount: {self.information.get('paidAmount')}\n"
                f"End Date: {self.information.get('endDate')}\n"
            )

            await _edit_same_message(interaction, content=followup_message, view=None)

    async def cancel_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer_update()
        except Exception:
            pass
        await _edit_same_message(interaction, content="Cancelled the request.", view=None)
