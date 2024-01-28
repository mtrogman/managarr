import sys, re, yaml, mysql.connector, logging, discord, math
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
                # There is at least one matching term length
                subscription_length_str = matching_lengths[0]
                termLength = int(''.join(filter(str.isdigit, subscription_length_str)))
            else:
                # The amount doesn't match any predefined values, try calculating based on 1Month value
                one_month_price = total_prices['1Month']
                calculated_months = total_amount / one_month_price

                if calculated_months.is_integer():
                    termLength = int(calculated_months)
                else:
                    termLength = math.floor(calculated_months)
                    extraBalance = total_amount - (termLength * one_month_price)
                    eachExtraBalance = extraBalance / user_count
                    notRounded = False

            print("#####################")
            for user in selected_users:
                expectedAmount = user['prices'][f'{termLength}Month']
                paymentAmount = float(expectedAmount) + float(eachExtraBalance)
                print(
                    f"Primary Discord: {user.get('primaryDiscord')}\n"
                    f"Primary Email: {user.get('primaryEmail')}\n"
                    f"Server: {user.get('server')}\n"
                    f"4k: {user.get('4k')}\n"
                    f"Start Date: {user.get('startDate')}\n"
                    f"End Date: {user.get('endDate')}\n"
                    f"Status: {user.get('status')}\n"
                    f"Expected Amount: {expectedAmount}\n"
                    f"Paid Amount: {paymentAmount}\n"
                    f"User Pay Correct Amount?: {notRounded}\n"
                    "---------------------"
                )


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