import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import re
import random
import time
from datetime import datetime, timedelta

# =========================================================
# AYARLAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Render Environment Variables kısmına bunu eklersen
# slash komutları anında o sunucuda görünür.
# Örnek:
# TEST_GUILD_ID = 123456789012345678
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

DATA_FILE = "kyxor_data.json"

# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# =========================================================
# VERİLER
# =========================================================

data = {
    "warnings": {},
    "economy": {},
    "xp": {},
    "daily": {},
    "settings": {}
}

def load_data():
    global data

    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception as e:
        print("Veri yükleme hatası:", e)

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Veri kaydetme hatası:", e)

load_data()

# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

start_time = time.time()

spam_cache = {}
xp_cooldown = {}

def get_guild_data(guild_id):
    gid = str(guild_id)

    if gid not in data["settings"]:
        data["settings"][gid] = {
            "log_channel": 0,
            "welcome_channel": 0,
            "auto_role": 0,
            "ticket_category": 0
        }

    return data["settings"][gid]


def get_user_economy(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)

    if gid not in data["economy"]:
        data["economy"][gid] = {}

    if uid not in data["economy"][gid]:
        data["economy"][gid][uid] = {
            "balance": 0
        }

    return data["economy"][gid][uid]


def get_user_xp(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)

    if gid not in data["xp"]:
        data["xp"][gid] = {}

    if uid not in data["xp"][gid]:
        data["xp"][gid][uid] = {
            "xp": 0,
            "level": 1
        }

    return data["xp"][gid][uid]


async def send_log(guild, title, description, color=discord.Color.blue()):
    if guild is None:
        return

    settings = get_guild_data(guild.id)
    channel_id = settings.get("log_channel", 0)

    if not channel_id:
        return

    channel = guild.get_channel(channel_id)

    if channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


def level_required(level):
    return level * 100


# =========================================================
# BOT HAZIR
# =========================================================

@bot.event
async def on_ready():

    print("=" * 50)
    print(f"Kyxor Bot giriş yaptı: {bot.user}")
    print(f"Sunucu sayısı: {len(bot.guilds)}")
    print("=" * 50)

    # -----------------------------------------------------
    # SLASH KOMUT SYNC
    # -----------------------------------------------------

    try:

        if TEST_GUILD_ID:

            guild = discord.Object(id=TEST_GUILD_ID)

            bot.tree.copy_global_to(guild=guild)

            synced = await bot.tree.sync(guild=guild)

            print(
                f"TEST SUNUCUSU slash komutları senkronize edildi: "
                f"{len(synced)}"
            )

        else:

            synced = await bot.tree.sync()

            print(
                f"GLOBAL slash komutları senkronize edildi: "
                f"{len(synced)}"
            )

    except Exception as e:
        print("Slash komut sync hatası:", e)

    print("Bot hazır!")

# =========================================================
# HATA YAKALAMA
# =========================================================

@bot.tree.error
async def on_app_command_error(interaction, error):

    if isinstance(error, app_commands.MissingPermissions):

        text = "❌ Bu komutu kullanmak için yetkin yok."

    elif isinstance(error, app_commands.BotMissingPermissions):

        text = "❌ Botun bu işlem için gerekli yetkileri yok."

    else:

        print("COMMAND ERROR:", repr(error))

        text = "❌ Komut çalıştırılırken bir hata oluştu."

    try:

        if interaction.response.is_done():
            await interaction.followup.send(
                text,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                text,
                ephemeral=True
            )

    except Exception:
        pass


# =========================================================
# PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Botun ping değerini gösterir."
)
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    await interaction.response.send_message(
        f"🏓 Pong!\n"
        f"📡 Ping: **{latency}ms**"
    )


# =========================================================
# HELP
# =========================================================

@bot.tree.command(
    name="help",
    description="Botun komutlarını gösterir."
)
async def help_command(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🤖 Kyxor Bot",
        description="Kullanabileceğin komutlar:",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🛠️ Genel",
        value=(
            "`/ping`\n"
            "`/server`\n"
            "`/userinfo`\n"
            "`/avatar`\n"
            "`/uptime`"
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ Moderasyon",
        value=(
            "`/clear`\n"
            "`/warn`\n"
            "`/warnings`\n"
            "`/mute`\n"
            "`/unmute`\n"
            "`/kick`\n"
            "`/ban`\n"
            "`/unban`\n"
            "`/slowmode`\n"
            "`/lock`\n"
            "`/unlock`"
        ),
        inline=False
    )

    embed.add_field(
        name="💰 Ekonomi",
        value=(
            "`/balance`\n"
            "`/daily`\n"
            "`/work`\n"
            "`/give`\n"
            "`/leaderboard`\n"
            "`/profile`"
        ),
        inline=False
    )

    embed.add_field(
        name="🎫 Ticket",
        value="`/ticket-panel`",
        inline=False
    )

    embed.add_field(
        name="📢 Diğer",
        value=(
            "`/say`\n"
            "`/announce`\n"
            "`/social`"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# SERVER
# =========================================================

@bot.tree.command(
    name="server",
    description="Sunucu bilgilerini gösterir."
)
async def server(interaction: discord.Interaction):

    guild = interaction.guild

    if guild is None:
        return await interaction.response.send_message(
            "Bu komut sunucuda kullanılabilir."
        )

    embed = discord.Embed(
        title=f"📊 {guild.name}",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="👥 Üyeler",
        value=str(guild.member_count)
    )

    embed.add_field(
        name="💬 Kanallar",
        value=str(len(guild.channels))
    )

    embed.add_field(
        name="🎭 Roller",
        value=str(len(guild.roles))
    )

    embed.add_field(
        name="🆔 Sunucu ID",
        value=str(guild.id)
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# USERINFO
# =========================================================

@bot.tree.command(
    name="userinfo",
    description="Kullanıcı bilgilerini gösterir."
)
@app_commands.describe(member="Bilgilerini görmek istediğin kullanıcı")
async def userinfo(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    embed = discord.Embed(
        title=f"👤 {member}",
        color=member.color
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(
        name="🆔 ID",
        value=str(member.id),
        inline=False
    )

    embed.add_field(
        name="📅 Hesap oluşturma",
        value=discord.utils.format_dt(
            member.created_at,
            style="F"
        ),
        inline=False
    )

    if member.joined_at:
        embed.add_field(
            name="📥 Sunucuya katılma",
            value=discord.utils.format_dt(
                member.joined_at,
                style="F"
            ),
            inline=False
        )

    embed.add_field(
        name="🎭 Rol",
        value=member.top_role.mention,
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# AVATAR
# =========================================================

@bot.tree.command(
    name="avatar",
    description="Kullanıcının avatarını gösterir."
)
@app_commands.describe(member="Avatarını görmek istediğin kullanıcı")
async def avatar(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    embed = discord.Embed(
        title=f"🖼️ {member.display_name} Avatar",
        color=discord.Color.blurple()
    )

    embed.set_image(url=member.display_avatar.url)

    await interaction.response.send_message(embed=embed)


# =========================================================
# UPTIME
# =========================================================

@bot.tree.command(
    name="uptime",
    description="Botun ne kadar süredir açık olduğunu gösterir."
)
async def uptime(interaction: discord.Interaction):

    seconds = int(time.time() - start_time)

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    await interaction.response.send_message(
        f"⏱️ Bot çalışma süresi:\n"
        f"**{days} gün {hours} saat {minutes} dakika {seconds} saniye**"
    )


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(
    name="clear",
    description="Mesajları siler."
)
@app_commands.describe(amount="Silinecek mesaj sayısı")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):

    await interaction.response.defer(ephemeral=True)

    deleted = await interaction.channel.purge(
        limit=amount
    )

    await interaction.followup.send(
        f"🧹 **{len(deleted)}** mesaj silindi.",
        ephemeral=True
    )

    await send_log(
        interaction.guild,
        "🧹 Mesajlar Silindi",
        f"{interaction.user.mention} {len(deleted)} mesaj sildi.",
        discord.Color.orange()
    )


# =========================================================
# WARN
# =========================================================

@bot.tree.command(
    name="warn",
    description="Kullanıcıya uyarı verir."
)
@app_commands.describe(
    member="Uyarılacak kullanıcı",
    reason="Uyarı sebebi"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "Sebep belirtilmedi"
):

    gid = str(interaction.guild.id)
    uid = str(member.id)

    if gid not in data["warnings"]:
        data["warnings"][gid] = {}

    if uid not in data["warnings"][gid]:
        data["warnings"][gid][uid] = []

    data["warnings"][gid][uid].append({
        "reason": reason,
        "moderator": interaction.user.id,
        "time": datetime.utcnow().isoformat()
    })

    save_data()

    count = len(data["warnings"][gid][uid])

    await interaction.response.send_message(
        f"⚠️ {member.mention} uyarıldı.\n"
        f"Sebep: **{reason}**\n"
        f"Toplam uyarı: **{count}**"
    )

    await send_log(
        interaction.guild,
        "⚠️ Kullanıcı Uyarıldı",
        f"{member.mention}\n"
        f"Yetkili: {interaction.user.mention}\n"
        f"Sebep: {reason}",
        discord.Color.yellow()
    )


# =========================================================
# WARNINGS
# =========================================================

@bot.tree.command(
    name="warnings",
    description="Kullanıcının uyarılarını gösterir."
)
@app_commands.describe(member="Uyarılarını görmek istediğin kullanıcı")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(
    interaction: discord.Interaction,
    member: discord.Member
):

    gid = str(interaction.guild.id)
    uid = str(member.id)

    warnings_list = data["warnings"].get(
        gid,
        {}
    ).get(
        uid,
        []
    )

    if not warnings_list:

        return await interaction.response.send_message(
            f"✅ {member.mention} kullanıcısının uyarısı yok."
        )

    text = ""

    for i, warning in enumerate(
        warnings_list[-10:],
        1
    ):

        text += (
            f"**{i}.** "
            f"{warning['reason']}\n"
        )

    embed = discord.Embed(
        title=f"⚠️ {member} Uyarıları",
        description=text,
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# MUTE
# =========================================================

@bot.tree.command(
    name="mute",
    description="Kullanıcıyı susturur."
)
@app_commands.describe(
    member="Susturulacak kullanıcı",
    minutes="Kaç dakika susturulacak",
    reason="Sebep"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "Sebep belirtilmedi"
):

    if member == interaction.guild.owner:
        return await interaction.response.send_message(
            "❌ Sunucu sahibini susturamazsın.",
            ephemeral=True
        )

    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message(
            "❌ Bu kullanıcı seninle aynı veya daha yüksek role sahip.",
            ephemeral=True
        )

    try:

        await member.timeout(
            timedelta(minutes=minutes),
            reason=reason
        )

        await interaction.response.send_message(
            f"🔇 {member.mention} **{minutes} dakika** susturuldu.\n"
            f"Sebep: {reason}"
        )

        await send_log(
            interaction.guild,
            "🔇 Kullanıcı Susturuldu",
            f"{member.mention}\n"
            f"Yetkili: {interaction.user.mention}\n"
            f"Süre: {minutes} dakika\n"
            f"Sebep: {reason}",
            discord.Color.red()
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ İşlem başarısız: `{e}`",
            ephemeral=True
        )


# =========================================================
# UNMUTE
# =========================================================

@bot.tree.command(
    name="unmute",
    description="Kullanıcının susturmasını kaldırır."
)
@app_commands.describe(member="Susturması kaldırılacak kullanıcı")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(
    interaction: discord.Interaction,
    member: discord.Member
):

    try:

        await member.timeout(
            None,
            reason=f"Yetkili: {interaction.user}"
        )

        await interaction.response.send_message(
            f"🔊 {member.mention} artık susturulmuyor."
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ İşlem başarısız: `{e}`",
            ephemeral=True
        )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Kullanıcıyı sunucudan atar."
)
@app_commands.describe(
    member="Atılacak kullanıcı",
    reason="Sebep"
)
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "Sebep belirtilmedi"
):

    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message(
            "❌ Bu kullanıcı seninle aynı veya daha yüksek role sahip.",
            ephemeral=True
        )

    try:

        await member.kick(reason=reason)

        await interaction.response.send_message(
            f"👢 {member} sunucudan atıldı.\n"
            f"Sebep: **{reason}**"
        )

        await send_log(
            interaction.guild,
            "👢 Kullanıcı Atıldı",
            f"Kullanıcı: {member}\n"
            f"Yetkili: {interaction.user.mention}\n"
            f"Sebep: {reason}",
            discord.Color.red()
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Hata: `{e}`",
            ephemeral=True
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Kullanıcıyı yasaklar."
)
@app_commands.describe(
    member="Yasaklanacak kullanıcı",
    reason="Sebep"
)
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "Sebep belirtilmedi"
):

    if member == interaction.guild.owner:
        return await interaction.response.send_message(
            "❌ Sunucu sahibini yasaklayamazsın.",
            ephemeral=True
        )

    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message(
            "❌ Bu kullanıcı seninle aynı veya daha yüksek role sahip.",
            ephemeral=True
        )

    try:

        await member.ban(reason=reason)

        await interaction.response.send_message(
            f"🔨 {member} yasaklandı.\n"
            f"Sebep: **{reason}**"
        )

        await send_log(
            interaction.guild,
            "🔨 Kullanıcı Yasaklandı",
            f"Kullanıcı: {member}\n"
            f"Yetkili: {interaction.user.mention}\n"
            f"Sebep: {reason}",
            discord.Color.dark_red()
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Hata: `{e}`",
            ephemeral=True
        )


# =========================================================
# UNBAN
# =========================================================

@bot.tree.command(
    name="unban",
    description="Yasaklı kullanıcının banını kaldırır."
)
@app_commands.describe(user_id="Kullanıcının Discord ID'si")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(
    interaction: discord.Interaction,
    user_id: str
):

    try:

        user = await bot.fetch_user(int(user_id))

        await interaction.guild.unban(
            user,
            reason=f"Yetkili: {interaction.user}"
        )

        await interaction.response.send_message(
            f"🔓 **{user}** kullanıcısının banı kaldırıldı."
        )

    except ValueError:

        await interaction.response.send_message(
            "❌ Geçerli bir kullanıcı ID'si gir.",
            ephemeral=True
        )

    except discord.NotFound:

        await interaction.response.send_message(
            "❌ Bu kullanıcı banlı değil veya bulunamadı.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Hata: `{e}`",
            ephemeral=True
        )


# =========================================================
# SLOWMODE
# =========================================================

@bot.tree.command(
    name="slowmode",
    description="Kanalın yavaş modunu ayarlar."
)
@app_commands.describe(
    seconds="0-21600 saniye"
)
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(
    interaction: discord.Interaction,
    seconds: app_commands.Range[int, 0, 21600]
):

    await interaction.channel.edit(
        slowmode_delay=seconds
    )

    await interaction.response.send_message(
        f"🐢 Yavaş mod **{seconds} saniye** olarak ayarlandı."
    )


# =========================================================
# LOCK
# =========================================================

@bot.tree.command(
    name="lock",
    description="Kanalı kilitler."
)
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):

    channel = interaction.channel

    overwrite = channel.overwrites_for(
        interaction.guild.default_role
    )

    overwrite.send_messages = False

    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite
    )

    await interaction.response.send_message(
        "🔒 Kanal kilitlendi."
    )


# =========================================================
# UNLOCK
# =========================================================

@bot.tree.command(
    name="unlock",
    description="Kanalın kilidini açar."
)
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):

    channel = interaction.channel

    overwrite = channel.overwrites_for(
        interaction.guild.default_role
    )

    overwrite.send_messages = None

    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite
    )

    await interaction.response.send_message(
        "🔓 Kanalın kilidi açıldı."
    )


# =========================================================
# ECONOMY - BALANCE
# =========================================================

@bot.tree.command(
    name="balance",
    description="Bakiyeni gösterir."
)
@app_commands.describe(member="Bakiyesini görmek istediğin kullanıcı")
async def balance(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    account = get_user_economy(
        interaction.guild.id,
        member.id
    )

    await interaction.response.send_message(
        f"💰 {member.mention} bakiyesi: "
        f"**{account['balance']:,} KyxCoin**"
    )


# =========================================================
# DAILY
# =========================================================

@bot.tree.command(
    name="daily",
    description="Günlük ödülünü al."
)
async def daily(interaction: discord.Interaction):

    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)

    if gid not in data["daily"]:
        data["daily"][gid] = {}

    now = time.time()

    last = data["daily"][gid].get(uid, 0)

    if now - last < 86400:

        remaining = int(
            86400 - (now - last)
        )

        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        return await interaction.response.send_message(
            f"⏳ Günlük ödülünü zaten aldın.\n"
            f"**{hours} saat {minutes} dakika** sonra tekrar alabilirsin.",
            ephemeral=True
        )

    account = get_user_economy(
        interaction.guild.id,
        interaction.user.id
    )

    reward = random.randint(250, 750)

    account["balance"] += reward

    data["daily"][gid][uid] = now

    save_data()

    await interaction.response.send_message(
        f"🎁 Günlük ödülün: **{reward:,} KyxCoin**\n"
        f"💰 Yeni bakiye: **{account['balance']:,}**"
    )


# =========================================================
# WORK
# =========================================================

@bot.tree.command(
    name="work",
    description="Çalışarak para kazan."
)
async def work(interaction: discord.Interaction):

    account = get_user_economy(
        interaction.guild.id,
        interaction.user.id
    )

    reward = random.randint(50, 300)

    jobs = [
        "Discord geliştiricisi oldun 💻",
        "Sunucu yöneticiliği yaptın 🛡️",
        "Kod yazdın 👨‍💻",
        "Ticket çözdün 🎫",
        "Bot geliştirdin 🤖",
        "Sunucuyu düzenledin 🔧"
    ]

    job = random.choice(jobs)

    account["balance"] += reward

    save_data()

    await interaction.response.send_message(
        f"💼 {job}\n"
        f"💰 Kazanç: **{reward:,} KyxCoin**"
    )


# =========================================================
# GIVE
# =========================================================

@bot.tree.command(
    name="give",
    description="Başka bir kullanıcıya para gönder."
)
@app_commands.describe(
    member="Para gönderilecek kullanıcı",
    amount="Gönderilecek miktar"
)
async def give(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 1000000]
):

    if member.bot:
        return await interaction.response.send_message(
            "❌ Botlara para gönderemezsin.",
            ephemeral=True
        )

    sender = get_user_economy(
        interaction.guild.id,
        interaction.user.id
    )

    receiver = get_user_economy(
        interaction.guild.id,
        member.id
    )

    if sender["balance"] < amount:

        return await interaction.response.send_message(
            "❌ Yeterli paran yok.",
            ephemeral=True
        )

    sender["balance"] -= amount
    receiver["balance"] += amount

    save_data()

    await interaction.response.send_message(
        f"💸 {member.mention} kullanıcısına "
        f"**{amount:,} KyxCoin** gönderdin."
    )


# =========================================================
# LEADERBOARD
# =========================================================

@bot.tree.command(
    name="leaderboard",
    description="Ekonomi sıralamasını gösterir."
)
async def leaderboard(interaction: discord.Interaction):

    gid = str(interaction.guild.id)

    guild_data = data["economy"].get(
        gid,
        {}
    )

    if not guild_data:

        return await interaction.response.send_message(
            "📊 Henüz ekonomi verisi yok."
        )

    sorted_users = sorted(
        guild_data.items(),
        key=lambda x: x[1].get("balance", 0),
        reverse=True
    )

    text = ""

    for i, (uid, account) in enumerate(
        sorted_users[:10],
        1
    ):

        member = interaction.guild.get_member(
            int(uid)
        )

        name = member.display_name if member else f"ID {uid}"

        text += (
            f"**{i}.** {name} — "
            f"💰 {account.get('balance', 0):,}\n"
        )

    embed = discord.Embed(
        title="🏆 KyxCoin Liderlik Tablosu",
        description=text,
        color=discord.Color.gold()
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# XP / PROFILE
# =========================================================

@bot.tree.command(
    name="profile",
    description="XP ve seviye bilgini gösterir."
)
@app_commands.describe(member="Profilini görmek istediğin kullanıcı")
async def profile(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    member = member or interaction.user

    user = get_user_xp(
        interaction.guild.id,
        member.id
    )

    balance_data = get_user_economy(
        interaction.guild.id,
        member.id
    )

    level = user["level"]
    xp = user["xp"]

    required = level_required(level)

    embed = discord.Embed(
        title=f"👤 {member.display_name}",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="⭐ Level",
        value=str(level)
    )

    embed.add_field(
        name="✨ XP",
        value=f"{xp}/{required}"
    )

    embed.add_field(
        name="💰 KyxCoin",
        value=f"{balance_data['balance']:,}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# SAY
# =========================================================

@bot.tree.command(
    name="say",
    description="Botun yazı göndermesini sağlar."
)
@app_commands.describe(message="Gönderilecek mesaj")
@app_commands.checks.has_permissions(manage_messages=True)
async def say(
    interaction: discord.Interaction,
    message: str
):

    await interaction.response.send_message(
        "✅ Mesaj gönderildi.",
        ephemeral=True
    )

    await interaction.channel.send(message)


# =========================================================
# ANNOUNCE
# =========================================================

@bot.tree.command(
    name="announce",
    description="Duyuru gönderir."
)
@app_commands.describe(
    title="Duyuru başlığı",
    message="Duyuru mesajı"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def announce(
    interaction: discord.Interaction,
    title: str,
    message: str
):

    embed = discord.Embed(
        title=f"📢 {title}",
        description=message,
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )

    embed.set_footer(
        text=f"Kyxor Bot • {interaction.guild.name}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# SOCIAL
# =========================================================

@bot.tree.command(
    name="social",
    description="Sosyal medya bilgilerini gösterir."
)
async def social(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🌐 Kyxor Sosyal Medya",
        description=(
            "🔴 YouTube: Yakında\n"
            "🟣 Twitch: Yakında\n"
            "⚫ TikTok: Yakında\n"
            "📸 Instagram: Yakında"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# TICKET SİSTEMİ
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ticket Aç",
        style=discord.ButtonStyle.green,
        custom_id="kyxor_ticket_open"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        # Aynı kullanıcının açık ticketını kontrol et
        for channel in guild.text_channels:

            if channel.topic == f"ticket-owner:{interaction.user.id}":

                return await interaction.response.send_message(
                    f"❌ Zaten açık bir ticketın var: {channel.mention}",
                    ephemeral=True
                )

        settings = get_guild_data(guild.id)

        category = None

        category_id = settings.get(
            "ticket_category",
            0
        )

        if category_id:
            category = guild.get_channel(
                category_id
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )
        }

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower()[:90],
            category=category,
            overwrites=overwrites,
            topic=f"ticket-owner:{interaction.user.id}"
        )

        embed = discord.Embed(
            title="🎫 Ticket",
            description=(
                f"Merhaba {interaction.user.mention}!\n\n"
                "Yetkililer en kısa sürede seninle ilgilenecektir.\n"
                "Ticketı kapatmak için aşağıdaki butona bas."
            ),
            color=discord.Color.green()
        )

        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=CloseTicketView()
        )

        await interaction.response.send_message(
            f"✅ Ticket oluşturuldu: {channel.mention}",
            ephemeral=True
        )


class CloseTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Ticket Kapat",
        style=discord.ButtonStyle.red,
        custom_id="kyxor_ticket_close"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "🔒 Ticket 5 saniye içinde kapatılacak."
        )

        await asyncio.sleep(5)

        try:
            await interaction.channel.delete()
        except Exception:
            pass


# =========================================================
# TICKET PANEL
# =========================================================

@bot.tree.command(
    name="ticket-panel",
    description="Ticket paneli oluşturur."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🎫 Destek Sistemi",
        description=(
            "Destek almak için aşağıdaki "
            "**Ticket Aç** butonuna bas."
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        view=TicketView()
    )


# =========================================================
# XP SİSTEMİ + AUTOMOD
# =========================================================

LINK_REGEX = re.compile(
    r"https?://\S+",
    re.IGNORECASE
)

BAD_WORDS = [
    "discord.gg/",
    "nitro-free",
    "free-nitro"
]

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.guild is None:
        return

    # -----------------------------------------------------
    # XP
    # -----------------------------------------------------

    key = (
        message.guild.id,
        message.author.id
    )

    now = time.time()

    if now - xp_cooldown.get(key, 0) >= 60:

        xp_cooldown[key] = now

        user = get_user_xp(
            message.guild.id,
            message.author.id
        )

        gained = random.randint(10, 25)

        user["xp"] += gained

        required = level_required(
            user["level"]
        )

        if user["xp"] >= required:

            user["xp"] -= required

            user["level"] += 1

            try:

                await message.channel.send(
                    f"🎉 {message.author.mention} "
                    f"**Level {user['level']}** oldun!"
                )

            except Exception:
                pass

        save_data()

    # -----------------------------------------------------
    # AUTOMOD LINK
    # -----------------------------------------------------

    if LINK_REGEX.search(message.content):

        lowered = message.content.lower()

        allowed = (
            "youtube.com",
            "youtu.be",
            "github.com",
            "discord.com",
            "discordapp.com"
        )

        if not any(
            domain in lowered
            for domain in allowed
        ):

            try:

                await message.delete()

                await message.channel.send(
                    f"🚫 {message.author.mention} "
                    "izinsiz link gönderemezsin.",
                    delete_after=5
                )

                await send_log(
                    message.guild,
                    "🚫 Link Engellendi",
                    f"{message.author.mention} izinsiz link gönderdi.",
                    discord.Color.red()
                )

                return

            except Exception:
                pass

    # -----------------------------------------------------
    # BASİT SPAM KORUMASI
    # -----------------------------------------------------

    spam_key = (
        message.guild.id,
        message.author.id
    )

    timestamps = spam_cache.get(
        spam_key,
        []
    )

    timestamps = [
        t for t in timestamps
        if now - t < 5
    ]

    timestamps.append(now)

    spam_cache[spam_key] = timestamps

    if len(timestamps) >= 6:

        try:

            await message.delete()

            await message.author.timeout(
                timedelta(seconds=30),
                reason="Spam koruması"
            )

            await message.channel.send(
                f"🚨 {message.author.mention} "
                "spam nedeniyle 30 saniye susturuldu.",
                delete_after=5
            )

            spam_cache[spam_key] = []

        except Exception:
            pass

    await bot.process_commands(message)


# =========================================================
# WELCOME + AUTO ROLE
# =========================================================

@bot.event
async def on_member_join(member):

    settings = get_guild_data(
        member.guild.id
    )

    # Auto role
    role_id = settings.get(
        "auto_role",
        0
    )

    if role_id:

        role = member.guild.get_role(
            role_id
        )

        if role:

            try:
                await member.add_roles(role)
            except Exception:
                pass

    # Welcome
    channel_id = settings.get(
        "welcome_channel",
        0
    )

    if channel_id:

        channel = member.guild.get_channel(
            channel_id
        )

        if channel:

            embed = discord.Embed(
                title="👋 Hoş Geldin!",
                description=(
                    f"Hoş geldin {member.mention}!\n"
                    f"Sunucumuzda artık **{member.guild.member_count}** üyeyiz."
                ),
                color=discord.Color.green()
            )

            embed.set_thumbnail(
                url=member.display_avatar.url
            )

            try:
                await channel.send(
                    embed=embed
                )
            except Exception:
                pass


# =========================================================
# OTOMATİK KAYIT
# =========================================================

async def autosave_loop():

    while True:

        await asyncio.sleep(300)

        save_data()

        print("Veriler otomatik kaydedildi.")


# =========================================================
# BOT BAŞLAT
# =========================================================

async def start_background_tasks():

    bot.loop.create_task(
        autosave_loop()
    )


# =========================================================
# TOKEN
# =========================================================

if not BOT_TOKEN:

    print(
        "❌ BOT_TOKEN bulunamadı!"
    )

else:

    bot.run(BOT_TOKEN)
