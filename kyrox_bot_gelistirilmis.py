import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import os
import random
from datetime import datetime, timezone, timedelta

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
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# =========================================================
# VERİ YÖNETİMİ
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

data.setdefault("warnings", {})
data.setdefault("rank", {})
data.setdefault("settings", {})

# =========================================================
# DEĞİŞKENLER & DEĞERLER
# =========================================================

start_time = datetime.now(timezone.utc)
rank_online = {}
voice_online = {}

# RANK SÜRELERİ (Saniye Cinsinden)
RANK_TIMES = [
    2 * 60 * 60,         # Rank 1 - 2 saat
    6 * 60 * 60,         # Rank 2 - 6 saat
    12 * 60 * 60,        # Rank 3 - 12 saat
    24 * 60 * 60,        # Rank 4 - 1 gün
    3 * 24 * 60 * 60,    # Rank 5 - 3 gün
    7 * 24 * 60 * 60,    # Rank 6 - 1 hafta
    14 * 24 * 60 * 60,   # Rank 7 - 2 hafta
    30 * 24 * 60 * 60,   # Rank 8 - 1 ay
    60 * 24 * 60 * 60,   # Rank 9 - 2 ay
    90 * 24 * 60 * 60,   # Rank 10 - 3 ay
]

# SUNUCUNDAKİ VAR OLAN ROL ID'LERİ (Sayısal Olarak)
RANK_ROLES = {
    1: Yeni Uye,      # Rank 1 Rol ID
    2: Aktif Uye,     # Rank 2 Rol ID
    3: Sohbetçi,      # Rank 3 Rol ID
    4: Tecrubeli,     # Rank 4 Rol ID
    5: Kıdemli,       # Rank 5 Rol ID
    6: Usta,          # Rank 6 Rol ID
    7: Elit,          # Rank 7 Rol ID
    8: Efsane,        # Rank 8 Rol ID
    9: Şampiyon,      # Rank 9 Rol ID
    10: Kyrox Efsanesi # Rank 10 Rol ID
}

BAD_WORDS = ["küfür1", "küfür2", "amk", "aq", "pic", "sik", "piç"]

# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

def get_guild_data(guild_id):
    gid = str(guild_id)
    if gid not in data["settings"]:
        data["settings"][gid] = {
            "log_channel": 0,
            "welcome_channel": 0,
            "auto_role": 0,
            "ticket_category": 0,
            "automod": True
        }
    return data["settings"][gid]

def get_user_rank(guild_id, user_id):
    gid, uid = str(guild_id), str(user_id)
    data["rank"].setdefault(gid, {})
    data["rank"][gid].setdefault(uid, {"seconds": 0})
    return data["rank"][gid][uid]

def get_rank(seconds):
    rank = 0
    for required in RANK_TIMES:
        if seconds >= required: rank += 1
        else: break
    return min(rank, len(RANK_TIMES))

def format_duration(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts = []
    if days: parts.append(f"{days} gün")
    if hours: parts.append(f"{hours} saat")
    if minutes or not parts: parts.append(f"{minutes} dk")
    return " ".join(parts)

def rank_progress(seconds):
    current = get_rank(seconds)
    if current >= len(RANK_TIMES): return (current, None, 0)
    previous = RANK_TIMES[current - 1] if current > 0 else 0
    target = RANK_TIMES[current]
    progress = max(0, min(seconds - previous, target - previous))
    return (current, target, progress)

async def set_rank_role(member, rank):
    if rank <= 0 or member.bot: return
    guild = member.guild
    
    target_role_id = RANK_ROLES.get(rank)
    if not target_role_id or not isinstance(target_role_id, int): return
    
    target_role = guild.get_role(target_role_id)
    if not target_role or not guild.me or target_role >= guild.me.top_role: return

    all_rank_role_ids = set([v for v in RANK_ROLES.values() if isinstance(v, int)])
    old_roles = [r for r in member.roles if r.id in all_rank_role_ids and r.id != target_role_id]
    
    try:
        if old_roles: 
            await member.remove_roles(*old_roles)
        if target_role not in member.roles: 
            await member.add_roles(target_role)
    except Exception: pass

async def send_log(guild, title, description, color=discord.Color.blue()):
    if not guild: return
    settings = get_guild_data(guild.id)
    cid = settings.get("log_channel", 0)
    if not cid: return
    channel = guild.get_channel(cid)
    if channel:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
        try: await channel.send(embed=embed)
        except Exception: pass

# =========================================================
# BUTTON & VIEW SINIFLARI (TICKET & ÇEKİLİŞ)
# =========================================================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Destek Talebi Aç", style=discord.ButtonStyle.primary, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        settings = get_guild_data(guild.id)
        cat_id = settings.get("ticket_category", 0)
        category = guild.get_channel(cat_id) if cat_id else None

        channel_name = f"ticket-{interaction.user.name}"
        existing = discord.utils.get(guild.channels, name=channel_name)
        if existing:
            return await interaction.response.send_message(f"❌ Zaten açık bir biletiniz var: {existing.mention}", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        ticket_chan = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        
        embed = discord.Embed(
            title="🎫 Destek Talebi Oluşturuldu",
            description=f"Merhaba {interaction.user.mention}, yetkililer kısa süre içinde ilgilenecektir.\nBileti kapatmak için aşağıdaki butona basabilirsiniz.",
            color=discord.Color.green()
        )
        await ticket_chan.send(embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"✅ Biletiniz oluşturuldu: {ticket_chan.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Bileti Kapat", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Bu bilet 5 saniye içinde silinecektir...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.participants = set()

    @discord.ui.button(label="🎉 Katıl", style=discord.ButtonStyle.success, custom_id="join_giveaway_btn")
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            self.participants.remove(interaction.user.id)
            await interaction.response.send_message("❌ Çekilişten ayrıldınız.", ephemeral=True)
        else:
            self.participants.add(interaction.user.id)
            await interaction.response.send_message("✅ Çekilişe başarıyla katıldınız!", ephemeral=True)

# =========================================================
# BOT EVENTS
# =========================================================

@bot.event
async def on_ready():
    print("=" * 50)
    print(f"Kyxor Bot Aktif: {bot.user}")
    print("=" * 50)

    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(GiveawayView())

    try:
        if TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"TEST SUNUCUSU Komutları Senkronize: {len(synced)}")
        else:
            synced = await bot.tree.sync()
            print(f"GLOBAL Komutlar Senkronize: {len(synced)}")
    except Exception as e:
        print("Sync Hatası:", e)

    for guild in bot.guilds:
        for member in guild.members:
            if not member.bot:
                rank_online[(guild.id, member.id)] = (member.status != discord.Status.offline)

    if not rank_updater_task.is_running():
        rank_updater_task.start()

@bot.event
async def on_member_join(member):
    if member.bot: return
    guild = member.guild
    settings = get_guild_data(guild.id)

    # Oto Rol
    auto_role_id = settings.get("auto_role", 0)
    if auto_role_id:
        role = guild.get_role(auto_role_id)
        if role:
            try: await member.add_roles(role)
            except Exception: pass

    # Hoş Geldin Mesajı
    welcome_id = settings.get("welcome_channel", 0)
    if welcome_id:
        chan = guild.get_channel(welcome_id)
        if chan:
            embed = discord.Embed(
                title="👋 Ailemize Hoş Geldin!",
                description=f"{member.mention} sunucumuza katıldı! Seninle birlikte **{guild.member_count}** kişi olduk.",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await chan.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return

    settings = get_guild_data(message.guild.id)
    if settings.get("automod", True):
        content_lower = message.content.lower()
        contains_bad_word = any(w in content_lower for w in BAD_WORDS)
        contains_link = "discord.gg/" in content_lower or "http://" in content_lower or "https://" in content_lower

        if contains_bad_word or contains_link:
            try:
                await message.delete()
                warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, reklam veya uygunsuz kelime kullanımı yasaktır!")
                await asyncio.sleep(3)
                await warn_msg.delete()
            except Exception: pass
            return

    await bot.process_commands(message)

@bot.event
async def on_presence_update(before, after):
    if not after.bot and after.guild:
        rank_online[(after.guild.id, after.id)] = (after.status != discord.Status.offline)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    if after.channel and not before.channel:
        voice_online[(member.guild.id, member.id)] = True
    elif before.channel and not after.channel:
        voice_online.pop((member.guild.id, member.id), None)

# =========================================================
# SLASH KOMUTLARI
# =========================================================

@bot.tree.command(name="ping", description="Botun ping değerini gösterir.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.tree.command(name="help", description="Tüm komut listesini gösterir.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Kyxor Bot Komut Rehberi", color=discord.Color.blurple())
    embed.add_field(name="🛡️ Moderasyon", value="`/clear`, `/warn`, `/warnings`, `/mute`, `/unmute`, `/kick`, `/ban`, `/unban`, `/slowmode`, `/lock`, `/unlock`", inline=False)
    embed.add_field(name="🏆 Rank & Profil", value="`/rank`, `/rank-list`, `/profile`", inline=False)
    embed.add_field(name="⚙️ Sunucu Ayarları", value="`/set-welcome`, `/set-autorole`, `/set-log`, `/ticket-setup`", inline=False)
    embed.add_field(name="🎉 Eğlence & Etkileşim", value="`/giveaway`, `/poll`, `/say`, `/announce`", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="clear", description="Mesajları siler.")
@app_commands.describe(amount="Silinecek mesaj sayısı")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 **{len(deleted)}** mesaj silindi.", ephemeral=True)

@bot.tree.command(name="warn", description="Kullanıcıya uyarı verir.")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Sebep yok"):
    gid, uid = str(interaction.guild.id), str(member.id)
    data["warnings"].setdefault(gid, {}).setdefault(uid, []).append({"reason": reason, "time": datetime.now(timezone.utc).isoformat()})
    save_data()
    await interaction.response.send_message(f"⚠️ {member.mention} uyarıldı. Sebep: **{reason}**")

@bot.tree.command(name="warnings", description="Kullanıcının uyarılarını gösterir.")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    gid, uid = str(interaction.guild.id), str(member.id)
    warns = data["warnings"].get(gid, {}).get(uid, [])
    if not warns:
        return await interaction.response.send_message(f"✅ {member.mention} kullanıcısının uyarısı yok.")
    txt = "\n".join([f"**{i}.** {w['reason']}" for i, w in enumerate(warns[-10:], 1)])
    embed = discord.Embed(title=f"⚠️ {member.display_name} Uyarıları", description=txt, color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mute", description="Kullanıcıyı susturur.")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Sebep yok"):
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"🔇 {member.mention} **{minutes} dakika** susturuldu.")

@bot.tree.command(name="unmute", description="Susturmayı kaldırır.")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"🔊 {member.mention} susturması kaldırıldı.")

@bot.tree.command(name="kick", description="Kullanıcıyı atar.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Sebep yok"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 {member.mention} atıldı.")

@bot.tree.command(name="ban", description="Kullanıcıyı yasaklar.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Sebep yok"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 {member.mention} yasaklandı.")

@bot.tree.command(name="unban", description="Ban kaldırır.")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user)
    await interaction.response.send_message(f"🔓 **{user}** banı kaldırıldı.")

@bot.tree.command(name="slowmode", description="Yavaş mod ayarlar.")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"⏱️ Yavaş mod **{seconds}sn** yapıldı.")

@bot.tree.command(name="lock", description="Kanalı kilitler.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    ow = interaction.channel.overwrites_for(interaction.guild.default_role)
    ow.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
    await interaction.response.send_message("🔒 Kanal kilitlendi.")

@bot.tree.command(name="unlock", description="Kanal kilidini açar.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    ow = interaction.channel.overwrites_for(interaction.guild.default_role)
    ow.send_messages = None
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
    await interaction.response.send_message("🔓 Kanal kilidi açıldı.")

# --- RANK & PROFİL ---
@bot.tree.command(name="rank", description="Rank durumunu gösterir.")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    if member.bot: return await interaction.response.send_message("Botların rankı yoktur.", ephemeral=True)
    u = get_user_rank(interaction.guild.id, member.id)
    sec = u.get("seconds", 0)
    current, target, _ = rank_progress(sec)
    
    role_id = RANK_ROLES.get(current)
    role_mention = f"<@&{role_id}>" if role_id and isinstance(role_id, int) else "Ranksız"

    embed = discord.Embed(title=f"🏆 {member.display_name} Rank Bilgisi", color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Mevcut Rank", value=f"**Seviye {current}** - {role_mention}", inline=False)
    embed.add_field(name="Aktiflik Süresi", value=format_duration(sec), inline=False)
    if target:
        embed.add_field(name="Sonraki Ranka Kalan", value=format_duration(target - sec), inline=False)
    else:
        embed.add_field(name="Sonraki Rank", value="👑 Maksimum Seviye!", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rank-list", description="En aktif 10 üyeyi sıralar.")
async def rank_list(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    gr = data["rank"].get(gid, {})
    if not gr: return await interaction.response.send_message("Henüz veri yok.")
    sorted_r = sorted(gr.items(), key=lambda x: x[1].get("seconds", 0), reverse=True)[:10]

    desc = ""
    for idx, (uid, udata) in enumerate(sorted_r, 1):
        m = interaction.guild.get_member(int(uid))
        name = m.mention if m else f"Kullanıcı ({uid})"
        s = udata.get("seconds", 0)
        desc += f"**{idx}.** {name} — **{format_duration(s)}** (Rank {get_rank(s)})\n"
    embed = discord.Embed(title="🏆 Aktiflik Sıralaması", description=desc, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="profile", description="Profil kartını gösterir.")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    u_rank = get_user_rank(interaction.guild.id, member.id)
    sec = u_rank.get("seconds", 0)
    current, _, _ = rank_progress(sec)
    
    role_id = RANK_ROLES.get(current)
    role_mention = f"<@&{role_id}>" if role_id and isinstance(role_id, int) else "Ranksız"

    embed = discord.Embed(title=f"👤 {member.display_name} Profili", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="Rank", value=f"**Seviye {current}** ({role_mention})", inline=True)
    embed.add_field(name="Sohbet / Ses Süresi", value=format_duration(sec), inline=False)
    await interaction.response.send_message(embed=embed)

# --- SUNUCU AYARLARI ---
@bot.tree.command(name="set-welcome", description="Hoş geldin kanalını ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    s = get_guild_data(interaction.guild.id)
    s["welcome_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Hoş geldin kanalı {channel.mention} olarak ayarlandı.")

@bot.tree.command(name="set-autorole", description="Oto-rolü ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def set_autorole(interaction: discord.Interaction, role: discord.Role):
    s = get_guild_data(interaction.guild.id)
    s["auto_role"] = role.id
    save_data()
    await interaction.response.send_message(f"✅ Otomatik verilecek rol {role.mention} olarak ayarlandı.")

@bot.tree.command(name="set-log", description="Log kanalını ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, channel: discord.TextChannel):
    s = get_guild_data(interaction.guild.id)
    s["log_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Log kanalı {channel.mention} olarak ayarlandı.")

@bot.tree.command(name="ticket-setup", description="Destek bileti sistemini kurar.")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_setup(interaction: discord.Interaction, category: discord.CategoryChannel = None):
    if category:
        s = get_guild_data(interaction.guild.id)
        s["ticket_category"] = category.id
        save_data()
    
    embed = discord.Embed(
        title="🎫 Destek & İletişim",
        description="Bir sorununuz veya talebiniz varsa aşağıdaki butona basarak destek talebi oluşturabilirsiniz.",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Destek sistemi kanala kuruldu.", ephemeral=True)

# --- EĞLENCE & DİĞER ---
@bot.tree.command(name="say", description="Bota mesaj yazdırır.")
@app_commands.checks.has_permissions(manage_messages=True)
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("✅ Gönderildi.", ephemeral=True)
    await interaction.channel.send(message)

@bot.tree.command(name="announce", description="Duyuru yaptırır.")
@app_commands.checks.has_permissions(administrator=True)
async def announce(interaction: discord.Interaction, title: str, message: str):
    embed = discord.Embed(title=title, description=message, color=discord.Color.brand_green())
    embed.set_footer(text=f"Duyuran: {interaction.user.display_name}")
    await interaction.response.send_message("📢 Duyuru yayınlandı.", ephemeral=True)
    await interaction.channel.send(embed=embed)

@bot.tree.command(name="poll", description="Anket oluşturur.")
async def poll(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title="📊 Anket", description=f"**{question}**", color=discord.Color.gold())
    embed.set_footer(text=f"Oluşturan: {interaction.user.display_name}")
    await interaction.response.send_message("Anket başlatıldı.", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.tree.command(name="giveaway", description="Çekiliş başlatır.")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, prize: str, duration_minutes: int, winners: int = 1):
    view = GiveawayView()
    embed = discord.Embed(
        title="🎉 ÇEKİLİŞ BAŞLADI!",
        description=f"**Ödül:** {prize}\n**Kazanan Sayısı:** {winners}\n**Süre:** {duration_minutes} dakika\n\nKatılmak için aşağıdaki **🎉 Katıl** butonuna basın!",
        color=discord.Color.brand_green()
    )
    await interaction.response.send_message("Çekiliş oluşturuldu.", ephemeral=True)
    msg = await interaction.channel.send(embed=embed, view=view)

    await asyncio.sleep(duration_minutes * 60)

    if not view.participants:
        await interaction.channel.send(f"🎉 **{prize}** çekilişi sona erdi. Katılan olmadığı için kazanan seçilemedi.")
    else:
        winner_ids = random.sample(list(view.participants), min(winners, len(view.participants)))
        winner_mentions = ", ".join([f"<@{uid}>" for uid in winner_ids])
        await interaction.channel.send(f"🎉 Tebrikler {winner_mentions}! **{prize}** çekilişini kazandınız!")

# =========================================================
# ARKA PLAN DÖNGÜSÜ (RANK UPDATER)
# =========================================================

@tasks.loop(seconds=60)
async def rank_updater_task():
    # 1. Çevrimiçi Aktiflik & Rank Güncellemesi
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
                    if member: await set_rank_role(member, new_rank)

    # 2. Ses Aktifliği (+1 Dakika Aktiflik)
    for (gid, uid) in list(voice_online.keys()):
        u_rank = get_user_rank(gid, uid)
        u_rank["seconds"] += 60

    save_data()

@rank_updater_task.before_loop
async def before_rank_updater():
    await bot.wait_until_ready()

# =========================================================
# BOTU BAŞLAT
# =========================================================

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ HATA: 'BOT_TOKEN' çevre değişkeni bulunamadı!")
    else:
        bot.run(BOT_TOKEN)
