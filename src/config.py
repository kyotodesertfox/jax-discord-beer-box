import discord

# ==============================================================================
# UNIFIED CONFIGURATION
# ==============================================================================

# --- CHANNELS ---
CHANNELS = {
    "welcome":      1444061318930763898,
    "logs":         1444811174733680722,
    "news":         1443965179472777247,
    "rules":        1444046239363629236,
    "general":      1443949229285441609,
    "chain_events": 1503622733072830464,
    "homebrew":     1443967692972363921,
}

# --- ROLES ---
ROLE_IDS = {
    "homebrewer":    1443976209380937748,
    "homebrewfinds": 1444036391984955403,
    "beta-tester":   1491536075603316766,
    "best-friend":   1504239291704807486,
}

# --- ROLE BUTTON MENUS ---
BUTTON_MENUS = {
    "homebrewfinds": {
        "role_key":    "homebrewfinds",
        "label":       "Homebrew Finds",
        "emoji":       "🍺",
        "style":       discord.ButtonStyle.green,
        "description": (
            "Feeds can generate a lot of notifications, so they are an **opt-in** feature.\n\n"
            "If you receive too many notifications you can mute them through your own notification "
            "preferences — or turn them off entirely here.\n\n"
            "Click below to assign the {role_mention} role."
        ),
    },
}

# --- SERVER RULES ---
RULES_CONFIG = {
    "serverules": {
        "role_key": "homebrewer",
        "label":    "Accept Rules",
        "emoji":    "📜",
        "style":    discord.ButtonStyle.green,
        "description": (
            "- **Be respectful** — treat others with respect; no harassment, personal attacks, or hate speech.\n"
            "- **No inappropriate content** — no explicit, pornographic, or NSFW material.\n"
            "- **No spam or misuse** — no spamming messages, @everyone/@here pings, or channel misuse.\n"
            "- **No advertising** — no unsolicited ads or self-promotion.\n\n"
            "Once you have read the rules, click **Accept** below to receive the {role_mention} role and gain server access."
        ),
    },
}

# --- CHAIN CONTRACTS (Taiko Mainnet) ---
from web3 import Web3

CONTRACTS = {
    "beer_nft":    Web3.to_checksum_address("0x210970F39B3AD4081090100Ed871fE42C54C2101"),
    "pair":        Web3.to_checksum_address("0x7Bbdb6214b0592031933345C8E75186f90d01222"),
    "marketplace": Web3.to_checksum_address("0x2321bDF62364ee38Fcf6b631C9742f6BF61B66Aa"),
    "treasury":    Web3.to_checksum_address("0x631f9D082019E25a2BfD219BF235cA0b742206EC"),
}

BEER_IS_TOKEN0 = True  # BEER (0x5a32...) < WETH (0xA518...) — lower address = token0
RPC_URL = "https://rpc.mainnet.taiko.xyz"
