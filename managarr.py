import sys, logging, discord, os
from plexapi.myplex import MyPlexAccount
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Modal, TextInput
from typing import Optional, List, Dict

from modules import globalBot
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
globalBot.bot = bot

from modules import dbFunctions, discordFunctions, configFunctions

# ---------------------- logging ----------------------
log_file = "/config/managarr.log"
if not os.path.exists(log_file):
    open(log_file, 'w').close()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file)]
)

# ---------------------- config/token ----------------------
config_location = "/config/config.yml"
config = configFunctions.get_config(config_location) or {}
bot_token = os.environ.get("DISCORD_BOT_TOKEN") or ((config.get("discord", {}) or {}).get("token"))
if not bot_token:
    print("[ERROR] No Discord bot token found. Set DISCORD_BOT_TOKEN or add discord.token in config.yml.", file=sys.stderr)
    sys.exit(1)

# =====================================================================
# Referrer picker (single-anchor: edits the same message; no bloat)
# =====================================================================
class _ReferrerPicker(Select):
    def __init__(self, results: List[Dict], information: dict, parent_view: "ReferrerPickerView"):
        self.results = results
        self.information = information
        self.parent_view = parent_view
        options = []
        for row in results[:25]:
            label_bits = [
                row.get('paymentPerson') or "",
                row.get('primaryDiscord') or "",
                row.get('primaryEmail') or "",
            ]
            label = " | ".join([b for b in label_bits if b]).strip() or f"ID {row.get('id')}"
            options.append(discord.SelectOption(label=label[:100], value=str(row.get('id'))))
        super().__init__(placeholder="Select the referrer…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Save selection
        picked_id = self.values[0]
        self.information['referrerUserId'] = picked_id
        self.parent_view.selected_referrer_interaction = interaction

        # Acknowledge without changing the message content
        try:
            await interaction.response.defer_update()  # no text; no new message
        except Exception:
            pass

        # Stop the view; the wizard will immediately overwrite this message
        self.view.stop()  # type: ignore


class ReferrerPickerView(View):
    def __init__(self, results: List[Dict], information: dict):
        super().__init__(timeout=60)
        self.selected_referrer_interaction: Optional[discord.Interaction] = None
        self.add_item(_ReferrerPicker(results, information, self))

# =====================================================================
# Modal form for Add New User (keeps one anchor message)
# =====================================================================
class AddNewUserModal(Modal, title="Add New User"):
    def __init__(self, ctx: discord.Interaction):
        super().__init__(timeout=180)
        self.ctx = ctx

        # Fields
        self.discorduser = TextInput(label="Discord Username (or 'none'/'na')", placeholder="e.g., user#1234 or none", required=True, default="none", max_length=64)
        self.email = TextInput(label="Email Address", placeholder="email@example.com", required=True, max_length=120)
        self.payment_person = TextInput(label="Payment Name", placeholder="Name shown on the payment", required=True, max_length=100)
        self.amount = TextInput(label="Amount Paid (USD)", placeholder="e.g., 1.00, 24, 87.00", required=True, max_length=20)
        self.referrer = TextInput(label="Referrer (optional)", placeholder="email, Discord handle, or payment name", required=False, max_length=120)

        self.add_item(self.discorduser)
        self.add_item(self.email)
        self.add_item(self.payment_person)
        self.add_item(self.amount)
        self.add_item(self.referrer)

    async def on_submit(self, interaction: discord.Interaction):
        # Defer so we can work without creating a visible new message right away
        await interaction.response.defer(ephemeral=True)

        # Gather values
        discorduser = str(self.discorduser.value or "none").strip()
        email = str(self.email.value or "").strip()
        payment_person = str(self.payment_person.value or "").strip()
        amount_str = str(self.amount.value or "0").strip()
        referred_by = str(self.referrer.value or "").strip()

        # Validate amount format
        try:
            amount_val = float(amount_str)
        except Exception:
            await interaction.followup.send("⚠️ Invalid amount format. Please use a number like 1, 24, 87.00", ephemeral=True)
            return

        # Prevent duplicate new-user email
        try:
            existing = dbFunctions.find_user(email) or []
        except Exception as e:
            existing = []
            logging.error(f"Error checking for existing user: {e}")

        if any(r for r in existing if (r.get("primaryEmail") or "").lower() == email.lower()):
            await interaction.followup.send(
                f"⚠️ A user with email **{discord.utils.escape_markdown(email)}** already exists in the database. Not adding a duplicate.",
                ephemeral=True
            )
            return

        # Info dict used by downstream flow
        information = {
            'what': 'newuser',
            'primaryEmail': email,
            'paidAmount': amount_val,
            'paymentPerson': payment_person
        }

        # Optional referrer resolution — keep a single anchor message
        anchor_inter: Optional[discord.Interaction] = None
        if referred_by:
            try:
                results = dbFunctions.find_user(referred_by) or []
            except Exception as e:
                results = []
                await interaction.followup.send(
                    f"[WARN] Referrer lookup failed: {e}. Continuing without referral.",
                    ephemeral=True
                )

            if results:
                view = ReferrerPickerView(results, information)
                # Send ONE prompt which will be edited in-place by the select callback
                await interaction.followup.send(
                    content=f"Select the referrer that matches **{discord.utils.escape_markdown(referred_by)}**:",
                    view=view,
                    ephemeral=True,
                )
                # Wait for selection; callback will edit the same message to "Starting…"
                await view.wait()
                anchor_inter = view.selected_referrer_interaction

        # Launch the wizard; if we have a referrer interaction, use it as the anchor
        launch_interaction = anchor_inter or self.ctx
        view = discordFunctions.DiscordUserView(information, launch_interaction, discorduser)
        await view.start()

# =====================================================================
# Commands
# =====================================================================
@bot.event
async def on_ready():
    print("Bot is Up and Ready!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"{e}")

@bot.tree.command(name="payment_received", description="Update user's paid amount and extend end date")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)", amount="Payment amount (float)")
async def payment_received(ctx, *, user: str, amount: float):
    await ctx.response.defer(ephemeral=True)
    search_results = dbFunctions.find_user(user)
    if not search_results:
        await ctx.followup.send(f"{ctx.user.name} No user found matching the given identifier: {user}", ephemeral=True)
        return
    information = {'what': 'payment', 'paidAmount': amount}
    await ctx.followup.send(
        "Select the correct user",
        view=discordFunctions.UpdateSelectorView(search_results, information),
        ephemeral=True,
    )

@bot.tree.command(name="add_new_user", description="Add new user to DB (first purchase promos + optional referrer).")
async def add_new_user(ctx: discord.Interaction):
    await ctx.response.send_modal(AddNewUserModal(ctx))

@bot.tree.command(name="move_user", description="Update user's plex libraries")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)", amount="Payment amount (float, optional)")
async def move_user(ctx, *, user: str, amount: float = None):
    await ctx.response.defer(ephemeral=True)
    search_results = dbFunctions.find_user(user)
    if not search_results:
        await ctx.followup.send(f"No user found matching the given identifier: {user}", ephemeral=True)
        return
    information = {'what': 'move', 'paidAmount': amount}
    await ctx.followup.send("Select the correct user", view=discordFunctions.UpdateSelectorView(search_results, information), ephemeral=True)

@bot.tree.command(name="add_plex_server", description="Add a new Plex server to the configuration")
@app_commands.describe(email="Plex account email", password="Plex account password")
async def add_plex_server(ctx, *, email: str, password: str):
    await ctx.response.defer(ephemeral=True)
    try:
        account = MyPlexAccount(email, password)
        servers = account.resources()
    except Exception as e:
        await ctx.followup.send(f"Error: {str(e)}", ephemeral=True)
        return

    servers = [server for server in servers if 'server' in server.provides]
    if not servers:
        await ctx.followup.send("No servers found. Please check your credentials.", ephemeral=True)
        return

    # ANCHOR: single message for the whole server/library selection flow
    view = View()
    view.add_item(discordFunctions.ServerSelect(ctx, servers))
    await ctx.followup.send("Choose a Plex server:", view=view, ephemeral=True)

@bot.tree.command(name="calculate_move", description="Estimate the pro-rated cost to move a user's plan to a new server/quality")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)")
async def calculate_move(ctx, *, user: str):
    await ctx.response.defer(ephemeral=True)
    view = discordFunctions.build_calculate_move_view(user)
    if view is None:
        await ctx.followup.send(f"No user found matching: {user}", ephemeral=True)
        return
    # Send an anchor message and have the view render the current subscription immediately.
    msg = await ctx.followup.send("Loading current subscription…", ephemeral=True, view=view)
    # Kick off the view to overwrite the same message with the current subscription summary.
    try:
        await view.start(ctx)
    except Exception:
        pass

# ---------------------- run ----------------------
bot.run(bot_token)