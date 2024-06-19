import sys
import re
import yaml
import mysql.connector
import logging
import discord
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from plexapi.server import PlexServer
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from discord import app_commands, Embed
from discord.ext import commands
from discord.ui import Select, View, Button

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Set up logging to both console and file
log_file = "/config/managarr.log"

# Check if the log file exists, create it if it doesn't
if not os.path.exists(log_file):
    open(log_file, 'w').close()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(log_file)
])


def get_config(file):
    with open(file, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


config_location = "/config/config.yml"
config = get_config(config_location)
bot_token = config['discord']['token']

db_config = {
    'host': config['database']['host'],
    'database': config['database']['database'],
    'user': config['database']['user'],
    'password': config['database']['password'],
    'port': config['database']['port']
}


def create_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            return connection
    except mysql.connector.Error as e:
        logging.error(f"Error connecting to the database: {e}")
        return None


def create_user(information):
    try:
        connection = create_connection()
        if connection:
            cursor = connection.cursor()

        # Extract information from the input dictionary
        primary_email = information.get('primaryEmail', '')
        primary_discord = information.get('primaryDiscord', '')
        primary_discord_id = information.get('primaryDiscordId', '')
        payment_method = information.get('paymentMethod', '')
        pay_name = information.get('payname', '')
        paid_amount = information.get('paidAmount', '')
        server = information.get('server', '')
        is_4k = information.get('4k', '')
        status = "Active"
        start_date = information.get('startDate', '')
        join_date = start_date
        end_date = information.get('endDate', '')

        # SQL query to insert a new user into the database
        insert_query = """
        INSERT INTO users (primaryEmail, primaryDiscord, primaryDiscordId, paymentMethod, payname, paidAmount, server, 4k, status, joinDate, startDate, endDate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (primary_email, primary_discord, primary_discord_id, payment_method, pay_name, paid_amount, server, is_4k, status, join_date, start_date, end_date))

        # Commit the changes
        connection.commit()
        logging.info(f"Created new user with primary email: {primary_email}")
    except mysql.connector.Error as e:
        logging.error(f"Error creating user: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def update_database(user_id, field, value):
    try:
        connection = create_connection()
        if connection:
            cursor = connection.cursor()

            # SQL query to update the specified field for the given user ID
            update_query = f"UPDATE users SET {field} = %s WHERE id = %s"
            cursor.execute(update_query, (value, user_id))

            # Commit the changes
            connection.commit()
            logging.info(f"Updated {field} for user ID {user_id} to {value}")
    except mysql.connector.Error as e:
        logging.error(f"Error updating database: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def find_user(search_term):
    search_term = search_term.lower()
    columns = ['primaryEmail', 'secondaryEmail', 'primaryDiscord', 'secondaryDiscord', 'paymentPerson']
    matching_rows_list = []
    email_regex = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'

    for column in columns:
        try:
            connection = create_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                is_email_field = re.search(email_regex, column.lower())
                if is_email_field:
                    query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s AND {column} REGEXP %s"
                    cursor.execute(query, ('%' + search_term + '%', email_regex))
                else:
                    query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s"
                    cursor.execute(query, ('%' + search_term + '%',))
                matching_rows = cursor.fetchall()
                for row in matching_rows:
                    if row not in matching_rows_list:
                        matching_rows_list.append(row)
        except mysql.connector.Error as e:
            logging.error(f"Error searching for users: {e}")
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()

    return matching_rows_list


async def add_role(user_id, role_name):
    guild_id = int(config['discord']['guildId'])

    try:
        guild = bot.get_guild(guild_id)
        if guild:
            user = await guild.fetch_member(user_id)
            if user:
                role = discord.utils.get(guild.roles, name=role_name)
                if role:
                    await user.add_roles(role)
                    logging.info(f"Added role {role_name} to user {user.name} ({user.id})")
                else:
                    logging.error(f"Role {role_name} not found")
            else:
                logging.error(f"Member {user_id} not found in the guild")
        else:
            logging.error(f"Guild {guild_id} not found")
    except discord.Forbidden:
        logging.error(f"Bot doesn't have permission to add roles")
    except discord.HTTPException as e:
        logging.error(f"Error adding role: {e}")


async def send_discord_message(to_user, subject, body):
    user = await bot.fetch_user(to_user)
    embed = Embed(title=f"**{subject}**", description=body, color=discord.Colour.blue())
    try:
        await user.send(embed=embed)
    except discord.errors.Forbidden as e:
        logging.warning(f"Failed to send message to {user.name}#{user.discriminator}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred for {user.name}: {e}")


def send_email(config_location, subject, body, to_emails):
    config = get_config(config_location)
    email_config = config.get('email', {})
    smtp_server = email_config.get('smtpServer', '')
    smtp_port = email_config.get('smtpPort', 587)
    smtp_username = email_config.get('smtpUsername', '')
    smtp_password = email_config.get('smtpPassword', '')

    if not smtp_server or not smtp_username or not smtp_password:
        raise ValueError("Email configuration is incomplete. Please check your config file.")

    msg = MIMEMultipart()
    msg['From'] = smtp_username
    msg['To'] = to_emails
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, to_emails, msg.as_string())


def calculate_term_length(server, amount, is_4k):
    config = get_config(config_location)
    plex_config = config.get(f"PLEX-{server}", {})
    pricing_section = plex_config.get('4k' if is_4k == 'Yes' else '1080p', {})

    for term_length, price in pricing_section.items():
        if price == amount:
            return int(term_length.strip('Month'))

    one_month_price = pricing_section.get('1Month', 0)
    if one_month_price == 0:
        return 0

    term_length = amount / one_month_price
    if term_length.is_integer():
        return int(term_length)
    else:
        return math.floor(term_length)


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
            new_end_date = user.get('newEndDate')
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
                await add_role(discord_user_id, discord_role)
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

            update_database(user_id, "paidAmount", new_paid_amount)
            update_database(user_id, "startDate", new_start_date)
            update_database(user_id, "endDate", new_end_date)
            update_database(user_id, "status", "Active")

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
                await send_discord_message(to_user=discord_user_id, subject=subject, body=body)
            # Send Email Msg to user
            send_email(config_location, subject, body, user_email)

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
            await add_role(discord_user_id, discord_role)

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

        create_user(self.information)
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
            try:
                update_user = plex.myPlexAccount().createExistingUser(user=email, server=plex, sections=section_names, allowSync=True)
                if update_user:
                    logging.info(f"User '{email}' has been successfully updated on Plex server '{new_server}'")
            except Exception as e:
                logging.error(f"Error updating libraries for user {email} on {old_server}")
                logging.exception(e)

        if new_server != old_server:
            update_database(self.information.get('id'), "server", new_server)
        if self.information['paymentAmount'] is not None:
            newPaidAmount = float(self.information['paidAmount']) + float(self.information['paymentAmount'])
            update_database(self.information.get('id'), "paidAmount", newPaidAmount)
        if old_4k != new_4k:
            update_database(self.information.get('id'), "4k", new_4k)

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


class DiscordUserView(View):
    def __init__(self, information, ctx, discord_user):
        super().__init__(timeout=None)
        self.add_item(DiscordUserSelector(information, ctx, discord_user))


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


class PaymentMethodView(View):
    def __init__(self, information):
        super().__init__()
        self.add_item(PaymentMethodSelector(information))


class PaymentMethodSelector(Select):
    def __init__(self, information):
        self.information = information
        config = get_config(config_location)
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


class ServerView(View):
    def __init__(self, information):
        super().__init__()
        self.add_item(ServerSelector(information))


class ServerSelector(Select):
    def __init__(self, information):
        self.information = information
        config = get_config(config_location)
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


class FourKView(View):
    def __init__(self, information):
        super().__init__()
        self.add_item(FourKSelector(information))

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

    async def handle_payment(self, interaction):
        server = self.information.get('server', '')
        term_length = calculate_term_length(server, self.information['paidAmount'], self.information['4k'])
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


class UpdateSelectorView(View):
    def __init__(self, search_results, information):
        super().__init__()
        self.add_item(UpdateSelector(search_results, information))


class UpdateSelector(Select):
    def __init__(self, search_results, information):
        self.search_results = search_results
        self.information = information
        max_options = 10
        options = [
            discord.SelectOption(
                label=f"{user['paymentPerson']} | {user['server']} ({user['status']})",
                value=str(idx),
                description=f"Discord: {user['primaryDiscord'] if user['primaryDiscord'] else 'N/A'} | Email: {user['primaryEmail']}",
                emoji="👤"
            )
            for idx, user in enumerate(search_results[:max_options])
        ]
        max_values = min(len(search_results), max_options)
        super().__init__(placeholder="Please select the user", options=options, min_values=1, max_values=max_values)

    async def callback(self, interaction: discord.Interaction):
        selected_user_indices = [int(value) for value in self.values]
        selected_users = [self.search_results[idx] for idx in selected_user_indices]
        self.information.setdefault('users', []).extend(selected_users)

        if self.information['what'] == 'payment':
            await self.view.handle_payment(interaction, selected_users)
        elif self.information['what'] == 'move':
            await self.view.handle_move(interaction, selected_users)

class UpdateSelectorView(View):
    def __init__(self, search_results, information):
        super().__init__()
        self.search_results = search_results
        self.information = information
        self.add_item(UpdateSelector(search_results, information))

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


# Sync commands with discord
@bot.event
async def on_ready():
    print(f"Bot is Up and Ready!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"{e}")


# Bot command to "receive payment"
@bot.tree.command(name="payment_received", description="Update user's paid amount and extend end date")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)", amount="Payment amount (float)")
async def payment_received(ctx, *, user: str, amount: float):
    search_results = find_user(user)
    if not search_results:
        await ctx.response.send_message(f"{ctx.user.name} No user found matching the given identifier: {user}")
        return
    information = {'what': 'payment', 'paymentAmount': amount}
    await ctx.response.send_message("Select the correct user", view=UpdateSelectorView(search_results, information), ephemeral=True)


@bot.tree.command(name="add_new_user", description="Add new user to DB")
@app_commands.describe(discorduser="Discord Username; Put none or na if user not on Discord", email="User email address", payname="The name on the payment", amount="Payment amount (float)")
async def add_new_user(ctx, *, discorduser: str = "none", email: str, payname: str, amount: float):
    information = {'what': 'newuser', 'primaryEmail': email, 'paidAmount': amount, 'payname': payname}
    await ctx.response.send_message("Confirm Discord User", view=DiscordUserView(information, ctx, discorduser), ephemeral=True)


# Bot command to "Change a user's subscription (change server or add/remove 4k library)"
@bot.tree.command(name="move_user", description="Update user's plex libraries")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)", amount="Payment amount (float)")
async def move_user(ctx, *, user: str, amount: float = None):
    search_results = find_user(user)
    if not search_results:
        await ctx.response.send_message(f"No user found matching the given identifier: {user}", ephemeral=True)
        return
    information = {'what': 'move', 'paymentAmount': amount}
    await ctx.response.send_message("Select the correct user", view=UpdateSelectorView(search_results, information), ephemeral=True)

bot.run(bot_token)
