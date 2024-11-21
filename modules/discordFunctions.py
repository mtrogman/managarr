import discord, logging, math, yaml
from modules.globalBot import bot
from discord.ui import Select
from discord.ui import View, Button
from plexapi.server import PlexServer
from datetime import datetime
from dateutil.relativedelta import relativedelta
from modules import configFunctions, discordFunctions, dbFunctions, emailFunctions, sharedFunctions, mathFunctions


config_location = "/config/config.yml"
config = configFunctions.get_config(config_location)


if bot is None:
    logging.error("The bot instance in globalBot is None!")
else:
    logging.info("The bot instance in globalBot is set correctly.")


async def add_role(user_id, role_name):
    guild_id = int(config['discord']['guildId'])

    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            logging.error(f"Guild with ID {guild_id} not found.")
            return  # Exit early if guild is not found

        user = await guild.fetch_member(user_id)
        if not user:
            logging.error(f"Member with ID {user_id} not found in the guild.")
            return  # Exit early if user is not found

        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            logging.error(f"Role '{role_name}' not found in guild '{guild.name}'.")
            return  # Exit early if role is not found

        logging.info(f"Assigning role '{role_name}' to user ID {user_id}")
        await user.add_roles(role)
        logging.info(f"Added role '{role_name}' to user {user.name} ({user.id})")

    except discord.Forbidden:
        logging.error(f"Bot doesn't have permission to add roles.")
    except discord.HTTPException as e:
        logging.error(f"HTTP error occurred while adding role: {e}")


async def send_discord_message(to_user, subject, body):
    if bot is None:
        logging.error("The bot instance in globalBot is None!")
        return

    if not bot.is_ready():
        logging.error("The bot is not ready yet!")
        return

    logging.info(f"Attempting to fetch user {to_user} with bot: {bot}")
    try:
        user = await bot.fetch_user(to_user)
        embed = discord.Embed(title=f"**{subject}**", description=body, color=discord.Colour.blue())
        await user.send(embed=embed)
    except discord.errors.Forbidden as e:
        logging.warning(f"Failed to send message to {to_user}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")


class ServerSelect(Select):
    def __init__(self, interaction, servers):
        server_options = [discord.SelectOption(label=server.name, value=server.name) for server in servers]
        super().__init__(placeholder="Choose a Plex server", options=server_options, min_values=1, max_values=1)
        self.interaction = interaction
        self.servers = servers

    async def callback(self, interaction: discord.Interaction):
        server_name = self.values[0]
        selected_server = next(server for server in self.servers if server.name == server_name)
        try:
            plex = selected_server.connect()
            libraries = plex.library.sections()
        except Exception as e:
            await interaction.response.send_message(f"Error connecting to server: {str(e)}", ephemeral=True)
            return

        view = View()
        view.add_item(StandardLibrarySelect(self.interaction, selected_server, libraries))
        await self.interaction.delete_original_response()
        await interaction.response.send_message("Choose standard libraries:", view=view, ephemeral=True)


class OptionalLibrarySelect(Select):
    def __init__(self, interaction, selected_server, standard_library_titles, optional_library_options):
        super().__init__(placeholder="Choose optional libraries (can be none)", options=optional_library_options, min_values=0, max_values=len(optional_library_options))
        self.interaction = interaction
        self.selected_server = selected_server
        self.standard_library_titles = standard_library_titles

    async def callback(self, interaction: discord.Interaction):
        optional_library_titles_selected = self.values
        await self.confirm(interaction, self.selected_server, self.standard_library_titles, optional_library_titles_selected)

    async def confirm(self, interaction: discord.Interaction, selected_server, standard_library_titles, optional_library_titles_selected):
        confirmation_message = (
            f"Selected Server: {selected_server.name}\n"
            f"Standard Libraries: {', '.join(standard_library_titles)}\n"
            f"Optional Libraries: {', '.join(optional_library_titles_selected)}\n"
            "Confirm?"
        )
        view = ConfirmButtonsNewServer(interaction, selected_server, standard_library_titles, optional_library_titles_selected)
        await interaction.response.edit_message(content=confirmation_message, view=view)


class StandardLibrarySelect(Select):
    def __init__(self, interaction, selected_server, libraries):
        standard_library_options = [discord.SelectOption(label=lib.title, value=lib.title) for lib in libraries]
        super().__init__(placeholder="Choose standard libraries", options=standard_library_options, min_values=1, max_values=len(libraries))
        self.interaction = interaction
        self.selected_server = selected_server
        self.libraries = libraries

    async def callback(self, interaction: discord.Interaction):
        standard_library_titles = self.values
        optional_library_titles = [lib.title for lib in self.libraries if lib.title not in standard_library_titles]

        if not optional_library_titles:
            await self.confirm(interaction, self.selected_server, standard_library_titles, [])
        else:
            optional_library_options = [discord.SelectOption(label=lib, value=lib) for lib in optional_library_titles]
            view = View()
            view.add_item(OptionalLibrarySelect(self.interaction, self.selected_server, standard_library_titles, optional_library_options))
            await interaction.response.edit_message(content="Choose optional libraries:", view=view)

    async def confirm(self, interaction: discord.Interaction, selected_server, standard_library_titles, optional_library_titles_selected):
        confirmation_message = (
            f"Selected Server: {selected_server.name}\n"
            f"Standard Libraries: {', '.join(standard_library_titles)}\n"
            f"Optional Libraries: {', '.join(optional_library_titles_selected)}\n"
            "Confirm?"
        )
        view = ConfirmButtonsNewServer(interaction, selected_server, standard_library_titles, optional_library_titles_selected)
        await interaction.response.edit_message(content=confirmation_message, view=view)


class ServerSelector(Select):
    def __init__(self, information):
        self.information = information
        config = configFunctions.get_config(config_location)
        server_names = [
            config[key].get('serverName', None)
            for key in config.keys() if key.startswith('PLEX-')
        ]
        options = [
            discord.SelectOption(label=server_name, value=server_name)
            for server_name in server_names
        ]
        options.append(discord.SelectOption(label="Cancel", value="cancel"))
        super().__init__(placeholder="Media Server", options=options, min_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="Cancelled the request", view=None)
            return
        self.information['server'] = self.values[0]
        await interaction.response.edit_message(content="Select the 4k", view=FourKView(self.information))


class FourKSelector(Select):
    def __init__(self, information):
        self.information = information
        options = [
            discord.SelectOption(label="Yes", value="Yes"),
            discord.SelectOption(label="No", value="No"),
            discord.SelectOption(label="Cancel", value="cancel")
        ]
        super().__init__(placeholder="4K?", options=options, min_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="Cancelled the request", view=None)
            return
        self.information['4k'] = self.values[0]
        if self.information['what'] == 'payment':
            await self.handle_payment(interaction)
        elif self.information['what'] == 'move':
            await self.handle_move(interaction)
        elif self.information['what'] == 'newuser':
            await self.handle_new_user(interaction)

    async def handle_payment(self, interaction):
        server = self.information.get('server', '')
        term_length = mathFunctions.calculate_term_length(server, self.information['paidAmount'], self.information['4k'])
        today = datetime.now().date()
        self.information['startDate'] = today.strftime('%Y-%m-%d')
        self.information['endDate'] = today + relativedelta(months=term_length)
        self.information['termLength'] = term_length
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
        )

        confirmation_view = ConfirmButtonsNewUser(interaction, self.information)
        await interaction.response.edit_message(content=confirmation_message, view=confirmation_view)

    async def handle_move(self, interaction):
        confirmation_message = (
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

        confirmation_view = ConfirmButtonsMoveUser(interaction, self.information)
        await interaction.response.edit_message(content=confirmation_message, view=confirmation_view)

    async def handle_new_user(self, interaction):
        server = self.information.get('server', '')
        term_length = mathFunctions.calculate_term_length(server, self.information['paidAmount'], self.information['4k'])
        today = datetime.now().date()
        self.information['startDate'] = today.strftime('%Y-%m-%d')
        self.information['endDate'] = today + relativedelta(months=term_length)
        self.information['termLength'] = term_length
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
        )

        confirmation_view = ConfirmButtonsNewUser(interaction, self.information)
        await interaction.response.edit_message(content=confirmation_message, view=confirmation_view)


class PaymentMethodSelector(Select):
    def __init__(self, information):
        self.information = information
        config = configFunctions.get_config(config_location)
        payment_methods = config.get('PaymentMethod', [])
        options = [
            discord.SelectOption(label=method, value=method)
            for method in payment_methods
        ]
        options.append(discord.SelectOption(label="Cancel", value="cancel"))
        super().__init__(placeholder="Please select the payment method", options=options, min_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="Cancelled the request", view=None)
            return
        self.information['paymentMethod'] = self.values[0]
        await interaction.response.edit_message(content="Select the Server", view=ServerView(self.information))


class DiscordUserSelector(Select):
    def __init__(self, information, ctx, discord_user):
        self.information = information
        options = []
        if discord_user.lower() != "none":
            guild = ctx.guild
            if not guild:
                ctx.response.edit_message("Command must be used in a guild/server.")
                return
            member = discord.utils.find(lambda m: m.name.lower() == discord_user.lower() or m.display_name.lower() == discord_user.lower(), guild.members)
            if not member:
                ctx.response.edit_message(f"User '{discord_user}' not found in the server.")
                return
            options.append(discord.SelectOption(label=member.name, value=member.id))
        else:
            options.append(discord.SelectOption(label="Not on Discord", value="N/A"))
        options.append(discord.SelectOption(label="Cancel", value="cancel"))
        super().__init__(placeholder="Please confirm Discord Username", options=options, min_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="Cancelled the request", view=None)
            return
        if self.values[0] != "N/A":
            selected_user_id = int(self.values[0])
            selected_user = discord.utils.get(interaction.guild.members, id=selected_user_id)
            if selected_user:
                self.information['primaryDiscord'] = selected_user.name
                self.information['primaryDiscordId'] = selected_user.id
            else:
                await interaction.response.send_message("Failed to find selected user, please try again.", ephemeral=True)
                return
        await interaction.response.edit_message(content="Select the payment method", view=PaymentMethodView(self.information))


class ConfirmButtonsPayment(View):
    def __init__(self, interaction, information):
        super().__init__()
        correct_button = Button(style=discord.ButtonStyle.primary, label="Correct")
        correct_button.callback = self.correct_callback
        self.add_item(correct_button)

        cancel_button = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

        self.interaction = interaction
        self.information = information

    async def correct_callback(self, button):
        await self.interaction.delete_original_response()
        followup_message = ""

        for user in self.information['users']:
            user_id = user.get('id')
            new_paid_amount = user.get('newPaidAmount')
            new_start_date = user.get('newStartDate')
            user_email = user.get('primaryEmail')
            server = user.get('server')
            discord_user = user.get('primaryDiscord')
            discord_user_id = user.get('primaryDiscordId')
            discord_role = config.get(f"PLEX-{server}", {}).get('role')
            standard_libraries = config.get(f"PLEX-{server}", {}).get('standardLibraries')
            optional_libraries = config.get(f"PLEX-{server}", {}).get('optionalLibraries')
            section_names = standard_libraries + optional_libraries if user.get('4k') == "Yes" else standard_libraries
            new_end_date = user.get('newEndDate')
            subject = config.get(f"discord", {}).get('paymentSubject')
            body = config.get(f"discord", {}).get('paymentBody')
            body = body.format(primaryEmail=user_email, server=server, section_names=section_names, newEndDate=new_end_date)

            plex_config = config.get(f'PLEX-{server}', None)
            if not isinstance(plex_config, dict):
                logging.error(f"No configuration found for Plex server '{server}'")
                return

            base_url = plex_config.get('baseUrl', None)
            token = plex_config.get('token', None)
            if user.get('status') == "Inactive" and discord_user and discord_user_id:  # Check if Discord user details are available
                await discordFunctions.add_role(discord_user_id, discord_role)
                if not base_url or not token:
                    logging.error(f"Invalid configuration for Plex server '{server}'")
                    return
                try:
                    plex = PlexServer(base_url, token)
                except Exception as e:
                    logging.error(f"Error authenticating to {base_url}")
                    logging.exception(e)
                try:
                    add_user = plex.myPlexAccount().inviteFriend(user=user_email, server=plex, sections=section_names, allowSync=True)
                    if add_user:
                        logging.info(f"User '{user_email}' has been successfully added to Plex server '{server}'")
                except Exception as e:
                    logging.error(f"Error inviting user {user_email} to {server} with the following libraries: {section_names}")
                    logging.exception(e)

            dbFunctions.update_database(user_id, "paidAmount", new_paid_amount)
            dbFunctions.update_database(user_id, "startDate", new_start_date)
            dbFunctions.update_database(user_id, "endDate", new_end_date)
            dbFunctions.update_database(user_id, "status", "Active")

            followup_message += (
                "---------------------\n"
                f"Discord: {discord_user}\n"
                f"Email: {user_email}\n"
                f"Server: {user.get('server')}\n"
                f"4k: {user.get('4k')}\n"
                f"Start Date: {user.get('newStartDate')}\n"
                f"End Date: {new_end_date}\n"
                f"Status: {user.get('status')}\n"
                f"Paid Amount: {user.get('newPaidAmount')}\n"
            )

            # Send Discord message if Discord user details are available
            if discord_user_id:
                await discordFunctions.send_discord_message(to_user=discord_user_id, subject=subject, body=body)
            # Send Email Msg to user
            emailFunctions.send_email(config_location, subject, body, user_email)

        await self.interaction.followup.send(content=f"{followup_message}", ephemeral=True)

    async def cancel_callback(self, button):
        await self.interaction.delete_original_response()
        await self.interaction.followup.send(content="Cancelled the request.", ephemeral=True)


class ConfirmButtonsNewUser(View):
    def __init__(self, interaction, information):
        super().__init__()
        correct_button = Button(style=discord.ButtonStyle.primary, label="Correct")
        correct_button.callback = self.correct_callback
        self.add_item(correct_button)

        cancel_button = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

        self.interaction = interaction
        self.information = information

    async def correct_callback(self, button):
        await self.interaction.delete_original_response()
        followup_message = ""
        server = self.information.get('server')
        email = self.information.get('primaryEmail')
        discord_user = self.information.get('primaryDiscord')
        discord_user_id = self.information.get('primaryDiscordId')
        discord_role = config.get(f"PLEX-{server}", {}).get('role')
        standard_libraries = config.get(f"PLEX-{server}", {}).get('standardLibraries')
        optional_libraries = config.get(f"PLEX-{server}", {}).get('optionalLibraries')
        section_names = standard_libraries + optional_libraries if self.information.get('4k') == "Yes" else standard_libraries
        start_date = self.information.get('startDate')
        end_date = self.information.get('endDate')

        plex_config = config.get(f'PLEX-{server}', None)
        if not isinstance(plex_config, dict):
            logging.error(f"No configuration found for Plex server '{server}'")
            return

        base_url = plex_config.get('baseUrl', None)
        token = plex_config.get('token', None)
        if discord_user and discord_user_id:  # Check if Discord user details are available
            await discordFunctions.add_role(discord_user_id, discord_role)

        if not base_url or not token:
            logging.error(f"Invalid configuration for Plex server '{server}'")
            return
        try:
            plex = PlexServer(base_url, token)
        except Exception as e:
            logging.error(f"Error authenticating to {base_url}")
            logging.exception(e)
        try:
            add_user = plex.myPlexAccount().inviteFriend(user=email, server=plex, sections=section_names, allowSync=True)
            if add_user:
                logging.info(f"User '{email}' has been successfully added to Plex server '{server}'")
        except Exception as e:
            logging.error(f"Error inviting user {email} to {server} with the following libraries: {section_names}")
            logging.exception(e)

        dbFunctions.create_user(self.information)
        followup_message += (
            f"Discord: {discord_user}\n"
            f"Email: {email}\n"
            f"Server: {self.information.get('server')}\n"
            f"4k: {self.information.get('4k')}\n"
            f"Start Date: {start_date}\n"
            f"End Date: {end_date}\n"
            f"Status: {self.information.get('status')}\n"
            f"Paid Amount: {self.information.get('PaidAmount')}\n"
        )

        await self.interaction.followup.send(content=f"{followup_message}", ephemeral=True)

    async def cancel_callback(self, button):
        await self.interaction.delete_original_response()
        await self.interaction.followup.send(content="Cancelled the request.", ephemeral=True)


class ConfirmButtonsMoveUser(View):
    def __init__(self, interaction, information):
        super().__init__()
        correct_button = Button(style=discord.ButtonStyle.primary, label="Correct")
        correct_button.callback = self.correct_callback
        self.add_item(correct_button)

        cancel_button = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

        self.interaction = interaction
        self.information = information

    async def correct_callback(self, button):
        await self.interaction.delete_original_response()
        followup_message = ""
        old_server = self.information.get('old_server')
        new_server = self.information.get('server')
        old_4k = self.information.get('old_4k')
        new_4k = self.information.get('4k')
        email = self.information.get('primaryEmail')
        discord_user_id = self.information.get('primaryDiscordId')
        standard_libraries = config.get(f"PLEX-{new_server}", {}).get('standardLibraries')
        optional_libraries = config.get(f"PLEX-{new_server}", {}).get('optionalLibraries')
        section_names = standard_libraries + optional_libraries if self.information.get('4k') == "Yes" else standard_libraries
        old_section_names = standard_libraries + optional_libraries if self.information.get('old_4k') == "Yes" else standard_libraries

        plex_config = config.get(f'PLEX-{new_server}', None)
        if not isinstance(plex_config, dict):
            logging.error(f"No configuration found for Plex server '{new_server}'")
            return

        base_url = plex_config.get('baseUrl', None)
        token = plex_config.get('token', None)

        if not base_url or not token:
            logging.error(f"Invalid configuration for Plex server '{new_server}'")
            return
        try:
            plex = PlexServer(base_url, token)
        except Exception as e:
            logging.error(f"Error authenticating to {base_url}")
            logging.exception(e)

        if old_server != new_server:
            try:
                add_user = plex.myPlexAccount().inviteFriend(user=email, server=plex, sections=section_names, allowSync=True)
                if add_user:
                    logging.info(f"User '{email}' has been successfully added to Plex server '{new_server}'")
            except Exception as e:
                logging.error(f"Error inviting user {email} to {new_server} with the following libraries: {section_names}")
                logging.exception(e)
            else:
                old_plex_config = config.get(f'PLEX-{old_server}', None)
                if not isinstance(old_plex_config, dict):
                    logging.error(f"No configuration found for Plex server '{old_server}'")
                    return

                old_base_url = old_plex_config.get('baseUrl', None)
                old_token = old_plex_config.get('token', None)

                if not old_base_url or not old_token:
                    logging.error(f"Invalid configuration for Plex server '{old_server}'")
                    return
                try:
                    old_plex = PlexServer(old_base_url, old_token)
                except Exception as e:
                    logging.error(f"Error authenticating to {old_base_url}")
                    logging.exception(e)

                try:
                    remove_libraries = old_plex.myPlexAccount().updateFriend(user=email, sections=old_section_names, server=old_plex, removeSections=True)
                    if remove_libraries:
                        logging.info(f"User '{email}' has been successfully removed from Old Plex server '{old_server}'")
                except Exception as e:
                    logging.error(f"Error removing user {email} from {old_server}")
                    logging.exception(e)
        else:
            # Remove the user from the server
            try:
                remove_user = plex.myPlexAccount().updateFriend(user=email, sections=section_names, server=plex, removeSections=True)
                if remove_user:
                    logging.info(f"User '{email}' has been successfully removed from Plex server '{new_server}'")
            except Exception as e:
                logging.error(f"Error removing user {email} from {new_server}")
                logging.exception(e)

            # Re-add the user with the new libraries
            try:
                add_user = plex.myPlexAccount().inviteFriend(user=email, server=plex, sections=section_names, allowSync=True)
                if add_user:
                    logging.info(
                        f"User '{email}' has been successfully added back to Plex server '{new_server}' with new libraries")
            except Exception as e:
                logging.error(
                    f"Error inviting user {email} to {new_server} with the following libraries: {section_names}")
                logging.exception(e)
                try:
                    # If adding with new libraries fails, re-add with old libraries
                    add_user = plex.myPlexAccount().inviteFriend(user=email, server=plex, sections=old_section_names, allowSync=True)
                    if add_user:
                        logging.info(
                            f"User '{email}' has been successfully re-added to Plex server '{new_server}' with old libraries")
                except Exception as e:
                    logging.error(
                        f"Error re-adding user {email} to {new_server} with the old libraries: {old_section_names}")
                    logging.exception(e)

        if new_server != old_server:
            dbFunctions.update_database(self.information.get('id'), "server", new_server)
        if self.information['paymentAmount'] is not None:
            newPaidAmount = float(self.information['paidAmount']) + float(self.information['paymentAmount'])
            dbFunctions.update_database(self.information.get('id'), "paidAmount", newPaidAmount)
        if old_4k != new_4k:
            dbFunctions.update_database(self.information.get('id'), "4k", new_4k)

        # Send Discord message if Discord user details are available
        subject = config.get(f"discord", {}).get('moveSubject')
        body = config.get(f"discord", {}).get('moveBody')
        body = body.format(primaryEmail=email, server=new_server, section_names=section_names)
        if discord_user_id:
            await discordFunctions.send_discord_message(to_user=discord_user_id, subject=subject, body=body)
        # Send Email Msg to user
        emailFunctions.send_email(config_location, subject, body, email)


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

        await self.interaction.followup.send(content=f"{followup_message}", ephemeral=True)

    async def cancel_callback(self, button):
        await self.interaction.delete_original_response()
        await self.interaction.followup.send(content="Cancelled the request.", ephemeral=True)


class UpdateSelectorView(View):
    def __init__(self, search_results, information):
        super().__init__()
        self.search_results = search_results
        self.information = information
        self.add_item(sharedFunctions.UpdateSelector(search_results, information))

    async def handle_payment(self, interaction, selected_users):
        user_count = len(self.information.get('users', []))
        if user_count >= 1:
            total_prices = {'1Month': 0, '3Month': 0, '6Month': 0, '12Month': 0}
            for user in selected_users:
                user_resolution = user.get('4k')
                user_server = user.get('server')
                pricing_section = config[f"PLEX-{user_server}"]["4k"] if user_resolution == "Yes" else config[f"PLEX-{user_server}"]["1080p"]
                total_prices['1Month'] += pricing_section['1Month']
                total_prices['3Month'] += pricing_section['3Month']
                total_prices['6Month'] += pricing_section['6Month']
                total_prices['12Month'] += pricing_section['12Month']
                user['prices'] = pricing_section

            total_amount = self.information['paymentAmount']
            matching_lengths = [key for key, value in total_prices.items() if value == total_amount]
            not_rounded = True
            each_extra_balance = 0

            if matching_lengths:
                subscription_length_str = matching_lengths[0]
                term_length = int(''.join(filter(str.isdigit, subscription_length_str)))
                self.information['length'] = term_length
                each_extra_balance = 0
            else:
                one_month_price = total_prices['1Month']
                calculated_months = total_amount / one_month_price
                if calculated_months.is_integer():
                    term_length = int(calculated_months)
                    each_extra_balance = 0
                else:
                    term_length = math.floor(calculated_months)
                    extra_balance = total_amount - (term_length * one_month_price)
                    each_extra_balance = extra_balance / user_count
                    not_rounded = False

            confirmation_message = ""
            for user in self.information['users']:
                if f'{term_length}Month' in user['prices']:
                    payment_amount = user['prices'][f'{term_length}Month']
                else:
                    payment_amount = user['prices'].get('1Month') * term_length

                user['newPaidAmount'] = float(user['paidAmount']) + payment_amount + each_extra_balance
                if user['status'] == 'Active':
                    user['newStartDate'] = user['endDate']
                else:
                    today = datetime.today().date()
                    user['newStartDate'] = today
                user['newEndDate'] = user['newStartDate'] + relativedelta(months=term_length)

                confirmation_message += (
                    "---------------------\n"
                    f"Primary Email: {user.get('primaryEmail')}\n"
                    f"Server: {user.get('server')}\n"
                    f"4k: {user.get('4k')}\n"
                    f"Old Start Date: {user.get('startDate')}\n"
                    f"Old End Date: {user.get('endDate')}\n"
                    f"Start Date: {user.get('newStartDate')}\n"
                    f"End Date: {user.get('newEndDate')}\n"
                    f"Status: {user.get('status')}\n"
                    f"Paid Amount: {user.get('newPaidAmount')}\n"
                    f"Old Paid Amount: {user.get('paidAmount')}\n"
                    f"User Pay Correct Amount?: {not_rounded}\n"
                )

            confirmation_view = ConfirmButtonsPayment(interaction, self.information)
            await interaction.response.edit_message(content=confirmation_message, view=confirmation_view)

    async def handle_move(self, interaction, selected_users):
        self.information['primaryEmail'] = selected_users[0].get('primaryEmail')
        self.information['old_server'] = selected_users[0].get('server')
        self.information['old_4k'] = selected_users[0].get('4k')
        self.information['startDate'] = selected_users[0].get('startDate')
        self.information['endDate'] = selected_users[0].get('endDate')
        self.information['status'] = selected_users[0].get('status')
        self.information['paidAmount'] = selected_users[0].get('paidAmount')
        self.information['id'] = selected_users[0].get('id')
        self.information['primaryDiscordId'] = selected_users[0].get('primaryDiscordId')


        content_message = (
            "---------------------\n"
            f"Primary Email: {self.information['primaryEmail']}\n"
            f"Server: {self.information['old_server']}\n"
            f"4k: {self.information['old_4k']}\n"
            f"Start Date: {self.information['startDate']}\n"
            f"End Date: {self.information['endDate']}\n"
            f"Status: {self.information['status']}\n"
            f"Paid Amount: {self.information['paidAmount']}\n"
            "---------------------\n\n"
        )
        if selected_users[0].get('status') != "Active":
            content_message += (
            f"USER IS INACTIVE"
            )
            await interaction.response.edit_message(content=content_message, view=None)
        else:
            content_message += (
            f"Please choose server to move user to\n"
            )
            await interaction.response.edit_message(content=content_message, view=ServerView(self.information))


class DiscordUserView(View):
    def __init__(self, information, ctx, discord_user):
        super().__init__(timeout=None)
        self.add_item(DiscordUserSelector(information, ctx, discord_user))

class PaymentMethodView(View):
    def __init__(self, information):
        super().__init__()
        self.add_item(PaymentMethodSelector(information))


class ServerView(View):
    def __init__(self, information):
        super().__init__(timeout=None)
        self.add_item(ServerSelector(information))


class FourKView(View):
    def __init__(self, information):
        super().__init__()
        self.add_item(FourKSelector(information))


class ConfirmButtonsNewServer(View):
    def __init__(self, interaction, selected_server, standard_library_titles, optional_library_titles_selected):
        super().__init__()
        correct_button = Button(style=discord.ButtonStyle.primary, label="Confirm")
        correct_button.callback = self.correct_callback
        self.add_item(correct_button)

        cancel_button = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

        self.interaction = interaction
        self.selected_server = selected_server
        self.standard_library_titles = standard_library_titles
        self.optional_library_titles_selected = optional_library_titles_selected

    async def correct_callback(self, interaction: discord.Interaction):
        await self.interaction.delete_original_response()

        base_url = self.selected_server.connections[0].uri
        token = self.selected_server.accessToken

        # Add the new Plex server to the config
        new_server = {
            'serverName': self.selected_server.name,
            'baseUrl': base_url,
            'token': token,
            'standardLibraries': self.standard_library_titles,
            'optionalLibraries': self.optional_library_titles_selected
        }

        config["PLEX-" + self.selected_server.name.replace(" ", "_")] = new_server

        with open(config_location, 'w') as config_file:
            yaml.dump(config, config_file)

        await self.interaction.followup.send(content="Plex server added successfully!", ephemeral=True)

    async def cancel_callback(self, interaction: discord.Interaction):
        await self.interaction.delete_original_response()
        await self.interaction.followup.send(content="Operation cancelled.", ephemeral=True)
