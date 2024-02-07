import sys, re, yaml, mysql.connector, logging, discord, math
from datetime import datetime, timedelta
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


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

            # Add user to paid role
            await addRole(discordUserId, discordRole)

            # Retrieve configuration for the Plex server
            plexConfig = config.get(f'PLEX-{server}', None)
            if not isinstance(plexConfig, dict):
                logging.error(f"No configuration found for Plex server '{server}'")
                return

            baseUrl = plexConfig.get('baseUrl', None)
            token = plexConfig.get('token', None)
            if status == "Inactive":
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
                f"End Date: {user.get('newEndDate')}\n"
                f"Status: {user.get('status')}\n"
                f"Paid Amount: {user.get('newPaidAmount')}\n"
            )


        await self.interaction.followup.send(content=f"{followup_message}", ephemeral=True)

    async def cancel_callback(self, button):
        await self.interaction.delete_original_response()
        await self.interaction.followup.send(content="Cancelled the request.", ephemeral=True)


# View & Select required to build out Discord Dropdown.
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
                paymentAmount = user['prices'].get(f'{termLength}Month', user['prices'].get('1Month', 0)) * termLength

                user['newPaidAmount'] = float(user['paidAmount']) + paymentAmount + eachExtraBalance

                if user['status'] == 'Active':
                    user['newStartDate'] = user['endDate']
                    user['newEndDate'] = user['newStartDate'] + timedelta(days=30 * termLength)
                else:
                    today = datetime.today().date()
                    user['newStartDate'] = today
                    user['newEndDate'] = today + timedelta(days=30 * termLength)

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
    logging.info('Bot is Up and Ready!')
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"{e}")


# Bot command to "receive payment"
@bot.tree.command(name="payment_received", description="Update user's paid amount and extend end date")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)", amount="Payment amount (integer)")
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


bot.run(bot_token)