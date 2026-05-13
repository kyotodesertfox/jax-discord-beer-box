import discord
from discord import app_commands
from discord.ext import commands, tasks
import feedparser
import json
from pathlib import Path
from config import CHANNELS

RSS_URL    = "https://www.homebrewfinds.com/feed/"
STATE_FILE = Path(__file__).resolve().parents[2] / 'secrets' / 'homebrewfinds_state.json'


class HomebrewFinds(commands.Cog):
    def __init__(self, bot):
        self.bot       = bot
        self.last_guid = self._load()
        self.check_feed.start()

    def cog_unload(self):
        self.check_feed.cancel()

    def _load(self):
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f).get('last_guid')
        return None

    def _save(self, guid: str):
        with open(STATE_FILE, 'w') as f:
            json.dump({'last_guid': guid}, f)

    @tasks.loop(minutes=5)
    async def check_feed(self):
        await self.bot.wait_until_ready()
        try:
            feed = feedparser.parse(RSS_URL)
            if not feed.entries:
                return

            new_items = []
            for entry in feed.entries:
                guid = entry.get('id', entry.get('link'))
                if guid == self.last_guid:
                    break
                new_items.append(entry)

            if not new_items:
                return

            new_items = new_items[:5]
            new_items.reverse()

            channel = self.bot.get_channel(CHANNELS["homebrew"])
            if channel:
                for entry in new_items:
                    await channel.send(f"📰 **New Find:** {entry.title}\n{entry.link}")

                latest = feed.entries[0]
                guid   = latest.get('id', latest.get('link'))
                self.last_guid = guid
                self._save(guid)
                print(f"[HomebrewFinds] Posted {len(new_items)} articles.")
        except Exception as e:
            print(f"[HomebrewFinds] Error: {e}")

    @app_commands.command(name="check_news", description="Force-check the Homebrew Finds feed")
    @app_commands.default_permissions(administrator=True)
    async def check_news(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔍 Checking feed...", ephemeral=True)
        self.check_feed.restart()


async def setup(bot):
    await bot.add_cog(HomebrewFinds(bot))
