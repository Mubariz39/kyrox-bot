import discord
from discord.ext import commands
from discord import app_commands

# Discord Developer Portal'dan YENI token al ve buraya yaz.
BOT_TOKEN = "Bot Token"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user}")
    print(f"Sunucu sayısı: {len(bot.guilds)}")

    for guild in bot.guilds:
        print(f"Sunucu bulundu: {guild.name} ({guild.id})")
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Komutlar yüklendi: {guild.name} ({len(synced)} komut)")
        except Exception as e:
            print(f"Sync hatası: {guild.name} -> {e}")


    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Komutlar yüklendi: {guild.name} ({len(synced)} komut)")
        except Exception as e:
            print(f"Sync hatası: {guild.name} -> {e}")


@bot.tree.command(name="ping", description="Botun gecikmesini gösterir.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! {round(bot.latency * 1000)} ms"
    )


@bot.tree.command(name="help", description="Botun komutlarını gösterir.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Kyxor Bot",
        description="Kullanabileceğin komutlar:"
    )
    embed.add_field(name="/ping", value="Bot gecikmesini gösterir.", inline=False)
    embed.add_field(name="/server", value="Sunucu bilgilerini gösterir.", inline=False)
    embed.add_field(name="/userinfo", value="Kullanıcı bilgilerini gösterir.", inline=False)
    embed.add_field(name="/avatar", value="Profil fotoğrafını gösterir.", inline=False)
    embed.add_field(name="/clear", value="Mesajları temizler.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="server", description="Sunucu bilgilerini gösterir.")
async def server(interaction: discord.Interaction):
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "Bu komut sadece sunucuda kullanılabilir.",
            ephemeral=True
        )
        return

    embed = discord.Embed(title=f"{guild.name} Bilgileri")
    embed.add_field(name="Üye sayısı", value=str(guild.member_count), inline=True)
    embed.add_field(name="Kanal sayısı", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Sunucu ID", value=str(guild.id), inline=False)

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="Bir kullanıcının bilgilerini gösterir.")
@app_commands.describe(user="Bilgisini görmek istediğin kullanıcı")
async def userinfo(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):
    user = user or interaction.user

    embed = discord.Embed(title=f"{user.display_name} Bilgileri")
    embed.add_field(name="Kullanıcı", value=str(user), inline=False)
    embed.add_field(name="ID", value=str(user.id), inline=False)

    if user.joined_at:
        embed.add_field(
            name="Sunucuya katılma",
            value=discord.utils.format_dt(user.joined_at, style="D"),
            inline=False
        )

    embed.set_thumbnail(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="Kullanıcının profil fotoğrafını gösterir.")
@app_commands.describe(user="Avatarını görmek istediğin kullanıcı")
async def avatar(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):
    user = user or interaction.user

    embed = discord.Embed(title=f"{user.display_name} - Avatar")
    embed.set_image(url=user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clear", description="Kanaldaki son mesajları temizler.")
@app_commands.describe(amount="Temizlenecek mesaj sayısı (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "Bu komut sadece yazı kanallarında kullanılabilir.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await channel.purge(limit=amount)
        await interaction.followup.send(
            f"{len(deleted)} mesaj temizlendi.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "Mesajları silmek için gerekli yetkim yok.",
            ephemeral=True
        )


@bot.event
async def on_member_join(member: discord.Member):
    # Sunucudaki sistem kanalına hoş geldin mesajı gönderir.
    channel = member.guild.system_channel

    if channel:
        await channel.send(
            f"👋 Hoş geldin {member.mention}! "
            f"{member.guild.name} sunucusuna katıldın."
        )


if BOT_TOKEN == "BURAYA_YENI_BOT_TOKENINI_YAZ":
    print("HATA: BOT_TOKEN kısmına yeni bot tokenını yaz.")
else:
    bot.run(BOT_TOKEN)
