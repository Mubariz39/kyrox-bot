import os
import json
import time
import asyncio
import random
import re
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks


# =========================================================
# KYXOR BOT - AYARLAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Discord kanal ID'lerini buraya yaz
LOG_CHANNEL_ID = 0
WELCOME_CHANNEL_ID = 0
NOTIFY_CHANNEL_ID = 0

# Yeni gelenlere verilecek rol
AUTO_ROLE_ID = 0

# Ticket kategorisi
TICKET_CATEGORY_ID = 0

# Ekonomi
DAILY_REWARD = 500
WORK_MIN_REWARD = 100
WORK_MAX_REWARD = 300

# XP
XP_MIN = 15
XP_MAX = 30
XP_COOLDOWN = 60

# Spam
SPAM_LIMIT = 5
SPAM_TIME = 6
SPAM_TIMEOUT_MINUTES = 2

# Link koruma
LINK_PROTECTION = True
BLOCK_DISCORD_INVITES = True

# Büyük harf koruma
CAPS_PROTECTION = True

# Küfür/kelime filtresi
BAD_WORDS = {
    "küfür",
    "siktir",
    "amk",
    "aq",
    "orospu",
    "piç",
    "salak",
    "aptal",
}

# İzin verilen link domainleri
ALLOWED_LINK_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "twitch.tv",
    "tiktok.com",
    "github.com",
    "discord.com",
}

# Seviye rollerini buradan ayarlayabilirsin
# Örnek:
# 5: 123456789012345678
# 10: 987654321098765432
LEVEL_ROLES = {
    5: 0,
    10: 0,
    20: 0,
}


# =========================================================
# DOSYA / VERİ SİSTEMİ
# =========================================================

DATA_FILE = "kyxor_data.json"

data = {
    "users": {},
    "warnings": {},
}


def load_data():
    global data

    if not os.path.exists(DATA_FILE):
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        if isinstance(loaded, dict):
            data.update(loaded)

    except Exception as e:
        print(f"Veri yükleme hatası: {e}")


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    except Exception as e:
        print(f"Veri kaydetme hatası: {e}")


load_data()


# =========================================================
# VERİ YARDIMCILARI
# =========================================================

def get_user_data(guild_id: int, user_id: int):
    guild_key = str(guild_id)
    user_key = str(user_id)

    if guild_key not in data["users"]:
        data["users"][guild_key] = {}

    if user_key not in data["users"][guild_key]:
        data["users"][guild_key][user_key] = {
            "coins": 0,
            "xp": 0,
            "level": 0,
            "last_daily": 0,
            "last_work": 0,
            "last_xp": 0,
        }

    return data["users"][guild_key][user_key]


def get_warnings(guild_id: int, user_id: int):
    guild_key = str(guild_id)
    user_key = str(user_id)

    if guild_key not in data["warnings"]:
        data["warnings"][guild_key] = {}

    if user_key not in data["warnings"][guild_key]:
        data["warnings"][guild_key][user_key] = []

    return data["warnings"][guild_key][user_key]


def xp_needed(level: int):
    return 100 + (level * 50)


def format_uptime(seconds: int):
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []

    if days:
        parts.append(f"{days}g")

    if hours:
        parts.append(f"{hours}s")

    if minutes:
        parts.append(f"{minutes}dk")

    parts.append(f"{seconds}sn")

    return " ".join(parts)


def get_log_channel(guild: discord.Guild):
    if not LOG_CHANNEL_ID:
        return None

    channel = guild.get_channel(LOG_CHANNEL_ID)

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


async def send_log(
    guild: discord.Guild,
    title: str,
    description: str,
    color: discord.Color = discord.Color.blurple(),
):
    channel = get_log_channel(guild)

    if channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"Log hatası: {e}")


def can_moderate(
    moderator: discord.Member,
    target: discord.Member,
):
    if moderator.id == target.id:
        return False, "Kendine işlem yapamazsın."

    if target.id == moderator.guild.owner_id:
        return False, "Sunucu sahibine işlem yapılamaz."

    if target.top_role >= moderator.top_role:
        return False, "Bu kişinin rolü seninkiyle aynı veya daha yüksek."

    return True, None


def has_mod_permission(member: discord.Member):
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or member.guild_permissions.manage_messages
    )


# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

start_time = time.time()

spam_tracker = {}
xp_cooldowns = {}


# =========================================================
# BOT BAŞLANGIÇ
# =========================================================

@bot.event
async def setup_hook():

    # Kalıcı ticket butonları
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())

    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} slash komutu senkronize edildi.")
    except Exception as e:
        print(f"Slash komut senkronizasyon hatası: {e}")

    autosave.start()


@bot.event
async def on_ready():

    print("================================")
    print("       KYXOR BOT ONLINE")
    print("================================")
    print(f"Bot: {bot.user}")
    print(f"ID: {bot.user.id}")
    print(f"Sunucu sayısı: {len(bot.guilds)}")
    print("Bot hazır!")


# =========================================================
# OTOMATİK KAYIT
# =========================================================

@tasks.loop(seconds=60)
async def autosave():
    save_data()


@autosave.before_loop
async def before_autosave():
    await bot.wait_until_ready()


# =========================================================
# ÜYE GİRİŞ / ÇIKIŞ
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):

    # Otomatik rol
    if AUTO_ROLE_ID:

        role = member.guild.get_role(AUTO_ROLE_ID)

        if role:
            try:
                await member.add_roles(
                    role,
                    reason="Kyxor Bot otomatik rol"
                )
            except Exception:
                pass

    # Hoş geldin mesajı
    channel = None

    if WELCOME_CHANNEL_ID:
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)

    if channel is None:
        channel = member.guild.system_channel

    if isinstance(channel, discord.TextChannel):

        embed = discord.Embed(
            title="👋 Hoş Geldin!",
            description=(
                f"**{member.mention}** sunucuya katıldı!\n\n"
                f"Sunucumuzda artık **{member.guild.member_count}** kişi var."
            ),
            color=discord.Color.green(),
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    await send_log(
        member.guild,
        "📥 Üye Katıldı",
        f"{member.mention} sunucuya katıldı.",
        discord.Color.green(),
    )


@bot.event
async def on_member_remove(member: discord.Member):

    await send_log(
        member.guild,
        "📤 Üye Ayrıldı",
        f"**{member}** sunucudan ayrıldı.",
        discord.Color.red(),
    )


# =========================================================
# MESAJ SİLME LOG
# =========================================================

@bot.event
async def on_message_delete(message: discord.Message):

    if not message.guild:
        return

    if message.author.bot:
        return

    content = message.content.strip()

    if not content:
        content = "(Mesaj içeriği yok)"

    if len(content) > 1000:
        content = content[:1000] + "..."

    await send_log(
        message.guild,
        "🗑️ Mesaj Silindi",
        (
            f"**Kullanıcı:** {message.author.mention}\n"
            f"**Kanal:** {message.channel.mention}\n"
            f"**Mesaj:** {content}"
        ),
        discord.Color.orange(),
    )


# =========================================================
# XP SİSTEMİ
# =========================================================

async def give_xp(message: discord.Message):

    if not message.guild:
        return

    if message.author.bot:
        return

    user_id = message.author.id
    guild_id = message.guild.id

    now = time.time()
    key = f"{guild_id}:{user_id}"

    last_xp = xp_cooldowns.get(key, 0)

    if now - last_xp < XP_COOLDOWN:
        return

    xp_cooldowns[key] = now

    user = get_user_data(guild_id, user_id)

    gained = random.randint(XP_MIN, XP_MAX)

    user["xp"] += gained

    leveled_up = False

    while user["xp"] >= xp_needed(user["level"]):
        user["xp"] -= xp_needed(user["level"])
        user["level"] += 1
        leveled_up = True

    if leveled_up:

        save_data()

        level = user["level"]

        embed = discord.Embed(
            title="🎉 Seviye Atladın!",
            description=(
                f"{message.author.mention}, tebrikler!\n\n"
                f"Yeni seviyen: **{level}** 🎯"
            ),
            color=discord.Color.gold(),
        )

        try:
            await message.channel.send(embed=embed)
        except Exception:
            pass

        # Level rolü
        role_id = LEVEL_ROLES.get(level, 0)

        if role_id:
            role = message.guild.get_role(role_id)

            if role:
                try:
                    await message.author.add_roles(
                        role,
                        reason=f"Seviye {level} rolü"
                    )
                except Exception:
                    pass

    # Her mesajda kaydetmek yerine XP değişikliklerini belli aralıklarla
    # kaydetmek için veri RAM'de tutuluyor.


# =========================================================
# OTOMOD
# =========================================================

def contains_bad_word(content: str):
    lowered = content.lower()

    for word in BAD_WORDS:
        if word.lower() in lowered:
            return True

    return False


def contains_link(content: str):
    pattern = r"(https?://[^\s]+|www\.[^\s]+|discord\.gg/[^\s]+|discord\.com/invite/[^\s]+)"
    return re.search(pattern, content, re.IGNORECASE)


def is_allowed_link(content: str):

    matches = re.findall(
        r"(?:https?://|www\.)([^/\s]+)",
        content,
        re.IGNORECASE,
    )

    if not matches:
        return True

    for domain in matches:

        domain = domain.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        allowed = False

        for allowed_domain in ALLOWED_LINK_DOMAINS:
            if domain == allowed_domain or domain.endswith("." + allowed_domain):
                allowed = True
                break

        if not allowed:
            return False

    return True


def is_caps_message(content: str):

    letters = [c for c in content if c.isalpha()]

    if len(letters) < 12:
        return False

    upper = sum(1 for c in letters if c.isupper())

    ratio = upper / len(letters)

    return ratio >= 0.75


async def handle_spam(message: discord.Message):

    if not message.guild:
        return False

    if message.author.bot:
        return False

    if has_mod_permission(message.author):
        return False

    guild_id = message.guild.id
    user_id = message.author.id

    key = f"{guild_id}:{user_id}"

    now = time.time()

    if key not in spam_tracker:
        spam_tracker[key] = []

    spam_tracker[key].append(now)

    spam_tracker[key] = [
        t for t in spam_tracker[key]
        if now - t <= SPAM_TIME
    ]

    if len(spam_tracker[key]) >= SPAM_LIMIT:

        spam_tracker[key] = []

        try:
            await message.delete()
        except Exception:
            pass

        try:
            await message.author.timeout(
                timedelta(minutes=SPAM_TIMEOUT_MINUTES),
                reason="Kyxor Bot spam koruması",
            )

            await send_log(
                message.guild,
                "🚨 Spam Engellendi",
                (
                    f"**Kullanıcı:** {message.author.mention}\n"
                    f"**Ceza:** {SPAM_TIMEOUT_MINUTES} dakika timeout"
                ),
                discord.Color.red(),
            )

        except discord.Forbidden:
            pass

        return True

    return False


@bot.event
async def on_message(message: discord.Message):

    if message.author.bot:
        return

    if message.guild:

        # Spam
        spam = await handle_spam(message)

        if spam:
            return

        # Kelime filtresi
        if contains_bad_word(message.content):

            if not has_mod_permission(message.author):

                try:
                    await message.delete()
                except Exception:
                    pass

                await send_log(
                    message.guild,
                    "🚨 Kelime Filtresi",
                    f"{message.author.mention} yasaklı bir kelime kullandı.",
                    discord.Color.red(),
                )

                return

        # Link filtresi
        if LINK_PROTECTION and contains_link(message.content):

            if not has_mod_permission(message.author):

                is_invite = bool(
                    re.search(
                        r"(discord\.gg/|discord\.com/invite/)",
                        message.content,
                        re.IGNORECASE,
                    )
                )

                blocked = False

                if is_invite and BLOCK_DISCORD_INVITES:
                    blocked = True

                elif not is_allowed_link(message.content):
                    blocked = True

                if blocked:

                    try:
                        await message.delete()
                    except Exception:
                        pass

                    await send_log(
                        message.guild,
                        "🔗 Link Engellendi",
                        f"{message.author.mention} engellenen bir link gönderdi.",
                        discord.Color.orange(),
                    )

                    return

        # Caps
        if CAPS_PROTECTION and is_caps_message(message.content):

            if not has_mod_permission(message.author):

                try:
                    await message.delete()
                except Exception:
                    pass

                return

        # XP
        await give_xp(message)

    await bot.process_commands(message)


# =========================================================
# PING
# =========================================================

@bot.tree.command(name="ping", description="Botun ping değerini gösterir.")
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    await interaction.response.send_message(
        f"🏓 Pong! **{latency}ms**"
    )


# =========================================================
# HELP
# =========================================================

@bot.tree.command(name="help", description="Kyxor Bot komutlarını gösterir.")
async def help_command(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🤖 Kyxor Bot",
        description="Kullanabileceğin komutlar:",
        color=discord.Color.blurple(),
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
        inline=True,
    )

    embed.add_field(
        name="💰 Ekonomi",
        value=(
            "`/balance`\n"
            "`/daily`\n"
            "`/work`\n"
            "`/give`\n"
            "`/leaderboard`"
        ),
        inline=True,
    )

    embed.add_field(
        name="🎯 Seviye",
        value=(
            "`/profile`\n"
            "`/leaderboard`"
        ),
        inline=True,
    )

    embed.add_field(
        name="🎫 Ticket",
        value="`/ticket-panel`",
        inline=True,
    )

    embed.add_field(
        name="📊 Bilgi",
        value=(
            "`/server`\n"
            "`/userinfo`\n"
            "`/avatar`\n"
            "`/uptime`"
        ),
        inline=True,
    )

    embed.add_field(
        name="📢 Diğer",
        value=(
            "`/say`\n"
            "`/announce`\n"
            "`/social`"
        ),
        inline=True,
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# SERVER
# =========================================================

@bot.tree.command(name="server", description="Sunucu bilgilerini gösterir.")
async def server(interaction: discord.Interaction):

    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "Bu komut sadece sunucuda kullanılabilir.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"📊 {guild.name}",
        color=discord.Color.blurple(),
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="👥 Üyeler",
        value=str(guild.member_count),
        inline=True,
    )

    embed.add_field(
        name="💬 Kanallar",
        value=str(len(guild.channels)),
        inline=True,
    )

    embed.add_field(
        name="🎭 Roller",
        value=str(len(guild.roles)),
        inline=True,
    )

    embed.add_field(
        name="👑 Sahip",
        value=guild.owner.mention if guild.owner else "Bilinmiyor",
        inline=True,
    )

    embed.add_field(
        name="🆔 Sunucu ID",
        value=str(guild.id),
        inline=True,
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# USERINFO
# =========================================================

@bot.tree.command(name="userinfo", description="Kullanıcı bilgilerini gösterir.")
@app_commands.describe(member="Bilgilerini görmek istediğin kişi.")
async def userinfo(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
):

    member = member or interaction.user

    embed = discord.Embed(
        title="👤 Kullanıcı Bilgisi",
        color=member.color,
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(
        name="Kullanıcı",
        value=member.mention,
        inline=True,
    )

    embed.add_field(
        name="ID",
        value=str(member.id),
        inline=True,
    )

    embed.add_field(
        name="Rol",
        value=member.top_role.mention,
        inline=True,
    )

    embed.add_field(
        name="Hesap",
        value=discord.utils.format_dt(member.created_at, "R"),
        inline=True,
    )

    if member.joined_at:
        embed.add_field(
            name="Sunucuya katılım",
            value=discord.utils.format_dt(member.joined_at, "R"),
            inline=True,
        )

    await interaction.response.send_message(embed=embed)


# =========================================================
# AVATAR
# =========================================================

@bot.tree.command(name="avatar", description="Kullanıcının avatarını gösterir.")
@app_commands.describe(member="Avatarını görmek istediğin kişi.")
async def avatar(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
):

    member = member or interaction.user

    embed = discord.Embed(
        title=f"🖼️ {member.display_name} Avatar",
        color=discord.Color.blurple(),
    )

    embed.set_image(url=member.display_avatar.url)

    await interaction.response.send_message(embed=embed)


# =========================================================
# UPTIME
# =========================================================

@bot.tree.command(name="uptime", description="Botun ne kadar süredir açık olduğunu gösterir.")
async def uptime(interaction: discord.Interaction):

    seconds = int(time.time() - start_time)

    await interaction.response.send_message(
        f"⏱️ Bot **{format_uptime(seconds)}** süredir açık."
    )


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(name="clear", description="Kanaldaki mesajları siler.")
@app_commands.describe(amount="Silinecek mesaj sayısı.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100],
):

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "Bu komut sadece yazı kanallarında kullanılabilir.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    deleted = await interaction.channel.purge(limit=amount)

    await interaction.followup.send(
        f"🗑️ **{len(deleted)}** mesaj silindi.",
        ephemeral=True,
    )

    await send_log(
        interaction.guild,
        "🗑️ Mesajlar Temizlendi",
        (
            f"{interaction.user.mention} "
            f"**{len(deleted)}** mesaj sildi."
        ),
        discord.Color.orange(),
    )


# =========================================================
# WARN
# =========================================================

@bot.tree.command(name="warn", description="Kullanıcıya uyarı verir.")
@app_commands.describe(
    member="Uyarılacak kişi.",
    reason="Uyarı sebebi.",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "Sebep belirtilmedi.",
):

    allowed, error = can_moderate(interaction.user, member)

    if not allowed:
        await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True,
        )
        return

    warnings = get_warnings(
        interaction.guild.id,
        member.id,
    )

    warnings.append({
        "moderator": interaction.user.id,
        "reason": reason,
        "time": int(time.time()),
    })

    save_data()

    await interaction.response.send_message(
        f"⚠️ {member.mention} uyarıldı.\n"
        f"**Sebep:** {reason}"
    )

    await send_log(
        interaction.guild,
        "⚠️ Uyarı",
        (
            f"**Yetkili:** {interaction.user.mention}\n"
            f"**Kullanıcı:** {member.mention}\n"
            f"**Sebep:** {reason}"
        ),
        discord.Color.orange(),
    )


# =========================================================
# WARNINGS
# =========================================================

@bot.tree.command(name="warnings", description="Kullanıcının uyarılarını gösterir.")
@app_commands.describe(member="Uyarılarına bakılacak kişi.")
@app_commands.checks.has_permissions(manage_messages=True)
async def warnings(
    interaction: discord.Interaction,
    member: discord.Member,
):

    warning_list = get_warnings(
        interaction.guild.id,
        member.id,
    )

    if not warning_list:
        await interaction.response.send_message(
            f"✅ {member.mention} hiç uyarı almamış.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title=f"⚠️ {member} Uyarıları",
        color=discord.Color.orange(),
    )

    for index, warning in enumerate(warning_list[-10:], start=1):

        moderator = interaction.guild.get_member(
            warning.get("moderator", 0)
        )

        moderator_text = (
            moderator.mention
            if moderator
            else "Bilinmeyen yetkili"
        )

        embed.add_field(
            name=f"Uyarı #{index}",
            value=(
                f"**Sebep:** {warning.get('reason', 'Belirtilmedi')}\n"
                f"**Yetkili:** {moderator_text}"
            ),
            inline=False,
        )

    embed.set_footer(
        text=f"Toplam uyarı: {len(warning_list)}"
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True,
    )


# =========================================================
# MUTE
# =========================================================

@bot.tree.command(name="mute", description="Kullanıcıya timeout verir.")
@app_commands.describe(
    member="Timeout verilecek kişi.",
    minutes="Dakika.",
    reason="Sebep.",
)
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "Sebep belirtilmedi.",
):

    allowed, error = can_moderate(interaction.user, member)

    if not allowed:
        await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True,
        )
        return

    try:

        await member.timeout(
            timedelta(minutes=minutes),
            reason=reason,
        )

        await interaction.response.send_message(
            f"🔇 {member.mention} **{minutes} dakika** susturuldu.\n"
            f"**Sebep:** {reason}"
        )

        await send_log(
            interaction.guild,
            "🔇 Timeout",
            (
                f"**Yetkili:** {interaction.user.mention}\n"
                f"**Kullanıcı:** {member.mention}\n"
                f"**Süre:** {minutes} dakika\n"
                f"**Sebep:** {reason}"
            ),
            discord.Color.red(),
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Bu kullanıcıya timeout veremiyorum.",
            ephemeral=True,
        )


# =========================================================
# UNMUTE
# =========================================================

@bot.tree.command(name="unmute", description="Timeout'u kaldırır.")
@app_commands.describe(member="Timeout'u kaldırılacak kişi.")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(
    interaction: discord.Interaction,
    member: discord.Member,
):

    try:

        await member.timeout(
            None,
            reason=f"Timeout kaldırıldı: {interaction.user}",
        )

        await interaction.response.send_message(
            f"🔊 {member.mention} artık susturulmuyor."
        )

        await send_log(
            interaction.guild,
            "🔊 Timeout Kaldırıldı",
            f"{interaction.user.mention}, {member.mention} kullanıcısının timeout'unu kaldırdı.",
            discord.Color.green(),
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Timeout kaldırılamadı.",
            ephemeral=True,
        )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(name="kick", description="Kullanıcıyı sunucudan atar.")
@app_commands.describe(
    member="Atılacak kişi.",
    reason="Sebep.",
)
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "Sebep belirtilmedi.",
):

    allowed, error = can_moderate(interaction.user, member)

    if not allowed:
        await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True,
        )
        return

    try:

        await member.kick(reason=reason)

        await interaction.response.send_message(
            f"👢 {member} sunucudan atıldı.\n"
            f"**Sebep:** {reason}"
        )

        await send_log(
            interaction.guild,
            "👢 Kick",
            (
                f"**Yetkili:** {interaction.user.mention}\n"
                f"**Kullanıcı:** {member}\n"
                f"**Sebep:** {reason}"
            ),
            discord.Color.red(),
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Bu kullanıcıyı atamıyorum. Bot rolünü kontrol et.",
            ephemeral=True,
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(name="ban", description="Kullanıcıyı yasaklar.")
@app_commands.describe(
    member="Yasaklanacak kişi.",
    reason="Sebep.",
)
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "Sebep belirtilmedi.",
):

    allowed, error = can_moderate(interaction.user, member)

    if not allowed:
        await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True,
        )
        return

    try:

        await member.ban(
            reason=reason,
            delete_message_days=1,
        )

        await interaction.response.send_message(
            f"🔨 {member} yasaklandı.\n"
            f"**Sebep:** {reason}"
        )

        await send_log(
            interaction.guild,
            "🔨 Ban",
            (
                f"**Yetkili:** {interaction.user.mention}\n"
                f"**Kullanıcı:** {member}\n"
                f"**Sebep:** {reason}"
            ),
            discord.Color.red(),
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Bu kullanıcıyı yasaklayamıyorum.",
            ephemeral=True,
        )


# =========================================================
# UNBAN
# =========================================================

@bot.tree.command(name="unban", description="Yasaklı kullanıcının banını kaldırır.")
@app_commands.describe(user_id="Kullanıcının Discord ID'si.")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(
    interaction: discord.Interaction,
    user_id: str,
):

    try:

        user = await bot.fetch_user(int(user_id))

        await interaction.guild.unban(
            user,
            reason=f"{interaction.user} tarafından unban",
        )

        await interaction.response.send_message(
            f"✅ **{user}** kullanıcısının banı kaldırıldı."
        )

        await send_log(
            interaction.guild,
            "🔓 Unban",
            f"{interaction.user.mention}, **{user}** kullanıcısının banını kaldırdı.",
            discord.Color.green(),
        )

    except ValueError:

        await interaction.response.send_message(
            "❌ Geçerli bir kullanıcı ID'si gir.",
            ephemeral=True,
        )

    except discord.NotFound:

        await interaction.response.send_message(
            "❌ Bu kullanıcı banlı değil veya bulunamadı.",
            ephemeral=True,
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Ban kaldırma yetkim yok.",
            ephemeral=True,
        )


# =========================================================
# SLOWMODE
# =========================================================

@bot.tree.command(name="slowmode", description="Kanal slowmode ayarlar.")
@app_commands.describe(seconds="0-21600 saniye.")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(
    interaction: discord.Interaction,
    seconds: app_commands.Range[int, 0, 21600],
):

    if not isinstance(interaction.channel, discord.TextChannel):

        await interaction.response.send_message(
            "❌ Bu kanal desteklenmiyor.",
            ephemeral=True,
        )
        return

    await interaction.channel.edit(
        slowmode_delay=seconds
    )

    await interaction.response.send_message(
        f"🐢 Slowmode **{seconds} saniye** olarak ayarlandı."
    )


# =========================================================
# LOCK / UNLOCK
# =========================================================

@bot.tree.command(name="lock", description="Kanalı kilitler.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "❌ Bu kanal desteklenmiyor.",
            ephemeral=True,
        )
        return

    overwrite = interaction.channel.overwrites_for(
        interaction.guild.default_role
    )

    overwrite.send_messages = False

    await interaction.channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
    )

    await interaction.response.send_message(
        "🔒 Kanal kilitlendi."
    )

    await send_log(
        interaction.guild,
        "🔒 Kanal Kilitlendi",
        f"{interaction.user.mention} kanalı kilitledi.",
        discord.Color.red(),
    )


@bot.tree.command(name="unlock", description="Kanalın kilidini açar.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "❌ Bu kanal desteklenmiyor.",
            ephemeral=True,
        )
        return

    overwrite = interaction.channel.overwrites_for(
        interaction.guild.default_role
    )

    overwrite.send_messages = None

    await interaction.channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
    )

    await interaction.response.send_message(
        "🔓 Kanalın kilidi açıldı."
    )

    await send_log(
        interaction.guild,
        "🔓 Kanal Açıldı",
        f"{interaction.user.mention} kanalın kilidini açtı.",
        discord.Color.green(),
    )


# =========================================================
# EKONOMİ - BALANCE
# =========================================================

@bot.tree.command(name="balance", description="Bakiyeni gösterir.")
@app_commands.describe(member="Bakiyesine bakılacak kişi.")
async def balance(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
):

    member = member or interaction.user

    user = get_user_data(
        interaction.guild.id,
        member.id,
    )

    embed = discord.Embed(
        title="💰 Bakiye",
        description=(
            f"{member.mention} hesabında "
            f"**{user['coins']:,} Kyxor Coin** var."
        ),
        color=discord.Color.gold(),
    )

    await interaction.response.send_message(embed=embed)


# =========================================================
# DAILY
# =========================================================

@bot.tree.command(name="daily", description="Günlük ödülünü al.")
async def daily(interaction: discord.Interaction):

    user = get_user_data(
        interaction.guild.id,
        interaction.user.id,
    )

    now = time.time()

    if now - user["last_daily"] < 86400:

        remaining = int(
            86400 - (now - user["last_daily"])
        )

        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        await interaction.response.send_message(
            f"⏳ Günlük ödülü zaten aldın.\n"
            f"Tekrar almak için yaklaşık **{hours}s {minutes}dk** bekle.",
            ephemeral=True,
        )

        return

    user["coins"] += DAILY_REWARD
    user["last_daily"] = now

    save_data()

    await interaction.response.send_message(
        f"🎁 Günlük ödülün: **+{DAILY_REWARD:,} coin**!\n"
        f"💰 Bakiyen: **{user['coins']:,} coin**"
    )


# =========================================================
# WORK
# =========================================================

@bot.tree.command(name="work", description="Çalışarak coin kazan.")
async def work(interaction: discord.Interaction):

    user = get_user_data(
        interaction.guild.id,
        interaction.user.id,
    )

    now = time.time()

    if now - user["last_work"] < 1800:

        remaining = int(
            1800 - (now - user["last_work"])
        )

        minutes = remaining // 60

        await interaction.response.send_message(
            f"⏳ Tekrar çalışmak için **{minutes} dakika** beklemelisin.",
            ephemeral=True,
        )

        return

    reward = random.randint(
        WORK_MIN_REWARD,
        WORK_MAX_REWARD,
    )

    user["coins"] += reward
    user["last_work"] = now

    save_data()

    jobs = [
        "💻 Yazılımcı olarak çalıştın.",
        "🍕 Restoranda çalıştın.",
        "🚚 Kuryelik yaptın.",
        "🎮 Oyun oynayarak para kazandın.",
        "🔧 Tamircilik yaptın.",
        "📦 Kargo taşıdın.",
    ]

    job = random.choice(jobs)

    await interaction.response.send_message(
        f"{job}\n"
        f"💰 Kazanç: **+{reward:,} coin**\n"
        f"💵 Yeni bakiye: **{user['coins']:,} coin**"
    )


# =========================================================
# GIVE
# =========================================================

@bot.tree.command(name="give", description="Başka kullanıcıya coin gönderir.")
@app_commands.describe(
    member="Coin gönderilecek kişi.",
    amount="Gönderilecek miktar.",
)
async def give(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 1000000],
):

    if member.id == interaction.user.id:

        await interaction.response.send_message(
            "❌ Kendine coin gönderemezsin.",
            ephemeral=True,
        )
        return

    sender = get_user_data(
        interaction.guild.id,
        interaction.user.id,
    )

    receiver = get_user_data(
        interaction.guild.id,
        member.id,
    )

    if sender["coins"] < amount:

        await interaction.response.send_message(
            "❌ Yeterli coinin yok.",
            ephemeral=True,
        )
        return

    sender["coins"] -= amount
    receiver["coins"] += amount

    save_data()

    await interaction.response.send_message(
        f"💸 {member.mention} kullanıcısına "
        f"**{amount:,} coin** gönderdin."
    )


# =========================================================
# LEADERBOARD
# =========================================================

@bot.tree.command(name="leaderboard", description="Ekonomi ve XP sıralamasını gösterir.")
async def leaderboard(interaction: discord.Interaction):

    guild_data = data["users"].get(
        str(interaction.guild.id),
        {},
    )

    if not guild_data:

        await interaction.response.send_message(
            "📊 Henüz sıralama verisi yok."
        )
        return

    entries = []

    for user_id, user_data in guild_data.items():

        try:
            uid = int(user_id)
        except ValueError:
            continue

        member = interaction.guild.get_member(uid)

        if member is None:
            continue

        entries.append(
            (
                member,
                user_data.get("coins", 0),
                user_data.get("level", 0),
                user_data.get("xp", 0),
            )
        )

    entries.sort(
        key=lambda x: (x[1], x[2], x[3]),
        reverse=True,
    )

    entries = entries[:10]

    embed = discord.Embed(
        title="🏆 Kyxor Leaderboard",
        color=discord.Color.gold(),
    )

    medals = [
        "🥇",
        "🥈",
        "🥉",
    ]

    for index, (member, coins, level, xp) in enumerate(entries):

        prefix = (
            medals[index]
            if index < 3
            else f"**{index + 1}.**"
        )

        embed.add_field(
            name=f"{prefix} {member.display_name}",
            value=(
                f"💰 {coins:,} coin\n"
                f"🎯 Seviye {level} • {xp} XP"
            ),
            inline=False,
        )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# PROFILE
# =========================================================

@bot.tree.command(name="profile", description="XP ve ekonomi profilini gösterir.")
@app_commands.describe(member="Profiline bakılacak kişi.")
async def profile(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
):

    member = member or interaction.user

    user = get_user_data(
        interaction.guild.id,
        member.id,
    )

    level = user["level"]
    xp = user["xp"]
    needed = xp_needed(level)

    embed = discord.Embed(
        title=f"🎯 {member.display_name} Profili",
        color=member.color,
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="🎯 Seviye",
        value=str(level),
        inline=True,
    )

    embed.add_field(
        name="⭐ XP",
        value=f"{xp}/{needed}",
        inline=True,
    )

    embed.add_field(
        name="💰 Coin",
        value=f"{user['coins']:,}",
        inline=True,
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# SAY
# =========================================================

@bot.tree.command(name="say", description="Botun mesaj göndermesini sağlar.")
@app_commands.describe(message="Gönderilecek mesaj.")
@app_commands.checks.has_permissions(manage_messages=True)
async def say(
    interaction: discord.Interaction,
    message: str,
):

    await interaction.response.send_message(
        "✅ Mesaj gönderildi.",
        ephemeral=True,
    )

    await interaction.channel.send(message)


# =========================================================
# ANNOUNCE
# =========================================================

@bot.tree.command(name="announce", description="Embed duyuru gönderir.")
@app_commands.describe(
    title="Duyuru başlığı.",
    message="Duyuru mesajı.",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def announce(
    interaction: discord.Interaction,
    title: str,
    message: str,
):

    embed = discord.Embed(
        title=f"📢 {title}",
        description=message,
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )

    embed.set_footer(
        text=f"Duyuru • {interaction.guild.name}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# SOCIAL
# =========================================================

@bot.tree.command(name="social", description="Sosyal medya bağlantılarını gösterir.")
async def social(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🌐 Kyxor Sosyal Medya",
        description=(
            "Aşağıdaki alanları kendi hesaplarınla değiştirebilirsin."
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="🎵 TikTok",
        value="TikTok bağlantını buraya ekle.",
        inline=False,
    )

    embed.add_field(
        name="🎥 YouTube",
        value="YouTube bağlantını buraya ekle.",
        inline=False,
    )

    embed.add_field(
        name="🎮 Twitch",
        value="Twitch bağlantını buraya ekle.",
        inline=False,
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# TICKET
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ticket Aç",
        style=discord.ButtonStyle.green,
        custom_id="kyxor_ticket_open",
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        guild = interaction.guild

        if guild is None:
            return

        # Zaten ticket var mı?
        existing = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{interaction.user.id}",
        )

        if existing:

            await interaction.response.send_message(
                f"❌ Zaten açık ticketın var: {existing.mention}",
                ephemeral=True,
            )
            return

        category = None

        if TICKET_CATEGORY_ID:
            category = guild.get_channel(
                TICKET_CATEGORY_ID
            )

        if category is not None and not isinstance(
            category,
            discord.CategoryChannel,
        ):
            category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),

            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
        }

        # Yetkili rolleri
        for role in guild.roles:

            if role.permissions.manage_channels or role.permissions.manage_guild:

                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                )

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            )

        try:

            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.id}",
                category=category,
                overwrites=overwrites,
                reason="Kyxor Ticket",
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ Kanal oluşturma yetkim yok.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎫 Ticket",
            description=(
                f"Merhaba {interaction.user.mention}!\n\n"
                "Yetkili ekip birazdan seninle ilgilenecek.\n"
                "Ticketı kapatmak için aşağıdaki butona basabilirsin."
            ),
            color=discord.Color.green(),
        )

        embed.set_footer(
            text=f"Ticket sahibi: {interaction.user}"
        )

        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=CloseTicketView(),
        )

        await interaction.response.send_message(
            f"✅ Ticket oluşturuldu: {channel.mention}",
            ephemeral=True,
        )

        await send_log(
            guild,
            "🎫 Ticket Açıldı",
            (
                f"**Kullanıcı:** {interaction.user.mention}\n"
                f"**Kanal:** {channel.mention}"
            ),
            discord.Color.green(),
        )


class CloseTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Ticket Kapat",
        style=discord.ButtonStyle.red,
        custom_id="kyxor_ticket_close",
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel,
        ):

            await interaction.response.send_message(
                "❌ Bu kanal ticket değil.",
                ephemeral=True,
            )
            return

        if not channel.name.startswith("ticket-"):

            await interaction.response.send_message(
                "❌ Bu kanal ticket değil.",
                ephemeral=True,
            )
            return

        is_owner = False

        try:

            owner_id = int(
                channel.name.replace(
                    "ticket-",
                    "",
                    1,
                )
            )

            is_owner = (
                interaction.user.id == owner_id
            )

        except ValueError:
            pass

        if not is_owner and not has_mod_permission(
            interaction.user
        ):

            await interaction.response.send_message(
                "❌ Bu ticketı kapatma yetkin yok.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "🔒 Ticket 5 saniye içinde kapatılacak."
        )

        await send_log(
            interaction.guild,
            "🔒 Ticket Kapatıldı",
            (
                f"**Kanal:** {channel.name}\n"
                f"**Kapatan:** {interaction.user.mention}"
            ),
            discord.Color.red(),
        )

        await asyncio.sleep(5)

        try:
            await channel.delete(
                reason=f"Ticket kapatıldı: {interaction.user}"
            )
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass


# =========================================================
# TICKET PANEL
# =========================================================

@bot.tree.command(
    name="ticket-panel",
    description="Ticket paneli gönderir."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(
    interaction: discord.Interaction,
):

    embed = discord.Embed(
        title="🎫 Destek Merkezi",
        description=(
            "Destek almak için aşağıdaki **Ticket Aç** "
            "butonuna bas.\n\n"
            "Yetkili ekibimiz seninle ilgilenecektir."
        ),
        color=discord.Color.blurple(),
    )

    embed.set_footer(
        text="Kyxor Bot • Destek Sistemi"
    )

    await interaction.channel.send(
        embed=embed,
        view=TicketView(),
    )

    await interaction.response.send_message(
        "✅ Ticket paneli gönderildi.",
        ephemeral=True,
    )


# =========================================================
# HATA YÖNETİMİ
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions,
    ):

        message = "❌ Bu komutu kullanmak için gerekli yetkin yok."

    elif isinstance(
        error,
        app_commands.errors.BotMissingPermissions,
    ):

        message = "❌ Botun gerekli yetkisi yok."

    elif isinstance(
        error,
        app_commands.errors.CommandOnCooldown,
    ):

        message = "⏳ Bu komutu tekrar kullanmadan önce beklemelisin."

    else:

        print(f"Komut hatası: {error}")

        message = (
            "❌ Komut çalışırken bir hata oluştu.\n"
            "Konsolu kontrol et."
        )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True,
            )

        else:

            await interaction.response.send_message(
                message,
                ephemeral=True,
            )

    except Exception:
        pass


# =========================================================
# TOKEN KONTROLÜ
# =========================================================

if not BOT_TOKEN:

    print("================================")
    print("❌ BOT_TOKEN BULUNAMADI")
    print("================================")
    print("Hosting/Secrets bölümüne BOT_TOKEN ekle.")

else:

    print("Kyxor Bot başlatılıyor...")
    bot.run(BOT_TOKEN)
