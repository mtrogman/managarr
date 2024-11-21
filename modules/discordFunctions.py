import discord, logging
from discord import Embed
from discord.ext import commands
from modules import configFunctions


config_location = "/config/config.yml"
config = configFunctions.get_config(config_location)

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())


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
    user = await bot.fetch_user(to_user)
    embed = Embed(title=f"**{subject}**", description=body, color=discord.Colour.blue())
    try:
        await user.send(embed=embed)
    except discord.errors.Forbidden as e:
        logging.warning(f"Failed to send message to {user.name}#{user.discriminator}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred for {user.name}: {e}")