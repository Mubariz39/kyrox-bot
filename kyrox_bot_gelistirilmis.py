import discord
from discord.ext import commands, tasks
import os
import json

# =========================================================
# AYARLAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

DATA_FILE = "kyxor_data.json"

# =========================================================
# RANKLAR
# =========================================================
# Süreler toplam ONLINE süredir.
# Offline geçirilen süre sayılmaz.

RANKS = [
    ("Yeni Üye", 0),
    ("Aktif Üye", 2 * 60 * 60),                  # 2 saat
    ("Sohbetçi", 6 * 60 * 60),                   # 6 saat
    ("Tecrübeli", 12 * 60 * 60),                 # 12 saat
    ("Kıdemli", 24 * 60 * 60),                   # 1 gün
    ("Usta", 3 * 24 * 60 * 60),                  # 3 gün
    ("Elit", 7 * 24 * 60 * 60),                  # 7 gün
    ("Efsane", 14 * 24 * 60 * 60),               # 14 gün
    ("Şampiyon", 30 * 24 * 60 * 60),             # 30 gün
    ("Kyrox Efsanesi", 60 * 24 * 60 * 60),       # 60 gün
]

# =========================================================
# INTENTS
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
# DATA
# =========================================================

data = {
    "users": {}
}


def load_data():
    global data

    if not os.path.exists(DATA_FILE):
        save_data()
        return

    try:
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if "users" not in data:
            data["users"] = {}

    except Exception as e:
        print("❌ Veri yükleme hatası:", e)

        data = {
            "users": {}
        }


def save_data():
    try:
        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=4
            )

    except Exception as e:
        print("❌ Veri kaydetme hatası:", e)


# =========================================================
# KULLANICI VERİSİ
# =========================================================

def get_user_data(user_id):

    user_id = str(user_id)

    if user_id not in data["users"]:

        data["users"][user_id] = {
            "online_seconds": 0,
            "rank": 1
        }

    user = data["users"][user_id]

    if "online_seconds" not in user:
        user["online_seconds"] = 0

    if "rank" not in user:
        user["rank"] = 1

    return user


# =========================================================
# RANK HESAPLAMA
# =========================================================

def get_rank_from_seconds(seconds):

    current_rank = 1

    for index, (_, required_seconds) in enumerate(
        RANKS,
        start=1
    ):

        if seconds >= required_seconds:
            current_rank = index

    return current_rank


def get_rank_name(rank):

    if rank < 1:
        rank = 1

    if rank > len(RANKS):
        rank = len(RANKS)

    return RANKS[rank - 1][0]


def get_next_rank_time(rank):

    if rank >= len(RANKS):
        return None

    return RANKS[rank][1]


# =========================================================
# SÜRE FORMATLAMA
# =========================================================

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


# =========================================================
# ROL BULMA
# =========================================================
# DİKKAT:
# BOT ROL OLUŞTURMAZ.
# SADECE MEVCUT ROLÜ BULUR.
# =========================================================

def get_role(guild, role_name):

    return discord.utils.get(
        guild.roles,
        name=role_name
    )


# =========================================================
# RANK ROLÜ VER
# =========================================================

async def set_member_rank(member, rank):

    if member.bot:
        return

    target_role_name = get_rank_name(rank)

    target_role = get_role(
        member.guild,
        target_role_name
    )

    # Rol sunucuda yoksa oluşturma!
    if target_role is None:

        print(
            f"⚠️ Rol bulunamadı: "
            f"{target_role_name} "
            f"| Sunucu: {member.guild.name}"
        )

        return

    # Bütün rank rollerini bul
    rank_roles = []

    for role_name, _ in RANKS:

        role = get_role(
            member.guild,
            role_name
        )

        if role:
            rank_roles.append(role)

    # Eski rank rollerini bul
    old_roles = []

    for role in rank_roles:

        if role in member.roles:

            if role.id != target_role.id:
                old_roles.append(role)

    try:

        # Eski rankları kaldır
        if old_roles:

            await member.remove_roles(
                *old_roles,
                reason="Kyrox otomatik rank sistemi"
            )

        # Yeni rankı ver
        if target_role not in member.roles:

            await member.add_roles(
                target_role,
                reason="Kyrox otomatik rank sistemi"
            )

            print(
                f"⬆️ RANK: "
                f"{member} -> {target_role_name}"
            )

    except discord.Forbidden:

        print(
            f"❌ {member} için "
            f"{target_role_name} verilemedi."
        )

        print(
            "Botun rolünü Discord'da "
            "rank rollerinin üzerine taşı."
        )

    except Exception as e:

        print(
            f"❌ Rank hatası: {e}"
        )


# =========================================================
# YENİ ÜYE
# =========================================================

@bot.event
async def on_member_join(member):

    if member.bot:
        return

    user = get_user_data(
        member.id
    )

    # Yeni üye olduğunda Rank 1
    user["rank"] = 1

    # Yeni Üye rolünü bul
    role = get_role(
        member.guild,
        "Yeni Üye"
    )

    if role is None:

        print(
            f"⚠️ 'Yeni Üye' rolü bulunamadı."
        )

    else:

        try:

            await member.add_roles(
                role,
                reason="Yeni üye"
            )

            print(
                f"👤 Yeni üye: "
                f"{member} -> Yeni Üye"
            )

        except discord.Forbidden:

            print(
                "❌ Yeni Üye rolü verilemedi."
            )

    save_data()


# =========================================================
# ÜYE ÇIKIŞ
# =========================================================

@bot.event
async def on_member_remove(member):

    # Verileri silmiyoruz.
    # Tekrar gelirse eski online süresi korunur.

    save_data()


# =========================================================
# ONLINE SÜRE TAKİBİ
# =========================================================

@tasks.loop(minutes=1)
async def online_tracker():

    changed = False

    for guild in bot.guilds:

        for member in guild.members:

            if member.bot:
                continue

            # SADECE ONLINE OLANLAR
            if member.status == discord.Status.offline:
                continue

            user = get_user_data(
                member.id
            )

            # 1 dakika ekle
            user["online_seconds"] += 60

            old_rank = user.get(
                "rank",
                1
            )

            new_rank = get_rank_from_seconds(
                user["online_seconds"]
            )

            # Rank değiştiyse
            if new_rank != old_rank:

                user["rank"] = new_rank

                await set_member_rank(
                    member,
                    new_rank
                )

                print(
                    f"🏆 {member} "
                    f"Rank {new_rank}: "
                    f"{get_rank_name(new_rank)}"
                )

            changed = True

    if changed:
        save_data()


@online_tracker.before_loop
async def before_online_tracker():

    await bot.wait_until_ready()


# =========================================================
# RANK KOMUTU
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

    # Sonraki rank
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
# RANKLAR KOMUTU
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
            f"**{index}. {name}**"
            f" — `{time_text}`\n"
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
# PROFİL
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

    for index, (member, seconds) in enumerate(
        members,
        start=1
    ):

        if index <= 3:
            prefix = medals[index - 1]
        else:
            prefix = f"**{index}.**"

        text += (
            f"{prefix} "
            f"{member.mention} — "
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
# HELP
# =========================================================

@bot.tree.command(
    name="help",
    description="Bot komutlarını gösterir."
)
async def help_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🤖 Kyrox Bot",
        description=(
            "**Rank Sistemi**\n"
            "`/rank` → Rankını gösterir\n"
            "`/ranklar` → Rank listesini gösterir\n"
            "`/profile` → Profilini gösterir\n"
            "`/leaderboard` → Online sıralaması\n\n"
            "**Diğer**\n"
            "`/ping` → Bot pingini gösterir"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print("=" * 60)
    print(f"✅ BOT: {bot.user}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"🌐 SUNUCU: {len(bot.guilds)}")
    print("=" * 60)

    # Roller oluşturulmaz.
    # Sadece mevcut roller kullanılır.

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

    # Online tracker sadece 1 kere başlasın
    if not online_tracker.is_running():

        online_tracker.start()

    print(
        "🟢 Kyrox online süre sistemi aktif."
    )


# =========================================================
# BAŞLAT
# =========================================================

if __name__ == "__main__":

    load_data()

    if not BOT_TOKEN:

        print()
        print("❌ BOT_TOKEN bulunamadı!")
        print()
        print("CMD:")
        print("set BOT_TOKEN=YENI_TOKEN")
        print("set TEST_GUILD_ID=SUNUCU_ID")
        print("python kyrox_bot.py")
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
