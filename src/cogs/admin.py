import discord
from discord import app_commands
from discord.ext import commands
import json
import io
from pathlib import Path

POINTS_DB_FILE = Path(__file__).resolve().parents[2] / 'secrets' / 'points_db.json'


def is_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == interaction.client.owner_id
    return app_commands.check(predicate)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync(self, ctx):
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send("🔄 Syncing...", delete_after=5)
        self.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        print(f"✅ Synced commands to {ctx.guild.name}")

    @commands.command(name="clear_global", hidden=True)
    @commands.is_owner()
    async def clear_global(self, ctx):
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send("🧹 Scrubbing global commands...", delete_after=5)
        self.bot.tree.clear_commands(guild=None)
        await self.bot.tree.sync()

    @commands.command(name="debug_tree", hidden=True)
    @commands.is_owner()
    async def debug_tree(self, ctx):
        cmds = await self.bot.tree.fetch_commands(guild=ctx.guild)
        names = [f"/{c.name}" for c in cmds]
        await ctx.send("📋 **Registered commands:**\n" + "\n".join(names))

    @app_commands.command(name="whois", description="Resolve a User ID to a name")
    @app_commands.describe(user_id="The Discord ID to look up")
    @app_commands.default_permissions(administrator=True)
    @is_owner()
    async def whois(self, interaction: discord.Interaction, user_id: str):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ Not a valid ID.", ephemeral=True)
            return

        member = interaction.guild.get_member(uid)
        if not member:
            try:
                user = await self.bot.fetch_user(uid)
                embed = discord.Embed(title=f"User: {user.name}", color=discord.Color.gray())
                embed.description = "⚠️ Not in this server."
                embed.set_thumbnail(url=user.display_avatar.url)
                embed.add_field(name="Global Name", value=user.global_name)
                embed.add_field(name="ID", value=f"`{uid}`")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except discord.NotFound:
                await interaction.response.send_message("❌ User ID not found.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Member: {member.display_name}", color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=member.name, inline=True)
        embed.add_field(name="ID", value=f"`{uid}`", inline=True)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) or "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="export_points", description="Download a points audit report")
    @app_commands.default_permissions(administrator=True)
    @is_owner()
    async def export_points(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔄 Generating...", ephemeral=True)
        if not POINTS_DB_FILE.exists():
            await interaction.followup.send("❌ No points database found.", ephemeral=True)
            return

        with open(POINTS_DB_FILE, 'r') as f:
            data = json.load(f)

        buf = io.StringIO()
        buf.write(f"{'USERNAME':<30} | {'POINTS':<10} | {'ID':<20}\n")
        buf.write("-" * 65 + "\n")
        for uid_str, points in data.items():
            try:
                member = interaction.guild.get_member(int(uid_str))
                name = member.display_name if member else "UNKNOWN (Left Server)"
            except:
                name = "INVALID ID"
            buf.write(f"{name:<30} | {points:<10} | {uid_str:<20}\n")

        buf.seek(0)
        await interaction.followup.send("✅ Report:", file=discord.File(buf, filename="points_audit.txt"), ephemeral=True)

    @app_commands.command(name="say", description="Make the bot say something")
    @app_commands.describe(message="Text to send")
    @app_commands.default_permissions(administrator=True)
    async def say(self, interaction: discord.Interaction, message: str):
        await interaction.response.send_message("✅ Sent!", ephemeral=True)
        await interaction.channel.send(message)

    @app_commands.command(name="membersync", description="Force a full member sync to the database")
    @app_commands.default_permissions(administrator=True)
    @is_owner()
    async def membersync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("MembersSync")
        if not cog:
            await interaction.followup.send("❌ MembersSync cog not loaded.", ephemeral=True)
            return
        try:
            count = await cog.perform_full_guild_sync(interaction.guild)
            await interaction.followup.send(f"✅ {count} members synced.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
