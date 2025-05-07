import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Select
import random
import asyncio
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# IDs des salons vocaux que tu as fournis
VOCAL_TEAMS = {
    4: [1369710510672711751, 1369710519543402578],
    6: [1369710449523822602, 1369710438769491979],
    8: [1369710384944250950, 1369710409774272623],
}

# ID de l'admin à qui envoyer les DM
ADMIN_ID = 943177409933488139

matches = {}  # Pour stocker les infos de chaque match en cours

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# Commande DELETE conservée
@bot.command()
@commands.has_permissions(manage_messages=True)
async def delete(ctx, amount: int):
    if amount < 1:
        await ctx.send("❌ Tu dois supprimer au moins 1 message.")
        return
    await ctx.channel.purge(limit=amount + 1)
    confirmation = await ctx.send(f"✅ {amount} messages supprimés.")
    await confirmation.delete(delay=3)

class MatchSetup(View):
    def __init__(self, ctx, players):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.players = players
        self.match_id = f"{ctx.channel.id}-{random.randint(1000, 9999)}"
        self.match_data = {"players": players, "ctx": ctx}
        matches[self.match_id] = self.match_data

        self.money = None
        self.mode = None
        self.first_to = None

        self.money_select = Select(
            placeholder="💰 Choisis ta mise...",
            options=[
                discord.SelectOption(label="1€", value="1"),
                discord.SelectOption(label="2€", value="2"),
                discord.SelectOption(label="5€", value="5"),
                discord.SelectOption(label="10€", value="10"),
                discord.SelectOption(label="Autre", value="custom")
            ]
        )
        self.money_select.callback = self.money_callback

        self.mode_select = Select(
            placeholder="🎮 Choisis le mode de jeu...",
            options=[
                discord.SelectOption(label="Realistic", value="Realistic"),
                discord.SelectOption(label="Zone Wars", value="Zone Wars"),
                discord.SelectOption(label="Boxfight", value="Boxfight"),
                discord.SelectOption(label="Personnalisé", value="custom")
            ]
        )
        self.mode_select.callback = self.mode_callback

        self.first_to_btn_3 = Button(label="First to 3 +2", style=discord.ButtonStyle.primary)
        self.first_to_btn_5 = Button(label="First to 5 +2", style=discord.ButtonStyle.primary)
        self.first_to_btn_3.callback = self.set_first_to_3
        self.first_to_btn_5.callback = self.set_first_to_5

        self.add_item(self.money_select)
        self.add_item(self.mode_select)
        self.add_item(self.first_to_btn_3)
        self.add_item(self.first_to_btn_5)

    async def money_callback(self, interaction):
        if self.money_select.values[0] == "custom":
            await interaction.response.send_message("💸 Envoie ta mise personnalisée en euros (ex: 3.5)", ephemeral=True)

            def check(m): return m.author == interaction.user and m.channel == self.ctx.channel
            try:
                msg = await bot.wait_for("message", check=check, timeout=30)
                self.money = msg.content
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Temps écoulé pour choisir la mise.", ephemeral=True)
                return
        else:
            self.money = self.money_select.values[0]
        await interaction.response.send_message(f"💸 Mise enregistrée : {self.money}€", ephemeral=True)

    async def mode_callback(self, interaction):
        if self.mode_select.values[0] == "custom":
            await interaction.response.send_message("🎯 Envoie ton mode de jeu personnalisé", ephemeral=True)

            def check(m): return m.author == interaction.user and m.channel == self.ctx.channel
            try:
                msg = await bot.wait_for("message", check=check, timeout=30)
                self.mode = msg.content
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Temps écoulé pour choisir le mode.", ephemeral=True)
                return
        else:
            self.mode = self.mode_select.values[0]
        await interaction.response.send_message(f"🎮 Mode de jeu : {self.mode}", ephemeral=True)

    async def set_first_to_3(self, interaction):
        self.first_to = "3+2"
        await self.finish_setup(interaction)

    async def set_first_to_5(self, interaction):
        self.first_to = "5+2"
        await self.finish_setup(interaction)

    async def finish_setup(self, interaction):
        if not self.money or not self.mode:
            await interaction.response.send_message("❗ Tu dois d'abord choisir la mise et le mode.", ephemeral=True)
            return

        number = len(self.players)
        random.shuffle(self.players)
        mid = number // 2
        team1 = self.players[:mid]
        team2 = self.players[mid:]
        self.match_data.update({"team1": team1, "team2": team2})

        # Déplacement dans les vocaux
        ch1 = self.ctx.guild.get_channel(VOCAL_TEAMS[number][0])
        ch2 = self.ctx.guild.get_channel(VOCAL_TEAMS[number][1])
        for m in team1:
            await m.move_to(ch1)
        for m in team2:
            await m.move_to(ch2)

        embed = discord.Embed(title="🎯 Match prêt !", description=f"Mise : {self.money}€\nMode : {self.mode}\nFormat : First to {self.first_to}", color=0x00ffcc)
        embed.add_field(name="Équipe 1", value="\n".join(m.mention for m in team1))
        embed.add_field(name="Équipe 2", value="\n".join(m.mention for m in team2))
        await interaction.response.send_message(embed=embed)

        await asyncio.sleep(10)  # temps d'attente avant envoi des boutons victoire/défaite
        await self.ctx.send("🏁 Match terminé ? Cliquez sur votre résultat :", view=MatchResultView(self.match_id))

class MatchResultView(View):
    def __init__(self, match_id):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.votes = {"team1": set(), "team2": set()}
        self.timeout_task = bot.loop.create_task(self.result_timeout())

    async def result_timeout(self):
        await asyncio.sleep(180)
        match = matches.get(self.match_id)
        if not match:
            return

        if len(self.votes["team1"]) > len(self.votes["team2"]):
            winner = match["team1"]
        elif len(self.votes["team2"]) > len(self.votes["team1"]):
            winner = match["team2"]
        else:
            # cas litigeux — demander preuve
            admin = await bot.fetch_user(ADMIN_ID)
            await admin.send("⚠️ Conflit de résultat pour le match {}. Demande de preuve vidéo.")
            return

        admin = await bot.fetch_user(ADMIN_ID)
        await admin.send(f"✅ L'équipe gagnante est : {' , '.join(p.name for p in winner)} — Match : {self.match_id}")

    @discord.ui.button(label="Victoire", style=discord.ButtonStyle.success)
    async def victory(self, interaction: discord.Interaction, button: Button):
        match = matches.get(self.match_id)
        user = interaction.user
        if user in match["team1"]:
            self.votes["team1"].add(user)
        elif user in match["team2"]:
            self.votes["team2"].add(user)
        await interaction.response.send_message("✅ Vote enregistré", ephemeral=True)

    @discord.ui.button(label="Défaite", style=discord.ButtonStyle.danger)
    async def defeat(self, interaction: discord.Interaction, button: Button):
        match = matches.get(self.match_id)
        user = interaction.user
        if user in match["team1"]:
            self.votes["team2"].add(user)
        elif user in match["team2"]:
            self.votes["team1"].add(user)
        await interaction.response.send_message("😔 Défaite enregistrée", ephemeral=True)

@bot.command()
async def create(ctx, number: int):
    if number not in VOCAL_TEAMS:
        await ctx.send("❌ Seuls les formats 4, 6 ou 8 joueurs sont supportés.")
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Tu dois être dans un salon vocal avec les joueurs.")
        return

    voice_channel = ctx.author.voice.channel
    members = [m for m in voice_channel.members if not m.bot]

    if len(members) != number:
        await ctx.send(f"❌ Il y a {len(members)} joueurs, mais tu as spécifié {number}.")
        return

    embed = discord.Embed(title="🎮 Création de match", description="Configure ta mise, ton mode et ton format.", color=0x00ffff)
    embed.add_field(name="Participants", value="\n".join(m.mention for m in members))
    await ctx.send(embed=embed, view=MatchSetup(ctx, members))

bot.run(os.getenv("DISCORD_TOKEN"))
