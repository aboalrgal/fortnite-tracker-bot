import discord
from discord.ext import tasks, commands
import requests
import json
import os

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "123456789012345678"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_DIR = "data"

ENDPOINTS = {
    "cosmetics": "https://fortnite-api.com/v2/cosmetics/br",
    "news": "https://fortnite-api.com/v2/news",
    "shop": "https://fortnite-api.com/v2/shop/br",
    "playlists": "https://fortnite-api.com/v1/playlists",
    "map": "https://fortnite-api.com/v1/map",
    "aes": "https://fortnite-api.com/v2/aes"
}

def load_data(name):
    path = f"{DATA_DIR}/{name}.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(name, content):
    with open(f"{DATA_DIR}/{name}.json", "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)

def deep_compare(old, new):
    changes = []

    if isinstance(old, dict) and isinstance(new, dict):
        for key in new:
            if key not in old:
                changes.append(("added", key, new[key]))
            elif old[key] != new[key]:
                changes.append(("changed", key, old[key], new[key]))
        for key in old:
            if key not in new:
                changes.append(("removed", key, old[key]))

    return changes


@bot.event
async def on_ready():
    print(f"Logged in as: {bot.user}")
    check_updates.start()


@tasks.loop(minutes=5)
async def check_updates():
    channel = bot.get_channel(CHANNEL_ID)

    for name, url in ENDPOINTS.items():
        try:
            old = load_data(name)
            res = requests.get(url).json()
            new = res.get("data", {})

            if not new:
                continue

            changes = deep_compare(old, new)

            if changes:
                save_data(name, new)

                embed = discord.Embed(
                    title=f"🔔 Fortnite Update Detected: {name.upper()}",
                    description=f"{len(changes)} change(s) detected.",
                    color=discord.Color.blue()
                )

                for c in changes[:5]:
                    embed.add_field(
                        name=f"• {c[0].upper()} — {c[1]}",
                        value="Value updated.",
                        inline=False
                    )

                embed.set_footer(text="Auto-update • Powered by Fortnite API")
                await channel.send(embed=embed)

        except Exception as e:
            print(f"Error checking {name}:", e)


bot.run(TOKEN)
