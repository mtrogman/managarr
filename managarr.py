import sys, re, yaml, mysql.connector, logging, discord, math, os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from discord import app_commands, Embed
from discord.ext import commands
from discord.ui import Select, View, Button

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Set up logging to both console and file
logFile = "/config/managarr.log"

# Check if the log file exists, create it if it doesn't
if not os.path.exists(logFile):
    open(logFile, 'w').close()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(logFile)
])


def getConfig(file):
    with open(file, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


config_location = "/config/config.yml"
config = getConfig(config_location)
bot_token = config['discord']['token']

db_config = {
    'host': config['database']['host'],
    'database': config['database']['database'],
    'user': config['database']['user'],
    'password': config['database']['password'],
    'port': config['database']['port']
}


def createConnection():
    try:
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            return connection
    except mysql.connector.Error as e:
        logging.error(f"Error connecting to the database: {e}")
        return None


def createUser(information):
    try:
        connection = createConnection()
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
        startDate = information.get('startDate', '')
        joinDate = startDate
        endDate = information.get('endDate', '')


        # SQL query to insert a new user into the database
        insert_query = "INSERT INTO users (primaryEmail, primaryDiscord, primaryDiscordId, paymentMethod, payname, paidAmount, server, 4k, status, joinDate, startDate, endDate) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(insert_query, (primary_email, primary_discord, primary_discord_id, payment_method, payname, paid_amount, server, is_4k, status, joinDate, startDate, endDate))

        # Commit the changes
        connection.commit()
        logging.info(f"Created new user with primary email: {primary_email}")
    except mysql.connector.Error as e:
        logging.error(f"Error creating user: {e}")

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def updateDatabase(user_id, field, value):
    try:
        connection = createConnection()
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


def findUser(search_term):
    # Convert search term to lowercase
    search_term = search_term.lower()

    # Columns to search in the database
    columns = ['primaryEmail', 'secondaryEmail', 'primaryDiscord', 'secondaryDiscord', 'paymentPerson']

    # Initialize a list to store matching rows
    matching_rows_list = []

    # Regex pattern to identify email addresses
    email_regex = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'

    # Iterate through columns and search for matches
    for column in columns:
        try:
            connection = createConnection()
            if connection:
                cursor = connection.cursor(dictionary=True)

                # Check if the column is an email field using regex
                is_email_field = re.search(email_regex, column.lower())

                # Build the SQL query based on whether it's an email field
                if is_email_field:
                    query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s AND {column} REGEXP %s"
                    cursor.execute(query, ('%' + search_term + '%', email_regex))
                else:
                    query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s"
                    cursor.execute(query, ('%' + search_term + '%',))

                # Fetch all matching rows
                matching_rows = cursor.fetchall()

                # Check for duplicates before adding to the list
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


async def addRole(user_id, role_name):
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


async def sendDiscordMessage(toUser, subject, body):
    user = await bot.fetch_user(toUser)
    embed = Embed(title=f"**{subject}**", description=body, color=discord.Colour.blue())
    try:
        await user.send(embed=embed)
    except discord.errors.Forbidden as e:
        logging.warning(f"Failed to send message to {user.name}#{user.discriminator}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred for {user.name}: {e}")


def sendEmail(config_location, subject, body, toEmails):
    # Retrieve the email configuration from the config file
    config = getConfig(config_location)
    emailConfig = config.get('email', {})

    # Extract email configuration values
    smtpServer = emailConfig.get('smtpServer', '')
    smtpPort = emailConfig.get('smtpPort', 587)
    smtpUsername = emailConfig.get('smtpUsername', '')
    smtpPassword = emailConfig.get('smtpPassword', '')

    # Check if any required values are missing
    if not smtpServer or not smtpUsername or not smtpPassword:
        raise ValueError("Email configuration is incomplete. Please check your config file.")

    # Create the email message
    msg = MIMEMultipart()
    msg['From'] = smtpUsername
    msg['To'] = toEmails
    msg['Subject'] = subject

    # Attach the body of the email
    msg.attach(MIMEText(body, 'plain'))

    # Connect to the SMTP server and send the email
    with smtplib.SMTP(smtpServer, smtpPort) as server:
        server.starttls()
        server.login(smtpUsername, smtpPassword)
        server.sendmail(smtpUsername, toEmails, msg.as_string())


def calculate_term_length(server, amount, is_4k):
    config = getConfig(config_location)
    plex_config = config.get(f"PLEX-{server}", {})

    # Get the pricing section based on the 4K status
    pricing_section = plex_config.get('4k' if is_4k == 'Yes' else '1080p', {})

    # Try to find a matching term length based on the amount
    for term_length, price in pricing_section.items():
        if price == amount:
            return int(term_length.strip('Month'))

    # If no exact match found, calculate based on 1 month price
    one_month_price = pricing_section.get('1Month', 0)
    if one_month_price == 0:
        return 0  # No pricing information found

    term_length = amount / one_month_price

    # Check if the calculated term length is an integer or if it needs to be rounded down
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
        # Use self.information to access user details
        await self.interaction.delete_original_response()

        followup_message = ""

        for user in self.information['users']:
            id = user.get('id')
            status = user.get('status')
            newPaidAmount = user.get('newPaidAmount')
            newStartDate = user.get('newStartDate')
            newEndDate = user.get('newEndDate')
            userEmail = user.get('primaryEmail')

            # Extract relevant information from the user object
            server = user.get('server')
            discordUser = user.get('primaryDiscord')
            discordUserId = user.get('primaryDiscordId')
            discordRole = config.get(f"PLEX-{server}", {}).get('role')
            standardLibraries = config.get(f"PLEX-{server}", {}).get('standardLibraries')
            optionalLibraries = config.get(f"PLEX-{server}", {}).get('optionalLibraries')
            section_names = standardLibraries + optionalLibraries if user.get('4k') == "Yes" else standardLibraries
            newEndDate = user.get('newEndDate')
            subject = config.get(f"discord", {}).get('paymentSubject')
            body = config.get(f"discord", {}).get('paymentBody')
            # Perform string interpolation to substitute variables with values
            body = body.format(primaryEmail=userEmail, server=server, section_names=section_names, newEndDate=newEndDate)

            # Retrieve configuration for the Plex server
            plexConfig = config.get(f'PLEX-{server}', None)
            if not isinstance(plexConfig, dict):
                logging.error(f"No configuration found for Plex server '{server}'")
                return

            baseUrl = plexConfig.get('baseUrl', None)
            token = plexConfig.get('token', None)
            if status == "Inactive":
                # Add user to paid role
                await addRole(discordUserId, discordRole)

                if not baseUrl or not token:
                    logging.error(f"Invalid configuration for Plex server '{server}'")
                    return
                # Authenticate to Plex
                try:
                    plex = PlexServer(baseUrl, token)
                except Exception as e:
                    logging.error(f"Error authenticating to {baseUrl}")
                    logging.exception(e)

                # Invite user back to Plex
                try:
                    addUser = plex.myPlexAccount().inviteFriend(user=userEmail, server=plex, sections=section_names, allowSync=True)
                    if addUser:
                        logging.info(f"User '{userEmail}' has been successfully removed from Plex server '{server}'")
                except Exception as e:
                    logging.error(f"Error inviting user {userEmail} to {server} with the following libraries: {section_names}")
                    logging.exception(e)

            updateDatabase(id, "paidAmount", newPaidAmount)
            updateDatabase(id, "startDate", newStartDate)
            updateDatabase(id, "endDate", newEndDate)
            updateDatabase(id, "status", "Active")

            followup_message += (
                "---------------------\n"
                f"Discord: {discordUser}\n"
                f"Email: {userEmail}\n"
                f"Server: {user.get('server')}\n"
                f"4k: {user.get('4k')}\n"
                f"Start Date: {user.get('newStartDate')}\n"
                f"End Date: {newEndDate}\n"
                f"Status: {user.get('status')}\n"
                f"Paid Amount: {user.get('newPaidAmount')}\n"
            )

            # Send Discord Msg to user
            await sendDiscordMessage(toUser=discordUserId, subject=subject, body=body)
            # Send Email Msg to user
            sendEmail(config_location, subject, body, userEmail)

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
        # Use self.information to access user details
        await self.interaction.delete_original_response()

        followup_message = ""

        # Extract relevant information from the user object
        server = self.information.get('server')
        email = self.information.get('primaryEmail')
        discordUser = self.information.get('primaryDiscord')
        discordUserId = self.information.get('primaryDiscordId')
        discordRole = config.get(f"PLEX-{server}", {}).get('role')
        standardLibraries = config.get(f"PLEX-{server}", {}).get('standardLibraries')
        optionalLibraries = config.get(f"PLEX-{server}", {}).get('optionalLibraries')
        section_names = standardLibraries + optionalLibraries if self.information.get('4k') == "Yes" else standardLibraries
        startDate = self.information.get('startDate')
        endDate = self.information.get('endDate')


        # Retrieve configuration for the Plex server
        plexConfig = config.get(f'PLEX-{server}', None)
        if not isinstance(plexConfig, dict):
            logging.error(f"No configuration found for Plex server '{server}'")
            return

        baseUrl = plexConfig.get('baseUrl', None)
        token = plexConfig.get('token', None)
        if discordUser:
            await addRole(discordUserId, discordRole)

        if not baseUrl or not token:
            logging.error(f"Invalid configuration for Plex server '{server}'")
            return
        # Authenticate to Plex
        try:
            plex = PlexServer(baseUrl, token)
        except Exception as e:
            logging.error(f"Error authenticating to {baseUrl}")
            logging.exception(e)

        # Invite user to Plex
        try:
            addUser = plex.myPlexAccount().inviteFriend(user=email, server=plex, sections=section_names, allowSync=True)
            if addUser:
                logging.info(f"User '{email}' has been successfully to {server}")
        except Exception as e:
            logging.error(f"Error inviting user {email} to {server} with the following libraries: {section_names}")
            logging.exception(e)

        # Create user in DB
        createUser(self.information)

        followup_message += (
            f"Discord: {discordUser}\n"
            f"Email: {email}\n"
            f"Server: {self.information.get('server')}\n"
            f"4k: {self.information.get('4k')}\n"
            f"Start Date: {startDate}\n"
            f"End Date: {endDate}\n"
            f"Status: {self.information.get('status')}\n"
            f"Paid Amount: {self.information.get('PaidAmount')}\n"
        )


        await self.interaction.followup.send(content=f"{followup_message}", ephemeral=True)

    async def cancel_callback(self, button):
        await self.interaction.delete_original_response()
        await self.interaction.followup.send(content="Cancelled the request.", ephemeral=True)


class DiscordUserView(View):
    def __init__(self, information, ctx, discorduser):
        super().__init__(timeout=None)
        self.add_item(DiscordUserSelector(information, ctx, discorduser))


class DiscordUserSelector(Select):
     def __init__(self, information, ctx, discorduser):
        self.information = information
        options = []
        # Find Discord User
        if discorduser.lower() != "none":
            guild = ctx.guild
            if not guild:
                ctx.response.edit_message("Command must be used in a guild/server.")
                return

            # Search for the member in the guild, checking both display name and username
            member = discord.utils.find(lambda m: m.name.lower() == discorduser.lower() or m.display_name.lower() == discorduser.lower(), guild.members)

            if not member:
                ctx.response.edit_message(f"User '{discorduser}' not found in the server.")
                return
            options.append(discord.SelectOption(label=member.name,value=member.id))
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

        config = getConfig(config_location)
        payment_methods = config.get('PaymentMethod', [])

        options = [
            discord.SelectOption(
                label=method,
                value=method
            )
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

        config = getConfig(config_location)
        server_names = []

        for key in config.keys():
            if key.startswith('PLEX-'):
                server_name = config[key].get('serverName', None)
                if server_name:
                    server_names.append(server_name)

        options = [
            discord.SelectOption(
                label=server_name,
                value=server_name
            )
            for server_name in server_names
        ]
        options.append(discord.SelectOption(label="Cancel", value="cancel"))

        super().__init__(placeholder="Media Server", options=options, min_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="Cancelled the request", view=None)
            return
        self.information['server'] = self.values[0]
        await interaction.response.edit_message(content="Select the 4k", view=fourKView(self.information))


class fourKView(View):
    def __init__(self, information):
        super().__init__()
        self.add_item(fourKSelector(information))


class fourKSelector(Select):
    def __init__(self, information):
        self.information = information

        options = []
        options.append(discord.SelectOption(label="Yes", value="Yes"))
        options.append(discord.SelectOption(label="No", value="No"))
        options.append(discord.SelectOption(label="Cancel", value="cancel"))

        super().__init__(placeholder="4K?", options=options, min_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "cancel":
            await interaction.response.edit_message(content="Cancelled the request", view=None)
            return
        self.information['4k'] = self.values[0]

        server = self.information.get('server', '')
        termLength = calculate_term_length(server, self.information['paidAmount'], self.information['4k'])
        today = datetime.now().date()
        self.information['startDate'] = today.strftime('%Y-%m-%d')
        self.information['endDate'] = today + relativedelta(months=termLength)
        self.information['termLength'] = termLength

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


class UpdateSelectorView(View):
    def __init__(self, searchResults, information):
        super().__init__()
        self.add_item(UpdateSelector(searchResults, information))


class UpdateSelector(Select):
    def __init__(self, searchResults, information):
        self.searchResults = searchResults
        self.information = information
        max_options = 10  # Adjust the number of options as needed

        options = [
            discord.SelectOption(
                label=f"{user['paymentPerson']} | {user['server']} ({user['status']})",
                value=str(idx),
                description=f"Discord: {user['primaryDiscord'] if user['primaryDiscord'] else 'N/A'} | Email: {user['primaryEmail']}",
                emoji="👤"
            )
            for idx, user in enumerate(searchResults[:max_options])
        ]

        # Adjust max_values dynamically based on the number of actual options
        max_values = min(len(searchResults), max_options)

        super().__init__(placeholder="Please select the user", options=options, min_values=1, max_values=max_values)

    async def callback(self, interaction: discord.Interaction):
        selected_user_indices = [int(value) for value in self.values]
        selected_users = [self.searchResults[idx] for idx in selected_user_indices]

        # Add the selected users to the information list
        self.information.setdefault('users', []).extend(selected_users)

        user_count = len(self.information.get('users', []))

        if user_count >= 1:
            # Initialize dictionaries to store prices for each term length
            total_prices = {'1Month': 0, '3Month': 0, '6Month': 0, '12Month': 0}

            for user in selected_users:
                user_resolution = user.get('4k')
                user_server = user.get('server')

                # Get the corresponding pricing section from the config based on the user's resolution
                pricing_section = config[f"PLEX-{user_server}"]["4k"] if user_resolution == "Yes" else config[f"PLEX-{user_server}"]["1080p"]

                # Add the prices to the total_prices dictionary
                total_prices['1Month'] += pricing_section['1Month']
                total_prices['3Month'] += pricing_section['3Month']
                total_prices['6Month'] += pricing_section['6Month']
                total_prices['12Month'] += pricing_section['12Month']

                # Store the prices for each user in information['users'][EACH USER]
                user['prices'] = pricing_section

            total_amount = self.information['paymentAmount']

            # Check if the total amount matches any of the values in the total_prices dictionary
            matching_lengths = [key for key, value in total_prices.items() if value == total_amount]

            notRounded = True
            eachExtraBalance = 0

            if matching_lengths:
                subscription_length_str = matching_lengths[0]
                termLength = int(''.join(filter(str.isdigit, subscription_length_str)))
                self.information['length'] = termLength
                eachExtraBalance = 0
            else:
                # The amount doesn't match any predefined values, try calculating based on 1Month value
                one_month_price = total_prices['1Month']
                calculated_months = total_amount / one_month_price

                if calculated_months.is_integer():
                    termLength = int(calculated_months)
                    eachExtraBalance = 0
                else:
                    termLength = math.floor(calculated_months)
                    extraBalance = total_amount - (termLength * one_month_price)
                    eachExtraBalance = extraBalance / user_count
                    notRounded = False

            confirmation_message = ""

            for user in self.information['users']:
                if f'{termLength}Month' in user['prices']:
                    paymentAmount = user['prices'][f'{termLength}Month']
                else:
                    paymentAmount = user['prices'].get('1Month') * termLength

                user['newPaidAmount'] = float(user['paidAmount']) + paymentAmount + eachExtraBalance

                if user['status'] == 'Active':
                    user['newStartDate'] = user['endDate']
                else:
                    today = datetime.today().date()
                    user['newStartDate'] = today
                user['newEndDate'] = user['newStartDate'] + relativedelta(months=termLength)

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
                    f"User Pay Correct Amount?: {notRounded}\n"
                )

            confirmation_view = ConfirmButtonsPayment(interaction, self.information)

            await interaction.response.edit_message(content=confirmation_message, view=confirmation_view)


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
    # Use the findUser function to get closely matching users
    searchResults = findUser(user)

    if not searchResults:
        await ctx.response.send_message(
            f"{ctx.user.name} No user found matching the given identifier: {user}")
        return

    information = {}
    information['what'] = 'payment'
    information['paymentAmount'] = amount
    await ctx.response.send_message("Select the correct user", view=UpdateSelectorView(searchResults, information), ephemeral=True)



@bot.tree.command(name="add_new_user", description="Add new user to DB")
@app_commands.describe(discorduser="Discord Username; Put none or na if user not on Discord", email="User email address", payname="The name on the payment", amount="Payment amount (float)")
async def add_new_user(ctx, *, discorduser: str = "none", email: str, payname: str, amount: float):
    information = {}
    information['what'] = 'newuser'
    information['primaryEmail'] = email
    information['paidAmount'] = amount
    information['payname'] = payname
    await ctx.response.send_message("Confirm Discord User", view=DiscordUserView(information, ctx, discorduser), ephemeral=True)


bot.run(bot_token)