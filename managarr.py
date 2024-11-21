import sys, logging, discord, os
from plexapi.myplex import MyPlexAccount
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button
from modules import dbFunctions, discordFunctions, configFunctions, mathFunctions, emailFunctions, selectFunctions

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

config_location = "/config/config.yml"
config = configFunctions.get_config(config_location)
bot_token = config['discord']['token']


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
    search_results = dbFunctions.find_user(user)
    if not search_results:
        await ctx.response.send_message(f"{ctx.user.name} No user found matching the given identifier: {user}")
        return
    information = {'what': 'payment', 'paymentAmount': amount}
    await ctx.response.send_message("Select the correct user", view=UpdateSelectorView(search_results, information), ephemeral=True)


@bot.tree.command(name="add_new_user", description="Add new user to DB")
@app_commands.describe(discorduser="Discord Username; Put none or na if user not on Discord", email="User email address", payment_person="The name on the payment", amount="Payment amount (float)")
async def add_new_user(ctx, *, discorduser: str = "none", email: str, payment_person: str, amount: float):
    information = {'what': 'newuser', 'primaryEmail': email, 'paidAmount': amount, 'paymentPerson': payment_person}
    await ctx.response.send_message("Confirm Discord User", view=discordFunctions.DiscordUserView(information, ctx, discorduser), ephemeral=True)


# Bot command to "Change a user's subscription (change server or add/remove 4k library)"
@bot.tree.command(name="move_user", description="Update user's plex libraries")
@app_commands.describe(user="User identifier (Discord user, email address, or paymentPerson)", amount="Payment amount (float)")
async def move_user(ctx, *, user: str, amount: float = None):
    search_results = dbFunctions.find_user(user)
    if not search_results:
        await ctx.response.send_message(f"No user found matching the given identifier: {user}", ephemeral=True)
        return
    information = {'what': 'move', 'paymentAmount': amount}
    await ctx.response.send_message("Select the correct user", view=UpdateSelectorView(search_results, information), ephemeral=True)


# Bot command to add a new Plex server
@bot.tree.command(name="add_plex_server", description="Add a new Plex server to the configuration")
@app_commands.describe(email="Plex account email", password="Plex account password")
async def add_plex_server(ctx, *, email: str, password: str):
    try:
        account = MyPlexAccount(email, password)
        servers = account.resources()
    except Exception as e:
        await ctx.response.send_message(f"Error: {str(e)}", ephemeral=True)
        return

    # Filter the resources to get only servers
    servers = [server for server in servers if 'server' in server.provides]

    if not servers:
        await ctx.response.send_message("No servers found. Please check your credentials.", ephemeral=True)
        return

    view = View()
    view.add_item(selectFunctions.ServerSelect(ctx, servers))
    await ctx.response.send_message("Choose a Plex server:", view=view, ephemeral=True)


bot.run(bot_token)