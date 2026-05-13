import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from config import CHANNELS, POINT_RANKS, ROLE_IDS, POINTS_ACCESS_ROLE_ID

base_dir = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=base_dir / 'secrets' / '.env')

WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')
STATE_FILE      = base_dir / 'secrets' / 'points_db.json'


class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db  = self._load()

    def _load(self) -> dict:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(self.db, f)

    def get_score(self, user_id) -> int:
        return self.db.get(str(user_id), 0)

    def set_score(self, user_id, points: int):
        self.db[str(user_id)] = points
        self._save()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id == CHANNELS["logs"]:
            try:
                clean = message.content.replace("```json", "").replace("```", "").strip()
                data  = json.loads(clean)

                if not WEBHOOK_SECRET or data.get("secret") != WEBHOOK_SECRET:
                    await message.add_reaction("⛔")
                    return

                user_id = int(data["user_id"])
                points  = int(data["points"])
                self.set_score(user_id, points)

                guild  = message.guild
                member = guild.get_member(user_id)
                if not member:
                    return

                sorted_ranks = sorted(POINT_RANKS.items(), key=lambda x: x[1]['points'], reverse=True)
                target_key   = None
                for _, rank in sorted_ranks:
                    if points >= rank['points']:
                        target_key = rank['role_key']
                        break

                for _, rank in POINT_RANKS.items():
                    role = guild.get_role(ROLE_IDS[rank['role_key']])
                    if not role:
                        continue
                    if rank['role_key'] == target_key:
                        if role not in member.roles:
                            await member.add_roles(role)
                            await message.add_reaction("📈")
                    else:
                        if role in member.roles:
                            await member.remove_roles(role)
            except Exception:
                pass
            return

        await self.bot.process_commands(message)

    @app_commands.command(name="points", description="Check your club points and rank")
    @app_commands.checks.has_role(POINTS_ACCESS_ROLE_ID)
    async def points(self, interaction: discord.Interaction):
        score        = self.get_score(interaction.user.id)
        current_rank = "Member"
        next_rank    = "Max Rank"
        needed       = 0

        for name, data in sorted(POINT_RANKS.items(), key=lambda x: x[1]['points']):
            if score >= data['points']:
                current_rank = name
            else:
                next_rank = name
                needed    = data['points'] - score
                break

        embed = discord.Embed(title=f"💳 {interaction.user.display_name}", color=discord.Color.gold())
        embed.add_field(name="Balance", value=f"**{score}**", inline=True)
        embed.add_field(name="Rank",    value=f"**{current_rank}**", inline=True)
        if needed > 0:
            embed.set_footer(text=f"{needed} more points to reach {next_rank}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Points(bot))
