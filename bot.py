import os
import json
import requests
import discord
from discord.ext import tasks, commands

# ================== الإعدادات الأساسية ==================

# توكن البوت ورقم القناة من متغيرات البيئة في Railway
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

# لغة Fortnite-API (نخليها عربي)
API_LANG = "ar"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# مجلد تخزين نسخ JSON السابقة
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# روابط الـ API مع إضافة language=ar
ENDPOINTS = {
    "cosmetics": f"https://fortnite-api.com/v2/cosmetics/br?language={API_LANG}",
    "news":      f"https://fortnite-api.com/v2/news?language={API_LANG}",
    "shop":      f"https://fortnite-api.com/v2/shop/br?language={API_LANG}",
    "playlists": f"https://fortnite-api.com/v1/playlists?language={API_LANG}",
    "map":       f"https://fortnite-api.com/v1/map?language={API_LANG}",
    "aes":       f"https://fortnite-api.com/v2/aes?language={API_LANG}"
}

# أسماء عربية لكل Endpoint (للعناوين)
ENDPOINT_NAMES_AR = {
    "cosmetics": "السكنات والعناصر",
    "news": "الأخبار",
    "shop": "الآيتم شوب",
    "playlists": "أطوار اللعب",
    "map": "الخريطة",
    "aes": "مفاتيح التشفير (AES)"
}

# ترجمة مفاتيح مهمة في JSON
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
    """قراءة نسخة JSON القديمة من القرص."""
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_data(name: str, content):
    """حفظ نسخة JSON جديدة في القرص."""
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)


def deep_compare(old, new):
    """
    مقارنة مبسّطة على مستوى المفاتيح العليا فقط:
    - added   → مفتاح جديد
    - removed → مفتاح انحذف
    - changed → نفس المفتاح لكن قيمته تغيّرت
    """
    changes = []

    if not isinstance(old, dict) or not isinstance(new, dict):
        if old != new:
            changes.append(("changed", "", old, new))
        return changes

    # المضافة أو المعدّلة
    for key in new:
        if key not in old:
            changes.append(("added", key, None, new[key]))
        elif old[key] != new[key]:
            changes.append(("changed", key, old[key], new[key]))

    # المحذوفة
    for key in old:
        if key not in new:
            changes.append(("removed", key, old[key], None))

    return changes


def get_image_for_endpoint(name: str, new_data: dict):
    """
    اختيار صورة مناسبة حسب نوع الـ endpoint:
    - news: صورة أخبار الـ BR
    - map : خريطة الـ POIs (بالعربي لو Epic داعمة اللغة)
    """
    try:
        if name == "news":
            br = new_data.get("br") or {}
            return br.get("image")

        if name == "map":
            images = new_data.get("images") or {}
            # نحاول أولاً خريطة الـ POIs (عادةً فيها أسماء الأماكن)
            return images.get("pois") or images.get("main") or images.get("map")

        # باقي الأنواع ما نربط لها صورة حالياً
        return None
    except Exception:
        return None


# ================== أحداث الديسكورد ==================

@bot.event
async def on_ready():
    """يتم استدعاؤها عند تشغيل البوت بنجاح."""
    print(f"تم تسجيل الدخول باسم: {bot.user}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ البوت شغّال الآن ويتابع تحديثات فورتنايت من الـ API (باللغة العربية).")

    check_updates.start()


# ================== المهمة الدورية ==================

@tasks.loop(minutes=5)
async def check_updates():
    """
    كل ٥ دقائق:
    - نطلب بيانات جديدة من كل Endpoint
    - نقارنها مع النسخة المخزّنة
    - لو فيه تغييرات → نرسل Embed واحد بالعربي لكل Endpoint فيه تغييرات
    """
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("CHANNEL_ID غير صحيح أو البوت ما يقدر يشوف القناة.")
        return

    for name, url in ENDPOINTS.items():
        try:
            old = load_data(name)

            res = requests.get(url, timeout=25)
            res.raise_for_status()
            json_res = res.json()

            new = json_res.get("data", {})
            if not new:
                continue

            changes = deep_compare(old, new)
            if not changes:
                continue  # ما فيه أي تغيير

            # حفظ النسخة الجديدة
            save_data(name, new)

            # -------- بناء رسالة التحديث --------
            changes_count = len(changes)
            name_ar = ENDPOINT_NAMES_AR.get(name, name)

            title = f"🔔 تحديث جديد في فورتنايت – {name_ar}"
            desc = f"تم اكتشاف **{changes_count}** تغيير/تغيّرات في قسم `{name_ar}`."

            embed = discord.Embed(
                title=title,
                description=desc,
                color=discord.Color.blue()
            )

            # نعرض أول 10 تغييرات فقط عشان ما تصير الرسالة طويلة جداً
            for change_type, key, _, _ in changes[:10]:
                raw_key = key if key else "root"
                display_key = DISPLAY_KEY_NAMES_AR.get(raw_key, raw_key)
                if change_type == "added":
                    line = f"✅ تمت إضافة `{display_key}`"
                elif change_type == "removed":
                    line = f"❌ تم حذف `{display_key}`"
                else:
                    line = f"🟡 تم تعديل `{display_key}`"

                embed.add_field(
                    name=display_key,
                    value=line,
                    inline=False
                )

            image_url = get_image_for_endpoint(name, new)
            if image_url:
                embed.set_image(url=image_url)

            embed.set_footer(text="تحديث تلقائي • فورتنايت بالعربي")

            await channel.send(embed=embed)

        except Exception as e:
            print(f"خطأ أثناء فحص {name}: {e}")
            try:
                await channel.send(f"⚠️ صار خطأ أثناء فحص `{name}`:\n`{e}`")
            except Exception:
                pass


# ================== تشغيل البوت ==================

if not TOKEN or CHANNEL_ID == 0:
    print("❌ تأكد إنك ضايف متغيرات TOKEN و CHANNEL_ID في Railway.")
else:
    bot.run(TOKEN)
