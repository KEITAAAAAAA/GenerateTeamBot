import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Select
import random
import asyncio
import os
from datetime import datetime

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

VOCAL_TEAMS = {
    4: [1369710510672711751, 1369710519543402578],
    6: [1369710449523822602, 1369710438769491979],
    8: [1369710384944250950, 1369710409774272623],
}

RANKS = [
    (1369709814585757801, "🐐", 20),  # GOAT
    (1369709889521189024, "T1", 15),
    (1369709929656746135, "T2", 10),
    (1369709959289376818, "T3", 0),
]

MATCH_LOG_CHANNEL_ID = 123456789012345678  # Remplacer
ADMIN_ID = 943177409933488139
PAYPAL_LINK = "https://paypal.me/tonlien"

user_stats = {}  # {user_id: {win: int, lose: int, progress: int}}
matches_in_progress = {}

@bot.command()
@commands.has_permissions(manage_messages=True)
async def delete(ctx, amount: int):
    if amount < 1:
        await ctx.send("❌ Tu dois supprimer au moins 1 message.")
        return
    await ctx.channel.purge(limit=amount + 1)
    confirmation = await ctx.send(f"✅ {amount} messages supprimés.")
    await confirmation.delete(delay=3)

@bot.command()
async def stats(ctx, user: discord.Member = None):
    user = user or ctx.author
    stats = user_stats.get(user.id, {"win": 0, "lose": 0, "progress": 0})
    win = stats["win"]
    lose = stats["lose"]
    total = win + lose
    winrate = (win / total * 100) if total > 0 else 0
    await ctx.send(f"📊 Stats de {user.display_name} :\n✅ Victoires : {win}\n❌ Défaites : {lose}\n🏅 Winrate : {winrate:.2f}%\n🔥 Progression : {stats['progress']}/5")

@bot.command()
async def rank(ctx, user: discord.Member = None):
    user = user or ctx.author
    stats = user_stats.get(user.id, {"win": 0, "lose": 0, "progress": 0})
    progress = stats["progress"]
    role_id = get_rank_role_id(progress + stats["win"])
    rank_name = next(name for rid, name, _ in RANKS if rid == role_id)
    await ctx.send(f"🏅 {user.display_name} est classé : {rank_name} ({progress}/5)")

@bot.command()
@commands.has_permissions(administrator=True)
async def reset_stats(ctx, user: discord.Member = None):
    if user:
        user_stats[user.id] = {"win": 0, "lose": 0, "progress": 0}
        for role_id, _, _ in RANKS:
            role = ctx.guild.get_role(role_id)
            if role in user.roles:
                await user.remove_roles(role)
        default_rank = ctx.guild.get_role(RANKS[-1][0])
        if default_rank:
            await user.add_roles(default_rank, reason="Reset des stats et du rang")
        await ctx.send(f"🔁 Stats et rank de {user.display_name} ont été réinitialisés.")
    else:
        for member in ctx.guild.members:
            if not member.bot:
                user_stats[member.id] = {"win": 0, "lose": 0, "progress": 0}
                for role_id, _, _ in RANKS:
                    role = ctx.guild.get_role(role_id)
                    if role in member.roles:
                        await member.remove_roles(role)
                default_rank = ctx.guild.get_role(RANKS[-1][0])
                if default_rank:
                    await member.add_roles(default_rank, reason="Reset global des stats et du rang")
        await ctx.send("🔁 Tous les stats et ranks ont été réinitialisés pour tous les membres.")

@bot.command()
async def create(ctx, nombre_joueurs: int):
    if nombre_joueurs not in VOCAL_TEAMS:
        await ctx.send("❌ Tu dois entrer 4, 6 ou 8 comme nombre de joueurs.")
        return

    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if not voice_channel:
        await ctx.send("❌ Tu dois être dans un salon vocal.")
        return

    members = [m for m in voice_channel.members if not m.bot]
    if len(members) != nombre_joueurs:
        await ctx.send(f"❌ Il y a {len(members)} membres dans le vocal au lieu de {nombre_joueurs}.")
        return

    class MatchConfig(View):
        def __init__(self):
            super().__init__(timeout=None)
            self.match_data = {"players": members, "voice_channel": voice_channel}
            self.mise_select = Select(placeholder="Choisis une mise", options=[
                discord.SelectOption(label="1€"),
                discord.SelectOption(label="2€"),
                discord.SelectOption(label="5€"),
                discord.SelectOption(label="10€"),
                discord.SelectOption(label="Autre")
            ])
            self.mise_select.callback = self.select_mise
            self.add_item(self.mise_select)

            self.mode_select = Select(placeholder="Choisis le mode de jeu", options=[
                discord.SelectOption(label="Realistic"),
                discord.SelectOption(label="Zone Wars"),
                discord.SelectOption(label="Box Fight"),
                discord.SelectOption(label="Autre")
            ])
            self.mode_select.callback = self.select_mode
            self.add_item(self.mode_select)

            self.format_select = Select(placeholder="Choisis le format du match", options=[
                discord.SelectOption(label="First to 3 (+2)"),
                discord.SelectOption(label="First to 5 (+2)")
            ])
            self.format_select.callback = self.select_format
            self.add_item(self.format_select)

        async def select_mise(self, interaction):
            value = self.mise_select.values[0]
            if value == "Autre":
                await interaction.response.send_message("Entre la mise personnalisée en euros :", ephemeral=True)
                def check(m): return m.author == interaction.user and m.channel == interaction.channel
                msg = await bot.wait_for("message", check=check)
                try:
                    self.match_data["mise"] = float(msg.content)
                except ValueError:
                    await interaction.followup.send("❌ Entrée invalide.", ephemeral=True)
                    return
            else:
                self.match_data["mise"] = float(value.replace("€", ""))
            await interaction.response.send_message(f"💶 Mise enregistrée : {self.match_data['mise']}€", ephemeral=True)

        async def select_mode(self, interaction):
            value = self.mode_select.values[0]
            if value == "Autre":
                await interaction.response.send_message("Entre le mode personnalisé :", ephemeral=True)
                def check(m): return m.author == interaction.user and m.channel == interaction.channel
                msg = await bot.wait_for("message", check=check)
                self.match_data["mode"] = msg.content
            else:
                self.match_data["mode"] = value
            await interaction.response.send_message(f"🎮 Mode enregistré : {self.match_data['mode']}", ephemeral=True)

        async def select_format(self, interaction):
            value = self.format_select.values[0]
            self.match_data["format"] = value
            await interaction.response.send_message(f"🎯 Format enregistré : {value}", ephemeral=True)
            await finalize_match(self.match_data)

    async def finalize_match(match_data):
        players = match_data["players"]
        random.shuffle(players)
        team1, team2 = players[:len(players)//2], players[len(players)//2:]
        ch1 = ctx.guild.get_channel(VOCAL_TEAMS[nombre_joueurs][0])
        ch2 = ctx.guild.get_channel(VOCAL_TEAMS[nombre_joueurs][1])

        for m in team1: await m.move_to(ch1)
        for m in team2: await m.move_to(ch2)

        for member in players:
            if member.id not in user_stats:
                user_stats[member.id] = {"win": 0, "lose": 0, "progress": 0}

        view = ResultView(team1, team2, match_data["mise"] * len(team1))
        result_msg = await ctx.send(embed=view.generate_embed(), view=view)
        view.message = result_msg
        matches_in_progress[result_msg.id] = {"team1": team1, "team2": team2, "channel": ctx.channel}

    await ctx.send("🔧 Création du match...")
    await ctx.send("🧹 Configuration du match :", view=MatchConfig())

def get_rank_role_id(wins):
    for role_id, _, threshold in RANKS:
        if wins >= threshold:
            return role_id
    return RANKS[-1][0]  # default T3

async def update_user_rank(member):
    total_win = user_stats[member.id]["win"]
    role_id = get_rank_role_id(total_win)
    role = member.guild.get_role(role_id)
    if role:
        await member.add_roles(role, reason="Mise à jour du rang")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))
