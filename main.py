from keep_alive import keep_alive
import logging
import discord
from discord.ext import commands
from discord.ext import commands, tasks
import os
import time
import asyncio

keep_alive()

os.system('clear')

# Set up logging to show only CRITICAL errors
logging.basicConfig(level=logging.CRITICAL)

# Access environment variables directly (no need for dotenv anymore)
TOKEN = os.getenv("DISCORD_TOKEN")  # Get bot's token from environment variable
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Get OWNER_ID from environment variable
ADMIN_USERS = set(map(int, os.getenv("ADMIN_USERS", "").split())) if os.getenv("ADMIN_USERS") else set()

# Set intents for the bot to read messages, view members, and server info
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)  # Use "!" as the prefix for commands

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

        # Check if user has already been notified
        if user_id not in notified_users:
            embed = discord.Embed(
                title="🚫 Spam Detected!",
                description=f"{message.author.mention} You are muted! Time left: Timestamp: {remaining_time}s",
                color=discord.Color.orange()
            )
            await send_ephemeral_message(message.author, embed)
            notified_users[user_id] = True  # User has been notified

        await message.delete()  # Delete the message the user tried to send
        
        # Countdown while the mute is active
        while remaining_time > 0:
            await asyncio.sleep(1)
            current_time = time.time()
            remaining_time = int(cooldown_users[user_id] - current_time)
            embed = discord.Embed(
                title="🚫 Spam Detected!",
                description=f"{message.author.mention} You are muted! Time left: Timestamp: {remaining_time}s",
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
        
        # Send the first notification message
        if user_id not in notified_users:  # Notify only once
            embed = discord.Embed(
                title="🚫 Spam Detected!",
                description=f"{message.author.mention} You are muted for 1 minute due to sending messages too quickly!",
                color=discord.Color.orange()
            )
            await send_ephemeral_message(message.author, embed)
            notified_users[user_id] = True  # User has been notified

        # Create "Muted" role if it doesn't exist
        muted_role = discord.utils.get(message.guild.roles, name=MUTE_ROLE_NAME)
        if muted_role is None:
            muted_role = await message.guild.create_role(name=MUTE_ROLE_NAME, permissions=discord.Permissions(send_messages=False))
            for channel in message.guild.text_channels:
                await channel.set_permissions(muted_role, send_messages=False)
        
        await message.author.add_roles(muted_role)
        member = message.guild.get_member(user_id)
        if member and member.voice:
            await member.edit(mute=True, deafen=True)
        
        await asyncio.sleep(60)  # Wait for 1 minute
        await message.author.remove_roles(muted_role)
        if member and member.voice:
            await member.edit(mute=False, deafen=False)
        
        del cooldown_users[user_id]
        notified_users.pop(user_id, None)  # Reset notifications after cooldown ends
        
        # Log the spam event with the remaining time
        await log_message(f"🚫 Spam detected! User {message.author.mention} was muted for 60 seconds due to sending too many messages.")
        
        return
    
    await bot.process_commands(message)

# -------------------- Admin Commands -------------------- #

@bot.tree.command(name="clear", description="ลบข้อความตามจำนวนที่เลือก")
async def clear(ctx: discord.Interaction, amount: int):
        """ Command to delete a specified number of messages """
        if ctx.user.id not in ADMIN_USERS:
            await ctx.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
            return

        if amount <= 0 or amount > 100:
            await ctx.response.send_message("❌ ใส่ได้แค่เลข 1 ถึง 100 เท่านั้น!", ephemeral=True)
            return

        # แจ้งว่าเราจะทำการลบข้อความ และป้องกันการหมดเวลา
        await ctx.response.defer(ephemeral=True)

        try:
            deleted_messages = await ctx.channel.purge(limit=amount)
            await ctx.followup.send(f"✅ ลบข้อความแล้ว {len(deleted_messages)} ข้อความ", ephemeral=True)
        except Exception as e:
            await ctx.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

@bot.tree.command(name="clear_all", description="ลบข้อความทั้งหมดในช่อง")
async def clear_all(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)  # ป้องกัน timeout

    channel = interaction.channel
    if isinstance(channel, discord.TextChannel):
        deleted = await channel.purge()
        await interaction.followup.send(f"✅ ลบข้อความแล้ว {len(deleted)} ข้อความ")
    else:
        await interaction.followup.send("❌ คำสั่งนี้ใช้ได้เฉพาะช่องข้อความเท่านั้น.")

@bot.tree.command(name="clear_user", description="ลบข้อความทั้งหมดจากผู้ใช้")
async def clear_user(ctx: discord.Interaction, member: discord.Member):
    """ Command to delete all messages from a specific user """
    if ctx.user.id not in ADMIN_USERS:
        await ctx.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
        return

    deleted_messages = await ctx.channel.purge(limit=100, check=lambda m: m.author == member)
    await ctx.response.send_message(f"✅ ลบข้อความแล้ว {len(deleted_messages)} ข้อความ จาก {member.mention}", ephemeral=True)

@bot.tree.command(name="add_admin", description="เพิ่มบทบาทผู้ดูแล")
async def add_admin(ctx: discord.Interaction, member: discord.Member):
    """ Command for the OWNER to add a new admin """
    if ctx.user.id != OWNER_ID:
        await ctx.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
        return

    global ADMIN_USERS
    ADMIN_USERS.add(member.id)  # Add the user to the admin set
    os.environ["ADMIN_USERS"] = " ".join(map(str, ADMIN_USERS))  # Update ENV
    
    with open(".env", "w") as f:
        f.write(f'DISCORD_TOKEN={TOKEN}\nOWNER_ID={OWNER_ID}\nADMIN_USERS={" ".join(map(str, ADMIN_USERS))}\n')
    
    embed = discord.Embed(
        title="✅ เพิ่มบทบาทผู้ดูแลเรียบร้อย!",
        description=f"{member.mention} ได้รับบทบาทผู้ดูแลแล้ว!",
        color=discord.Color.green()
    )
    await ctx.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove_admin", description="ลบบทบาทผู้ดูแล")
async def remove_admin(ctx: discord.Interaction, member: discord.Member):
    """ Command for the OWNER to remove an admin """
    if ctx.user.id != OWNER_ID:
        await ctx.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
        return

    global ADMIN_USERS
    if member.id in ADMIN_USERS:
        ADMIN_USERS.remove(member.id)
        os.environ["ADMIN_USERS"] = " ".join(map(str, ADMIN_USERS))
        
        with open(".env", "w") as f:
            f.write(f'DISCORD_TOKEN={TOKEN}\nOWNER_ID={OWNER_ID}\nADMIN_USERS={" ".join(map(str, ADMIN_USERS))}\n')

        embed = discord.Embed(
            title="❌ ลบบทบาทผู้ดูแลเรียบร้อย!",
            description=f"{member.mention} ลบบทบาทผู้ดูแลแล้ว!",
            color=discord.Color.red()
        )
    else:
        embed = discord.Embed(
            title="⚠️ ไม่พบผู้ใช้ในรายชื่อผู้ดูแล",
            description=f"{member.mention} ไม่มีบทบาทผู้ดูแล",
            color=discord.Color.orange()
        )
    await ctx.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="admin_list", description="แสดงรายชื่อผู้ดูแลทั้งหมด")
async def admin_list(ctx: discord.Interaction):
    """ Command to show the list of admins """
    if ctx.user.id not in ADMIN_USERS:
        await ctx.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
        return

    if ADMIN_USERS:
        admin_names = [f"<@{user_id}>" for user_id in ADMIN_USERS]
        embed = discord.Embed(
            title="รายชื่อผู้ดูแล",
            description="\n".join(admin_names),
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="ไม่พบรายชื่อผู้ดูแล",
            description="ในระบบขณะนี้ไม่มีผู้ดูแลระบบ",
            color=discord.Color.red()
        )
    await ctx.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="log", description="ตั้งค่าช่องสำหรับแจ้งเตือนการบันทึก")
async def set_log_channel(ctx: discord.Interaction, channel: discord.TextChannel):
    """ Command to set the log channel """
    if ctx.user.id != OWNER_ID:
        await ctx.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้!", ephemeral=True)
        return

    # Update the .env file to store the log channel ID
    with open(".env", "a") as f:
        f.write(f"LOG_CHANNEL_ID={channel.id}\n")
    
    # Confirm the user that the log channel has been set
    embed = discord.Embed(
        title="✅ ตั้งค่าช่องสำหรับแจ้งเตือนการบันทึกเรียบร้อย!",
        description=f"ตั้งค่าการบันทึกที่ช่อง {channel.mention}.",
        color=discord.Color.green()
    )
    await ctx.response.send_message(embed=embed, ephemeral=True)

    # Now, send a notification to the log channel that it has been set
    log_channel = bot.get_channel(channel.id)
    if log_channel:
        await log_channel.send("🚨 ตั้งค่าช่องนี้เป็นห้องสำหรับแจ้งเตือนการบันทึกเรียบร้อย!")
    else:
        await ctx.response.send_message("❌ ไม่พบช่อง", ephemeral=True)


@bot.tree.command(name="help", description="แสดงคำสั่งของบอท")
async def help(ctx: discord.Interaction):
    """ Command to show all available bot commands """
    embed = discord.Embed(
        title="คำสั่งบอท",
        description="นี้คือคำสั่งทั้งหมดของบอท",
        color=discord.Color.blue()
    )

    embed.add_field(name="/clear <จำนวน>", value="ลบข้อความตามจำนวนที่เลือก (ผู้ดูแลเท่านั้น)", inline=False)
    embed.add_field(name="/clear_all", value="ลบข้อความทั้งหมดในช่อง (ผู้ดูแลเท่านั้น)", inline=False)
    embed.add_field(name="/clear_user <ผู้ใช้>", value="ลบข้อความทั้งหมดจากผู้ใช้ (ผู้ดูแลเท่านั้น)", inline=False)
    embed.add_field(name="/add_admin <ผู้ใช้>", value="เพิ่มบทบาทผู้ดูแล (เจ้าของเท่านั้น)", inline=False)
    embed.add_field(name="/remove_admin <ผู้ใช้>", value="ลบบทบาทผู้ดูแล (เจ้าของเท่านั้น)", inline=False)
    embed.add_field(name="/admin_list", value="แสดงรายชื่อผู้ดูแลทั้งหมด", inline=False)
    embed.add_field(name="/log <ช่อง>", value="ตั้งค่าช่องสำหรับแจ้งเตือนการบันทึก (เจ้าของเท่านั้น)", inline=False)

    await ctx.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="Test", description="เทสเฉยๆ")
async def help(ctx: discord.Interaction):
    """ Command to show all available bot commands """
    embed = discord.Embed(
        title="คำสั่งบอท",
        description="นี้คือคำสั่งทั้งหมดของบอท",
        color=discord.Color.blue()
    )

    embed.add_field(name="/clear <จำนวน>", value="ลบข้อความตามจำนวนที่เลือก (ผู้ดูแลเท่านั้น)", inline=True)
    embed.add_field(name="/clear_all", value="ลบข้อความทั้งหมดในช่อง (ผู้ดูแลเท่านั้น)", inline=True)
    embed.add_field(name="/clear_user <ผู้ใช้>", value="ลบข้อความทั้งหมดจากผู้ใช้ (ผู้ดูแลเท่านั้น)", inline=True)
    embed.add_field(name="/add_admin <ผู้ใช้>", value="เพิ่มบทบาทผู้ดูแล (เจ้าของเท่านั้น)", inline=False)
    embed.add_field(name="/remove_admin <ผู้ใช้>", value="ลบบทบาทผู้ดูแล (เจ้าของเท่านั้น)", inline=False)
    embed.add_field(name="/admin_list", value="แสดงรายชื่อผู้ดูแลทั้งหมด", inline=False)
    embed.add_field(name="/log <ช่อง>", value="ตั้งค่าช่องสำหรับแจ้งเตือนการบันทึก (เจ้าของเท่านั้น)", inline=False)

    await ctx.response.send_message(embed=embed, ephemeral=False)

custom_messages = [
    "Kaida AntiSpam ready!💚",
    "Made by wasd.",
]

@tasks.loop(seconds=5)  # เปลี่ยนข้อความทุก 5 วินาที
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
    # รีเฟรชคำสั่งใหม่ให้กับ Discord API
    rotate_custom_activity.start()  # เริ่มหมุนข้อความ
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)
