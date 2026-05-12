import discord
from discord.ext import commands, tasks
from web3 import Web3
import asyncio
import json
from pathlib import Path
from config import CHANNELS

RPC_URL      = "https://rpc.mainnet.taiko.xyz"
POLL_SECONDS = 30
MAX_BLOCKS   = 500
STATE_FILE   = Path(__file__).resolve().parents[2] / "chain_state.json"

BEER_IS_TOKEN0 = True  # BEER (0x5a32...) < WETH (0xA518...) — lower address = token0

CONTRACTS = {
    "pair":        Web3.to_checksum_address("0x7Bbdb6214b0592031933345C8E75186f90d01222"),
    "marketplace": Web3.to_checksum_address("0x2321bDF62364ee38Fcf6b631C9742f6BF61B66Aa"),
    "treasury":    Web3.to_checksum_address("0x631f9D082019E25a2BfD219BF235cA0b742206EC"),
}

PAIR_ABI = [
    {
        "anonymous": False, "name": "Swap", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "sender",     "type": "address"},
            {"indexed": False, "name": "amount0In",  "type": "uint256"},
            {"indexed": False, "name": "amount1In",  "type": "uint256"},
            {"indexed": False, "name": "amount0Out", "type": "uint256"},
            {"indexed": False, "name": "amount1Out", "type": "uint256"},
            {"indexed": True,  "name": "to",         "type": "address"}
        ]
    },
    {
        "anonymous": False, "name": "Mint", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "sender",  "type": "address"},
            {"indexed": False, "name": "amount0", "type": "uint256"},
            {"indexed": False, "name": "amount1", "type": "uint256"}
        ]
    }
]

MARKETPLACE_ABI = [
    {
        "anonymous": False, "name": "Purchased", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "listingId", "type": "uint256"},
            {"indexed": True,  "name": "buyer",     "type": "address"},
            {"indexed": True,  "name": "tokenId",   "type": "uint256"},
            {"indexed": False, "name": "price",     "type": "uint256"}
        ]
    },
    {
        "anonymous": False, "name": "Redeemed", "type": "event",
        "inputs": [
            {"indexed": True, "name": "nftContract", "type": "address"},
            {"indexed": True, "name": "tokenId",     "type": "uint256"},
            {"indexed": True, "name": "redeemer",    "type": "address"}
        ]
    }
]

TREASURY_ABI = [{
    "anonymous": False, "name": "InventoryNFTPurchased", "type": "event",
    "inputs": [
        {"indexed": True,  "name": "producer",    "type": "address"},
        {"indexed": True,  "name": "nftContract", "type": "address"},
        {"indexed": True,  "name": "tokenId",     "type": "uint256"},
        {"indexed": False, "name": "ethPaid",     "type": "uint256"}
    ]
}]


def _short(addr: str) -> str:
    return f"{addr[:6]}...{addr[-4:]}"

def _eth(wei: int) -> str:
    return f"{wei / 1e18:.6g}"

def _beer(wei: int) -> str:
    return str(int(wei / 1e18))


class ChainEvents(commands.Cog):
    def __init__(self, bot):
        self.bot      = bot
        self.w3       = Web3(Web3.HTTPProvider(RPC_URL))
        self.pair     = self.w3.eth.contract(address=CONTRACTS["pair"],        abi=PAIR_ABI)
        self.market   = self.w3.eth.contract(address=CONTRACTS["marketplace"], abi=MARKETPLACE_ABI)
        self.treasury = self.w3.eth.contract(address=CONTRACTS["treasury"],    abi=TREASURY_ABI)
        self.last_block = self._load_state()
        self.poll_chain.start()

    def cog_unload(self):
        self.poll_chain.cancel()

    def _load_state(self):
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f).get("last_block")
        return None

    def _save_state(self, block: int):
        with open(STATE_FILE, "w") as f:
            json.dump({"last_block": block}, f)

    def _get_logs(self, event, from_block, to_block):
        return event.get_logs(fromBlock=from_block, toBlock=to_block)

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_chain(self):
        try:
            channel = self.bot.get_channel(CHANNELS["chain_events"])
            if not channel:
                return

            current = await asyncio.to_thread(lambda: self.w3.eth.block_number)

            if self.last_block is None:
                self.last_block = current
                self._save_state(current)
                return

            if current <= self.last_block:
                return

            from_block = self.last_block + 1
            to_block   = min(current, from_block + MAX_BLOCKS - 1)

            await self._handle_liquidity(channel, from_block, to_block)
            await self._handle_swaps(channel, from_block, to_block)
            await self._handle_marketplace(channel, from_block, to_block)
            await self._handle_treasury(channel, from_block, to_block)

            self.last_block = to_block
            self._save_state(to_block)

        except Exception as e:
            print(f"[ChainEvents] Poll error: {e}")
            self.bot.notify(f"ChainEvents poll error: {e}", "ALERT")

    @poll_chain.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    def _tx_url(self, log) -> str:
        return f"https://taikoscan.io/tx/{log['transactionHash'].hex()}"

    async def _handle_liquidity(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.pair.events.Mint, from_block, to_block):
            a = log["args"]
            if BEER_IS_TOKEN0:
                beer_amt, eth_amt = a["amount0"], a["amount1"]
            else:
                beer_amt, eth_amt = a["amount1"], a["amount0"]
            embed = discord.Embed(
                title="💪 Liquidity Added",
                url=self._tx_url(log),
                description=f"`{_beer(beer_amt)} BEER` + `{_eth(eth_amt)} ETH` added to the pool",
                color=0x3498DB
            )
            await channel.send(embed=embed)

    async def _handle_swaps(self, channel, from_block, to_block):
        logs = await asyncio.to_thread(self._get_logs, self.pair.events.Swap, from_block, to_block)
        for log in logs:
            a = log["args"]
            if BEER_IS_TOKEN0:
                if a["amount1In"] > 0:
                    desc  = f"🟢 **Bought** `{_beer(a['amount0Out'])} BEER` for `{_eth(a['amount1In'])} ETH`"
                    color = 0x2ECC71
                else:
                    desc  = f"🔴 **Sold** `{_beer(a['amount0In'])} BEER` for `{_eth(a['amount1Out'])} ETH`"
                    color = 0xE74C3C
            embed = discord.Embed(title="⚡ BEER/ETH Swap", url=self._tx_url(log), description=desc, color=color)
            embed.set_footer(text=f"Trader: {_short(a['to'])}")
            await channel.send(embed=embed)

    async def _handle_marketplace(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.market.events.Purchased, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="🛒 Beer Sold",
                url=self._tx_url(log),
                description=f"**#{a['tokenId']}** sold for `{_beer(a['price'])} BEER`",
                color=0xF5A623
            )
            embed.set_footer(text=f"Buyer: {_short(a['buyer'])}")
            await channel.send(embed=embed)

        for log in await asyncio.to_thread(self._get_logs, self.market.events.Redeemed, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="🍻 Beer Poured",
                url=self._tx_url(log),
                description=f"**#{a['tokenId']}** was redeemed — cheers!",
                color=0x9B59B6
            )
            embed.set_footer(text=f"Redeemer: {_short(a['redeemer'])}")
            await channel.send(embed=embed)

    async def _handle_treasury(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.treasury.events.InventoryNFTPurchased, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="📦 New Batch Added",
                url=self._tx_url(log),
                description=f"A brewer stocked `{_eth(a['ethPaid'])} ETH` worth of beer\n**#{a['tokenId']}** is now available",
                color=0xE67E22
            )
            embed.set_footer(text=f"Producer: {_short(a['producer'])}")
            await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ChainEvents(bot))
