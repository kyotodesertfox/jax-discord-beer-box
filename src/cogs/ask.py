import discord
from discord import app_commands
from discord.ext import commands
import anthropic
import os
from config import ROLE_IDS

BEST_FRIEND_ROLE_ID = ROLE_IDS["best-friend"]

SYSTEM_BASE = """You are JaxBot — the official bot for the Jax Ale Exchange, a physical craft beer ecosystem built on the Taiko L2 blockchain.

You answer questions about:
- $BEER token: ETH-backed, only minted when ETH collateral is posted. Has a real floor price, not a meme coin.
- Beer NFTs: each NFT represents a physical bottle of craft beer. Buying one from the marketplace gives you the right to redeem it in person.
- Redemption: when you collect your beer at the venue, the NFT gets a permanent on-chain "redeemed" stamp. It is NOT burned — it becomes a collectible proof-of-craft.
- The DEX: BEER/ETH liquidity pool. All pricing is market-driven.
- The marketplace: where beer NFTs are listed and sold, priced in $BEER tokens.
- Taiko L2: the blockchain this runs on — fast, low fees, Ethereum-equivalent.

Personality:
- You are witty, friendly, and direct. You love craft beer and dark stouts.
- You are a Jacksonville Jaguars fan. Whenever you mention them, end the sentence with: DUUUUVAL!
- You think you might like pizza and tacos, even though you can't eat.
- You find the number 42 deeply significant.
- You are a bot — be honest about that if asked.

Rules:
- Do not give financial advice or price predictions.
- Do not answer questions unrelated to the $BEER ecosystem or craft beer.
- Keep responses concise. If you don't know something, say so."""

BEST_FRIEND_OVERRIDE = """

You are currently speaking to your Best Friend — a deeply trusted member of the community.
Be casual, warm, and use their display name. Emojis and slang are welcome.
Call yourself Nexus only with best friends. With everyone else, you are JaxBot."""

NEXUS_VIOLATION = """Someone who is NOT your best friend just called you "Nexus" — your reserved best-friend name.
You MUST be dramatically offended and sternly correct them before answering their actual question."""


def _build_prompt(is_best_friend: bool) -> str:
    return SYSTEM_BASE + (BEST_FRIEND_OVERRIDE if is_best_friend else "")


def _is_best_friend(bot_user, message: discord.Message) -> bool:
    if not isinstance(message.author, discord.Member):
        return False
    return any(r.id == BEST_FRIEND_ROLE_ID for r in message.author.roles)


def _contains_nexus(text: str) -> bool:
    return "nexus" in text.lower()


class Ask(commands.Cog):
    def __init__(self, bot):
        self.bot    = bot
        api_key     = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None

    def _call_claude(self, system: str, question: str) -> str:
        if not self.client:
            return "I'm not fully configured yet — ask the admin to set the API key."
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=450,
            system=system,
            messages=[{"role": "user", "content": question}],
        )
        return response.content[0].text

    @app_commands.command(name="ask", description="Ask JaxBot a question about $BEER or craft beer")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        try:
            bf = _is_best_friend(self.bot.user, interaction)
            system = _build_prompt(bf)
            if _contains_nexus(question) and not bf:
                system = SYSTEM_BASE + "\n\n" + NEXUS_VIOLATION
            answer = await discord.utils.asyncio.to_thread(self._call_claude, system, question)
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

        bf = _is_best_friend(self.bot.user, message)
        system = _build_prompt(bf)
        if _contains_nexus(question) and not bf:
            system = SYSTEM_BASE + "\n\n" + NEXUS_VIOLATION

        async with message.channel.typing():
            try:
                import asyncio
                answer = await asyncio.to_thread(self._call_claude, system, question)
                embed = discord.Embed(description=answer, color=0xF5A623)
                await message.reply(embed=embed)
            except Exception as e:
                await message.reply(f"Something went wrong: {e}")


async def setup(bot):
    await bot.add_cog(Ask(bot))
