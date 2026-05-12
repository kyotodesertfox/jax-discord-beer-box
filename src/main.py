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

base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / 'secrets' / '.env'
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv('BEER_BOT_TOKEN')

RPC_URL  = "https://rpc.mainnet.taiko.xyz"
PAIR_ADDR = Web3.to_checksum_address("0x7Bbdb6214b0592031933345C8E75186f90d01222")
PAIR_ABI  = [{
    "name": "getReserves", "type": "function", "stateMutability": "view",
    "inputs": [],
    "outputs": [
        {"name": "_reserve0", "type": "uint112"},
        {"name": "_reserve1", "type": "uint112"}
    ]
}]
BEER_IS_TOKEN0 = True  # BEER (0x5a32...) < WETH (0xA518...)

intents = discord.Intents.none()


class BeerBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.notify = notify
        self.w3     = Web3(Web3.HTTPProvider(RPC_URL))
        self.pair   = self.w3.eth.contract(address=PAIR_ADDR, abi=PAIR_ABI)

    async def setup_hook(self):
        print("--- Loading Extensions ---")
        cogs_dir = Path(__file__).parent / 'cogs'
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py') and filename != '__init__.py':
                cog_name = filename[:-3]
                try:
                    await self.load_extension(f'cogs.{cog_name}')
                    print(f"✅ Loaded: {cog_name}")
                except Exception as e:
                    print(f"❌ Failed to load {cog_name}: {e}")
        self.update_status.start()

    async def on_ready(self):
        print(f"BeerBot online as {self.user}")
        print("------")
        self.notify("BeerBot session started.", "SUCCESS")

    def _get_price(self):
        r = self.pair.functions.getReserves().call()
        r0, r1 = r[0], r[1]
        if r0 == 0 or r1 == 0:
            return 0.0
        # BEER is token0 → price = r1/r0 (ETH per BEER)
        if BEER_IS_TOKEN0:
            return r1 / r0
        return r0 / r1

    @tasks.loop(minutes=2)
    async def update_status(self):
        try:
            price = await asyncio.to_thread(self._get_price)
            label = f"$BEER = {price:.6f} ETH"
            await self.change_presence(
                activity=discord.CustomActivity(name=label)
            )
        except Exception as e:
            print(f"[BeerBot] Status update error: {e}")

    @update_status.before_loop
    async def before_status(self):
        await self.wait_until_ready()


bot = BeerBot()


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == '__main__':
    while True:
        try:
            asyncio.run(main())

        except (aiohttp.ClientConnectorError, discord.errors.LoginFailure) as e:
            print(f"Network error: {e}")
            notify("BeerBot: Network Error", "ALERT")
            time.sleep(30)

        except KeyboardInterrupt:
            print("BeerBot stopped by user.")
            notify("BeerBot: Stopped By User", "INFO")
            break

        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            notify(f"BeerBot: Unexpected Error - {e}", "CRITICAL")
            raise e
