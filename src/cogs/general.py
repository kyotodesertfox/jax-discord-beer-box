import discord
from discord import app_commands
from discord.ext import commands
import inspect


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _user_can_use(self, interaction: discord.Interaction, command: app_commands.Command) -> bool:
        if command.name.startswith(("setup_", "clear_", "debug_", "export_", "sync")):
            return interaction.user.guild_permissions.administrator

        required = getattr(command, 'default_member_permissions', None)
        if required and not interaction.user.guild_permissions.is_superset(required):
            return False

        for check in command.checks:
            try:
                result = check(interaction)
                if inspect.iscoroutine(result):
                    await result
            except app_commands.AppCommandError:
                return False
            except Exception:
                return False

        return True

    @app_commands.command(name="status", description="Check if JaxBot is online")
    async def status(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 JaxBot is online! ({latency}ms)", ephemeral=True)

    @app_commands.command(name="help", description="Show commands available to you")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("⚙️ Compiling your command list...", ephemeral=True)

        available: dict[str, list[str]] = {}
        for command in self.bot.tree.walk_commands():
            if command.name == 'help' or command.parent or command.binding is None:
                continue
            if await self._user_can_use(interaction, command):
                category = getattr(command, 'cog_name', None) or "General"
                available.setdefault(category, []).append(f"`/{command.name}` — {command.description}")

        embed = discord.Embed(
            title="📚 JaxBot Commands",
            description="Commands your roles allow you to use:",
            color=discord.Color.teal()
        )
        if not available:
            embed.description = "You don't have access to any commands yet. Accept the server rules first."
        else:
            for category, cmds in available.items():
                embed.add_field(name=f"🛠️ {category}", value="\n".join(cmds), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(General(bot))
