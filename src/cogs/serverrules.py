import discord
from discord import app_commands
from discord.ext import commands
import json
from pathlib import Path
from config import RULES_CONFIG, ROLE_IDS


class RuleButton(discord.ui.Button):
    def __init__(self, key: str, action: str):
        data         = RULES_CONFIG[key]
        self.role_id = ROLE_IDS[data["role_key"]]
        self.action  = action

        if action == "join":
            label, style, emoji = "Accept", discord.ButtonStyle.green, "✅"
        else:
            label, style, emoji = "Decline", discord.ButtonStyle.red, "🗑️"

        super().__init__(label=label, style=style, emoji=emoji, custom_id=f"rule_btn:{key}:{action}")

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Role config error.", ephemeral=True)
            return
        try:
            if self.action == "join":
                if role in interaction.user.roles:
                    await interaction.response.send_message("✅ You've already accepted the rules.", ephemeral=True)
                else:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(f"🎉 Welcome! You're now a **{role.name}**.", ephemeral=True)
            else:
                if role in interaction.user.roles:
                    await interaction.user.remove_roles(role)
                    await interaction.response.send_message("👋 Rules declined and role removed.", ephemeral=True)
                else:
                    await interaction.response.send_message("You don't have the role yet.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Hierarchy error — move my role higher.", ephemeral=True)


class RulesView(discord.ui.View):
    def __init__(self, keys=None):
        super().__init__(timeout=None)
        for key in (keys or RULES_CONFIG.keys()):
            if key in RULES_CONFIG:
                self.add_item(RuleButton(key, "join"))
                self.add_item(RuleButton(key, "leave"))


class ServerRules(commands.Cog):
    def __init__(self, bot):
        self.bot        = bot
        self.state_file = Path(__file__).parents[2] / 'secrets' / 'serverRules_state.json'

    def _load(self) -> dict:
        return json.loads(self.state_file.read_text()) if self.state_file.exists() else {}

    def _save(self, data: dict):
        self.state_file.write_text(json.dumps(data))

    def _embed(self, key: str) -> discord.Embed:
        data = RULES_CONFIG[key]
        r_id = ROLE_IDS[data["role_key"]]
        desc = data["description"].format(role_mention=f"<@&{r_id}>")
        return discord.Embed(title=f"{data['emoji']} Community Rules", description=desc, color=discord.Color.gold())

    async def cog_load(self):
        self.bot.add_view(RulesView())
        self.bot.loop.create_task(self._refresh_all())

    async def _refresh_all(self):
        await self.bot.wait_until_ready()
        saved = self._load()
        kept  = {}
        for key, loc in saved.items():
            if key not in RULES_CONFIG:
                continue
            try:
                channel = self.bot.get_channel(loc['channel_id'])
                if channel:
                    msg = await channel.fetch_message(loc['message_id'])
                    await msg.edit(embed=self._embed(key), view=RulesView([key]))
                    kept[key] = loc
            except Exception:
                pass
        self._save(kept)

    @app_commands.command(name="setup_serverrules", description="Post the server rules acceptance message")
    @app_commands.describe(key="Which rule set to post")
    @app_commands.choices(key=[app_commands.Choice(name=k, value=k) for k in RULES_CONFIG])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_serverrules(self, interaction: discord.Interaction, key: str):
        await interaction.response.send_message("✅ Rules posted!", ephemeral=True)
        msg   = await interaction.channel.send(embed=self._embed(key), view=RulesView([key]))
        state = self._load()
        state[key] = {"channel_id": msg.channel.id, "message_id": msg.id}
        self._save(state)


async def setup(bot):
    await bot.add_cog(ServerRules(bot))
