import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Select, Modal, TextInput
import random
import asyncio
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

VOCAL_TEAMS = {
    4: [1369710510672711751, 1369710519543402578],  # 2v2
    6: [1369710449523822602, 1369710438769491979],  # 3v3
    8: [1369710384944250950, 1369710409774272623],  # 4v4
}

matches = {}

class Match:
    def __init__(self, ctx, players, team1, team2):
        self.ctx = ctx
        self.players = players
        self.team1 = team1
        self.team2 = team2
        self.amount = None
        self.mode = None
        self.format = None
        self.results = {}
        self.vote_task = None

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- UI Elements ---

class AmountSelect(discord.ui.Select):
    def __init__(self, match):
        self.match = match
        options = [
            discord.SelectOption(label=f"{v}€", value=str(v)) for v in [1, 2, 5, 10]
        ] + [
            discord.SelectOption(label="Autre", value="custom")
        ]
        super().__init__(placeholder="Choisis ta mise", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "custom":
            await interaction.response.send_modal(CustomAmountModal(self.match))
        else:
            self.match.amount = int(self.values[0])
            await interaction.response.send_message(embed=get_mode_embed(), view=ModeView(self.match), ephemeral=True)

class ModeSelect(discord.ui.Select):
    def __init__(self, match):
        self.match = match
        options = [
            discord.SelectOption(label=mode, value=mode.lower()) for mode in ["Realistic", "Zone Wars", "Boxfight"]
        ] + [
            discord.SelectOption(label="Autre", value="custom")
        ]
        super().__init__(placeholder="Choisis un mode de jeu", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "custom":
            await interaction.response.send_modal(CustomModeModal(self.match))
        else:
            self.match.mode = self.values[0].capitalize()
            await interaction.response.send_message(embed=get_format_embed(), view=FormatView(self.match), ephemeral=True)

class CustomAmountModal(Modal, title="Mise personnalisée"):
    montant = TextInput(label="Entrez la mise (min 2€)", required=True)

    def __init__(self, match):
        super().__init__()
        self.match = match

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = float(self.montant.value)
            if value < 2:
                await interaction.response.send_message("❌ Mise trop basse.", ephemeral=True)
                return
            self.match.amount = value
            await interaction.response.send_message(embed=get_mode_embed(), view=ModeView(self.match), ephemeral=True)
        except:
            await interaction.response.send_message("❌ Valeur invalide.", ephemeral=True)

class CustomModeModal(Modal, title="Mode personnalisé"):
    mode = TextInput(label="Entrez le mode de jeu", required=True)

    def __init__(self, match):
        super().__init__()
        self.match = match

    async def on_submit(self, interaction: discord.Interaction):
        self.match.mode = self.mode.value
        await interaction.response.send_message(embed=get_format_embed(), view=FormatView(self.match), ephemeral=True)

class ModeView(View):
    def __init__(self, match):
        super().__init__(timeout=None)
        self.add_item(ModeSelect(match))

class AmountView(View):
    def __init__(self, match):
        super().__init__(timeout=None)
        self.add_item(AmountSelect(match))

class FormatView(View):
    def __init__(self, match):
        super().__init__(timeout=None)
        self.match = match
        self.add_item(Button(label="First to 3 +2", style=discord.ButtonStyle.success, custom_id="format_3"))
        self.add_item(Button(label="First to 5 +2", style=discord.ButtonStyle.success, custom_id="format_5"))

class ResultView(View):
    def __init__(self, match):
        super().__init__(timeout=None)
        self.match = match
        self.add_item(Button(label="✅ Victoire", style=discord.ButtonStyle.green, custom_id="win"))
        self.add_item(Button(label="❌ Défaite", style=discord.ButtonStyle.red, custom_id="lose"))

# --- Embeds ---

def get_mode_embed():
    return discord.Embed(title="🎮 Sélection du mode", description="Choisis un mode de jeu", color=0x00acee)

def get_format_embed():
    return discord.Embed(title="🧱 Format du match", description="Choisis un format First to +2", color=0xffcc00)

# --- Commande CREATE ---

@bot.command()
async def create(ctx, number: int):
    if number not in VOCAL_TEAMS:
        await ctx.send("❌ Nombre de joueurs non pris en charge (4, 6, 8 uniquement).")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Tu dois être dans un salon vocal.")
        return

    voice_channel = ctx.author.voice.channel
    members = [m for m in voice_channel.members if not m.bot]

    if len(members) != number:
        await ctx.send(f"❌ Il y a {len(members)} joueurs, il en faut exactement {number}.")
        return

    random.shuffle(members)
    mid = number // 2
    team1 = members[:mid]
    team2 = members[mid:]

    ch1 = ctx.guild.get_channel(VOCAL_TEAMS[number][0])
    ch2 = ctx.guild.get_channel(VOCAL_TEAMS[number][1])

    for m in team1:
        await m.move_to(ch1)
    for m in team2:
        await m.move_to(ch2)

    match = Match(ctx, members, team1, team2)
    matches[ctx.channel.id] = match

    embed = discord.Embed(title="⚔️ Création de match", color=0x7289DA)
    embed.add_field(name="Joueurs déplacés ✅", value=f"{ch1.name} et {ch2.name}", inline=False)
    embed.add_field(name="Étape suivante", value="Choisissez la mise.", inline=False)

    await ctx.send(embed=embed, view=AmountView(match))

# --- INTERACTIONS ---

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    match = matches.get(interaction.channel.id)
    if not match:
        await interaction.response.send_message("❌ Aucun match actif.", ephemeral=True)
        return

    cid = interaction.data['custom_id']

    if cid.startswith("format_"):
        match.format = cid.split("_")[1]

        embed = discord.Embed(title="✅ Match prêt !", color=0x00ff00)
        embed.add_field(name="Mise", value=f"{match.amount}€", inline=True)
        embed.add_field(name="Mode", value=match.mode, inline=True)
        embed.add_field(name="Format", value=f"FT{match.format}+2", inline=True)

        for p in match.players:
            try:
                await p.send(embed=embed)
            except:
                pass

        await match.ctx.send(embed=embed, view=ResultView(match))
        match.vote_task = bot.loop.create_task(auto_win_timeout(match))

    elif cid in ["win", "lose"]:
        match.results[interaction.user.id] = cid
        await interaction.response.send_message("✅ Résultat enregistré", ephemeral=True)

        # Vérifier si une team a 100% des votes
        t1_votes = [match.results.get(p.id) for p in match.team1]
        t2_votes = [match.results.get(p.id) for p in match.team2]

        if all(v == "win" for v in t1_votes if v) and all(v == "lose" for v in t2_votes if v):
            await finalize_result(match, match.team1, match.team2)
        elif all(v == "win" for v in t2_votes if v) and all(v == "lose" for v in t1_votes if v):
            await finalize_result(match, match.team2, match.team1)

async def auto_win_timeout(match):
    await asyncio.sleep(180)  # 3 minutes

    t1_votes = [match.results.get(p.id) for p in match.team1]
    t2_votes = [match.results.get(p.id) for p in match.team2]

    if all(v == "win" for v in t1_votes if v):
        await finalize_result(match, match.team1, match.team2, timeout=True)
    elif all(v == "win" for v in t2_votes if v):
        await finalize_result(match, match.team2, match.team1, timeout=True)

async def finalize_result(match, winners, losers, timeout=False):
    total = match.amount * len(losers)
    win_names = ", ".join(f"<@{p.id}>" for p in winners)
    lose_names = ", ".join(f"<@{p.id}>" for p in losers)

    reason = "(temps écoulé)" if timeout else ""
    await match.ctx.send(f"🏆 {win_names} remportent {total}€ contre {lose_names} {reason}")
    if match.vote_task:
        match.vote_task.cancel()
    matches.pop(match.ctx.channel.id, None)

bot.run(os.getenv("DISCORD_TOKEN"))
