import discord
from discord import app_commands
from discord.ext import commands, tasks
from web3 import Web3
import asyncio
import json
from pathlib import Path
from config import CHANNELS, CONTRACTS, BEER_IS_TOKEN0, RPC_URL

POLL_SECONDS = 30
MAX_BLOCKS   = 500
STATE_FILE   = Path(__file__).resolve().parents[2] / "chain_state.json"

NFT_ABI = [
    {"anonymous": False, "name": "Minted", "type": "event",
     "inputs": [{"indexed": True, "name": "to", "type": "address"}, {"indexed": True, "name": "tokenId", "type": "uint256"}, {"indexed": False, "name": "cid", "type": "string"}]},
    {"anonymous": False, "name": "BatchMinted", "type": "event",
     "inputs": [{"indexed": True, "name": "to", "type": "address"}, {"indexed": False, "name": "startTokenId", "type": "uint256"}, {"indexed": False, "name": "count", "type": "uint256"}]},
    {"name": "nextTokenId", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "totalSupply", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "tokenURI",    "type": "function", "stateMutability": "view", "inputs": [{"name": "tokenId", "type": "uint256"}], "outputs": [{"type": "string"}]},
]

MARKETPLACE_EVENT_ABI = [
    {"anonymous": False, "name": "Purchased", "type": "event",
     "inputs": [{"indexed": True, "name": "listingId", "type": "uint256"}, {"indexed": True, "name": "buyer", "type": "address"}, {"indexed": True, "name": "tokenId", "type": "uint256"}, {"indexed": False, "name": "price", "type": "uint256"}]},
    {"anonymous": False, "name": "Redeemed", "type": "event",
     "inputs": [{"indexed": True, "name": "nftContract", "type": "address"}, {"indexed": True, "name": "tokenId", "type": "uint256"}, {"indexed": True, "name": "redeemer", "type": "address"}]},
    {"anonymous": False, "name": "InventoryDeposited", "type": "event",
     "inputs": [{"indexed": True, "name": "listingId", "type": "uint256"}, {"indexed": False, "name": "count", "type": "uint256"}, {"indexed": False, "name": "totalInventory", "type": "uint256"}]},
]

MARKETPLACE_FUNC_ABI = [
    {"name": "getListing", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "listingId", "type": "uint256"}],
     "outputs": [{"name": "nftContract", "type": "address"}, {"name": "paymentToken", "type": "address"}, {"name": "price", "type": "uint256"}, {"name": "proceeds", "type": "address"}, {"name": "inventoryCount", "type": "uint256"}, {"name": "active", "type": "bool"}]},
    {"name": "getInventory", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "listingId", "type": "uint256"}], "outputs": [{"type": "uint256[]"}]},
]

PAIR_ABI = [
    {"anonymous": False, "name": "Swap", "type": "event",
     "inputs": [{"indexed": True, "name": "sender", "type": "address"}, {"indexed": False, "name": "amount0In", "type": "uint256"}, {"indexed": False, "name": "amount1In", "type": "uint256"}, {"indexed": False, "name": "amount0Out", "type": "uint256"}, {"indexed": False, "name": "amount1Out", "type": "uint256"}, {"indexed": True, "name": "to", "type": "address"}]},
    {"anonymous": False, "name": "Mint", "type": "event",
     "inputs": [{"indexed": True, "name": "sender", "type": "address"}, {"indexed": False, "name": "amount0", "type": "uint256"}, {"indexed": False, "name": "amount1", "type": "uint256"}]},
    {"name": "getReserves", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "_reserve0", "type": "uint112"}, {"name": "_reserve1", "type": "uint112"}]},
]

TREASURY_ABI = [
    {"anonymous": False, "name": "InventoryNFTPurchased", "type": "event",
     "inputs": [{"indexed": True, "name": "producer", "type": "address"}, {"indexed": True, "name": "nftContract", "type": "address"}, {"indexed": True, "name": "tokenId", "type": "uint256"}, {"indexed": False, "name": "ethPaid", "type": "uint256"}]},
]


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
        self.market   = self.w3.eth.contract(address=CONTRACTS["marketplace"], abi=MARKETPLACE_EVENT_ABI)
        self.treasury = self.w3.eth.contract(address=CONTRACTS["treasury"],    abi=TREASURY_ABI)
        self.nft      = self.w3.eth.contract(address=CONTRACTS["beer_nft"],    abi=NFT_ABI)
        self.mkt_r    = self.w3.eth.contract(address=CONTRACTS["marketplace"], abi=MARKETPLACE_FUNC_ABI)
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
        return event.get_logs(from_block=from_block, to_block=to_block)

    def _tx_url(self, log) -> str:
        return f"https://taikoscan.io/tx/{log['transactionHash'].hex()}"

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_chain(self):
        try:
            channel = self.bot.get_channel(CHANNELS["chain_events"])
            if not channel:
                return

            current = (await asyncio.to_thread(lambda: self.w3.eth.block_number)) - 1

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
            await self._handle_nft_mints(channel, from_block, to_block)

            self.last_block = to_block
            self._save_state(to_block)

        except Exception as e:
            print(f"[ChainEvents] Poll error: {e}")

    @poll_chain.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    async def _handle_liquidity(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.pair.events.Mint, from_block, to_block):
            a = log["args"]
            beer_amt, eth_amt = (a["amount0"], a["amount1"]) if BEER_IS_TOKEN0 else (a["amount1"], a["amount0"])
            embed = discord.Embed(
                title="💪 Liquidity Added", url=self._tx_url(log),
                description=f"`{_beer(beer_amt)} BEER` + `{_eth(eth_amt)} ETH` added to the pool",
                color=0x3498DB
            )
            await channel.send(embed=embed)

    async def _handle_swaps(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.pair.events.Swap, from_block, to_block):
            a = log["args"]
            if BEER_IS_TOKEN0:
                if a["amount1In"] > 0:
                    desc, color = f"🟢 **Bought** `{_beer(a['amount0Out'])} BEER` for `{_eth(a['amount1In'])} ETH`", 0x2ECC71
                else:
                    desc, color = f"🔴 **Sold** `{_beer(a['amount0In'])} BEER` for `{_eth(a['amount1Out'])} ETH`", 0xE74C3C
            embed = discord.Embed(title="⚡ BEER/ETH Swap", url=self._tx_url(log), description=desc, color=color)
            embed.set_footer(text=f"Trader: {_short(a['to'])}")
            await channel.send(embed=embed)

    async def _handle_marketplace(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.market.events.Purchased, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="🛒 Beer Sold", url=self._tx_url(log),
                description=f"**#{a['tokenId']}** sold for `{_beer(a['price'])} BEER`",
                color=0xF5A623
            )
            embed.set_footer(text=f"Buyer: {_short(a['buyer'])}")
            await channel.send(embed=embed)

        for log in await asyncio.to_thread(self._get_logs, self.market.events.Redeemed, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="🍻 Beer Poured", url=self._tx_url(log),
                description=f"**#{a['tokenId']}** was redeemed — cheers!",
                color=0x9B59B6
            )
            embed.set_footer(text=f"Redeemer: {_short(a['redeemer'])}")
            await channel.send(embed=embed)

    async def _handle_treasury(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.treasury.events.InventoryNFTPurchased, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="📦 New Batch Added", url=self._tx_url(log),
                description=f"A brewer stocked `{_eth(a['ethPaid'])} ETH` worth of beer\n**#{a['tokenId']}** is now available",
                color=0xE67E22
            )
            embed.set_footer(text=f"Producer: {_short(a['producer'])}")
            await channel.send(embed=embed)

    async def _handle_nft_mints(self, channel, from_block, to_block):
        for log in await asyncio.to_thread(self._get_logs, self.nft.events.BatchMinted, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="🍺 New Beer Batch Minted", url=self._tx_url(log),
                description=f"`{a['count']}` NFTs minted  ·  IDs `{a['startTokenId']}` – `{a['startTokenId'] + a['count'] - 1}`",
                color=0xF5A623
            )
            embed.set_footer(text=f"To: {_short(a['to'])}")
            await channel.send(embed=embed)

        for log in await asyncio.to_thread(self._get_logs, self.nft.events.Minted, from_block, to_block):
            a = log["args"]
            embed = discord.Embed(
                title="🍺 Beer NFT Minted", url=self._tx_url(log),
                description=f"Token `#{a['tokenId']}` minted",
                color=0xF5A623
            )
            embed.set_footer(text=f"To: {_short(a['to'])}")
            await channel.send(embed=embed)

    @app_commands.command(name="pool", description="Show current BEER/ETH pool reserves and price")
    async def pool(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            reserves = await asyncio.to_thread(self.pair.functions.getReserves().call)
            r0, r1 = reserves[0], reserves[1]
            beer_r, eth_r = (r0, r1) if BEER_IS_TOKEN0 else (r1, r0)

            if beer_r == 0 or eth_r == 0:
                await interaction.followup.send("Pool is empty — no liquidity yet.")
                return

            price = eth_r / beer_r
            embed = discord.Embed(
                title="🍺 BEER/ETH Pool",
                description=f"**Reserves**\n`{_beer(beer_r)} BEER`  ·  `{_eth(eth_r)} ETH`\n\n**Price**\n`{price:.6f} ETH` per BEER",
                color=0x3498DB
            )
            channel = self.bot.get_channel(CHANNELS["chain_events"])
            if channel and channel.id != interaction.channel_id:
                await channel.send(embed=embed)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(name="announce-mint", description="Announce the latest NFT batch mint")
    async def announce_mint(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            current = await asyncio.to_thread(lambda: self.w3.eth.block_number)
            total   = await asyncio.to_thread(self.nft.functions.totalSupply().call)
            next_id = await asyncio.to_thread(self.nft.functions.nextTokenId().call)
            channel = self.bot.get_channel(CHANNELS["chain_events"])

            tx_url, logs = None, []
            try:
                lookback = max(1, current - 2000)
                logs = await asyncio.to_thread(self._get_logs, self.nft.events.BatchMinted, lookback, current)
            except Exception:
                pass

            if logs:
                last  = logs[-1]
                a     = last["args"]
                tx_url = self._tx_url(last)
                desc  = f"`{a['count']}` NFTs minted · IDs `{a['startTokenId']}` – `{a['startTokenId'] + a['count'] - 1}`\n`{total}` total Beer NFTs"
            else:
                desc = f"`{total}` total Beer NFTs · next ID: `{next_id}`"

            embed = discord.Embed(title="🍺 New Beer Batch Minted", url=tx_url, description=desc, color=0xF5A623)
            if logs:
                embed.set_footer(text=f"To: {_short(logs[-1]['args']['to'])}")
            if channel and channel.id != interaction.channel_id:
                await channel.send(embed=embed)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(name="announce-stock", description="Announce current marketplace inventory")
    @app_commands.describe(listing_id="Listing ID (default: 0)")
    async def announce_stock(self, interaction: discord.Interaction, listing_id: int = 0):
        await interaction.response.defer()
        try:
            listing   = await asyncio.to_thread(self.mkt_r.functions.getListing(listing_id).call)
            inventory = await asyncio.to_thread(self.mkt_r.functions.getInventory(listing_id).call)
            channel   = self.bot.get_channel(CHANNELS["chain_events"])
            status    = "active" if listing[5] else "inactive"
            ids_str   = f"`{inventory[0]}` – `{inventory[-1]}`" if inventory else "empty"

            tx_url = None
            try:
                current  = await asyncio.to_thread(lambda: self.w3.eth.block_number)
                dep_logs = await asyncio.to_thread(self._get_logs, self.market.events.InventoryDeposited, max(1, current - 2000), current)
                matching = [l for l in dep_logs if l["args"]["listingId"] == listing_id]
                tx_url   = self._tx_url(matching[-1]) if matching else None
            except Exception:
                pass

            embed = discord.Embed(
                title="📦 Market Stocked", url=tx_url,
                description=f"Listing `#{listing_id}` ({status})\n`{listing[4]}` NFTs in custody · IDs {ids_str}",
                color=0x3498DB
            )
            if channel and channel.id != interaction.channel_id:
                await channel.send(embed=embed)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")


async def setup(bot):
    await bot.add_cog(ChainEvents(bot))
