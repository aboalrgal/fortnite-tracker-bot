import os
import json
import requests
import discord
from discord.ext import tasks, commands

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ENDPOINTS = {
    "cosmetics": "https://fortnite-api.com/v2/cosmetics/br",
    "news": "https://fortnite-api.com/v2/news",
    "shop": "https://fortnite-api.com/v2/shop/br",
    "playlists": "https://fortnite-api.com/v1/playlists",
    "map": "https://fortnite-api.com/v1/map",
    "aes": "https://fortnite-api.com/v2/aes"
}


# ================== HELPERS ==================
def load_data(name: str):
    """Load old JSON snapshot from disk."""
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_data(name: str, content):
    """Save new JSON snapshot to disk."""
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)


def deep_compare(old, new):
    """
    Shallow dict compare:
    - نركز على مستوى المفاتيح العليا فقط (br, stw, images, pois, build, ...).
    - أي مفتاح جديد = ADDED
    - أي مفتاح اختفى = REMOVED
    - أي مفتاح قيمته تغيرت = CHANGED
    """
    changes = []

    if not isinstance(old, dict) or not isinstance(new, dict):
        if old != new:
            changes.append(("changed", "", old, new))
        return changes

    # Added or changed
    for key in new:
        if key not in old:
            changes.append(("added", key, None, new[key]))
        elif old[key] != new[key]:
            changes.append(("changed", key, old[key], new[key]))

    # Removed
    for key in old:
        if key not in new:
            changes.append(("removed", key, old[key], None))

    return changes


def get_image_for_endpoint(name: str, new_data: dict):
    """
    نحاول نجيب أفضل صورة مرتبطة بالتحديث:
    - news  -> صورة الـ BR news
    - map   -> صورة الخريطة / POIs
    - غيرها -> غالباً بدون صورة
    """
    try:
        if name == "news":
            br = new_data.get("br") or {}
            # بعض الأحيان key اسمه 'image'
            return br.get("image")

        if name == "map":
            images = new_data.get("images") or {}
            # نحاول نجيب POIs ثم الصورة الرئيسية
            return images.get("pois") or images.get("main") or images.get("map")

        # ممكن تطوّرها لاحقاً لـ cosmetics / shop الخ..
        return None
    except Exception:
        return None


# ================== DISCORD EVENTS ==================
@bot.event
async def on_ready():
    print(f"Logged in as: {bot.user}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        # رسالة بداية (عربي + English)
        start_msg = (
            "✅ البوت شغّال الآن ويتابع تحديثات Fortnite API تلقائياً.\n"
            "✅ Bot is now running and tracking Fortnite API updates automatically."
        )
        await channel.send(start_msg)

    check_updates.start()


# ================== MAIN LOOP ==================
@tasks.loop(minutes=5)
async def check_updates():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("CHANNEL_ID is invalid or bot can't see the channel.")
        return

    for name, url in ENDPOINTS.items():
        try:
            old = load_data(name)

            res = requests.get(url, timeout=20)
            res.raise_for_status()
            json_res = res.json()

            new = json_res.get("data", {})
            if not new:
                continue

            changes = deep_compare(old, new)
            if not changes:
                continue  # لا يوجد أي تغييرات

            # حفظ الـ snapshot الجديد
            save_data(name, new)

            # -------- بناء الرسالة ----------
            changes_count = len(changes)

            # عنوان مكوّن من عربي + English
            title = f"🔔 تحديث فورتنايت: {name.upper()} | Fortnite Update: {name.upper()}"

            desc_ar = f"تم اكتشاف **{changes_count}** تغيير/تغيّرات في `{name}`."
            desc_en = f"Detected **{changes_count}** change(s) in `{name}`."

            embed = discord.Embed(
                title=title,
                description=f"{desc_ar}\n{desc_en}",
                color=discord.Color.blue()
            )

            # نضيف ملخّص لأهم التغييرات (أسماء المفاتيح فقط)
            for change_type, key, _, _ in changes[:10]:  # نكتفي بأول 10 تغييرات
                if key == "":
                    key_text = "root"
                else:
                    key_text = key

                if change_type == "added":
                    line_ar = f"✅ تمت إضافة `{key_text}`"
                    line_en = f"✅ ADDED — `{key_text}`"
                elif change_type == "removed":
                    line_ar = f"❌ تم حذف `{key_text}`"
                    line_en = f"❌ REMOVED — `{key_text}`"
                else:
                    line_ar = f"🟡 تم تحديث `{key_text}`"
                    line_en = f"🟡 CHANGED — `{key_text}`"

                embed.add_field(
                    name=f"{key_text}",
                    value=f"{line_ar}\n{line_en}",
                    inline=False
                )

            # صورة مرتبطة بالـ endpoint (مثل news/map)
            image_url = get_image_for_endpoint(name, new)
            if image_url:
                embed.set_image(url=image_url)

            embed.set_footer(
                text="تحديث تلقائي • Powered by Fortnite API | Auto-update • Powered by Fortnite API"
            )

            await channel.send(embed=embed)

        except Exception as e:
            print(f"Error checking {name}:", e)
            try:
                await channel.send(
                    f"⚠️ خطأ أثناء فحص `{name}`:\n`{e}`\n⚠️ Error while checking `{name}`."
                )
            except Exception:
                pass


# ================== RUN ==================
if not TOKEN or CHANNEL_ID == 0:
    print("TOKEN or CHANNEL_ID is missing. Make sure they are set in Railway Variables.")
else:
    bot.run(TOKEN)
