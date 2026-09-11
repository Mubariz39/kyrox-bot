import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import re
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
    "rank": {},
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

# Eski dosyada ekonomi/XP verileri varsa kullanılmaz; rank sistemi temiz şekilde çalışır.
data.setdefault("warnings", {})
data.setdefault("rank", {})
data.setdefault("settings", {})

# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

start_time = time.time()

spam_cache = {}
rank_activity = {}
rank_channel = {}
background_started = False

# Rank süreleri (aktif sohbet süresi)
RANK_TIMES = [
    30 * 60,
    60 * 60,
    2 * 60 * 60,
    3 * 60 * 60,
    5 * 60 * 60,
    7 * 60 * 60,
    10 * 60 * 60,
    15 * 60 * 60,
    20 * 60 * 60,
    30 * 60 * 60,
]


# Rank rolleri: (rol adı, rol rengi)
RANK_ROLES = {
    1: ("Yeni Üye", discord.Color.green()),
    2: ("Aktif Üye", discord.Color.blue()),
    3: ("Sohbetçi", discord.Color.purple()),
    4: ("Tecrübeli", discord.Color.gold()),
    5: ("Kıdemli", discord.Color.orange()),
    6: ("Usta", discord.Color.red()),
    7: ("Elit", discord.Color.from_rgb(0, 200, 255)),
    8: ("Efsane", discord.Color.from_rgb(255, 0, 255)),
    9: ("Şampiyon", discord.Color.from_rgb(255, 80, 0)),
    10: ("Kyxor Efsanesi", discord.Color.from_rgb(255, 215, 0)),
}


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


def get_user_rank(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)

    if gid not in data["rank"]:
        data["rank"][gid] = {}

    if uid not in data["rank"][gid]:
        data["rank"][gid][uid] = {"seconds": 0}

    return data["rank"][gid][uid]


def get_rank(seconds):
    rank = 0
    for required in RANK_TIMES:
        if seconds >= required:
            rank += 1
        else:
            break
    return min(rank, len(RANK_TIMES))


def format_duration(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)

    parts = []
    if days:
        parts.append(f"{days} gün")
    if hours:
        parts.append(f"{hours} saat")
    if minutes or not parts:
        parts.append(f"{minutes} dakika")
    return " ".join(parts)


def rank_progress(seconds):
    current = get_rank(seconds)
    if current >= len(RANK_TIMES):
        return current, None, 0
    previous = RANK_TIMES[current - 1] if current > 0 else 0
    target = RANK_TIMES[current]
    progress = max(0, min(seconds - previous, target - previous))
    return current, target, progress


async def ensure_rank_roles(guild):
    roles = {}
    for rank, (role_name, role_color) in RANK_ROLES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            try:
                role = await guild.create_role(
                    name=role_name,
                    color=role_color,
                    reason="Kyxor Bot rank sistemi"
                )
                print(f"[RANK] {guild.name}: {role_name} rolü oluşturuldu.")
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"[RANK] {guild.name}: {role_name} oluşturulamadı: {e}")
                continue
        roles[rank] = role
    return roles


async def set_rank_role(member, rank):
    if rank <= 0 or member.bot:
        return

    guild = member.guild
    roles = await ensure_rank_roles(guild)
    target_role = roles.get(rank)
    me = guild.me

    if target_role is None or me is None:
        return

    if target_role >= me.top_role:
        print(
            f"[RANK] {guild.name}: {target_role.name} verilemedi. "
            f"Bot rolünü rank rollerinin üstüne taşı."
        )
        return

    rank_role_names = {name for name, _ in RANK_ROLES.values()}
    old_rank_roles = [
        role for role in member.roles
        if role.name in rank_role_names and role != target_role
    ]

    try:
        if old_rank_roles:
            await member.remove_roles(
                *old_rank_roles,
                reason="Kyxor Bot rank yükseltmesi"
            )
        if target_role not in member.roles:
            await member.add_roles(
                target_role,
                reason=f"Kyxor Bot Rank {rank}"
            )
    except discord.Forbidden:
        print(
            f"[RANK] {guild.name}: {member} için rol verilemedi. "
            f"Botun 'Rolleri Yönet' yetkisini ve rol sırasını kontrol et."
        )
    except discord.HTTPException as e:
        print(f"[RANK] Rol işlemi hatası: {e}")


async def sync_member_rank_role(member):
    if member.bot:
        return
    user = get_user_rank(member.guild.id, member.id)
    rank = get_rank(user.get("seconds", 0))
    if rank > 0:
        await set_rank_role(member, rank)


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

    # Mevcut kullanıcıların rank rollerini de kontrol et
    for guild in bot.guilds:
        try:
            await ensure_rank_roles(guild)
            for member in guild.members:
                if not member.bot:
                    await sync_member_rank_role(member)
        except Exception as e:
            print(f"[RANK] {guild.name} rol senkronizasyon hatası: {e}")

    print("Bot hazır!")

    global background_started
    if not background_started:
        background_started = True
        await start_background_tasks()

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
        name="🏆 Rank",
        value=(
            "`/rank`\n"
            "`/rank-list`\n"
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
# RANK SİSTEMİ
# =========================================================

@bot.tree.command(
    name="rank",
    description="Aktif sürene göre rank bilgini gösterir."
)
@app_commands.describe(member="Rankını görmek istediğin kullanıcı")
async def rank_command(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    user = get_user_rank(interaction.guild.id, member.id)
    seconds = user["seconds"]
    current, target, progress = rank_progress(seconds)

    if target is None:
        progress_text = "🏆 Maksimum ranka ulaştın!"
    else:
        remaining = target - seconds
        progress_text = (
            f"Sonraki rank: **Rank {current + 1}**\n"
            f"Kalan süre: **{format_duration(remaining)}**"
        )

    embed = discord.Embed(
        title=f"🏆 {member.display_name} Rank",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏅 Rank", value=f"**{current}**", inline=True)
    embed.add_field(name="⏱️ Aktif süre", value=format_duration(seconds), inline=True)
    embed.add_field(name="📈 Durum", value=progress_text, inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="rank-list",
    description="Sunucudaki rank sıralamasını gösterir."
)
async def rank_list(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    guild_data = data["rank"].get(gid, {})

    if not guild_data:
        return await interaction.response.send_message("📊 Henüz rank verisi yok.")

    sorted_users = sorted(
        guild_data.items(),
        key=lambda item: item[1].get("seconds", 0),
        reverse=True
    )

    lines = []
    for i, (uid, info) in enumerate(sorted_users[:10], 1):
        member = interaction.guild.get_member(int(uid))
        if not member:
            continue
        seconds = info.get("seconds", 0)
        lines.append(
            f"**{i}.** {member.mention} — 🏆 Rank **{get_rank(seconds)}** — ⏱️ {format_duration(seconds)}"
        )

    if not lines:
        return await interaction.response.send_message("📊 Henüz rank verisi yok.")

    embed = discord.Embed(
        title="🏆 Kyxor Rank Sıralaması",
        description="\n".join(lines),
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="profile",
    description="Rank profilini gösterir."
)
@app_commands.describe(member="Profilini görmek istediğin kullanıcı")
async def profile(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    user = get_user_rank(interaction.guild.id, member.id)
    seconds = user["seconds"]
    current, target, _ = rank_progress(seconds)

    embed = discord.Embed(
        title=f"👤 {member.display_name}",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏆 Rank", value=str(current), inline=True)
    embed.add_field(name="⏱️ Aktif süre", value=format_duration(seconds), inline=True)
    if target is None:
        embed.add_field(name="🎯 Sonraki", value="Maksimum rank", inline=False)
    else:
        embed.add_field(
            name="🎯 Sonraki rank",
            value=f"Rank {current + 1} • {format_duration(target - seconds)} kaldı",
            inline=False
        )
    await interaction.response.send_message(embed=embed)


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
    if message.author.bot or message.guild is None:
        return

    now = time.time()
    key = (message.guild.id, message.author.id)

    # Aktif süre: kullanıcı mesaj attığında aktif kabul edilir.
    # 5 dakikadan uzun sessizlik tek seferde sayılmaz.
    rank_activity[key] = now
    rank_channel[key] = message.channel.id

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
        if not any(domain in lowered for domain in allowed):
            try:
                await message.delete()
                await message.channel.send(
                    f"🚫 {message.author.mention} izinsiz link gönderemezsin.",
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
    spam_key = (message.guild.id, message.author.id)
    timestamps = spam_cache.get(spam_key, [])
    timestamps = [t for t in timestamps if now - t < 5]
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
                f"🚨 {message.author.mention} spam nedeniyle 30 saniye susturuldu.",
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
# RANK TAKİP SİSTEMİ
# =========================================================

async def rank_tracker_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        await asyncio.sleep(60)
        now = time.time()
        changed = False

        for key, last_active in list(rank_activity.items()):
            if now - last_active > 300:
                del rank_activity[key]
                rank_channel.pop(key, None)
                continue

            guild_id, user_id = key
            user = get_user_rank(guild_id, user_id)
            old_rank = get_rank(user["seconds"])
            user["seconds"] += 60
            new_rank = get_rank(user["seconds"])
            changed = True

            if new_rank > old_rank:
                guild = bot.get_guild(guild_id)
                member = guild.get_member(user_id) if guild else None

                if member:
                    await set_rank_role(member, new_rank)

                channel_id = rank_channel.get(key)
                channel = bot.get_channel(channel_id) if channel_id else None
                if channel:
                    try:
                        await channel.send(
                            f"🎉 <@{user_id}> **Rank {new_rank}** oldun! 🏆\n"
                            f"⏱️ Toplam aktif süren: **{format_duration(user['seconds'])}**"
                        )
                    except Exception:
                        pass

        if changed:
            save_data()


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
    bot.loop.create_task(rank_tracker_loop())

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
