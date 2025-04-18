from keep_alive import keep_alive
import logging
import discord
from discord.ext import commands
from discord.ext import tasks
import os
import time
import asyncio

keep_alive()

TOKEN = os.environ["DISCORD_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
ADMIN_USERS = set(map(int, os.environ.get("ADMIN_USERS", "").split())) if os.environ.get("ADMIN_USERS") else set()
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))

os.system('clear')

# Set up logging to show only CRITICAL errors
logging.basicConfig(level=logging.CRITICAL)

# Set intents for the bot to read messages, view members, and server info
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- Spam Protection System -------------------- #

MAX_MESSAGES_PER_MINUTE = 10  # Limit to 5 messages per minute
MUTE_ROLE_NAME = "Muted"  # Role name for muting users
message_times = {}  # Store the time each user sent a message
cooldown_users = {}  # Store users who are muted
notified_users = {}  # Store users who have been notified

async def send_ephemeral_message(user, embed):
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        await user.guild.system_channel.send(f"{user.mention} Please enable DM to receive notifications!")

async def log_message(message: str):
    log_channel_id = os.getenv("LOG_CHANNEL_ID")
    if log_channel_id:
        log_channel = bot.get_channel(int(log_channel_id))
        if log_channel:
            await log_channel.send(message)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    current_time = time.time()

    if user_id in cooldown_users and cooldown_users[user_id] > current_time:
        remaining_time = int(cooldown_users[user_id] - current_time)

        if user_id not in notified_users:
            embed = discord.Embed(
                title="🚫 Spam Detected!",
                description=f"{message.author.mention} You are muted! Time left: {remaining_time}s",
                color=discord.Color.orange()
            )
            await send_ephemeral_message(message.author, embed)
            notified_users[user_id] = True

        await message.delete()

        while remaining_time > 0:
            await asyncio.sleep(1)
            current_time = time.time()
            remaining_time = int(cooldown_users[user_id] - current_time)
            embed = discord.Embed(
                title="🚫 Spam Detected!",
                description=f"{message.author.mention} You are muted! Time left: {remaining_time}s",
                color=discord.Color.orange()
            )
            try:
                await message.author.send(embed=embed)
            except discord.Forbidden:
                await message.guild.system_channel.send(f"{message.author.mention} Please enable DM to receive notifications!")

        return

    if user_id not in message_times:
        message_times[user_id] = []

    message_times[user_id].append(current_time)
    message_times[user_id] = [t for t in message_times[user_id] if current_time - t <= 60]

    if len(message_times[user_id]) > MAX_MESSAGES_PER_MINUTE:
        await message.delete()
        cooldown_users[user_id] = current_time + 60  # Set a cooldown of 60 seconds

        if user_id not in notified_users:
            embed = discord.Embed(
                title="🚫 Spam Detected!",
                description=f"{message.author.mention} You are muted for 1 minute due to sending too many messages!",
                color=discord.Color.orange()
            )
            await send_ephemeral_message(message.author, embed)
            notified_users[user_id] = True

        muted_role = discord.utils.get(message.guild.roles, name=MUTE_ROLE_NAME)
        if muted_role is None:
            muted_role = await message.guild.create_role(name=MUTE_ROLE_NAME, permissions=discord.Permissions(send_messages=False))
            for channel in message.guild.text_channels:
                await channel.set_permissions(muted_role, send_messages=False)

        await message.author.add_roles(muted_role)
        member = message.guild.get_member(user_id)
        if member and member.voice:
            await member.edit(mute=True, deafen=True)

        await asyncio.sleep(60)
        await message.author.remove_roles(muted_role)
        if member and member.voice:
            await member.edit(mute=False, deafen=False)

        del cooldown_users[user_id]
        notified_users.pop(user_id, None)

        await log_message(f"🚫 Spam detected! User {message.author.mention} was muted for 60 seconds.")

        return

    await bot.process_commands(message)

# -------------------- Admin Commands -------------------- #

@bot.tree.command(name="clear", description="Delete a specified number of messages in the chat")
async def clear(ctx: discord.Interaction, amount: int):
    if ctx.user.id not in ADMIN_USERS:
        await ctx.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    if amount <= 0 or amount > 100:
        await ctx.response.send_message("❌ Please specify a number of messages between 1 and 100.", ephemeral=True)
        return

    deleted_messages = await ctx.channel.purge(limit=amount)
    await ctx.response.send_message(f"✅ Deleted {len(deleted_messages)} messages.", ephemeral=True)

@bot.tree.command(name="help", description="Show the bot's commands")
async def help(ctx: discord.Interaction):
    embed = discord.Embed(
        title="Bot Commands",
        description="Here are the available commands you can use with this bot:",
        color=discord.Color.blue()
    )
    embed.add_field(name="/clear <amount>", value="Delete a specified number of messages in the chat (Admins only)", inline=False)
    await ctx.response.send_message(embed=embed, ephemeral=True)

# -------------------- Custom Activity -------------------- #

custom_messages = [
    "Kaida Dm ready!💚",
    "Made by wasd.",
]

@tasks.loop(seconds=5)
async def rotate_custom_activity():
    current_message = custom_messages[rotate_custom_activity.current_index]
    await bot.change_presence(
        activity=discord.CustomActivity(name=current_message),
        status=discord.Status.online
    )
    rotate_custom_activity.current_index = (rotate_custom_activity.current_index + 1) % len(custom_messages)

rotate_custom_activity.current_index = 0

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name="Kaida AntiSpam💚"))
    rotate_custom_activity.start()  # Start rotating the custom activity
    await bot.tree.sync()  # Sync the slash commands with the Discord API
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)
