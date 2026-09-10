import os
import time
import discord

from discord.ext import commands
from discord import app_commands


# =========================================================
# AYARLAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# İsteğe bağlı:
# Discord kanal / rol ID'lerini buraya yazabilirsin.
# Kullanmayacaksan 0 bırak.
LOG_CHANNEL_ID = 0
AUTO_ROLE_ID = 0
TICKET_CATEGORY_ID = 0


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
    help_command=None
)

start_time = time.time()


# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

def get_log_channel(guild: discord.Guild):
    if LOG_CHANNEL_ID == 0:
        return None

    channel = guild.get_channel(LOG_CHANNEL_ID)

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


def format_uptime():
    seconds = int(time.time() - start_time)

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    return f"{days}g {hours}s {minutes}dk {seconds}sn"


# =========================================================
# BOT AÇILDI
# =========================================================

@bot.event
async def on_ready():

    print("=" * 50)
    print(f"Bot aktif: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Sunucu sayısı: {len(bot.guilds)}")
    print("=" * 50)

    # Slash komutları senkronize et
    try:
        synced = await bot.tree.sync()

        print(f"Global komutlar senkronize edildi: {len(synced)}")

    except Exception as e:
        print(f"Global sync hatası: {e}")

    # Ticket butonunu yeniden aktif et
    bot.add_view(TicketView())

    print("Ticket sistemi hazır.")


# =========================================================
# ÜYE KATILDI
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):

    # Otomatik rol
    if AUTO_ROLE_ID != 0:

        role = member.guild.get_role(AUTO_ROLE_ID)

        if role:

            try:
                await member.add_roles(
                    role,
                    reason="Otomatik üye rolü"
                )

            except discord.Forbidden:
                print(
                    f"Rol verilemedi: {member} "
                    f"(Botun rolü yeterince yukarıda olmayabilir.)"
                )

    # Hoş geldin mesajı
    channel = member.guild.system_channel

    if channel:

        embed = discord.Embed(
            title="👋 Hoş Geldin!",
            description=(
                f"Hoş geldin {member.mention}!\n\n"
                f"**{member.guild.name}** sunucusuna katıldın."
            ),
            color=discord.Color.green()
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.set_footer(
            text=f"Üye sayısı: {member.guild.member_count}"
        )

        try:
            await channel.send(embed=embed)

        except discord.Forbidden:
            pass

    # Log
    log_channel = get_log_channel(member.guild)

    if log_channel:

        embed = discord.Embed(
            title="📥 Yeni Üye",
            description=f"{member.mention} sunucuya katıldı.",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Kullanıcı",
            value=str(member),
            inline=True
        )

        embed.add_field(
            name="ID",
            value=str(member.id),
            inline=True
        )

        await log_channel.send(embed=embed)


# =========================================================
# ÜYE AYRILDI
# =========================================================

@bot.event
async def on_member_remove(member: discord.Member):

    log_channel = get_log_channel(member.guild)

    if log_channel:

        embed = discord.Embed(
            title="📤 Üye Ayrıldı",
            description=f"**{member}** sunucudan ayrıldı.",
            color=discord.Color.red()
        )

        embed.add_field(
            name="ID",
            value=str(member.id),
            inline=True
        )

        await log_channel.send(embed=embed)


# =========================================================
# PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Botun gecikmesini gösterir."
)
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot gecikmesi: **{latency}ms**",
        color=discord.Color.green()
    )

    await interaction.response.send_message(
        embed=embed
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
        name="ℹ️ Genel",
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
            "`/kick`\n"
            "`/ban`\n"
            "`/unban`"
        ),
        inline=False
    )

    embed.add_field(
        name="📢 Yönetim",
        value=(
            "`/say`\n"
            "`/announce`"
        ),
        inline=False
    )

    embed.add_field(
        name="🎫 Ticket",
        value="`/ticket-panel`",
        inline=False
    )

    embed.set_footer(
        text="Kyxor Bot"
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


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

        await interaction.response.send_message(
            "Bu komut sadece sunucuda kullanılabilir.",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title=f"🌐 {guild.name}",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="👥 Üye",
        value=str(guild.member_count),
        inline=True
    )

    embed.add_field(
        name="💬 Kanal",
        value=str(len(guild.channels)),
        inline=True
    )

    embed.add_field(
        name="🎭 Rol",
        value=str(len(guild.roles)),
        inline=True
    )

    embed.add_field(
        name="🆔 Sunucu ID",
        value=str(guild.id),
        inline=False
    )

    if guild.owner:
        embed.add_field(
            name="👑 Sahip",
            value=guild.owner.mention,
            inline=False
        )

    if guild.icon:
        embed.set_thumbnail(
            url=guild.icon.url
        )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# USERINFO
# =========================================================

@bot.tree.command(
    name="userinfo",
    description="Kullanıcı bilgilerini gösterir."
)
@app_commands.describe(
    user="Bilgisini görmek istediğin kullanıcı"
)
async def userinfo(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):

    user = user or interaction.user

    embed = discord.Embed(
        title=f"👤 {user.display_name}",
        color=user.color
    )

    embed.add_field(
        name="Kullanıcı",
        value=str(user),
        inline=False
    )

    embed.add_field(
        name="ID",
        value=str(user.id),
        inline=False
    )

    embed.add_field(
        name="Bot mu?",
        value="Evet" if user.bot else "Hayır",
        inline=True
    )

    if user.joined_at:

        embed.add_field(
            name="Katılma tarihi",
            value=discord.utils.format_dt(
                user.joined_at,
                style="D"
            ),
            inline=False
        )

    embed.set_thumbnail(
        url=user.display_avatar.url
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# AVATAR
# =========================================================

@bot.tree.command(
    name="avatar",
    description="Kullanıcının profil fotoğrafını gösterir."
)
@app_commands.describe(
    user="Avatarını görmek istediğin kullanıcı"
)
async def avatar(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):

    user = user or interaction.user

    embed = discord.Embed(
        title=f"🖼️ {user.display_name} - Avatar",
        color=discord.Color.blurple()
    )

    embed.set_image(
        url=user.display_avatar.url
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# UPTIME
# =========================================================

@bot.tree.command(
    name="uptime",
    description="Botun ne kadar süredir açık olduğunu gösterir."
)
async def uptime(interaction: discord.Interaction):

    embed = discord.Embed(
        title="⏱️ Bot Uptime",
        description=f"Bot **{format_uptime()}** süredir açık.",
        color=discord.Color.green()
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(
    name="clear",
    description="Mesajları temizler."
)
@app_commands.describe(
    amount="Silinecek mesaj sayısı (1-100)"
)
@app_commands.default_permissions(
    manage_messages=True
)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):

    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):

        await interaction.response.send_message(
            "Bu komut sadece yazı kanallarında kullanılabilir.",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        deleted = await channel.purge(
            limit=amount
        )

        await interaction.followup.send(
            f"🧹 **{len(deleted)}** mesaj temizlendi.",
            ephemeral=True
        )

        log_channel = get_log_channel(
            interaction.guild
        )

        if log_channel:

            embed = discord.Embed(
                title="🧹 Mesajlar Temizlendi",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="Yetkili",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="Miktar",
                value=str(len(deleted)),
                inline=True
            )

            embed.add_field(
                name="Kanal",
                value=channel.mention,
                inline=True
            )

            await log_channel.send(
                embed=embed
            )

    except discord.Forbidden:

        await interaction.followup.send(
            "❌ Mesajları silmek için yetkim yok.",
            ephemeral=True
        )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Bir kullanıcıyı sunucudan atar."
)
@app_commands.describe(
    user="Atılacak kullanıcı",
    reason="Atılma sebebi"
)
@app_commands.default_permissions(
    kick_members=True
)
async def kick(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "Sebep belirtilmedi"
):

    if user == interaction.user:

        await interaction.response.send_message(
            "Kendini atamazsın.",
            ephemeral=True
        )

        return

    if user.top_role >= interaction.user.top_role:

        await interaction.response.send_message(
            "Bu kullanıcıyı atamazsın. Rolü senden yüksek veya eşit.",
            ephemeral=True
        )

        return

    try:

        await user.kick(
            reason=reason
        )

        await interaction.response.send_message(
            f"👢 {user.mention} sunucudan atıldı.\n"
            f"**Sebep:** {reason}"
        )

        log_channel = get_log_channel(
            interaction.guild
        )

        if log_channel:

            embed = discord.Embed(
                title="👢 Kullanıcı Atıldı",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="Kullanıcı",
                value=str(user),
                inline=False
            )

            embed.add_field(
                name="Yetkili",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="Sebep",
                value=reason,
                inline=False
            )

            await log_channel.send(
                embed=embed
            )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Bu kullanıcıyı atmak için yetkim yok.",
            ephemeral=True
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Bir kullanıcıyı sunucudan yasaklar."
)
@app_commands.describe(
    user="Yasaklanacak kullanıcı",
    reason="Yasaklama sebebi"
)
@app_commands.default_permissions(
    ban_members=True
)
async def ban(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "Sebep belirtilmedi"
):

    if user == interaction.user:

        await interaction.response.send_message(
            "Kendini banlayamazsın.",
            ephemeral=True
        )

        return

    if user.top_role >= interaction.user.top_role:

        await interaction.response.send_message(
            "Bu kullanıcıyı banlayamazsın. Rolü senden yüksek veya eşit.",
            ephemeral=True
        )

        return

    try:

        await user.ban(
            reason=reason
        )

        await interaction.response.send_message(
            f"🔨 {user.mention} sunucudan banlandı.\n"
            f"**Sebep:** {reason}"
        )

        log_channel = get_log_channel(
            interaction.guild
        )

        if log_channel:

            embed = discord.Embed(
                title="🔨 Kullanıcı Banlandı",
                color=discord.Color.red()
            )

            embed.add_field(
                name="Kullanıcı",
                value=str(user),
                inline=False
            )

            embed.add_field(
                name="Yetkili",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="Sebep",
                value=reason,
                inline=False
            )

            await log_channel.send(
                embed=embed
            )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Bu kullanıcıyı banlamak için yetkim yok.",
            ephemeral=True
        )


# =========================================================
# UNBAN
# =========================================================

@bot.tree.command(
    name="unban",
    description="ID ile ban kaldırır."
)
@app_commands.describe(
    user_id="Banı kaldırılacak kullanıcının ID'si"
)
@app_commands.default_permissions(
    ban_members=True
)
async def unban(
    interaction: discord.Interaction,
    user_id: str
):

    try:

        user = await bot.fetch_user(
            int(user_id)
        )

        await interaction.guild.unban(
            user
        )

        await interaction.response.send_message(
            f"🔓 {user} kullanıcısının banı kaldırıldı."
        )

    except ValueError:

        await interaction.response.send_message(
            "❌ Geçerli bir kullanıcı ID'si gir.",
            ephemeral=True
        )

    except discord.NotFound:

        await interaction.response.send_message(
            "❌ Bu kullanıcı banlı değil.",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ Ban kaldırmak için yetkim yok.",
            ephemeral=True
        )


# =========================================================
# SAY
# =========================================================

@bot.tree.command(
    name="say",
    description="Botun belirttiğin mesajı göndermesini sağlar."
)
@app_commands.describe(
    message="Gönderilecek mesaj"
)
@app_commands.default_permissions(
    manage_messages=True
)
async def say(
    interaction: discord.Interaction,
    message: str
):

    await interaction.response.send_message(
        "Mesaj gönderildi.",
        ephemeral=True
    )

    await interaction.channel.send(
        message
    )


# =========================================================
# ANNOUNCE
# =========================================================

@bot.tree.command(
    name="announce",
    description="Şık bir duyuru gönderir."
)
@app_commands.describe(
    title="Duyuru başlığı",
    message="Duyuru mesajı"
)
@app_commands.default_permissions(
    manage_messages=True
)
async def announce(
    interaction: discord.Interaction,
    title: str,
    message: str
):

    embed = discord.Embed(
        title=f"📢 {title}",
        description=message,
        color=discord.Color.gold()
    )

    embed.set_footer(
        text=f"Duyuran: {interaction.user}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# TICKET SİSTEMİ
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Ticket Aç",
        emoji="🎫",
        style=discord.ButtonStyle.green,
        custom_id="kyxor_ticket_open"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "Bu buton sadece sunucuda kullanılabilir.",
                ephemeral=True
            )

            return

        # Zaten ticket var mı?
        for channel in guild.text_channels:

            if channel.name == f"ticket-{interaction.user.id}":

                await interaction.response.send_message(
                    f"❌ Zaten açık bir ticketın var: {channel.mention}",
                    ephemeral=True
                )

                return

        # Kategori
        category = None

        if TICKET_CATEGORY_ID != 0:

            category = guild.get_channel(
                TICKET_CATEGORY_ID
            )

            if not isinstance(
                category,
                discord.CategoryChannel
            ):
                category = None

        # Ticket kanal izinleri
        overwrites = {

            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),

            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            ),

            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )
        }

        # Yönetici rolleri de görebilsin
        for role in guild.roles:

            if role.permissions.manage_guild:

                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        try:

            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.id}",
                category=category,
                overwrites=overwrites,
                reason="Ticket oluşturuldu"
            )

            embed = discord.Embed(
                title="🎫 Ticket",
                description=(
                    f"Merhaba {interaction.user.mention}!\n\n"
                    "Yetkililer en kısa sürede seninle ilgilenecektir.\n\n"
                    "Ticketı kapatmak için aşağıdaki "
                    "**Ticket Kapat** butonuna bas."
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

            log_channel = get_log_channel(guild)

            if log_channel:

                await log_channel.send(
                    f"🎫 {interaction.user.mention} "
                    f"ticket açtı: {channel.mention}"
                )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ Ticket kanalı oluşturmak için yetkim yok.",
                ephemeral=True
            )


class CloseTicketView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Ticket Kapat",
        emoji="🔒",
        style=discord.ButtonStyle.red,
        custom_id="kyxor_ticket_close"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            return

        await interaction.response.send_message(
            "🔒 Ticket 5 saniye içinde kapatılıyor..."
        )

        await discord.utils.sleep_until(
            discord.utils.utcnow()
            + discord.utils.timedelta(seconds=5)
        )

        try:

            await channel.delete(
                reason=f"Ticket kapatıldı: {interaction.user}"
            )

        except discord.NotFound:
            pass


# =========================================================
# TICKET PANEL
# =========================================================

@bot.tree.command(
    name="ticket-panel",
    description="Ticket açma paneli gönderir."
)
@app_commands.default_permissions(
    manage_guild=True
)
async def ticket_panel(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🎫 Destek Sistemi",
        description=(
            "Yardıma mı ihtiyacın var?\n\n"
            "Aşağıdaki **Ticket Aç** butonuna basarak "
            "özel destek kanalı oluşturabilirsin."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="Kyxor Destek Sistemi"
    )

    await interaction.response.send_message(
        embed=embed,
        view=TicketView()
    )


# =========================================================
# HATA SİSTEMİ
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        message = (
            "❌ Bu komutu kullanmak için "
            "gerekli yetkiye sahip değilsin."
        )

    elif isinstance(
        error,
        app_commands.BotMissingPermissions
    ):

        message = (
            "❌ Botun gerekli Discord yetkilerine sahip değil."
        )

    else:

        print(
            f"Komut hatası: {error}"
        )

        message = (
            "❌ Komut çalıştırılırken bir hata oluştu."
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
# TOKEN KONTROL
# =========================================================

if not BOT_TOKEN:

    print(
        "❌ HATA: BOT_TOKEN bulunamadı!"
    )

    print(
        "GitHub/hosting ortamındaki Secrets bölümüne "
        "BOT_TOKEN eklemelisin."
    )

else:

    bot.run(BOT_TOKEN)
