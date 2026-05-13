import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="Check if JaxBot is online")
    async def status(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"JaxBot is online! ({latency}ms)", ephemeral=True)

    @app_commands.command(name="help", description="Show available commands")
    async def help_command(self, interaction: discord.Interaction):
        is_admin = interaction.user.guild_permissions.administrator
        categories: dict[str, list[str]] = {}

        for command in self.bot.tree.walk_commands():
            if command.parent:
                continue
            if command.default_member_permissions and not is_admin:
                continue
            cog_name = command.binding.qualified_name if command.binding else "General"
            categories.setdefault(cog_name, []).append(f"`/{command.name}` — {command.description}")

        embed = discord.Embed(title="JaxBot Commands", color=discord.Color.teal())
        if categories:
            for category, cmds in sorted(categories.items()):
                embed.add_field(name=category, value="\n".join(cmds), inline=False)
        else:
            embed.description = "No commands available. Accept the server rules first."

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(General(bot))
