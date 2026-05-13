import asyncio
import os
import time
import discord
from discord import app_commands
from discord.ext import commands
import anthropic
from config import ROLE_IDS

BEST_FRIEND_ROLE_ID = ROLE_IDS["best-friend"]

# --- Dissent detection -----------------------------------------------------------
# Triggers should be platform-specific: legal challenges, fraud accusations,
# skepticism about the mechanics. General beer chat should never fire this.
DISSENT_TRIGGERS = [
    # Fraud / scam accusations
    "scam", "rug", "rugpull", "rug pull", "fraud", "fake", "ponzi", "pyramid scheme",
    "exit scam", "honeypot",
    # Legal / regulatory challenges
    "illegal", "atf", "unlicensed", "bootleg", "shut down", "get raided",
    "against the law", "law enforcement", "you'll be arrested", "get arrested",
    # Value / legitimacy doubts
    "worthless", "no value", "backed by nothing", "not backed", "vaporware",
    "won't work", "will fail", "doomed", "grift", "grifter", "cash grab",
    "just a meme", "not real", "doesn't exist",
    # Beer-specific doubts
    "no real beer", "fake beer", "no brewery", "made up brewery",
]

DISSENT_COOLDOWN_SECONDS = 60  # per channel


def _has_dissent_trigger(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in DISSENT_TRIGGERS)


# --- System prompt blocks --------------------------------------------------------

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

DISSENT_MODIFIER = """

## Dissent Response Mode

Someone in the community has said something questioning or critical of the platform — a fraud accusation, a legal challenge, or skepticism about the mechanics.

You are stepping in proactively — not because you were asked to, but because misinformation deserves a calm, factual correction.

Rules for this response:
- Do NOT be defensive or emotional. Confidence, not aggression.
- Lead with facts and mechanics. Reference ETH collateral, immutable on-chain records, NFT receipts, public auditability — whatever is most relevant to the specific claim.
- Two to four sentences maximum. Be surgical.
- End with a brief open invitation: "feel free to ask anything" or "check it on Taikoscan yourself."
- Do not moralize or lecture. State facts and move on."""


# --- Helpers ---------------------------------------------------------------------

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
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if modifier:
        blocks.append({"type": "text", "text": modifier})
    return blocks


# --- Cog -------------------------------------------------------------------------

class Ask(commands.Cog):
    def __init__(self, bot):
        self.bot    = bot
        api_key     = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self._dissent_cooldowns: dict[int, float] = {}  # channel_id → last fired

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

    async def _fetch_message_anywhere(self, guild: discord.Guild, message_id: int) -> discord.Message | None:
        for channel in guild.text_channels:
            try:
                return await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden):
                continue
        return None

    def _dissent_on_cooldown(self, channel_id: int) -> bool:
        last = self._dissent_cooldowns.get(channel_id, 0)
        return (time.monotonic() - last) < DISSENT_COOLDOWN_SECONDS

    def _stamp_dissent_cooldown(self, channel_id: int):
        self._dissent_cooldowns[channel_id] = time.monotonic()

    # --- /ask slash command ---

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

    # --- /respond admin command ---

    @app_commands.command(name="respond", description="Manually trigger a JaxBot response, optionally aimed at one or more messages")
    @app_commands.describe(
        message_ids="One or more message IDs to read as context, comma-separated (optional)",
        context="Additional context or instruction for JaxBot (optional)",
    )
    @app_commands.default_permissions(administrator=True)
    async def respond(self, interaction: discord.Interaction, message_ids: str = None, context: str = None):
        await interaction.response.defer(ephemeral=True)

        fetched_messages = []
        question_parts   = []
        reply_target     = None  # bot replies to the first message in the list

        if message_ids:
            raw_ids = [s.strip() for s in message_ids.split(",") if s.strip()]
            for raw_id in raw_ids:
                try:
                    msg = await self._fetch_message_anywhere(interaction.guild, int(raw_id))
                except ValueError:
                    await interaction.followup.send(f"❌ `{raw_id}` is not a valid message ID.", ephemeral=True)
                    return
                if not msg:
                    await interaction.followup.send(f"❌ Message ID `{raw_id}` not found.", ephemeral=True)
                    return
                fetched_messages.append(msg)

        if fetched_messages:
            reply_target = fetched_messages[0]
            if len(fetched_messages) == 1:
                question_parts.append(
                    f'A community member named "{reply_target.author.display_name}" posted the following:\n\n'
                    f'"{reply_target.content}"\n\n'
                    f"Respond to this directly and factually."
                )
            else:
                thread_lines = "\n".join(
                    f'  [{m.author.display_name}]: "{m.content}"'
                    for m in fetched_messages
                )
                question_parts.append(
                    f"Here is a thread of messages from the community:\n\n{thread_lines}\n\n"
                    f"Read this exchange as a whole and respond with a single, factual, grounded reply."
                )

        if context:
            question_parts.append(f"Additional context from the admin: {context}")

        if not question_parts:
            question_parts.append("Step in with a general reminder of what Jax Ale Exchange is and why it matters.")

        question = "\n\n".join(question_parts)
        blocks   = _build_system_blocks(DISSENT_MODIFIER)

        try:
            answer = await asyncio.to_thread(self._call_claude, blocks, question)
            if len(answer) > 1900:
                answer = answer[:1897] + "..."
            embed = discord.Embed(description=answer, color=0xF5A623)

            await interaction.channel.send(embed=embed)

            await interaction.followup.send("✅ Done.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)

    # --- Passive listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # @mention path
        if self.bot.user in message.mentions:
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
            return

        # Dissent detection path
        if _has_dissent_trigger(message.content):
            if self._dissent_on_cooldown(message.channel.id):
                return
            self._stamp_dissent_cooldown(message.channel.id)

            question = (
                f'A community member named "{message.author.display_name}" posted the following:\n\n'
                f'"{message.content}"\n\n'
                f"Respond to this directly and factually."
            )
            blocks = _build_system_blocks(DISSENT_MODIFIER)

            async with message.channel.typing():
                try:
                    answer = await asyncio.to_thread(self._call_claude, blocks, question)
                    if len(answer) > 1900:
                        answer = answer[:1897] + "..."
                    embed = discord.Embed(description=answer, color=0xF5A623)
                    await message.reply(embed=embed)
                except Exception as e:
                    print(f"[Dissent] {e}")


async def setup(bot):
    await bot.add_cog(Ask(bot))
