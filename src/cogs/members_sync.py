import discord
from discord.ext import commands, tasks
import hashlib
import os
from dotenv import load_dotenv
from pathlib import Path
from db_manager import DBManager

base_dir = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=base_dir / 'secrets' / '.env')
load_dotenv(dotenv_path=base_dir / 'secrets' / 'db_conn.env')

PREMIUM_ROLE_IDS = [1443966261255082116]


class MembersSync(commands.Cog):
    def __init__(self, bot):
        self.bot              = bot
        self.salt             = os.getenv('MEMBER_SALT')
        self.tracked          = ['display_name', 'roles', 'avatar']

        if not self.salt:
            raise ValueError("❌ MEMBER_SALT not set — MembersSync aborted.")

        try:
            self.db = DBManager()
            self.hourly_sync.start()
        except Exception as e:
            print(f"[MembersSync] DB unavailable, skipping: {e}")

    def cog_unload(self):
        self.hourly_sync.cancel()

    def _hash(self, user_id: int) -> str:
        return hashlib.sha256(f"{user_id}{self.salt}".encode()).hexdigest()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if any(getattr(before, a) != getattr(after, a) for a in self.tracked):
            await self._sync_one(after)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.name != after.name or before.avatar != after.avatar:
            for guild in self.bot.guilds:
                member = guild.get_member(after.id)
                if member:
                    await self._sync_one(member)

    @tasks.loop(hours=24)
    async def hourly_sync(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self.perform_full_guild_sync(guild)

    async def perform_full_guild_sync(self, guild: discord.Guild) -> int:
        count = 0
        async for member in guild.fetch_members(limit=None):
            if not member.bot:
                await self._sync_one(member)
                count += 1
        return count

    async def _sync_one(self, member: discord.Member):
        is_shiny = any(r.id in PREMIUM_ROLE_IDS for r in member.roles)
        sql = """
            INSERT INTO discord_members.users
                (discord_id, username, user_hash, is_shiny, top_role, joined_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (discord_id) DO UPDATE SET
                username  = EXCLUDED.username,
                is_shiny  = EXCLUDED.is_shiny,
                top_role  = EXCLUDED.top_role,
                last_seen = CURRENT_TIMESTAMP;
        """
        conn, cur = self.db.get_cursor()
        try:
            cur.execute(sql, (
                member.id,
                member.display_name,
                self._hash(member.id),
                is_shiny,
                member.top_role.name if member.top_role else "Member",
                member.joined_at,
            ))
            conn.commit()
        except Exception as e:
            print(f"[MembersSync] DB error: {e}")
            conn.rollback()
        finally:
            cur.close()
            self.db.release_conn(conn)


async def setup(bot):
    await bot.add_cog(MembersSync(bot))
