import discord
from discord.ext import commands


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self.bot.notify(f"New member: {member.name} ({member.id}) joined.", "INFO")


async def setup(bot):
    await bot.add_cog(Events(bot))
