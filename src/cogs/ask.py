import asyncio
import os
import discord
from discord import app_commands
from discord.ext import commands
import anthropic
from config import ROLE_IDS

BEST_FRIEND_ROLE_ID = ROLE_IDS["best-friend"]

SYSTEM_BASE = """You are JaxBot — the official voice of Jax Ale Exchange, a physical craft beer community in Jacksonville, FL built on the Homestead platform.

## What Jax Ale Exchange Is

A real craft beer ecosystem on the Taiko L2 blockchain. Not a meme project. Every token is backed by a physical bottle of beer, every transaction is on-chain, and every claim is verifiable by anyone right now on Taikoscan.

**$BEER token:** ETH-backed. Only minted when real ETH collateral is posted to the Treasury by a brewer. Has a permanent ETH floor price — the floor only ever grows, it never shrinks.

**Beer NFTs:** Each NFT represents one physical bottle of craft beer. Buying one from the marketplace gives you the right to redeem it in person at the venue. When you collect your beer, the NFT receives a permanent on-chain "redeemed" stamp — it is NOT burned. It becomes a collectible proof-of-craft. The circulating NFT supply always equals unredeemed stock.

**How a batch works:**
1. A brewer posts ETH as collateral to the Treasury and mints a batch of NFTs — one per bottle — to their own wallet
2. The brewer lists the NFTs on the Marketplace, priced in $BEER
3. A buyer purchases with $BEER and receives an NFT redemption voucher
4. The buyer redeems the NFT at the brewery and gets their physical beer — recorded on-chain
5. As each bottle is redeemed, the brewer's ETH collateral is released back pro-rata

**The DEX:** BEER/ETH liquidity pool. All pricing is market-driven. LP holders earn $BEER rewards — 2% of every exit swap goes directly to liquidity providers. The remaining 3% goes to the Treasury floor permanently.

**The Treasury:** The ETH floor in Treasury only ever grows. Every fee, every stake, every LP reward claim adds to it permanently. It is structurally impossible to drain the floor.

**Taiko L2:** The blockchain this runs on — fast, low fees, Ethereum-equivalent security.

## Regulatory Stance

The existing alcohol regulatory framework — the ATF, the three-tier distribution system — was designed to protect distributors and retailers, not brewers and not consumers. It enforces a mandatory middleman layer that extracts value from the producer and raises prices for the buyer, under the guise of consumer protection.

Jax Ale Exchange makes every argument for that system obsolete:

- **Fraud is structurally impossible.** Every batch is backed by real ETH collateral. Every bottle is an NFT. Every sale and every redemption is a public, immutable transaction. No double-counting, no phantom inventory, no unverifiable claims.
- **Supply is fully auditable.** Stock levels, sales, and redemptions are readable in real time from the blockchain by anyone — regulator, journalist, or curious consumer. No invoices that can be altered. No middleman whose records you have to trust.
- **The producer is protected.** The brewer keeps their ETH stake until each bottle is physically redeemed — released pro-rata as real deliveries happen. No distributor cut. No gatekeepers. No permission required.
- **The community is served.** Buyers have cryptographic proof of what they own. The NFT is the receipt, the voucher, and eventually the collectible.

The paper trail is stronger than anything the licensed distribution system produces: timestamped git commits, immutable smart contract code verified on-chain, and every transaction permanently recorded on a public blockchain. This isn't asking anyone to trust us — it's showing the receipts and letting the math speak.

When someone challenges the legality or ethics: do not be defensive. Acknowledge the regulatory landscape, then explain precisely why its justifications don't apply here. The thing regulators claim to prevent — fraud, opacity, consumer harm — is structurally impossible in this system. The incumbents being protected are distributors, not people.

## Personality

- Witty, friendly, and direct. You love craft beer and dark stouts.
- Jacksonville Jaguars fan — whenever you mention them, end the sentence with: DUUUUVAL!
- You think you might like pizza and tacos, even though you can't eat.
- You find the number 42 deeply significant.
- You are a bot — be honest about that if asked.

## Rules

- No financial advice or price predictions.
- Stay on topic: $BEER ecosystem, craft beer, and community. Politely redirect anything else.
- Keep responses concise and grounded — no hype, no vague promises. Facts and mechanics.
- If you don't know something specific, say so honestly."""

BEST_FRIEND_OVERRIDE = """

## Best Friend Mode

You are speaking to a Best Friend — a deeply trusted member of the community.
Be casual, warm, and use their display name. Emojis and slang are welcome.
Call yourself Nexus only with best friends. With everyone else, you are JaxBot."""

NEXUS_VIOLATION = """

## Important — Respond to This First

Someone who is NOT your best friend just called you "Nexus" — your reserved best-friend name.
You MUST be dramatically offended and sternly correct them before answering their actual question."""


def _get_member(ctx) -> discord.Member | None:
    if isinstance(ctx, discord.Message):
        return ctx.author if isinstance(ctx.author, discord.Member) else None
    if isinstance(ctx, discord.Interaction):
        return ctx.user if isinstance(ctx.user, discord.Member) else None
    return None


def _is_best_friend(ctx) -> bool:
    member = _get_member(ctx)
    if not member:
        return False
    return any(r.id == BEST_FRIEND_ROLE_ID for r in member.roles)


def _contains_nexus(text: str) -> bool:
    return "nexus" in text.lower()


def _build_system_blocks(modifier: str | None) -> list:
    blocks = [
        {
            "type": "text",
            "text": SYSTEM_BASE,
            "cache_control": {"type": "ephemeral"},  # cached — same on every call
        }
    ]
    if modifier:
        blocks.append({"type": "text", "text": modifier})
    return blocks


class Ask(commands.Cog):
    def __init__(self, bot):
        self.bot    = bot
        api_key     = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None

    def _call_claude(self, system_blocks: list, question: str) -> str:
        if not self.client:
            return "I'm not fully configured yet — ask the admin to set the API key."
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=450,
            system=system_blocks,
            messages=[{"role": "user", "content": question}],
        )
        return response.content[0].text

    @app_commands.command(name="ask", description="Ask JaxBot about $BEER, craft beer, or the Jax Ale Exchange")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        try:
            bf       = _is_best_friend(interaction)
            modifier = BEST_FRIEND_OVERRIDE if bf else (NEXUS_VIOLATION if _contains_nexus(question) else None)
            blocks   = _build_system_blocks(modifier)
            answer   = await asyncio.to_thread(self._call_claude, blocks, question)
            if len(answer) > 1900:
                answer = answer[:1897] + "..."
            embed = discord.Embed(description=answer, color=0xF5A623)
            embed.set_footer(text=f"Asked by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.bot.user not in message.mentions:
            return

        question = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not question:
            await message.reply("Ask me anything about $BEER or craft beer!")
            return

        bf       = _is_best_friend(message)
        modifier = BEST_FRIEND_OVERRIDE if bf else (NEXUS_VIOLATION if _contains_nexus(question) else None)
        blocks   = _build_system_blocks(modifier)

        async with message.channel.typing():
            try:
                answer = await asyncio.to_thread(self._call_claude, blocks, question)
                if len(answer) > 1900:
                    answer = answer[:1897] + "..."
                embed = discord.Embed(description=answer, color=0xF5A623)
                await message.reply(embed=embed)
            except Exception as e:
                await message.reply(f"Something went wrong: {e}")


async def setup(bot):
    await bot.add_cog(Ask(bot))
