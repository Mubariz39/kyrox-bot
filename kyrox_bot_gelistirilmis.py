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
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

DATA_FILE = "kyxor_data.json"

# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

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
            with open(
                DATA_FILE,
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)
    except Exception as e:
        print("Veri yükleme hatası:", e)


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
        print("Veri kaydetme hatası:", e)


load_data()

data.setdefault("warnings", {})
data.setdefault("rank", {})
data.setdefault("settings", {})


# =========================================================
# YARDIMCI DEĞİŞKENLER
# =========================================================

start_time = time.time()
spam_cache = {}
rank_online = {}
background_started = False


# =========================================================
# RANK SÜRELERİ (GÜNCELLENDİ)
# =========================================================

RANK_TIMES = [
    2 * 60 * 60,         # Rank 1 - 2 saat
    6 * 60 * 60,         # Rank 2 - 6 saat
    12 * 60 * 60,        # Rank 3 - 12 saat
    24 * 60 * 60,        # Rank 4 - 1 gün (24 saat)
    3 * 24 * 60 * 60,    # Rank 5 - 3 gün (72 saat)
    7 * 24 * 60 * 60,    # Rank 6 - 1 hafta (168 saat)
    14 * 24 * 60 * 60,   # Rank 7 - 2 hafta (336 saat)
    30 * 24 * 60 * 60,   # Rank 8 - 1 ay (720 saat)
    60 * 24 * 60 * 60,   # Rank 9 - 2 ay (1440 saat)
    90 * 24 * 60 * 60,   # Rank 10 - 3 ay (2160 saat)
]


# =========================================================
# RANK ROLLERİ
# =========================================================

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
    10: ("Kyxor Efsanesi", discord.Color.from_rgb(255, 215, 0))
}


# =========================================================
# SUNUCU VE USER VERİLERİ
# =========================================================

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
        return (current, None, 0)

    previous = RANK_TIMES[current - 1] if current > 0 else 0
    target = RANK_TIMES[current]
    progress = max(0, min(seconds - previous, target - previous))
    return (current, target, progress)


# =========================================================
# ROL YÖNETİMİ
# =========================================================

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
        print(f"[RANK] {guild.name}: {target_role.name} verilemedi. Botun rolü rank rollerinin üstünde olmalı.")
        return

    rank_role_names = {name for name, _ in RANK_ROLES.values()}
    old_rank_roles = [
        role for role in member.roles
        if role.name in rank_role_names and role != target_role
    ]

    try:
        if old_rank_roles:
            await member.remove_roles(*old_rank_roles, reason="Kyxor Bot rank güncellemesi")
        if target_role not in member.roles:
            await member.add_roles(target_role, reason=f"Kyxor Bot Rank {rank}")
    except Exception as e:
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

    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# =========================================================
# BOT EVENTS
# =========================================================

@bot.event
async def on_ready():
    print("=" * 50)
    print(f"Kyxor Bot giriş yaptı: {bot.user}")
    print(f"Sunucu sayısı: {len(bot.guilds)}")
    print("=" * 50)

    try:
        if TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            synced = await bot.tree.sync(guild=guild)
            print(f"TEST SUNUCUSU slash komutları senkronize edildi: {len(synced)}")
        else:
            synced = await bot.tree.sync()
            print(f"GLOBAL slash komutları senkronize edildi: {len(synced)}")
    except Exception as e:
        print("Slash komut sync hatası:", e)

    for guild in bot.guilds:
        try:
            await ensure_rank_roles(guild)
            for member in guild.members:
                if member.bot:
                    continue
                rank_online[(guild.id, member.id)] = (member.status == discord.Status.online)
                await sync_member_rank_role(member)
        except Exception as e:
            print(f"[RANK] {guild.name} rol senkronizasyon hatası: {e}")

    print("🏆 Rank sistemi aktif!")

    global background_started
    if not background_started:
        background_started = True
        await start_background_tasks()


@bot.event
async def on_presence_update(before, after):
    if after.bot:
        return
    key = (after.guild.id, after.id)
    rank_online[key] = (after.status == discord.Status.online)


@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        text = "❌ Bu komutu kullanmak için yetkin yok."
    elif isinstance(error, app_commands.BotMissingPermissions):
        text = "❌ Botun bu işlem için gerekli yetkileri yok."
    else:
        text = "❌ Komut çalıştırılırken bir hata oluştu."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except Exception:
        pass


# =========================================================
# SLASH KOMUTLARI
# =========================================================

@bot.tree.command(name="ping", description="Botun ping değerini gösterir.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong!\n📡 Ping: **{latency}ms**")


@bot.tree.command(name="help", description="Botun komutlarını gösterir.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Kyxor Bot", description="Kullanabileceğin komutlar:", color=discord.Color.blurple())
    embed.add_field(name="🛠️ Genel", value="`/ping`\n`/server`\n`/userinfo`\n`/avatar`\n`/uptime`", inline=False)
    embed.add_field(name="🛡️ Moderasyon", value="`/clear`\n`/warn`\n`/warnings`\n`/mute`\n`/unmute`\n`/kick`\n`/ban`\n`/unban`\n`/slowmode`\n`/lock`\n`/unlock`", inline=False)
    embed.add_field(name="🏆 Rank", value="`/rank`\n`/rank-list`\n`/profile`", inline=False)
    embed.add_field(name="📢 Diğer", value="`/say`\n`/announce`\n`/social`", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="server", description="Sunucu bilgilerini gösterir.")
async def server(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("Bu komut sunucuda kullanılabilir.")

    embed = discord.Embed(title=f"📊 {guild.name}", color=discord.Color.blue())
    embed.add_field(name="👥 Üyeler", value=str(guild.member_count))
    embed.add_field(name="💬 Kanallar", value=str(len(guild.channels)))
    embed.add_field(name="🎭 Roller", value=str(len(guild.roles)))
    embed.add_field(name="🆔 Sunucu ID", value=str(guild.id))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="Kullanıcı bilgilerini gösterir.")
@app_commands.describe(member="Bilgilerini görmek istediğin kullanıcı")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"👤 {member}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🆔 ID", value=str(member.id), inline=False)
    embed.add_field(name="📅 Hesap oluşturma", value=discord.utils.format_dt(member.created_at, style="F"), inline=False)
    if member.joined_at:
        embed.add_field(name="📥 Sunucuya katılma", value=discord.utils.format_dt(member.joined_at, style="F"), inline=False)
    embed.add_field(name="🎭 Rol", value=member.top_role.mention, inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="Kullanıcının avatarını gösterir.")
@app_commands.describe(member="Avatarını görmek istediğin kullanıcı")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"🖼️ {member.display_name} Avatar", color=discord.Color.blurple())
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="uptime", description="Botun ne kadar süredir açık olduğunu gösterir.")
async def uptime(interaction: discord.Interaction):
    seconds = int(time.time() - start_time)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    await interaction.response.send_message(f"⏱️ Bot çalışma süresi:\n**{days} gün {hours} saat {minutes} dakika {seconds} saniye**")


@bot.tree.command(name="clear", description="Mesajları siler.")
@app_commands.describe(amount="Silinecek mesaj sayısı")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 **{len(deleted)}** mesaj silindi.", ephemeral=True)
    await send_log(interaction.guild, "🧹 Mesajlar Silindi", f"{interaction.user.mention} {len(deleted)} mesaj sildi.", discord.Color.orange())


@bot.tree.command(name="warn", description="Kullanıcıya uyarı verir.")
@app_commands.describe(member="Uyarılacak kullanıcı", reason="Uyarı sebebi")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Sebep belirtilmedi"):
    gid = str(interaction.guild.id)
    uid = str(member.id)

    data["warnings"].setdefault(gid, {}).setdefault(uid, []).append({
        "reason": reason,
        "moderator": interaction.user.id,
        "time": datetime.utcnow().isoformat()
    })
    save_data()

    count = len(data["warnings"][gid][uid])
    await interaction.response.send_message(f"⚠️ {member.mention} uyarıldı.\nSebep: **{reason}**\nToplam uyarı: **{count}**")
    await send_log(interaction.guild, "⚠️ Kullanıcı Uyarıldı", f"{member.mention}\nYetkili: {interaction.user.mention}\nSebep: {reason}", discord.Color.yellow())


@bot.tree.command(name="warnings", description="Kullanıcının uyarılarını gösterir.")
@app_commands.describe(member="Uyarılarını görmek istediğin kullanıcı")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    gid = str(interaction.guild.id)
    uid = str(member.id)
    warnings_list = data["warnings"].get(gid, {}).get(uid, [])

    if not warnings_list:
        return await interaction.response.send_message(f"✅ {member.mention} kullanıcısının uyarısı yok.")

    text = "".join([f"**{i}.** {w['reason']}\n" for i, w in enumerate(warnings_list[-10:], 1)])
    embed = discord.Embed(title=f"⚠️ {member} Uyarıları", description=text, color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="mute", description="Kullanıcıyı susturur.")
@app_commands.describe(member="Susturulacak kullanıcı", minutes="Kaç dakika susturulacak", reason="Sebep")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "Sebep belirtilmedi"):
    if member == interaction.guild.owner:
        return await interaction.response.send_message("❌ Sunucu sahibini susturamazsın.", ephemeral=True)
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("❌ Bu kullanıcı seninle aynı veya daha yüksek role sahip.", ephemeral=True)

    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"🔇 {member.mention} **{minutes} dakika** susturuldu.\nSebep: {reason}")
        await send_log(interaction.guild, "🔇 Kullanıcı Susturuldu", f"{member.mention}\nYetkili: {interaction.user.mention}\nSüre: {minutes} dakika\nSebep: {reason}", discord.Color.red())
    except Exception as e:
        await interaction.response.send_message(f"❌ İşlem başarısız: `{e}`", ephemeral=True)


@bot.tree.command(name="unmute", description="Kullanıcının susturmasını kaldırır.")
@app_commands.describe(member="Susturması kaldırılacak kullanıcı")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None, reason=f"Yetkili: {interaction.user}")
        await interaction.response.send_message(f"🔊 {member.mention} artık susturulmuyor.")
    except Exception as e:
        await interaction.response.send_message(f"❌ İşlem başarısız: `{e}`", ephemeral=True)


@bot.tree.command(name="kick", description="Kullanıcıyı sunucudan atar.")
@app_commands.describe(member="Atılacak kullanıcı", reason="Sebep")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Sebep belirtilmedi"):
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("❌ Bu kullanıcı seninle aynı veya daha yüksek role sahip.", ephemeral=True)
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member} sunucudan atıldı.\nSebep: **{reason}**")
        await send_log(interaction.guild, "👢 Kullanıcı Atıldı", f"Kullanıcı: {member}\nYetkili: {interaction.user.mention}\nSebep: {reason}", discord.Color.red())
    except Exception as e:
        await interaction.response.send_message(f"❌ Hata: `{e}`", ephemeral=True)


@bot.tree.command(name="ban", description="Kullanıcıyı yasaklar.")
@app_commands.describe(member="Yasaklanacak kullanıcı", reason="Sebep")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Sebep belirtilmedi"):
    if member == interaction.guild.owner:
        return await interaction.response.send_message("❌ Sunucu sahibini yasaklayamazsın.", ephemeral=True)
    if member.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("❌ Bu kullanıcı seninle aynı veya daha yüksek role sahip.", ephemeral=True)
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member} yasaklandı.\nSebep: **{reason}**")
        await send_log(interaction.guild, "🔨 Kullanıcı Yasaklandı", f"Kullanıcı: {member}\nYetkili: {interaction.user.mention}\nSebep: {reason}", discord.Color.dark_red())
    except Exception as e:
        await interaction.response.send_message(f"❌ Hata: `{e}`", ephemeral=True)


@bot.tree.command(name="unban", description="Yasaklı kullanıcının banını kaldırır.")
@app_commands.describe(user_id="Kullanıcının Discord ID'si")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=f"Yetkili: {interaction.user}")
        await interaction.response.send_message(f"🔓 **{user}** kullanıcısının banı kaldırıldı.")
    except ValueError:
        await interaction.response.send_message("❌ Geçerli bir kullanıcı ID'si gir.", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("❌ Bu kullanıcı banlı değil veya bulunamadı.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hata oluştu: `{e}`", ephemeral=True)


@bot.tree.command(name="slowmode", description="Kanalın yavaş mod süresini ayarlar.")
@app_commands.describe(seconds="Mesajlar arası bekleme süresi (Saniye - 0 kapatır)")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
    try:
        await interaction.channel.edit(slowmode_delay=seconds)
        msg = "🚀 Yavaş mod kapatıldı." if seconds == 0 else f"⏱️ Yavaş mod **{seconds} saniye** olarak ayarlandı."
        await interaction.response.send_message(msg)
    except Exception as e:
        await interaction.response.send_message(f"❌ İşlem başarısız: `{e}`", ephemeral=True)


@bot.tree.command(name="lock", description="Kanalı mesaj gönderimine kapatır.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔒 Kanal mesaj gönderimine kilitlendi.")
    except Exception as e:
        await interaction.response.send_message(f"❌ İşlem başarısız: `{e}`", ephemeral=True)


@bot.tree.command(name="unlock", description="Kanalın kilidini açar.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 Kanalın kilidi açıldı.")
    except Exception as e:
        await interaction.response.send_message(f"❌ İşlem başarısız: `{e}`", ephemeral=True)


@bot.tree.command(name="rank", description="Rank ve aktiflik bilgini gösterir.")
@app_commands.describe(member="Bakılacak kullanıcı")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    if member.bot:
        return await interaction.response.send_message("🤖 Botların rank verisi bulunmaz.", ephemeral=True)

    user = get_user_rank(interaction.guild.id, member.id)
    seconds = user.get("seconds", 0)
    current, target, _ = rank_progress(seconds)
    role_info = RANK_ROLES.get(current, ("Ranksız", discord.Color.default()))

    embed = discord.Embed(title=f"🏆 {member.display_name} Rank Bilgisi", color=role_info[1])
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Mevcut Rank", value=f"**{current}** - {role_info[0]}", inline=False)
    embed.add_field(name="Toplam Aktiflik", value=format_duration(seconds), inline=False)

    if target:
        embed.add_field(name="Sonraki Rank İçi Süre", value=f"{format_duration(target - seconds)} kaldı", inline=False)
    else:
        embed.add_field(name="Sonraki Rank", value="👑 Maksimum seviyedesin!", inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rank-list", description="Sunucunun en aktif üyelerini sıralar.")
async def rank_list(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    guild_ranks = data["rank"].get(gid, {})

    if not guild_ranks:
        return await interaction.response.send_message("📊 Henüz rank verisi bulunmuyor.")

    sorted_ranks = sorted(guild_ranks.items(), key=lambda x: x[1].get("seconds", 0), reverse=True)[:10]

    description = ""
    for idx, (uid, udata) in enumerate(sorted_ranks, 1):
        member = interaction.guild.get_member(int(uid))
        name = member.mention if member else f"Kullanıcı ({uid})"
        sec = udata.get("seconds", 0)
        description += f"**{idx}.** {name} — **{format_duration(sec)}** (Rank {get_rank(sec)})\n"

    embed = discord.Embed(title=f"🏆 {interaction.guild.name} Aktiflik Liderlik Tablosu", description=description, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="profile", description="Detaylı kullanıcı profil kartını gösterir.")
@app_commands.describe(member="Bakılacak kullanıcı")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user = get_user_rank(interaction.guild.id, member.id)
    seconds = user.get("seconds", 0)
    current, _, _ = rank_progress(seconds)
    role_info = RANK_ROLES.get(current, ("Ranksız", discord.Color.default()))

    gid = str(interaction.guild.id)
    uid = str(member.id)
    warn_count = len(data["warnings"].get(gid, {}).get(uid, []))

    embed = discord.Embed(title=f"👤 {member.display_name} Profili", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="İsim / ID", value=f"{member.mention}\n`{member.id}`", inline=True)
    embed.add_field(name="Rank Unvanı", value=f"**{role_info[0]}** (Rank {current})", inline=True)
    embed.add_field(name="Çevrimiçi Süresi", value=format_duration(seconds), inline=False)
    embed.add_field(name="Uyarı Sayısı", value=f"⚠️ {warn_count}", inline=True)
    embed.add_field(name="Hesap Açılış", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="say", description="Bota mesaj yazdırır.")
@app_commands.describe(message="Yazdırılacak mesaj")
@app_commands.checks.has_permissions(manage_messages=True)
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("✅ Gönderildi.", ephemeral=True)
    await interaction.channel.send(message)


@bot.tree.command(name="announce", description="Duyuru yaptırır (Embed).")
@app_commands.describe(title="Başlık", message="Duyuru metni")
@app_commands.checks.has_permissions(administrator=True)
async def announce(interaction: discord.Interaction, title: str, message: str):
    embed = discord.Embed(title=title, description=message, color=discord.Color.brand_green())
    embed.set_footer(text=f"Duyuran: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message("📢 Duyuru yayınlandı.", ephemeral=True)
    await interaction.channel.send(embed=embed)


@bot.tree.command(name="social", description="Sosyal medya bağlantılarını gösterir.")
async def social(interaction: discord.Interaction):
    embed = discord.Embed(title="🌐 Sosyal Medya & Bağlantılar", description="Bizi aşağıdaki platformlardan takip edebilirsiniz!", color=discord.Color.blurple())
    embed.add_field(name="Website", value="[Tıklayın](https://example.com)", inline=True)
    embed.add_field(name="Discord", value="[Sunucuya Katıl](https://discord.gg)", inline=True)
    await interaction.response.send_message(embed=embed)


# =========================================================
# ARKA PLAN GÖREVLERİ
# =========================================================

async def start_background_tasks():
    bot.loop.create_task(rank_updater_task())


async def rank_updater_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(60)

        for (gid, uid), is_online in list(rank_online.items()):
            if is_online:
                u_rank = get_user_rank(gid, uid)
                old_rank = get_rank(u_rank["seconds"])

                u_rank["seconds"] += 60
                new_rank = get_rank(u_rank["seconds"])

                if new_rank > old_rank:
                    guild = bot.get_guild(gid)
                    if guild:
                        member = guild.get_member(uid)
                        if member:
                            await set_rank_role(member, new_rank)

        save_data()


# =========================================================
# BOTU BAŞLAT
# =========================================================

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ HATA: 'BOT_TOKEN' çevre değişkeni bulunamadı!")
    else:
        bot.run(BOT_TOKEN)
