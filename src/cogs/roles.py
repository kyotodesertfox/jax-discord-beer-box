import discord
from discord import app_commands
from discord.ext import commands
import json
from pathlib import Path
from config import BUTTON_MENUS, ROLE_IDS


class DynamicRoleButton(discord.ui.Button):
    def __init__(self, role_key: str, action: str):
        data = BUTTON_MENUS.get(role_key)
        if not data:
            super().__init__(label="Error", disabled=True)
            return

        self.role_id = ROLE_IDS[data["role_key"]]
        self.action  = action

        if action == "join":
            label, style, emoji = f"Join {data['label']}", discord.ButtonStyle.green, "✅"
        else:
            label, style, emoji = "Leave", discord.ButtonStyle.red, "🗑️"

        super().__init__(label=label, style=style, emoji=emoji, custom_id=f"role_btn:{role_key}:{action}")

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            return
        try:
            if self.action == "join":
                if role in interaction.user.roles:
                    await interaction.response.send_message(f"🤔 You already have **{role.name}**.", ephemeral=True)
                else:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(f"✅ Joined **{role.name}**!", ephemeral=True)
            else:
                if role not in interaction.user.roles:
                    await interaction.response.send_message(f"🤔 You don't have **{role.name}**.", ephemeral=True)
                else:
                    await interaction.user.remove_roles(role)
                    await interaction.response.send_message(f"👋 Left **{role.name}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission. Move my role higher.", ephemeral=True)


class MasterView(discord.ui.View):
    def __init__(self, keys=None):
        super().__init__(timeout=None)
        for key in (keys or BUTTON_MENUS.keys()):
            if key in BUTTON_MENUS:
                self.add_item(DynamicRoleButton(key, "join"))
                self.add_item(DynamicRoleButton(key, "leave"))


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot        = bot
        self.state_file = Path(__file__).parents[2] / 'secrets' / 'roles_state.json'

    def _load(self) -> dict:
        return json.loads(self.state_file.read_text()) if self.state_file.exists() else {}

    def _save(self, data: dict):
        self.state_file.write_text(json.dumps(data))

    def _embed(self, role_key: str) -> discord.Embed:
        data  = BUTTON_MENUS[role_key]
        r_id  = ROLE_IDS[data["role_key"]]
        desc  = data["description"].format(role_mention=f"<@&{r_id}>")
        return discord.Embed(title=f"{data['emoji']} Feed: {data['label']}", description=desc, color=discord.Color.gold())

    async def cog_load(self):
        self.bot.add_view(MasterView())
        self.bot.loop.create_task(self._refresh_all())

    async def _refresh_all(self):
        await self.bot.wait_until_ready()
        saved = self._load()
        kept  = {}
        for role_key, loc in saved.items():
            if role_key not in BUTTON_MENUS:
                continue
            try:
                channel = self.bot.get_channel(loc['channel_id'])
                if channel:
                    msg = await channel.fetch_message(loc['message_id'])
                    await msg.edit(embed=self._embed(role_key), view=MasterView([role_key]))
                    kept[role_key] = loc
            except Exception:
                pass
        self._save(kept)

    @app_commands.command(name="setup_roles", description="Post a role opt-in button")
    @app_commands.describe(role_key="Which role button to post")
    @app_commands.choices(role_key=[app_commands.Choice(name=k, value=k) for k in BUTTON_MENUS])
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_roles(self, interaction: discord.Interaction, role_key: str):
        await interaction.response.send_message("✅ Posted!", ephemeral=True)
        msg   = await interaction.channel.send(embed=self._embed(role_key), view=MasterView([role_key]))
        state = self._load()
        state[role_key] = {"channel_id": msg.channel.id, "message_id": msg.id}
        self._save(state)


async def setup(bot):
    await bot.add_cog(Roles(bot))
