import os
import json
import requests
import discord
from discord.ext import tasks, commands

# ================== الإعدادات الأساسية ==================

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# مفتاح Fortnite-API (لو عندك حطه في Railway باسم FORTNITE_API_KEY)
API_KEY = os.getenv("FORTNITE_API_KEY")
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

API_LANG = "ar"  # نخلي كل شيء بالعربي من الـ API

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ENDPOINTS = {
    "cosmetics": f"https://fortnite-api.com/v2/cosmetics/br?language={API_LANG}",
    "news":      f"https://fortnite-api.com/v2/news?language={API_LANG}",
    "shop":      f"https://fortnite-api.com/v2/shop/br?language={API_LANG}",
    "playlists": f"https://fortnite-api.com/v1/playlists?language={API_LANG}",
    "map":       f"https://fortnite-api.com/v1/map?language={API_LANG}",
    "aes":       f"https://fortnite-api.com/v2/aes?language={API_LANG}"
}

ENDPOINT_NAMES_AR = {
    "cosmetics": "السكنات والعناصر",
    "news": "الأخبار",
    "shop": "الآيتم شوب",
    "playlists": "أطوار اللعب",
    "map": "الخريطة",
    "aes": "مفاتيح التشفير (AES)"
}

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

# ================== دوال مساعدة عامة ==================

def load_data(name: str):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_data(name: str, content):
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)


def deep_compare(old, new):
    """مقارنة بسيطة على مستوى المفاتيح العليا للـ dict."""
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
    """اختيار صورة مناسبة للـ map/news (ULTRA)."""
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


def build_generic_changes_text(name: str, changes):
    """نص مرتب لأي Endpoint غير السكنات."""
    name_ar = ENDPOINT_NAMES_AR.get(name, name)
    lines = []

    lines.append(f"تم اكتشاف **{len(changes)}** تغيير/تغيّرات في قسم `{name_ar}`.\n")

    for change_type, key, _, _ in changes[:10]:
        raw_key = key if key else "root"
        display_key = DISPLAY_KEY_NAMES_AR.get(raw_key, raw_key)

        if change_type == "added":
            emoji = "✅"
            text = f"تمت إضافة {display_key}"
        elif change_type == "removed":
            emoji = "❌"
            text = f"تم حذف {display_key}"
        else:
            emoji = "🟡"
            text = f"تم تعديل {display_key}"

        lines.append(emoji)
        lines.append(f" {text}\n")

    if name == "map":
        lines.append("🗺️")
        lines.append(" تم تحديث الخريطة، الصورة في الأسفل توضح شكل التحديث.\n")
    elif name == "news":
        lines.append("📰")
        lines.append(" تم تحديث لوحة الأخبار، الصورة في الأسفل توضح التغييرات.\n")

    return "\n".join(lines)

# ================== منطق خاص للسكنات (ULTRA Skins) ==================

def extract_cosmetics_list(data_obj):
    """يتأكد أن الناتج دائماً list من الكوزماتكس."""
    if isinstance(data_obj, list):
        return data_obj
    if isinstance(data_obj, dict) and "data" in data_obj and isinstance(data_obj["data"], list):
        return data_obj["data"]
    return []


async def process_cosmetics_update(channel, url):
    """يتعامل مع السكنات بطريقة خاصة: يحسب السكنات الجديدة ويرسل أسماء + صور."""
    old_raw = load_data("cosmetics")
    old_list = extract_cosmetics_list(old_raw) if old_raw is not None else []

    # طلب جديد من الـ API
    res = requests.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    json_res = res.json()
    new_list = json_res.get("data", [])
    new_list = extract_cosmetics_list(new_list)

    # أول تشغيل → نخزن فقط بدون ما نعلن (عشان ما نرسل آلاف السكنات)
    if not old_list:
        save_data("cosmetics", new_list)
        return

    old_ids = {c.get("id") for c in old_list if c.get("id")}
    new_ids = {c.get("id") for c in new_list if c.get("id")}

    added_ids = [cid for cid in new_ids if cid not in old_ids]

    if not added_ids:
        # مافي سكنات جديدة
        save_data("cosmetics", new_list)
        return

    new_cosmetics = [c for c in new_list if c.get("id") in added_ids]

    count = len(new_cosmetics)
    # أسماء السكنات (أي لغة تجي من الـ API – عربي أو إنجليزي)
    names = [c.get("name") for c in new_cosmetics if c.get("name")]
    names_str = "، ".join(names) if names else "بدون أسماء متوفرة"

    title = "🔔 تحديث جديد في فورتنايت – السكنات الجديدة"

    desc_lines = []
    desc_lines.append(f"تم إضافة **{count}** سكن/سكنات جديدة في قسم السكنات والعناصر.\n")
    desc_lines.append("✅")
    desc_lines.append(f" تمت إضافة السكنات التالية:\n{names_str}\n")
    desc_lines.append("🖼️")
    desc_lines.append(" سيتم عرض صور السكنات الجديدة في الرسالة التالية.\n")

    description = "\n".join(desc_lines)

    # الرسالة الأولى: النص
    text_embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    text_embed.set_footer(text="تحديث تلقائي • فورتنايت بالعربي – ULTRA")
    await channel.send(embed=text_embed)

    # الرسالة الثانية: صور السكنات الجديدة
    embeds = []
    for c in new_cosmetics[:8]:  # لو كثير نكتفي بأول 8
        name = c.get("name") or "سكن جديد"
        desc = c.get("description") or ""
        images = c.get("images") or {}
        icon_url = images.get("icon") or images.get("featured") or images.get("smallIcon")

        if not icon_url:
            continue

        e = discord.Embed(
            title=name,
            description=desc,
            color=discord.Color.blue()
        )
        e.set_image(url=icon_url)
        e.set_footer(text="سكن جديد • فورتنايت بالعربي – ULTRA")
        embeds.append(e)

    if embeds:
        # لو مكتبتك تدعم multiple embeds:
        try:
            await channel.send(content="🖼️ صور السكنات الجديدة:", embeds=embeds)
        except TypeError:
            # لو الإصدار قديم → نرسل كل واحد لحاله
            await channel.send(content="🖼️ صور السكنات الجديدة:")
            for e in embeds:
                await channel.send(embed=e)

    # في النهاية نحفظ النسخة الجديدة
    save_data("cosmetics", new_list)

# ================== أحداث الديسكورد ==================

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول باسم: {bot.user}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ تم تشغيل نسخة ULTRA – تتابع كل التغييرات في فورتنايت بالعربي.")
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
            # سكنات لها معالجة خاصة
            if name == "cosmetics":
                await process_cosmetics_update(channel, url)
                continue

            # باقي الـ endpoints (خريطة، أخبار، شوب، AES، أطوار...)
            old_data = load_data(name)
            if old_data is None:
                old_data = {}

            res = requests.get(url, headers=HEADERS, timeout=25)
            res.raise_for_status()
            json_res = res.json()

            new_data = json_res.get("data", {})
            if not new_data:
                continue

            changes = deep_compare(old_data, new_data)
            if not changes:
                save_data(name, new_data)
                continue

            save_data(name, new_data)

            name_ar = ENDPOINT_NAMES_AR.get(name, name)
            title = f"🔔 تحديث جديد في فورتنايت – {name_ar}"
            description = build_generic_changes_text(name, changes)

            # الرسالة الأولى: نص التغييرات
            text_embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue()
            )
            text_embed.set_footer(text="تحديث تلقائي • فورتنايت بالعربي – ULTRA")
            await channel.send(embed=text_embed)

            # الرسالة الثانية: صورة (للخريطة أو الأخبار لو فيه)
            image_url = get_image_for_endpoint(name, new_data)
            if image_url:
                img_embed = discord.Embed(color=discord.Color.blue())
                img_embed.set_image(url=image_url)
                img_embed.set_footer(text="تحديث تلقائي • فورتنايت بالعربي – ULTRA")
                await channel.send(embed=img_embed)

        except Exception as e:
            print(f"خطأ أثناء فحص {name}: {e}")

# ================== تشغيل البوت ==================

if not TOKEN or CHANNEL_ID == 0:
    print("❌ تأكد إنك ضايف متغيرات TOKEN و CHANNEL_ID في Railway.")
else:
    bot.run(TOKEN)
