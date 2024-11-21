import discord
from discord.ui import Select, View, Button
from datetime import datetime
from dateutil.relativedelta import relativedelta
from modules import configFunctions, mathFunctions, viewFunctions
import managarr

config_location = "/config/config.yml"
config = configFunctions.get_config(config_location)


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
        view = viewFunctions.ConfirmButtonsNewServer(interaction, selected_server, standard_library_titles, optional_library_titles_selected)
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
        view = viewFunctions.ConfirmButtonsNewServer(interaction, selected_server, standard_library_titles, optional_library_titles_selected)
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
        await interaction.response.edit_message(content="Select the 4k", view=viewFunctions.FourKView(self.information))


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

        confirmation_view = viewFunctions.ConfirmButtonsNewUser(interaction, self.information)
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

        confirmation_view = viewFunctions.ConfirmButtonsMoveUser(interaction, self.information)
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

        confirmation_view = viewFunctions.ConfirmButtonsNewUser(interaction, self.information)
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
        await interaction.response.edit_message(content="Select the Server", view=viewFunctions.ServerView(self.information))


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
        await interaction.response.edit_message(content="Select the payment method", view=viewFunctions.PaymentMethodView(self.information))