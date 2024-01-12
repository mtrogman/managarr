import sys
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button
import yaml
import logging


bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def getConfig(file):
    with open(file, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


config_location = "/config/config.yml"
config = getConfig(config_location)
bot_token = config['bot']['token']



# View & Select required to build out Discord Dropdown.
class UserSelectorView(View):
    def __init__(self, searchResults, information):
        super().__init__()
        self.add_item(UserSelector(searchResults, information))


class UserSelector(Select):
    def __init__(self, searchResults, information):
        self.searchResults = searchResults
        options = [
            discord.SelectOption(
                label=user['discord'],
                value=str(idx),
                description=user['email']
            )
            for idx, user in enumerate(searchResults)
        ]
        super().__init__(placeholder="Please select the user", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        selectedUserIndex = int(self.values[0])
        selectedUserData = self.searchResults[selectedUserIndex]
        self.userInfo['movieId'] = selectedUserData.get('id', 'N/A')

        confirmation_message = (
            f"Please confirm this is correct user:\n"
            f"**Discord Name:** {selectedUserData.get('discord', 'N/A')}\n"
            f"**Email Address:** {selectedUserData.get('email', 'N/A')}\n"
        )


        # # Add media_info parameter to callback method
        # await interaction.response.edit_message(content="Please select season(s) you wish to request",  view=BaseSeasonSelectorView(self.media_info))

information = {}


# Sync commands with discord
@bot.event
async def on_ready():
    logging.info('Bot is Up and Ready!')
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(f"{e}")


# Bot command to "grab" (search) for movie
@bot.tree.command(name="paymentRecieved", description="Update users paid amount and extend end date")
@app_commands.describe(user="What user paid?")
async def paymentRecieved(ctx, *, user: str, paymentAmount: int):
    
    # Thinking input should be:
        # Person who paid (real name)
        # Email address (in case they emailed that they paid)
        # Discord name (needs to close match as display name and discord username are not the same always)
    # Should I at this point include the amount recieved?  I think so as it'll make it more streamlined.
    
    #Returns user information so we can confirm which user we want to modify their record on.
    userResult = await fetchUser(user)
    
    if not userResult:
        await ctx.response.send_message(
            f"{ctx.user.name} No user found matching that name on discord: {user}")
        return
    information['what'] = 'payment'
    information['paymentAmount'] = paymentAmount

    await ctx.response.send_message("Select the correct user", view=UserSelectorView(userResult), ephemeral=True)


bot.run(bot_token)