import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Select
import random
import asyncio
import os
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Identifiants des salons vocaux pour le split automatique
VOCAL_TEAMS = {
    4: [1369710510672711751, 1369710519543402578],
    6: [1369710449523822602, 1369710438769491979],
    8: [1369710384944250950, 1369710409774272623],
}

# Salon textuel pour les preuves de litiges
MATCH_LOG_CHANNEL_ID = 123456789012345678  # À remplacer par l'ID de ton salon textuel

# ID de l'admin à notifier (à remplacer)
ADMIN_ID = 943177409933488139

# Lien PayPal
PAYPAL_LINK = "https://paypal.me/tonlien"

# Commande de suppression
@bot.command()
@commands.has_permissions(manage_messages=True)
async def delete(ctx, amount: int):
    if amount < 1:
        await ctx.send("❌ Tu dois supprimer au moins 1 message.")
        return
    await ctx.channel.purge(limit=amount + 1)
    confirmation = await ctx.send(f"✅ {amount} messages supprimés.")
    await confirmation.delete(delay=3)

# Commande principale de création de match
@bot.command()
async def create(ctx, nombre_joueurs: int):
    if nombre_joueurs not in VOCAL_TEAMS:
        await ctx.send("❌ Tu dois entrer 4, 6 ou 8 comme nombre de joueurs.")
        return

    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if not voice_channel:
        await ctx.send("❌ Tu dois être dans un salon vocal.")
        return

    members = [member for member in voice_channel.members if not member.bot]
    if len(members) != nombre_joueurs:
        await ctx.send(f"❌ Il y a {len(members)} membres dans le vocal au lieu de {nombre_joueurs}.")
        return

    class MatchConfig(View):
        def __init__(self):
            super().__init__(timeout=None)
            self.match_data = {}
            self.match_data["players"] = members
            self.match_data["voice_channel"] = voice_channel

        @discord.ui.select(
            placeholder="Choisis une mise",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="1€"),
                discord.SelectOption(label="2€"),
                discord.SelectOption(label="5€"),
                discord.SelectOption(label="10€"),
                discord.SelectOption(label="Autre")
            ]
        )
        async def select_mise(self, interaction: discord.Interaction, select: discord.ui.Select):
            if select.values[0] == "Autre":
                await interaction.response.send_message("Entre la mise personnalisée en euros (supérieure à 1€) :", ephemeral=True)

                def check(msg):
                    return msg.author == interaction.user and msg.channel == interaction.channel

                msg = await bot.wait_for("message", check=check)
                try:
                    self.match_data["mise"] = float(msg.content)
                except ValueError:
                    await interaction.followup.send("❌ Entrée invalide.", ephemeral=True)
                    return
            else:
                self.match_data["mise"] = float(select.values[0].replace("€", ""))
            await interaction.followup.send(f"💶 Mise enregistrée : {self.match_data['mise']}€", ephemeral=True)

        @discord.ui.select(
            placeholder="Choisis le mode de jeu",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Realistic"),
                discord.SelectOption(label="Zone Wars"),
                discord.SelectOption(label="Box Fight"),
                discord.SelectOption(label="Autre")
            ]
        )
        async def select_mode(self, interaction: discord.Interaction, select: discord.ui.Select):
            if select.values[0] == "Autre":
                await interaction.response.send_message("Entre le mode personnalisé :", ephemeral=True)
                def check(msg):
                    return msg.author == interaction.user and msg.channel == interaction.channel
                msg = await bot.wait_for("message", check=check)
                self.match_data["mode"] = msg.content
            else:
                self.match_data["mode"] = select.values[0]
            await interaction.followup.send(f"🎮 Mode enregistré : {self.match_data['mode']}", ephemeral=True)

        @discord.ui.select(
            placeholder="Choisis le format du match",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="First to 3 (+2)"),
                discord.SelectOption(label="First to 5 (+2)")
            ]
        )
        async def select_format(self, interaction: discord.Interaction, select: discord.ui.Select):
            self.match_data["format"] = select.values[0]
            await interaction.followup.send(f"🎯 Format enregistré : {self.match_data['format']}", ephemeral=True)
            await finalize_match(self.match_data)

    async def finalize_match(match_data):
        players = match_data["players"]
        random.shuffle(players)
        team1 = players[:len(players)//2]
        team2 = players[len(players)//2:]

        ch1 = ctx.guild.get_channel(VOCAL_TEAMS[nombre_joueurs][0])
        ch2 = ctx.guild.get_channel(VOCAL_TEAMS[nombre_joueurs][1])

        for member in team1:
            await member.move_to(ch1)
            await member.send(f"➡️ Tu joues dans **{match_data['mode']}**, mise : **{match_data['mise']}€**, format **{match_data['format']}**. Envoie **{match_data['mise']}€** à ce PayPal : {PAYPAL_LINK}")
        for member in team2:
            await member.move_to(ch2)
            await member.send(f"➡️ Tu joues dans **{match_data['mode']}**, mise : **{match_data['mise']}€**, format **{match_data['format']}**. Envoie **{match_data['mise']}€** à ce PayPal : {PAYPAL_LINK}")

        result_msg = await ctx.send(
            embed=discord.Embed(
                title="🎮 Fin du match - Résultats",
                description=f"L'équipe 1 : {', '.join(m.name for m in team1)}\nL'équipe 2 : {', '.join(m.name for m in team2)}",
                color=discord.Color.blue()
            ),
            view=ResultView(team1, team2, match_data["mise"] * len(team1))
        )

    await ctx.send("🔧 Création du match...")
    await ctx.send("🧩 Configuration du match :", view=MatchConfig())

class ResultView(View):
    def __init__(self, team1, team2, gain):
        super().__init__(timeout=None)
        self.team1 = team1
        self.team2 = team2
        self.gain = gain
        self.votes = {"team1": set(), "team2": set()}
        self.start_time = datetime.utcnow()
        self.message = None
        self.update_task.start()

    @tasks.loop(seconds=5)
    async def update_task(self):
        if self.message:
            remaining = 180 - int((datetime.utcnow() - self.start_time).total_seconds())
            if remaining <= 0:
                await self.check_result()
                self.update_task.cancel()
            else:
                await self.message.edit(content=f"⏳ Temps restant pour valider le résultat : {remaining}s")

    async def check_result(self):
        if len(self.votes["team1"]) == len(self.team1) and len(self.votes["team2"]) == len(self.team2):
            await self.message.channel.send("✅ Résultat validé. GG à tous !")
            for m in self.team1:
                if m.id in self.votes["team1"]:
                    await m.send(f"✅ Vous avez gagné {self.gain}€")
            for m in self.team2:
                if m.id in self.votes["team2"]:
                    await m.send("❌ Vous avez perdu votre mise.")
            return

        elif self.votes["team1"] and self.votes["team2"]:
            await self.message.channel.send(
                "⚠️ Conflit détecté. Veuillez déposer une preuve (vidéo, lien Streamable...) dans ce salon dans les 3 minutes."
            )

    @discord.ui.button(label="Victoire", style=discord.ButtonStyle.success)
    async def victoire(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.team1:
            self.votes["team1"].add(interaction.user.id)
        elif interaction.user in self.team2:
            self.votes["team2"].add(interaction.user.id)
        await interaction.response.send_message("🟢 Vote enregistré.", ephemeral=True)

    @discord.ui.button(label="Défaite", style=discord.ButtonStyle.danger)
    async def defaite(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.team1:
            self.votes["team2"].add(interaction.user.id)
        elif interaction.user in self.team2:
            self.votes["team1"].add(interaction.user.id)
        await interaction.response.send_message("🔴 Vote enregistré.", ephemeral=True)

@bot.event
async def on_message(message):
    if message.channel.id == MATCH_LOG_CHANNEL_ID and message.attachments:
        admin = await bot.fetch_user(ADMIN_ID)
        for file in message.attachments:
            await admin.send(f"📩 Preuve reçue : {file.url}")
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))
