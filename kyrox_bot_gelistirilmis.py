import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import time
import asyncio
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

# =========================================================
# AYARLAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

DATA_FILE = "kyxor_data.json"

# XP ayarları
XP_PER_MESSAGE = 5
XP_COOLDOWN = 30

# Anti-spam
SPAM_MESSAGE_LIMIT = 6
SPAM_WINDOW = 8
SPAM_TIMEOUT_MINUTES = 5

# Ticket
TICKET_CATEGORY_NAME = "Tickets"

# Premium mevcut rol üzerinden çalışır.
PREMIUM_ROLE_NAME = "Premium"

# Filtre
BAD_WORDS = {
    "küfür1",
    "küfür2",
    "küfür3",
}

# =========================================================
# RANKLAR
# =========================================================
  RANKS=[
    ("Yeni Uye", 0),
    ("Aktif Uye", 3 * 24 * 60 * 60),
    ("Sohbetçi", 7 * 24 * 60 * 60),
    ("Tecrubeli", 14 * 24 * 60 * 60),
    ("Kıdemli", 30 * 24 * 60 * 60),
    ("Usta", 60 * 24 * 60 * 60),
    ("Elit", 120 * 24 * 60 * 60),
    ("Efsane", 240 * 24 * 60 * 60),
    ("Şampiyon", 365 * 24 * 60 * 60),
    ("Kyrox Efsanesi", 730 * 24 * 60 * 60),
]
# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# =========================================================
# VERİ
# =========================================================

data = {
    "users": {},
    "guilds": {}
}

message_cooldowns = {}
spam_tracker = defaultdict(lambda: deque(maxlen=SPAM_MESSAGE_LIMIT))

# =========================================================
# DATA
# =========================================================

def load_data():
    global data

    if not os.path.exists(DATA_FILE):
        save_data()
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "users" not in data:
            data["users"] = {}

        if "guilds" not in data:
            data["guilds"] = {}

    except Exception as e:
        print("❌ Veri yükleme hatası:", e)
        data = {
            "users": {},
            "guilds": {}
        }


def save_data():
    try:
        temp_file = DATA_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=4
            )

        os.replace(temp_file, DATA_FILE)

    except Exception as e:
        print("❌ Veri kaydetme hatası:", e)


# =========================================================
# USER DATA
# =========================================================

def get_user_data(user_id):
    user_id = str(user_id)

    if user_id not in data["users"]:
        data["users"][user_id] = {
            "online_seconds": 0,
            "rank": 1,
            "xp": 0,
            "level": 1,
            "messages": 0,
            "achievements": [],
            "streak": 0,
            "last_message": 0,
            "last_active_day": "",
            "afk": False,
            "afk_reason": "",
        }

    user = data["users"][user_id]

    defaults = {
        "online_seconds": 0,
        "rank": 1,
        "xp": 0,
        "level": 1,
        "messages": 0,
        "achievements": [],
        "streak": 0,
        "last_message": 0,
        "last_active_day": "",
        "afk": False,
        "afk_reason": "",
    }

    for key, value in defaults.items():
        if key not in user:
            user[key] = value

    return user


def get_guild_data(guild_id):
    guild_id = str(guild_id)

    if guild_id not in data["guilds"]:
        data["guilds"][guild_id] = {
            "log_channel": 0,
            "welcome_channel": 0,
            "welcome_message": "Hoş geldin {member}! 🎉",
            "leave_channel": 0,
            "filter_enabled": True,
            "antispam_enabled": True,
        }

    guild = data["guilds"][guild_id]

    defaults = {
        "log_channel": 0,
        "welcome_channel": 0,
        "welcome_message": "Hoş geldin {member}! 🎉",
        "leave_channel": 0,
        "filter_enabled": True,
        "antispam_enabled": True,
    }

    for key, value in defaults.items():
        if key not in guild:
            guild[key] = value

    return guild


# =========================================================
# RANK
# =========================================================

def get_rank_from_seconds(seconds):
    current_rank = 1

    for index, (_, required_seconds) in enumerate(RANKS, start=1):
        if seconds >= required_seconds:
            current_rank = index

    return current_rank


def get_rank_name(rank):
    rank = max(1, min(rank, len(RANKS)))
    return RANKS[rank - 1][0]


def get_next_rank_time(rank):
    if rank >= len(RANKS):
        return None

    return RANKS[rank][1]


def format_time(seconds):
    seconds = int(seconds)

    days = seconds // 86400
    seconds %= 86400

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60

    parts = []

    if days:
        parts.append(f"{days} gün")

    if hours:
        parts.append(f"{hours} saat")

    if minutes:
        parts.append(f"{minutes} dakika")

    if not parts:
        parts.append("0 dakika")

    return " ".join(parts)


def get_role(guild, role_name):
    return discord.utils.get(
        guild.roles,
        name=role_name
    )


async def set_member_rank(member, rank):
    if member.bot:
        return

    target_role_name = get_rank_name(rank)
    target_role = get_role(
        member.guild,
        target_role_name
    )

    if target_role is None:
        print(
            f"⚠️ Rol bulunamadı: "
            f"{target_role_name} | "
            f"{member.guild.name}"
        )
        return

    rank_roles = []

    for role_name, _ in RANKS:
        role = get_role(
            member.guild,
            role_name
        )

        if role:
            rank_roles.append(role)

    old_roles = []

    for role in rank_roles:
        if role in member.roles:
            if role.id != target_role.id:
                old_roles.append(role)

    try:
        if old_roles:
            await member.remove_roles(
                *old_roles,
                reason="Kyrox otomatik rank sistemi"
            )

        if target_role not in member.roles:
            await member.add_roles(
                target_role,
                reason="Kyrox otomatik rank sistemi"
            )

            print(
                f"⬆️ RANK: {member} -> "
                f"{target_role_name}"
            )

    except discord.Forbidden:
        print(
            f"❌ {member} için "
            f"{target_role_name} verilemedi."
        )

    except Exception as e:
        print("❌ Rank hatası:", e)


# =========================================================
# XP / LEVEL
# =========================================================

def xp_required(level):
    return 100 + ((level - 1) * 50)


def add_xp(user, amount):
    old_level = user["level"]

    user["xp"] += amount

    levels_gained = 0

    while user["xp"] >= xp_required(user["level"]):
        user["xp"] -= xp_required(user["level"])
        user["level"] += 1
        levels_gained += 1

    return old_level, user["level"], levels_gained


def level_progress(user):
    required = xp_required(user["level"])

    if required <= 0:
        return 100

    return min(
        100,
        int((user["xp"] / required) * 100)
    )


# =========================================================
# BAŞARIMLAR
# =========================================================

ACHIEVEMENTS = {
    "first_message": {
        "name": "İlk Mesaj",
        "description": "İlk mesajını gönder.",
        "icon": "💬"
    },
    "100_messages": {
        "name": "Sohbetçi",
        "description": "100 mesaj gönder.",
        "icon": "🗣️"
    },
    "500_messages": {
        "name": "Aktif Sohbetçi",
        "description": "500 mesaj gönder.",
        "icon": "🔥"
    },
    "1000_messages": {
        "name": "Sohbet Ustası",
        "description": "1000 mesaj gönder.",
        "icon": "👑"
    },
    "level_5": {
        "name": "Seviye 5",
        "description": "5. seviyeye ulaş.",
        "icon": "⭐"
    },
    "level_10": {
        "name": "Seviye 10",
        "description": "10. seviyeye ulaş.",
        "icon": "💎"
    },
    "level_25": {
        "name": "Seviye 25",
        "description": "25. seviyeye ulaş.",
        "icon": "🏆"
    },
    "streak_3": {
        "name": "3 Günlük Seri",
        "description": "3 günlük aktivite serisi yap.",
        "icon": "🔥"
    },
    "streak_7": {
        "name": "7 Günlük Seri",
        "description": "7 günlük aktivite serisi yap.",
        "icon": "⚡"
    },
}


def check_achievements(user):
    unlocked = []

    def unlock(key):
        if key not in user["achievements"]:
            user["achievements"].append(key)
            unlocked.append(key)

    if user["messages"] >= 1:
        unlock("first_message")

    if user["messages"] >= 100:
        unlock("100_messages")

    if user["messages"] >= 500:
        unlock("500_messages")

    if user["messages"] >= 1000:
        unlock("1000_messages")

    if user["level"] >= 5:
        unlock("level_5")

    if user["level"] >= 10:
        unlock("level_10")

    if user["level"] >= 25:
        unlock("level_25")

    if user["streak"] >= 3:
        unlock("streak_3")

    if user["streak"] >= 7:
        unlock("streak_7")

    return unlocked


# =========================================================
# STREAK
# =========================================================

def update_streak(user):
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    last_day = user.get("last_active_day", "")

    if last_day == today_str:
        return False

    if last_day:
        try:
            previous = datetime.strptime(
                last_day,
                "%Y-%m-%d"
            ).date()

            difference = (today - previous).days

            if difference == 1:
                user["streak"] += 1

            elif difference > 1:
                user["streak"] = 1

        except Exception:
            user["streak"] = 1
    else:
        user["streak"] = 1

    user["last_active_day"] = today_str

    return True


# =========================================================
# LOG
# =========================================================

async def send_log(
    guild,
    title,
    description,
    color=discord.Color.blurple()
):
    guild_data = get_guild_data(guild.id)

    channel_id = guild_data.get(
        "log_channel",
        0
    )

    if not channel_id:
        return

    channel = guild.get_channel(channel_id)

    if channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# =========================================================
# WELCOME
# =========================================================

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    user = get_user_data(member.id)

    user["rank"] = 1

    role = get_role(
        member.guild,
        "Yeni Üye"
    )

    if role:
        try:
            await member.add_roles(
                role,
                reason="Yeni üye"
            )
        except discord.Forbidden:
            print("❌ Yeni Üye rolü verilemedi.")

    guild_data = get_guild_data(
        member.guild.id
    )

    channel_id = guild_data.get(
        "welcome_channel",
        0
    )

    channel = member.guild.get_channel(
        channel_id
    )

    if channel:
        message = guild_data.get(
            "welcome_message",
            "Hoş geldin {member}! 🎉"
        )

        message = message.replace(
            "{member}",
            member.mention
        )

        message = message.replace(
            "{server}",
            member.guild.name
        )

        message = message.replace(
            "{count}",
            str(member.guild.member_count)
        )

        try:
            await channel.send(message)
        except Exception:
            pass

    await send_log(
        member.guild,
        "👋 Üye Katıldı",
        f"{member.mention} sunucuya katıldı.",
        discord.Color.green()
    )

    save_data()


@bot.event
async def on_member_remove(member):
    await send_log(
        member.guild,
        "📤 Üye Ayrıldı",
        f"**{member}** sunucudan ayrıldı.",
        discord.Color.red()
    )

    save_data()


# =========================================================
# ONLINE TRACKER
# =========================================================

@tasks.loop(minutes=1)
async def online_tracker():
    changed = False

    for guild in bot.guilds:
        for member in guild.members:

            if member.bot:
                continue

            if member.status == discord.Status.offline:
                continue

            user = get_user_data(member.id)

            user["online_seconds"] += 60

            old_rank = user.get(
                "rank",
                1
            )

            new_rank = get_rank_from_seconds(
                user["online_seconds"]
            )

            if new_rank != old_rank:
                user["rank"] = new_rank

                await set_member_rank(
                    member,
                    new_rank
                )

                print(
                    f"🏆 {member} Rank "
                    f"{new_rank}: "
                    f"{get_rank_name(new_rank)}"
                )

            changed = True

    if changed:
        save_data()


@online_tracker.before_loop
async def before_online_tracker():
    await bot.wait_until_ready()


# =========================================================
# MESAJ XP / AFK / SPAM / FİLTRE
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.guild is None:
        await bot.process_commands(message)
        return

    user = get_user_data(
        message.author.id
    )

    guild_data = get_guild_data(
        message.guild.id
    )

    # AFK'dan çıkış
    if user.get("afk"):
        user["afk"] = False
        user["afk_reason"] = ""

        try:
            await message.channel.send(
                f"👋 {message.author.mention}, "
                f"AFK durumundan çıktın."
            )
        except Exception:
            pass

    # Başkasının AFK'sını göster
    for mentioned in message.mentions:

        if mentioned.bot:
            continue

        mentioned_data = get_user_data(
            mentioned.id
        )

        if mentioned_data.get("afk"):
            reason = mentioned_data.get(
                "afk_reason",
                ""
            )

            text = (
                f"💤 {mentioned.mention} şu anda AFK."
            )

            if reason:
                text += f"\n📝 Sebep: {reason}"

            try:
                await message.channel.send(
                    text,
                    delete_after=8
                )
            except Exception:
                pass

    # Kelime filtresi
    if guild_data.get(
        "filter_enabled",
        True
    ):

        content_lower = message.content.lower()

        found_word = None

        for word in BAD_WORDS:
            if word and word.lower() in content_lower:
                found_word = word
                break

        if found_word:

            try:
                await message.delete()
            except Exception:
                pass

            try:
                await message.channel.send(
                    f"🚫 {message.author.mention}, "
                    f"bu mesaj filtrelendi.",
                    delete_after=5
                )
            except Exception:
                pass

            await send_log(
                message.guild,
                "🚫 Kelime Filtresi",
                f"{message.author.mention} tarafından "
                f"filtrelenen mesaj.",
                discord.Color.red()
            )

            await bot.process_commands(message)
            return

    # Anti spam
    if guild_data.get(
        "antispam_enabled",
        True
    ):

        now = time.time()

        key = (
            message.guild.id,
            message.author.id
        )

        tracker = spam_tracker[key]

        tracker.append(now)

        if len(tracker) >= SPAM_MESSAGE_LIMIT:

            if now - tracker[0] <= SPAM_WINDOW:

                try:
                    await message.author.timeout(
                        timedelta(
                            minutes=SPAM_TIMEOUT_MINUTES
                        ),
                        reason="Kyrox Anti-Spam"
                    )

                    await message.channel.send(
                        f"🛡️ {message.author.mention} "
                        f"spam nedeniyle "
                        f"{SPAM_TIMEOUT_MINUTES} dakika susturuldu.",
                        delete_after=8
                    )

                    await send_log(
                        message.guild,
                        "🛡️ Anti-Spam",
                        f"{message.author.mention} "
                        f"spam nedeniyle timeout aldı.",
                        discord.Color.orange()
                    )

                except discord.Forbidden:
                    pass

                tracker.clear()

    # XP cooldown
    now = time.time()

    cooldown_key = (
        message.guild.id,
        message.author.id
    )

    last_xp = message_cooldowns.get(
        cooldown_key,
        0
    )

    if now - last_xp >= XP_COOLDOWN:

        message_cooldowns[cooldown_key] = now

        user["messages"] += 1

        update_streak(user)

        old_level, new_level, levels_gained = add_xp(
            user,
            XP_PER_MESSAGE
        )

        achievements = check_achievements(
            user
        )

        if levels_gained > 0:

            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} "
                    f"**Level {new_level}** oldun!",
                    delete_after=8
                )
            except Exception:
                pass

        if achievements:

            for achievement in achievements:

                info = ACHIEVEMENTS.get(
                    achievement
                )

                if info:
                    try:
                        await message.channel.send(
                            f"{info['icon']} "
                            f"{message.author.mention} "
                            f"**Yeni başarım:** "
                            f"{info['name']}",
                            delete_after=10
                        )
                    except Exception:
                        pass

        save_data()

    await bot.process_commands(message)


# =========================================================
# RANK
# =========================================================

@bot.tree.command(
    name="rank",
    description="Rankını ve online süreni gösterir."
)
async def rank_command(
    interaction: discord.Interaction
):

    member = interaction.user

    user = get_user_data(
        member.id
    )

    seconds = user["online_seconds"]

    rank = get_rank_from_seconds(
        seconds
    )

    rank_name = get_rank_name(
        rank
    )

    if rank < len(RANKS):

        next_rank = rank + 1

        next_name = get_rank_name(
            next_rank
        )

        required = get_next_rank_time(
            rank
        )

        remaining = max(
            0,
            required - seconds
        )

        next_text = (
            f"**{next_name}** için "
            f"`{format_time(remaining)}` kaldı."
        )

    else:
        next_text = (
            "🏆 **Maksimum ranka ulaştın!**"
        )

    embed = discord.Embed(
        title="🏆 Kyrox Rank",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="👤 Üye",
        value=member.mention,
        inline=False
    )

    embed.add_field(
        name="🎖️ Rank",
        value=f"**{rank}/10**",
        inline=True
    )

    embed.add_field(
        name="🏷️ Rol",
        value=f"**{rank_name}**",
        inline=True
    )

    embed.add_field(
        name="🕐 Online Süre",
        value=f"`{format_time(seconds)}`",
        inline=False
    )

    embed.add_field(
        name="📈 Sonraki Rank",
        value=next_text,
        inline=False
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# RANKLAR
# =========================================================

@bot.tree.command(
    name="ranklar",
    description="Tüm rankları gösterir."
)
async def ranklar_command(
    interaction: discord.Interaction
):

    text = ""

    for index, (name, seconds) in enumerate(
        RANKS,
        start=1
    ):

        if seconds == 0:
            time_text = "Sunucuya giriş"
        else:
            time_text = format_time(
                seconds
            )

        text += (
            f"**{index}. {name}** — "
            f"`{time_text}`\n"
        )

    embed = discord.Embed(
        title="🏆 Kyrox Rank Sistemi",
        description=text,
        color=discord.Color.gold()
    )

    embed.set_footer(
        text="Sadece çevrim içi olduğun süre sayılır."
    )

    await interaction.response.send_message(
        embed=embed
    )

# =========================================================
# RANK LIST
# =========================================================

@bot.tree.command(
    name="ranklist",
    description="Sunucudaki herkesin rankını gösterir."
)
async def ranklist_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "❌ Bu komut sadece sunucuda kullanılabilir.",
            ephemeral=True
        )
        return

    members = []

    for member in guild.members:

        if member.bot:
            continue

        user = get_user_data(member.id)

        seconds = user["online_seconds"]

        rank = get_rank_from_seconds(seconds)

        rank_name = get_rank_name(rank)

        members.append(
            (
                member,
                rank,
                rank_name,
                seconds
            )
        )

    # Önce rank, sonra online süreye göre sırala
    members.sort(
        key=lambda x: (x[1], x[3]),
        reverse=True
    )

    if not members:
        await interaction.response.send_message(
            "❌ Henüz üye verisi bulunmuyor."
        )
        return

    # Discord mesaj limiti için sayfalama
    pages = []

    current_page = ""

    for index, (
        member,
        rank,
        rank_name,
        seconds
    ) in enumerate(
        members,
        start=1
    ):

        line = (
            f"**{index}.** {member.mention} "
            f"— 🏆 **{rank}/10** "
            f"`{rank_name}` "
            f"— 🕐 `{format_time(seconds)}`\n"
        )

        if len(current_page) + len(line) > 3500:
            pages.append(current_page)
            current_page = ""

        current_page += line

    if current_page:
        pages.append(current_page)

    # İlk sayfayı gönder
    embed = discord.Embed(
        title="🏆 Kyrox Rank Listesi",
        description=pages[0],
        color=discord.Color.gold()
    )

    embed.set_footer(
        text=f"Toplam {len(members)} üye • Sayfa 1/{len(pages)}"
    )

    await interaction.response.send_message(
        embed=embed
    )
# =========================================================
# PROFILE
# =========================================================

@bot.tree.command(
    name="profile",
    description="Profilini gösterir."
)
async def profile_command(
    interaction: discord.Interaction
):

    member = interaction.user

    user = get_user_data(
        member.id
    )

    seconds = user["online_seconds"]

    rank = get_rank_from_seconds(
        seconds
    )

    rank_name = get_rank_name(
        rank
    )

    progress = level_progress(
        user
    )

    embed = discord.Embed(
        title=f"👤 {member.display_name}",
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="🏆 Rank",
        value=f"{rank}/10",
        inline=True
    )

    embed.add_field(
        name="🏷️ Rol",
        value=rank_name,
        inline=True
    )

    embed.add_field(
        name="🕐 Online Süre",
        value=format_time(seconds),
        inline=False
    )

    embed.add_field(
        name="⭐ Level",
        value=f"{user['level']}",
        inline=True
    )

    embed.add_field(
        name="✨ XP",
        value=f"{user['xp']}/{xp_required(user['level'])}",
        inline=True
    )

    embed.add_field(
        name="📊 Level İlerlemesi",
        value=f"%{progress}",
        inline=True
    )

    embed.add_field(
        name="💬 Mesaj",
        value=str(user["messages"]),
        inline=True
    )

    embed.add_field(
        name="🔥 Streak",
        value=f"{user['streak']} gün",
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# LEADERBOARD
# =========================================================

@bot.tree.command(
    name="leaderboard",
    description="En çok online olan üyeleri gösterir."
)
async def leaderboard_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "Bu komut sunucuda kullanılabilir."
        )
        return

    members = []

    for member in guild.members:

        if member.bot:
            continue

        user = get_user_data(
            member.id
        )

        members.append(
            (
                member,
                user["online_seconds"]
            )
        )

    members.sort(
        key=lambda x: x[1],
        reverse=True
    )

    members = members[:10]

    if not members:
        await interaction.response.send_message(
            "Henüz veri bulunmuyor."
        )
        return

    text = ""

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    for index, (
        member,
        seconds
    ) in enumerate(
        members,
        start=1
    ):

        if index <= 3:
            prefix = medals[index - 1]
        else:
            prefix = f"**{index}.**"

        text += (
            f"{prefix} {member.mention} — "
            f"`{format_time(seconds)}`\n"
        )

    embed = discord.Embed(
        title="🏆 Kyrox Leaderboard",
        description=text,
        color=discord.Color.gold()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# XP LEADERBOARD
# =========================================================

@bot.tree.command(
    name="xptop",
    description="En yüksek level üyelerini gösterir."
)
async def xptop_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "Bu komut sunucuda kullanılabilir."
        )
        return

    members = []

    for member in guild.members:

        if member.bot:
            continue

        user = get_user_data(
            member.id
        )

        total_xp = (
            user["level"] * 100
            + user["xp"]
        )

        members.append(
            (
                member,
                user,
                total_xp
            )
        )

    members.sort(
        key=lambda x: x[2],
        reverse=True
    )

    members = members[:10]

    text = ""

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    for index, (
        member,
        user,
        _
    ) in enumerate(
        members,
        start=1
    ):

        prefix = (
            medals[index - 1]
            if index <= 3
            else f"**{index}.**"
        )

        text += (
            f"{prefix} {member.mention} — "
            f"Level **{user['level']}** "
            f"({user['xp']} XP)\n"
        )

    embed = discord.Embed(
        title="⭐ Kyrox XP Sıralaması",
        description=text,
        color=discord.Color.purple()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# LEVEL
# =========================================================

@bot.tree.command(
    name="level",
    description="Level ve XP bilgini gösterir."
)
async def level_command(
    interaction: discord.Interaction
):

    user = get_user_data(
        interaction.user.id
    )

    required = xp_required(
        user["level"]
    )

    progress = level_progress(
        user
    )

    bar_length = 10

    filled = int(
        progress / 10
    )

    bar = (
        "█" * filled
        + "░" * (bar_length - filled)
    )

    embed = discord.Embed(
        title="⭐ Level Sistemi",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="🎖️ Level",
        value=f"**{user['level']}**",
        inline=True
    )

    embed.add_field(
        name="✨ XP",
        value=f"{user['xp']} / {required}",
        inline=True
    )

    embed.add_field(
        name="📊 İlerleme",
        value=f"`{bar}` %{progress}",
        inline=False
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# BAŞARIMLAR
# =========================================================

@bot.tree.command(
    name="achievements",
    description="Kazandığın başarımları gösterir."
)
async def achievements_command(
    interaction: discord.Interaction
):

    user = get_user_data(
        interaction.user.id
    )

    text = ""

    for key, info in ACHIEVEMENTS.items():

        if key in user["achievements"]:
            status = "✅"
        else:
            status = "🔒"

        text += (
            f"{status} {info['icon']} "
            f"**{info['name']}** — "
            f"{info['description']}\n"
        )

    embed = discord.Embed(
        title="🏅 Kyrox Başarımları",
        description=text,
        color=discord.Color.gold()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# STREAK
# =========================================================

@bot.tree.command(
    name="streak",
    description="Aktivite serini gösterir."
)
async def streak_command(
    interaction: discord.Interaction
):

    user = get_user_data(
        interaction.user.id
    )

    embed = discord.Embed(
        title="🔥 Aktivite Streak",
        description=(
            f"{interaction.user.mention}, "
            f"mevcut serin:\n\n"
            f"🔥 **{user['streak']} gün**"
        ),
        color=discord.Color.orange()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# AFK
# =========================================================

@bot.tree.command(
    name="afk",
    description="AFK durumuna geç."
)
@app_commands.describe(
    sebep="AFK sebebi"
)
async def afk_command(
    interaction: discord.Interaction,
    sebep: str = "Belirtilmedi"
):

    user = get_user_data(
        interaction.user.id
    )

    user["afk"] = True
    user["afk_reason"] = sebep

    save_data()

    await interaction.response.send_message(
        f"💤 {interaction.user.mention} "
        f"artık AFK.\n"
        f"📝 Sebep: **{sebep}**"
    )


# =========================================================
# USERINFO
# =========================================================

@bot.tree.command(
    name="userinfo",
    description="Bir üyenin bilgilerini gösterir."
)
@app_commands.describe(
    uye="Bilgilerini görmek istediğin üye"
)
async def userinfo_command(
    interaction: discord.Interaction,
    uye: discord.Member = None
):

    member = uye or interaction.user

    user = get_user_data(
        member.id
    )

    roles = [
        role.mention
        for role in member.roles
        if role != interaction.guild.default_role
    ]

    roles_text = (
        ", ".join(roles[-10:])
        if roles
        else "Yok"
    )

    embed = discord.Embed(
        title=f"👤 {member}",
        color=member.color
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="🆔 ID",
        value=str(member.id),
        inline=False
    )

    embed.add_field(
        name="📅 Hesap",
        value=discord.utils.format_dt(
            member.created_at,
            style="R"
        ),
        inline=True
    )

    if member.joined_at:
        embed.add_field(
            name="📥 Katılım",
            value=discord.utils.format_dt(
                member.joined_at,
                style="R"
            ),
            inline=True
        )

    embed.add_field(
        name="⭐ Level",
        value=str(user["level"]),
        inline=True
    )

    embed.add_field(
        name="🏆 Rank",
        value=get_rank_name(
            get_rank_from_seconds(
                user["online_seconds"]
            )
        ),
        inline=True
    )

    embed.add_field(
        name="🎭 Roller",
        value=roles_text,
        inline=False
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# SERVER INFO
# =========================================================

@bot.tree.command(
    name="serverinfo",
    description="Sunucu bilgilerini gösterir."
)
async def serverinfo_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        return

    embed = discord.Embed(
        title=f"🖥️ {guild.name}",
        color=discord.Color.blurple()
    )

    if guild.icon:
        embed.set_thumbnail(
            url=guild.icon.url
        )

    embed.add_field(
        name="👑 Sahip",
        value=(
            guild.owner.mention
            if guild.owner
            else "Bilinmiyor"
        ),
        inline=True
    )

    embed.add_field(
        name="👥 Üye",
        value=str(guild.member_count),
        inline=True
    )

    embed.add_field(
        name="💬 Kanallar",
        value=str(len(guild.channels)),
        inline=True
    )

    embed.add_field(
        name="🎭 Roller",
        value=str(len(guild.roles)),
        inline=True
    )

    embed.add_field(
        name="😀 Emojiler",
        value=str(len(guild.emojis)),
        inline=True
    )

    embed.add_field(
        name="📅 Oluşturulma",
        value=discord.utils.format_dt(
            guild.created_at,
            style="D"
        ),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# STATS
# =========================================================

@bot.tree.command(
    name="stats",
    description="Kyrox bot istatistiklerini gösterir."
)
async def stats_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        return

    humans = len([
        m for m in guild.members
        if not m.bot
    ])

    bots = len([
        m for m in guild.members
        if m.bot
    ])

    online = len([
        m for m in guild.members
        if not m.bot
        and m.status != discord.Status.offline
    ])

    embed = discord.Embed(
        title="📊 Kyrox Server Stats",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="👥 İnsan",
        value=str(humans),
        inline=True
    )

    embed.add_field(
        name="🤖 Bot",
        value=str(bots),
        inline=True
    )

    embed.add_field(
        name="🟢 Online",
        value=str(online),
        inline=True
    )

    embed.add_field(
        name="💬 Metin Kanalları",
        value=str(len(guild.text_channels)),
        inline=True
    )

    embed.add_field(
        name="🔊 Ses Kanalları",
        value=str(len(guild.voice_channels)),
        inline=True
    )

    embed.add_field(
        name="🎭 Roller",
        value=str(len(guild.roles)),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Botun pingini gösterir."
)
async def ping_command(
    interaction: discord.Interaction
):

    ping = round(
        bot.latency * 1000
    )

    await interaction.response.send_message(
        f"🏓 Pong! `{ping}ms`"
    )


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(
    name="clear",
    description="Mesajları siler."
)
@app_commands.describe(
    miktar="Silinecek mesaj sayısı"
)
@app_commands.default_permissions(
    manage_messages=True
)
async def clear_command(
    interaction: discord.Interaction,
    miktar: app_commands.Range[int, 1, 100]
):

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ Bu komut için mesaj yönetme yetkin olmalı.",
            ephemeral=True
        )
        return

    await interaction.response.defer(
        ephemeral=True
    )

    deleted = await interaction.channel.purge(
        limit=miktar
    )

    await interaction.followup.send(
        f"🧹 **{len(deleted)}** mesaj silindi.",
        ephemeral=True
    )

    await send_log(
        interaction.guild,
        "🧹 Mesaj Temizleme",
        f"{interaction.user.mention} "
        f"{len(deleted)} mesaj sildi.",
        discord.Color.orange()
    )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Üyeyi sunucudan atar."
)
@app_commands.describe(
    uye="Atılacak üye",
    sebep="Atılma sebebi"
)
@app_commands.default_permissions(
    kick_members=True
)
async def kick_command(
    interaction: discord.Interaction,
    uye: discord.Member,
    sebep: str = "Sebep belirtilmedi"
):

    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message(
            "❌ Kick yetkin yok.",
            ephemeral=True
        )
        return

    if uye == interaction.user:
        await interaction.response.send_message(
            "❌ Kendini atamazsın.",
            ephemeral=True
        )
        return

    if uye.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            "❌ Bu üyeyi atamazsın.",
            ephemeral=True
        )
        return

    try:
        await uye.kick(
            reason=f"{sebep} | {interaction.user}"
        )

        await interaction.response.send_message(
            f"👢 {uye.mention} sunucudan atıldı.\n"
            f"📝 Sebep: **{sebep}**"
        )

        await send_log(
            interaction.guild,
            "👢 Kick",
            f"{interaction.user.mention}, "
            f"{uye} kullanıcısını attı.\n"
            f"Sebep: {sebep}",
            discord.Color.orange()
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Bu üyeyi atamıyorum. "
            "Bot rolünü kontrol et.",
            ephemeral=True
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Üyeyi yasaklar."
)
@app_commands.describe(
    uye="Yasaklanacak üye",
    sebep="Ban sebebi"
)
@app_commands.default_permissions(
    ban_members=True
)
async def ban_command(
    interaction: discord.Interaction,
    uye: discord.Member,
    sebep: str = "Sebep belirtilmedi"
):

    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message(
            "❌ Ban yetkin yok.",
            ephemeral=True
        )
        return

    if uye == interaction.user:
        await interaction.response.send_message(
            "❌ Kendini banlayamazsın.",
            ephemeral=True
        )
        return

    if uye.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            "❌ Bu üyeyi banlayamazsın.",
            ephemeral=True
        )
        return

    try:
        await uye.ban(
            reason=f"{sebep} | {interaction.user}"
        )

        await interaction.response.send_message(
            f"🔨 {uye.mention} yasaklandı.\n"
            f"📝 Sebep: **{sebep}**"
        )

        await send_log(
            interaction.guild,
            "🔨 Ban",
            f"{interaction.user.mention}, "
            f"{uye} kullanıcısını banladı.\n"
            f"Sebep: {sebep}",
            discord.Color.red()
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Bu üyeyi banlayamıyorum.",
            ephemeral=True
        )


# =========================================================
# MUTE / TIMEOUT
# =========================================================

@bot.tree.command(
    name="mute",
    description="Üyeyi geçici olarak susturur."
)
@app_commands.describe(
    uye="Susturulacak üye",
    dakika="Dakika",
    sebep="Sebep"
)
@app_commands.default_permissions(
    moderate_members=True
)
async def mute_command(
    interaction: discord.Interaction,
    uye: discord.Member,
    dakika: app_commands.Range[int, 1, 10080],
    sebep: str = "Sebep belirtilmedi"
):

    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message(
            "❌ Timeout yetkin yok.",
            ephemeral=True
        )
        return

    if uye == interaction.user:
        await interaction.response.send_message(
            "❌ Kendini susturamazsın.",
            ephemeral=True
        )
        return

    if uye.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            "❌ Bu üyeyi susturamazsın.",
            ephemeral=True
        )
        return

    try:
        await uye.timeout(
            timedelta(minutes=dakika),
            reason=f"{sebep} | {interaction.user}"
        )

        await interaction.response.send_message(
            f"🔇 {uye.mention} "
            f"**{dakika} dakika** susturuldu.\n"
            f"📝 Sebep: **{sebep}**"
        )

        await send_log(
            interaction.guild,
            "🔇 Timeout",
            f"{interaction.user.mention}, "
            f"{uye} kullanıcısını {dakika} dakika "
            f"susturdu.\nSebep: {sebep}",
            discord.Color.orange()
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Bu üyeye timeout veremiyorum.",
            ephemeral=True
        )


# =========================================================
# UNMUTE
# =========================================================

@bot.tree.command(
    name="unmute",
    description="Timeout'u kaldırır."
)
@app_commands.describe(
    uye="Timeout'u kaldırılacak üye"
)
@app_commands.default_permissions(
    moderate_members=True
)
async def unmute_command(
    interaction: discord.Interaction,
    uye: discord.Member
):

    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message(
            "❌ Yetkin yok.",
            ephemeral=True
        )
        return

    try:
        await uye.timeout(
            None,
            reason=f"Timeout kaldırıldı | {interaction.user}"
        )

        await interaction.response.send_message(
            f"🔊 {uye.mention} artık susturulmuyor."
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Timeout kaldırılamadı.",
            ephemeral=True
        )


# =========================================================
# LOG AYARLAMA
# =========================================================

@bot.tree.command(
    name="setlog",
    description="Log kanalını ayarlar."
)
@app_commands.describe(
    kanal="Log kanalı"
)
@app_commands.default_permissions(
    manage_guild=True
)
async def setlog_command(
    interaction: discord.Interaction,
    kanal: discord.TextChannel
):

    guild_data = get_guild_data(
        interaction.guild.id
    )

    guild_data["log_channel"] = kanal.id

    save_data()

    await interaction.response.send_message(
        f"📝 Log kanalı {kanal.mention} olarak ayarlandı."
    )


# =========================================================
# WELCOME AYARLAMA
# =========================================================

@bot.tree.command(
    name="setwelcome",
    description="Hoş geldin kanalını ayarlar."
)
@app_commands.describe(
    kanal="Hoş geldin kanalı"
)
@app_commands.default_permissions(
    manage_guild=True
)
async def setwelcome_command(
    interaction: discord.Interaction,
    kanal: discord.TextChannel
):

    guild_data = get_guild_data(
        interaction.guild.id
    )

    guild_data["welcome_channel"] = kanal.id

    save_data()

    await interaction.response.send_message(
        f"👋 Hoş geldin kanalı "
        f"{kanal.mention} olarak ayarlandı."
    )


# =========================================================
# FILTER ON/OFF
# =========================================================

@bot.tree.command(
    name="filter",
    description="Kelime filtresini açar/kapatır."
)
@app_commands.describe(
    durum="on veya off"
)
@app_commands.default_permissions(
    manage_guild=True
)
async def filter_command(
    interaction: discord.Interaction,
    durum: str
):

    durum = durum.lower()

    if durum not in ["on", "off"]:
        await interaction.response.send_message(
            "❌ `on` veya `off` yaz.",
            ephemeral=True
        )
        return

    guild_data = get_guild_data(
        interaction.guild.id
    )

    guild_data["filter_enabled"] = (
        durum == "on"
    )

    save_data()

    await interaction.response.send_message(
        f"🚫 Kelime filtresi: "
        f"**{'Açık' if durum == 'on' else 'Kapalı'}**"
    )


# =========================================================
# ANTISPAM ON/OFF
# =========================================================

@bot.tree.command(
    name="antispam",
    description="Anti-spam sistemini açar/kapatır."
)
@app_commands.describe(
    durum="on veya off"
)
@app_commands.default_permissions(
    manage_guild=True
)
async def antispam_command(
    interaction: discord.Interaction,
    durum: str
):

    durum = durum.lower()

    if durum not in ["on", "off"]:
        await interaction.response.send_message(
            "❌ `on` veya `off` yaz.",
            ephemeral=True
        )
        return

    guild_data = get_guild_data(
        interaction.guild.id
    )

    guild_data["antispam_enabled"] = (
        durum == "on"
    )

    save_data()

    await interaction.response.send_message(
        f"🛡️ Anti-spam: "
        f"**{'Açık' if durum == 'on' else 'Kapalı'}**"
    )


# =========================================================
# TICKET
# =========================================================

@bot.tree.command(
    name="ticket",
    description="Destek ticketı açar."
)
async def ticket_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        return

    existing = discord.utils.get(
        guild.text_channels,
        name=f"ticket-{interaction.user.id}"
    )

    if existing:
        await interaction.response.send_message(
            f"🎫 Zaten açık ticketın var: "
            f"{existing.mention}",
            ephemeral=True
        )
        return

    category = discord.utils.get(
        guild.categories,
        name=TICKET_CATEGORY_NAME
    )

    if category is None:

        try:
            category = await guild.create_category(
                TICKET_CATEGORY_NAME,
                reason="Kyrox Ticket Sistemi"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Ticket kategorisi oluşturulamıyor.",
                ephemeral=True
            )
            return

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
            manage_channels=True,
            read_message_history=True
        )
    }

    try:

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=category,
            overwrites=overwrites,
            reason="Kyrox Ticket Sistemi"
        )

        embed = discord.Embed(
            title="🎫 Kyrox Ticket",
            description=(
                f"Hoş geldin {interaction.user.mention}!\n\n"
                "Yetkililer en kısa sürede ilgilenecektir.\n\n"
                "Ticketı kapatmak için:\n"
                "`/close`"
            ),
            color=discord.Color.blurple()
        )

        await channel.send(
            content=interaction.user.mention,
            embed=embed
        )

        await interaction.response.send_message(
            f"🎫 Ticket oluşturuldu: "
            f"{channel.mention}",
            ephemeral=True
        )

        await send_log(
            guild,
            "🎫 Ticket Açıldı",
            f"{interaction.user.mention} "
            f"tarafından {channel.mention} oluşturuldu.",
            discord.Color.green()
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Ticket kanalı oluşturulamıyor.",
            ephemeral=True
        )


# =========================================================
# TICKET CLOSE
# =========================================================

@bot.tree.command(
    name="close",
    description="Mevcut ticketı kapatır."
)
async def close_command(
    interaction: discord.Interaction
):

    channel = interaction.channel

    if not channel.name.startswith(
        "ticket-"
    ):
        await interaction.response.send_message(
            "❌ Bu kanal bir ticket değil.",
            ephemeral=True
        )
        return

    if not (
        interaction.user.guild_permissions.manage_channels
        or channel.name == f"ticket-{interaction.user.id}"
    ):
        await interaction.response.send_message(
            "❌ Bu ticketı kapatma yetkin yok.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🔒 Ticket 5 saniye içinde kapatılıyor."
    )

    await asyncio.sleep(5)

    await send_log(
        interaction.guild,
        "🔒 Ticket Kapatıldı",
        f"{interaction.user.mention} "
        f"tarafından ticket kapatıldı.",
        discord.Color.red()
    )

    try:
        await channel.delete(
            reason="Kyrox Ticket kapatma"
        )
    except discord.Forbidden:
        pass


# =========================================================
# PREMIUM
# =========================================================

@bot.tree.command(
    name="premium",
    description="Premium durumunu gösterir."
)
async def premium_command(
    interaction: discord.Interaction
):

    role = get_role(
        interaction.guild,
        PREMIUM_ROLE_NAME
    )

    if role is None:
        await interaction.response.send_message(
            f"⚠️ `{PREMIUM_ROLE_NAME}` rolü bulunamadı."
        )
        return

    if role in interaction.user.roles:

        await interaction.response.send_message(
            "💎 Premium durumun: **AKTİF**"
        )

    else:

        await interaction.response.send_message(
            "💎 Premium durumun: **AKTİF DEĞİL**"
        )


# =========================================================
# HELP
# =========================================================

@bot.tree.command(
    name="help",
    description="Tüm Kyrox komutlarını gösterir."
)
async def help_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🤖 Kyrox Bot",
        description=(
            "Kyrox sunucu sistemi\n"
            "━━━━━━━━━━━━━━━━━━━━"
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🏆 Rank",
        value=(
            "`/rank`\n"
            "`/ranklar`\n"
            "`/profile`\n"
            "`/leaderboard`"
        ),
        inline=True
    )

    embed.add_field(
        name="⭐ XP / Level",
        value=(
            "`/level`\n"
            "`/xptop`\n"
            "`/achievements`\n"
            "`/streak`"
        ),
        inline=True
    )

    embed.add_field(
        name="👤 Kullanıcı",
        value=(
            "`/userinfo`\n"
            "`/afk`\n"
            "`/premium`"
        ),
        inline=True
    )

    embed.add_field(
        name="🖥️ Sunucu",
        value=(
            "`/serverinfo`\n"
            "`/stats`\n"
            "`/ping`"
        ),
        inline=True
    )

    embed.add_field(
        name="🎫 Ticket",
        value=(
            "`/ticket`\n"
            "`/close`"
        ),
        inline=True
    )

    embed.add_field(
        name="🛡️ Moderasyon",
        value=(
            "`/ban`\n"
            "`/kick`\n"
            "`/mute`\n"
            "`/unmute`\n"
            "`/clear`"
        ),
        inline=True
    )

    embed.add_field(
        name="⚙️ Yönetim",
        value=(
            "`/setlog`\n"
            "`/setwelcome`\n"
            "`/filter`\n"
            "`/antispam`"
        ),
        inline=True
    )

    embed.set_footer(
        text="Kyrox • Rank + XP + Moderasyon Sistemi"
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# HATA YÖNETİMİ
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):
        message = (
            "❌ Bu komutu kullanmak için "
            "gerekli yetkin yok."
        )

    elif isinstance(
        error,
        app_commands.BotMissingPermissions
    ):
        message = (
            "❌ Botun gerekli Discord yetkilerine sahip değil."
        )

    elif isinstance(
        error,
        app_commands.CommandOnCooldown
    ):
        message = (
            f"⏳ Biraz bekle: "
            f"{error.retry_after:.1f} saniye."
        )

    else:
        print(
            "❌ Komut hatası:",
            repr(error)
        )

        message = (
            "❌ Komut çalıştırılırken "
            "bir hata oluştu."
        )

    try:

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True
            )

    except Exception:
        pass


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print("=" * 60)

    print(
        f"✅ BOT: {bot.user}"
    )

    print(
        f"🆔 ID: {bot.user.id}"
    )

    print(
        f"🌐 SUNUCU: {len(bot.guilds)}"
    )

    print("=" * 60)

    try:

        if TEST_GUILD_ID:

            guild_object = discord.Object(
                id=TEST_GUILD_ID
            )

            bot.tree.copy_global_to(
                guild=guild_object
            )

            synced = await bot.tree.sync(
                guild=guild_object
            )

            print(
                f"✅ {len(synced)} slash komutu "
                f"sunucuya yüklendi."
            )

        else:

            synced = await bot.tree.sync()

            print(
                f"✅ {len(synced)} global komut yüklendi."
            )

    except Exception as e:

        print(
            f"❌ Slash komut hatası: {e}"
        )

    if not online_tracker.is_running():
        online_tracker.start()

    print(
        "🟢 Kyrox online süre sistemi aktif."
    )

    print(
        "⭐ XP / Level sistemi aktif."
    )

    print(
        "🛡️ Anti-Spam sistemi aktif."
    )


# =========================================================
# BAŞLAT
# =========================================================

if __name__ == "__main__":

    load_data()

    if not BOT_TOKEN:

        print()
        print(
            "❌ BOT_TOKEN bulunamadı!"
        )

        print()
        print(
            "CMD:"
        )

        print(
            "set BOT_TOKEN=YENI_TOKEN"
        )

        print(
            "set TEST_GUILD_ID=SUNUCU_ID"
        )

        print(
            "python kyrox_bot.py"
        )

        print()

        raise SystemExit

    try:

        bot.run(
            BOT_TOKEN
        )

    except discord.LoginFailure:

        print(
            "❌ Discord token geçersiz."
        )

    except Exception as e:

        print(
            f"❌ Bot başlatılamadı: {e}"
        )
