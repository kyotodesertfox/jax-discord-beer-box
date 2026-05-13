import discord
from discord.ext import commands


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self.bot.notify(f"New member: {member.name} ({member.id}) joined.", "INFO")

    @commands.command()
    async def remind(self, ctx, *, message):
        self.bot.notify(f"Discord Reminder from {ctx.author}: {message}", "SUCCESS")
        await ctx.send("✅ Notification sent!")


async def setup(bot):
    await bot.add_cog(Events(bot))
