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

from discord.ui import View, Button, Select, Modal, TextInput
from discord import Embed, Interaction

matches = {}  # stocke les données temporaires de match

class Match:
    def __init__(self, ctx, players):
        self.ctx = ctx
        self.players = players
        self.amount = None
        self.mode = None
        self.format = None

class AmountView(View):
    def __init__(self, match):
        super().__init__()
        self.match = match

        for value in [1, 2, 5, 10]:
            self.add_item(Button(label=f"{value}€", style=discord.ButtonStyle.primary, custom_id=f"amount_{value}"))

        self.add_item(Button(label="Autre", style=discord.ButtonStyle.secondary, custom_id="amount_custom"))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Match annulé.", ephemeral=True)
        self.stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user in self.match.players

    async def on_error(self, error, item, interaction):
        await interaction.response.send_message("❌ Erreur interne.", ephemeral=True)

    async def on_timeout(self):
        await self.match.ctx.send("⏰ Temps écoulé pour la sélection de la mise.")

@bot.command()
async def create(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Tu dois être dans un salon vocal.")
        return

    members = [m for m in ctx.author.voice.channel.members if not m.bot]
    if len(members) < 4:
        await ctx.send("❌ Il faut être au moins 4 joueurs dans le vocal.")
        return

    match = Match(ctx, members)
    matches[ctx.channel.id] = match

    embed = Embed(title="Création d'un match", description="Choisissez une mise par joueur :", color=0x00ff00)
    await ctx.send(embed=embed, view=AmountView(match))

@bot.event
async def on_interaction(interaction: Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    match = matches.get(interaction.channel.id)
    if not match:
        return

    if interaction.data['custom_id'].startswith("amount_"):
        if interaction.data['custom_id'] == "amount_custom":
            await interaction.response.send_modal(CustomAmountModal(match))
        else:
            match.amount = int(interaction.data['custom_id'].split("_")[1])
            await interaction.response.send_message(f"✅ Mise choisie : {match.amount}€", ephemeral=True)
            await send_mode_selection(interaction, match)

class CustomAmountModal(Modal, title="Mise personnalisée"):
    custom_amount = TextInput(label="Entre la mise souhaitée (en euros)", required=True)

    def __init__(self, match):
        super().__init__()
        self.match = match

    async def on_submit(self, interaction: Interaction):
        try:
            value = float(self.custom_amount.value)
            if value <= 1:
                await interaction.response.send_message("❌ La mise doit être supérieure à 1€.", ephemeral=True)
                return
            self.match.amount = value
            await interaction.response.send_message(f"✅ Mise personnalisée : {value}€", ephemeral=True)
            await send_mode_selection(interaction, self.match)
        except ValueError:
            await interaction.response.send_message("❌ Valeur invalide.", ephemeral=True)

async def send_mode_selection(interaction, match):
    view = View()
    for label in ["Realistic", "Zone Wars", "Boxfight"]:
        view.add_item(Button(label=label, style=discord.ButtonStyle.primary, custom_id=f"mode_{label.lower()}"))
    view.add_item(Button(label="Autre", style=discord.ButtonStyle.secondary, custom_id="mode_custom"))
    await interaction.followup.send("Choisissez un mode de jeu :", view=view)

@bot.event
async def on_interaction(interaction: Interaction):
    await bot.process_application_commands(interaction)  # nécessaire pour slash cmd, si activées

    match = matches.get(interaction.channel.id)
    if not match or interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data['custom_id']

    if custom_id.startswith("amount_") or custom_id.startswith("mode_"):
        # handled elsewhere
        return

    if custom_id.startswith("mode_"):
        if custom_id == "mode_custom":
            await interaction.response.send_modal(CustomModeModal(match))
        else:
            match.mode = custom_id.split("_")[1]
            await interaction.response.send_message(f"✅ Mode choisi : {match.mode}", ephemeral=True)
            await send_format_selection(interaction, match)

class CustomModeModal(Modal, title="Mode de jeu personnalisé"):
    custom_mode = TextInput(label="Entrez le mode de jeu souhaité", required=True)

    def __init__(self, match):
        super().__init__()
        self.match = match

    async def on_submit(self, interaction: Interaction):
        self.match.mode = self.custom_mode.value
        await interaction.response.send_message(f"✅ Mode personnalisé : {self.match.mode}", ephemeral=True)
        await send_format_selection(interaction, self.match)

async def send_format_selection(interaction, match):
    view = View()
    view.add_item(Button(label="First to 3 +2", style=discord.ButtonStyle.success, custom_id="format_3"))
    view.add_item(Button(label="First to 5 +2", style=discord.ButtonStyle.success, custom_id="format_5"))
    await interaction.followup.send("Choisissez un format :", view=view)

@bot.event
async def on_interaction(interaction: Interaction):
    await bot.process_application_commands(interaction)

    match = matches.get(interaction.channel.id)
    if not match:
        return

    custom_id = interaction.data['custom_id']

    if custom_id.startswith("format_"):
        match.format = custom_id.split("_")[1]
        await interaction.response.send_message(f"✅ Format sélectionné : First to {match.format} +2", ephemeral=True)

        # DM aux joueurs
        for player in match.players:
            try:
                await player.send(
                    f"📢 Un match a été créé !\n"
                    f"Mise : {match.amount}€\n"
                    f"Mode : {match.mode}\n"
                    f"Format : First to {match.format} +2\n"
                    f"Bonne chance !"
                )
            except:
                pass

        await match.ctx.send("✅ Match créé et informations envoyées aux joueurs.")

        # Résultat
        await send_result_buttons(match.ctx, match)

async def send_result_buttons(ctx, match):
    class ResultView(View):
        def __init__(self):
            super().__init__()
            self.add_item(Button(label="✅ Victoire", style=discord.ButtonStyle.green, custom_id="win"))
            self.add_item(Button(label="❌ Défaite", style=discord.ButtonStyle.red, custom_id="lose"))

        async def interaction_check(self, interaction: Interaction) -> bool:
            return interaction.user in match.players

        async def on_error(self, error, item, interaction):
            await interaction.response.send_message("❌ Erreur interne.", ephemeral=True)

        @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: Interaction, button: Button):
            await interaction.response.send_message("Match annulé.", ephemeral=True)
            self.stop()

        async def on_timeout(self):
            await ctx.send("⏰ Résultat non reçu à temps.")

    await ctx.send("Cliquez sur le résultat du match :", view=ResultView())
