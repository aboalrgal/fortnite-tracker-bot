import os
import json
import requests
import discord
from discord.ext import tasks, commands

# ================== الإعدادات الأساسية ==================

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# مفتاح Fortnite-API (إذا عندك واحد حطه في Railway باسم FORTNITE_API_KEY)
API_KEY = os.getenv("FORTNITE_API_KEY")
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

# لغة بيانات Fortnite-API
API_LANG = "ar"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# روابط الـ API مع language=ar
ENDPOINTS = {
    "cosmetics": f"https://fortnite-api.com/v2/cosmetics/br?language={API_LANG}",
    "news":      f"https://fortnite-api.com/v2/news?language={API_LANG}",
    "shop":      f"https://fortnite-api.com/v2/shop/br?language={API_LANG}",
    "playlists": f"https://fortnite-api.com/v1/playlists?language={API_LANG}",
    "map":       f"https://fortnite-api.com/v1/map?language={API_LANG}",
    "aes":       f"https://fortnite-api.com/v2/aes?language={API_LANG}"
}

# أسماء عربية لكل Endpoint
ENDPOINT_NAMES_AR = {
    "cosmetics": "السكنات والعناصر",
    "news": "الأخبار",
    "shop": "الآيتم شوب",
    "playlists": "أطوار اللعب",
    "map": "الخريطة",
    "aes": "مفاتيح التشفير (AES)"
}

# ترجمة لبعض المفاتيح داخل الـ JSON
DISPLAY_KEY_NAMES_AR = {
    "images": "الصور",
    "pois": "نقاط الاهتمام",
    "br": "أخبار الباتل رويال",
    "stw": "أخبار أنقِذ العالم",
    "build": "رقم البناء (Build)",
    "mainKey": "المفتاح الرئيسي",
    "dynamicKeys": "المفاتيح الديناميكية",
    "updated": "وقت آخر تحديث"
}


# ================== دوال مساعدة ==================

def load_data(name: str):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_data(name: str, content):
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)


def deep_compare(old, new):
    changes = []

    if not isinstance(old, dict) or not isinstance(new, dict):
        if old != new:
            changes.append(("changed", "", old, new))
        return changes

    for key in new:
        if key not in old:
            changes.append(("added", key, None, new[key]))
        elif old[key] != new[key]:
            changes.append(("changed", key, old[key], new[key]))

    for key in old:
        if key not in new:
            changes.append(("removed", key, old[key], None))

    return changes


def get_image_for_endpoint(name: str, new_data: dict):
    try:
        if name == "news":
            br = new_data.get("br") or {}
            return br.get("image")

        if name == "map":
            images = new_data.get("images") or {}
            return images.get("pois") or images.get("main") or images.get("map")

        return None
    except Exception:
        return None


def build_changes_text(name: str, changes):
    """
    يرجّع نص بالشكل اللي تبيه:

    تم اكتشاف 2 تغيير/تغيّرات في قسم الخريطة.

    ✅
     تمت إضافة الصور
    ✅
     تمت إضافة نقاط الاهتمام

    🗺️
     تم تحديث الخريطة، الصورة في الأسفل توضح شكل التحديث.
    """
    name_ar = ENDPOINT_NAMES_AR.get(name, name)
    lines = []

    # السطر الأساسي
    lines.append(f"تم اكتشاف **{len(changes)}** تغيير/تغيّرات في قسم `{name_ar}`.\n")

    # كل تغيير على سطرين: إيموجي ثم النص
    for change_type, key, _, _ in changes[:10]:
        raw_key = key if key else "root"
        display_key = DISPLAY_KEY_NAMES_AR.get(raw_key, raw_key)

        if change_type == "added":
            text = f"تمت إضافة {display_key}"
        elif change_type == "removed":
            text = f"تم حذف {display_key}"
        else:
            text = f"تم تعديل {display_key}"

        lines.append("✅" if change_type == "added" else ("❌" if change_type == "removed" else "🟡"))
        lines.append(f" {text}\n")

    # ملاحظة خاصة للخريطة والأخبار
    if name == "map":
        lines.append("🗺️")
        lines.append(" تم تحديث الخريطة، الصورة في الأسفل توضح شكل التحديث.\n")
    elif name == "news":
        lines.append("📰")
        lines.append(" تم تحديث لوحة الأخبار، الصورة في الأسفل توضح التغييرات.\n")

    return "\n".join(lines)


# ================== أحداث الديسكورد ==================

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول باسم: {bot.user}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ البوت شغّال الآن ويتابع تحديثات فورتنايت من الـ API (عربي بالكامل).")
    check_updates.start()


# ================== المهمة الدورية ==================

@tasks.loop(minutes=5)
async def check_updates():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("CHANNEL_ID غير صحيح أو البوت ما يقدر يشوف القناة.")
        return

    for name, url in ENDPOINTS.items():
        try:
            old = load_data(name)

            res = requests.get(url, headers=HEADERS, timeout=25)
            res.raise_for_status()
            json_res = res.json()

            new = json_res.get("data", {})
            if not new:
                continue

            changes = deep_compare(old, new)
            if not changes:
                continue

            save_data(name, new)

            name_ar = ENDPOINT_NAMES_AR.get(name, name)
            title = f"🔔 تحديث جديد في فورتنايت – {name_ar}"
            description = build_changes_text(name, changes)

            # الرسالة الأولى: نص فقط
            text_embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue()
            )
            text_embed.set_footer(text="تحديث تلقائي • فورتنايت بالعربي")
            await channel.send(embed=text_embed)

            # الرسالة الثانية (إذا فيه صورة): صورة فقط
            image_url = get_image_for_endpoint(name, new)
            if image_url:
                img_embed = discord.Embed(color=discord.Color.blue())
                img_embed.set_image(url=image_url)
                img_embed.set_footer(text="تحديث تلقائي • فورتنايت بالعربي")
                await channel.send(embed=img_embed)

        except Exception as e:
            print(f"خطأ أثناء فحص {name}: {e}")


# ================== تشغيل البوت ==================

if not TOKEN or CHANNEL_ID == 0:
    print("❌ تأكد إنك ضايف متغيرات TOKEN و CHANNEL_ID في Railway.")
else:
    bot.run(TOKEN)
