import discord
from discord.ext import commands
import random

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# IDs des salons vocaux que tu as fournis
VOCAL_TEAMS = {
    4: [1369710510672711751, 1369710519543402578],  # 2v2
    6: [1369710449523822602, 1369710438769491979],  # 3v3
    8: [1369710384944250950, 1369710409774272623],  # 4v4
}

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

@bot.command()
async def split(ctx, number: int):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Tu dois être dans un salon vocal.")
        return

    voice_channel = ctx.author.voice.channel
    members = [member for member in voice_channel.members if not member.bot]

    if len(members) != number:
        await ctx.send(f"❌ Il y a {len(members)} personnes dans le salon, pas {number}.")
        return

    if number not in VOCAL_TEAMS:
        await ctx.send("❌ Ce nombre de joueurs n'est pas supporté (seulement 4, 6 ou 8).")
        return

    # Mélanger les membres et les séparer en deux équipes
    random.shuffle(members)
    mid = number // 2
    team1 = members[:mid]
    team2 = members[mid:]

    # Récupère les salons vocaux par ID
    channel1 = ctx.guild.get_channel(VOCAL_TEAMS[number][0])
    channel2 = ctx.guild.get_channel(VOCAL_TEAMS[number][1])

    if not channel1 or not channel2:
        await ctx.send("❌ Un des salons vocaux n'a pas été trouvé.")
        return

    # Déplacer les membres dans les salons
    for member in team1:
        await member.move_to(channel1)
    for member in team2:
        await member.move_to(channel2)

    await ctx.send(f"✅ Les équipes ont été déplacées dans {channel1.name} et {channel2.name}.")

# 🔹 Commande pour supprimer les messages
@bot.command()
@commands.has_permissions(manage_messages=True)
async def delete(ctx, amount: int):
    if amount < 1:
        await ctx.send("❌ Tu dois supprimer au moins 1 message.")
        return
    await ctx.channel.purge(limit=amount + 1)  # Supprime aussi la commande elle-même
    confirmation = await ctx.send(f"✅ {amount} messages supprimés.")
    await confirmation.delete(delay=3)

# Remplace par ton token ici
import os
bot.run(os.getenv("DISCORD_TOKEN"))