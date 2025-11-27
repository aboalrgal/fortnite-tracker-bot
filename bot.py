import os
import json
import requests
import discord
from discord.ext import tasks, commands

# ================== الإعدادات الأساسية ==================

# توكن البوت وقناة الإرسال يتم تحديدهم من متغيرات البيئة في Railway
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# مجلد تخزين نسخ الـ JSON السابقة
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# روابط الـ API التي نتابعها
ENDPOINTS = {
    "cosmetics": "https://fortnite-api.com/v2/cosmetics/br",
    "news": "https://fortnite-api.com/v2/news",
    "shop": "https://fortnite-api.com/v2/shop/br",
    "playlists": "https://fortnite-api.com/v1/playlists",
    "map": "https://fortnite-api.com/v1/map",
    "aes": "https://fortnite-api.com/v2/aes"
}

# أسماء عربية لكل Endpoint (للاستخدام في العناوين)
ENDPOINT_NAMES_AR = {
    "cosmetics": "السكنات والعناصر",
    "news": "الأخبار",
    "shop": "الآيتم شوب",
    "playlists": "أطوار اللعب",
    "map": "الخريطة",
    "aes": "مفاتيح التشفير (AES)"
}


# ================== دوال مساعدة للتخزين والقراءة ==================

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
    مقارنة مبسطة بين كائنين من نوع dict على مستوى المفاتيح العليا فقط.

    - أي مفتاح جديد في new وليس في old → تمت إضافته (added)
    - أي مفتاح موجود في old وليس في new → تم حذفه (removed)
    - أي مفتاح موجود في الاثنين لكن قيمته مختلفة → تم تعديله (changed)

    هذا يكفي عشان نعرف إنه في تغيير صار (حتى لو تفصيل صغير).
    """
    changes = []

    # لو مو dict (مثلاً list)، نعاملها كقيمة واحدة
    if not isinstance(old, dict) or not isinstance(new, dict):
        if old != new:
            changes.append(("changed", "", old, new))
        return changes

    # المفاتيح المضافة أو المعدلة
    for key in new:
        if key not in old:
            changes.append(("added", key, None, new[key]))
        elif old[key] != new[key]:
            changes.append(("changed", key, old[key], new[key]))

    # المفاتيح المحذوفة
    for key in old:
        if key not in new:
            changes.append(("removed", key, old[key], None))

    return changes


def get_image_for_endpoint(name: str, new_data: dict):
    """
    محاولة استخراج صورة مناسبة للـ Embed حسب نوع الـ endpoint:
    - الأخبار: صورة الـ BR news
    - الخريطة: صورة الـ POIs أو الصورة الرئيسية
    - غيرها: غالباً بدون صورة (ممكن نطوّرها لاحقاً)
    """
    try:
        if name == "news":
            br = new_data.get("br") or {}
            return br.get("image")

        if name == "map":
            images = new_data.get("images") or {}
            return images.get("pois") or images.get("main") or images.get("map")

        # ممكن تطويرها لاحقاً لـ cosmetics / shop / playlists
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
        # رسالة بداية تأكيد إن البوت شغال
        start_msg = "✅ البوت شغّال الآن ويتابع تحديثات فورتنايت من الـ API بشكل تلقائي."
        await channel.send(start_msg)

    # بدء المهمة الدورية
    check_updates.start()


# ================== المهمة الدورية لفحص التحديثات ==================

@tasks.loop(minutes=5)
async def check_updates():
    """
    كل ٥ دقائق:
    - نقرأ النسخة القديمة من كل Endpoint
    - نطلب النسخة الجديدة من Fortnite API
    - نقارن بينهم
    - لو فيه تغييرات → نرسل Embed واحد لكل Endpoint فيه تغييرات
    """
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("CHANNEL_ID غير صحيح أو البوت ما يقدر يشوف القناة.")
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
                # ما فيه تغييرات لهذا الـ endpoint
                continue

            # حفظ النسخة الجديدة
            save_data(name, new)

            # ---------------- بناء رسالة التحديث ----------------

            changes_count = len(changes)
            name_ar = ENDPOINT_NAMES_AR.get(name, name)

            title = f"🔔 تحديث جديد في فورتنايت – {name_ar}"

            desc = f"تم اكتشاف **{changes_count}** تغيير/تغيّرات في قسم `{name_ar}`."

            embed = discord.Embed(
                title=title,
                description=desc,
                color=discord.Color.blue()
            )

            # نضيف ملخّص لأهم 10 تغييرات فقط عشان ما يصير Spam كبير داخل نفس الرسالة
            for change_type, key, _, _ in changes[:10]:
                key_text = key if key else "الجذر (Root)"

                if change_type == "added":
                    line = f"✅ تمت إضافة `{key_text}`"
                elif change_type == "removed":
                    line = f"❌ تم حذف `{key_text}`"
                else:
                    line = f"🟡 تم تعديل `{key_text}`"

                embed.add_field(
                    name=key_text,
                    value=line,
                    inline=False
                )

            # إضافة صورة لو متاحة (news / map)
            image_url = get_image_for_endpoint(name, new)
            if image_url:
                embed.set_image(url=image_url)

            # فوتر عربي
            embed.set_footer(
                text="تحديث تلقائي • فورتنايت بالعربي"
            )

            await channel.send(embed=embed)

        except Exception as e:
            print(f"خطأ أثناء فحص {name}:", e)
            try:
                await channel.send(
                    f"⚠️ صار خطأ أثناء فحص `{name}`:\n`{e}`"
                )
            except Exception:
                pass


# ================== تشغيل البوت ==================

if not TOKEN or CHANNEL_ID == 0:
    print("❌ تأكد إنك ضايف متغيرات TOKEN و CHANNEL_ID في Railway.")
else:
    bot.run(TOKEN)
