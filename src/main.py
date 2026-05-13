import discord
from discord.ext import commands, tasks
from web3 import Web3
import os
import asyncio
import aiohttp
import time
from notifications import notify
from dotenv import load_dotenv
from pathlib import Path
from config import CONTRACTS, BEER_IS_TOKEN0, RPC_URL

base_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=base_dir / 'secrets' / '.env')

TOKEN = os.getenv('BEER_BOT_TOKEN')

PAIR_ABI = [{
    "name": "getReserves", "type": "function", "stateMutability": "view",
    "inputs": [],
    "outputs": [
        {"name": "_reserve0", "type": "uint112"},
        {"name": "_reserve1", "type": "uint112"},
    ]
}]

intents = discord.Intents.default()
intents.members         = True
intents.message_content = True


class JaxBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.notify = notify
        self.w3     = Web3(Web3.HTTPProvider(RPC_URL))
        self.pair   = self.w3.eth.contract(address=CONTRACTS["pair"], abi=PAIR_ABI)

    async def setup_hook(self):
        print("--- Loading Extensions ---")
        cogs_dir = Path(__file__).parent / 'cogs'
        for filename in sorted(os.listdir(cogs_dir)):
            if filename.endswith('.py') and filename != '__init__.py':
                cog_name = filename[:-3]
                try:
                    await self.load_extension(f'cogs.{cog_name}')
                    print(f"✅ Loaded: {cog_name}")
                except Exception as e:
                    print(f"❌ Failed: {cog_name} — {e}")
        self.update_status.start()
        await self.tree.sync()
        print("✅ Slash commands synced")

    async def on_ready(self):
        if self.user.name != 'Jax Ale eXchange Bot':
            await self.user.edit(username='Jax Ale eXchange Bot')
            print("✅ Bot renamed to Jax Ale eXchange Bot")
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"✅ Guild sync: {guild.name}")
        print(f"JaxBot online as {self.user}")
        self.notify("JaxBot session started.", "SUCCESS")

    def _get_price(self):
        r = self.pair.functions.getReserves().call()
        r0, r1 = r[0], r[1]
        if r0 == 0 or r1 == 0:
            return 0.0
        return (r1 / r0) if BEER_IS_TOKEN0 else (r0 / r1)

    @tasks.loop(minutes=2)
    async def update_status(self):
        try:
            price = await asyncio.to_thread(self._get_price)
            await self.change_presence(
                activity=discord.CustomActivity(name=f"$BEER = {price:.6f} ETH")
            )
        except Exception as e:
            print(f"[Status] {e}")

    @update_status.before_loop
    async def before_status(self):
        await self.wait_until_ready()


bot = JaxBot()


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == '__main__':
    while True:
        try:
            asyncio.run(main())
        except (aiohttp.ClientConnectorError, discord.errors.LoginFailure) as e:
            print(f"Network error: {e}")
            notify("JaxBot: Network Error", "ALERT")
            time.sleep(30)
        except KeyboardInterrupt:
            notify("JaxBot: Stopped By User", "INFO")
            break
        except Exception as e:
            print(f"⚠️ {e}")
            notify(f"JaxBot: Unexpected Error — {e}", "CRITICAL")
            raise
