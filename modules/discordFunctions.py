import discord
import logging
from discord import app_commands, Embed
from discord.ext import commands
from discord.ui import Select, View, Button
from modules import configFunctions, mathFunctions


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
        await interaction.response.edit_message(content="Select the payment method", view=mathFunctions.PaymentMethodView(self.information))