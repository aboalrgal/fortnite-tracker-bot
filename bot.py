import os
import json
from io import BytesIO

import requests
import discord
from discord.ext import tasks, commands

# ================== الإعدادات الأساسية ==================

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

API_KEY = os.getenv("FORTNITE_API_KEY")  # لو عندك مفتاح من Fortnite-API
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

API_LANG = "ar"  # نخلي البيانات بالعربي قدر الإمكان

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
    "aes":       f"https://fortnite-api.com/v2/aes?language={API_LANG}",
}

ENDPOINT_NAMES_AR = {
    "cosmetics": "السكنات والعناصر",
    "news": "الأخبار",
    "shop": "الآيتم شوب",
    "playlists": "أطوار اللعب",
    "map": "الخريطة",
    "aes": "مفاتيح التشفير (AES)",
}


# ================== دوال مساعدة للملفات ==================

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


# ================== أخبار فورتنايت ==================

async def handle_news(channel, new_data, old_data):
    """
    يقارن أخبار BR/STW ويطلع الأخبار الجديدة بالاسم،
    ويرسل الصور الخاصة بها في رسالة ثانية.
    """
    if not isinstance(new_data, dict):
        return

    new_br = (new_data.get("br") or {})
    new_motds = new_br.get("motds") or []

    old_br = (old_data.get("br") or {})
    old_motds = old_br.get("motds") or []

    old_ids = {m.get("id") for m in old_motds if m.get("id")}
    # الأخبار الجديدة فقط
    new_news = [m for m in new_motds if m.get("id") and m.get("id") not in old_ids]

    # STW (إن وجدت)
    new_stw = (new_data.get("stw") or {})
    new_stw_messages = new_stw.get("messages") or new_stw.get("alerts") or []
    old_stw = (old_data.get("stw") or {})
    old_stw_messages = old_stw.get("messages") or old_stw.get("alerts") or []
    old_stw_ids = {m.get("id") for m in old_stw_messages if m.get("id")}
    new_stw_news = [m for m in new_stw_messages if m.get("id") and m.get("id") not in old_stw_ids]

    total_new = len(new_news) + len(new_stw_news)
    if total_new == 0:
        return

    lines = []
    name_ar = ENDPOINT_NAMES_AR["news"]
    lines.append(f"تم اكتشاف **{total_new}** تغيير/تغيّرات في قسم `{name_ar}`.\n")

    if new_news:
        lines.append("✅ تمت إضافة أخبار الباتل رويال:")
        for m in new_news:
            title = m.get("title") or "خبر جديد"
            lines.append(f"• {title}")
        lines.append("")

    if new_stw_news:
        lines.append("✅ تمت إضافة أخبار أنقِذ العالم:")
        for m in new_stw_news:
            title = m.get("title") or "خبر جديد"
            lines.append(f"• {title}")
        lines.append("")

    # نضيف وصف أول خبر مهم كنص تفصيلي
    highlight = new_news[0] if new_news else (new_stw_news[0] if new_stw_news else None)
    if highlight:
        title = highlight.get("title") or ""
        body = highlight.get("body") or highlight.get("message") or ""
        if title or body:
            lines.append("📰")
            if title:
                lines.append(f" **{title}**")
            if body:
                lines.append(f"\n{body}")

    description = "\n".join(lines)

    embed = discord.Embed(
        title="🔔 تحديث جديد في فورتنايت – الأخبار",
        description=description,
    )
    await channel.send(embed=embed)

    # رسالة ثانية: كل الصور للأخبار الجديدة (BR + STW)
    image_urls = []
    for m in new_news:
        img = m.get("image")
        if img:
            image_urls.append(img)
    for m in new_stw_news:
        img = m.get("image")
        if img:
            image_urls.append(img)

    if not image_urls:
        return

    # كل صورة في Embed خاص فيها
    for url in image_urls:
        img_embed = discord.Embed()
        img_embed.set_image(url=url)
        await channel.send(embed=img_embed)


# ================== الخريطة (MAP) ==================

async def handle_map(channel, new_data, old_data):
    """
    يوضح التغييرات في نقاط الاهتمام (POIs) وصور الخريطة، ويرسل صورة الخريطة.
    """
    if not isinstance(new_data, dict):
        return

    new_pois_list = new_data.get("pois") or []
    old_pois_list = old_data.get("pois") or []

    def pois_to_dict(pois):
        out = {}
        for p in pois:
            pid = p.get("id") or p.get("name")
            if pid:
                out[pid] = p
        return out

    new_pois = pois_to_dict(new_pois_list)
    old_pois = pois_to_dict(old_pois_list)

    added_ids = [pid for pid in new_pois if pid not in old_pois]
    removed_ids = [pid for pid in old_pois if pid not in new_pois]

    # نتحقق من تغيير الصور
    new_images = new_data.get("images") or {}
    old_images = old_data.get("images") or {}
    images_changed = (new_images != old_images)

    if not added_ids and not removed_ids and not images_changed:
        return

    name_ar = ENDPOINT_NAMES_AR["map"]
    change_count = len(added_ids) + len(removed_ids) + (1 if images_changed else 0)

    lines = []
    lines.append(f"تم اكتشاف **{change_count}** تغيير/تغيّرات في قسم `{name_ar}`.\n")

    if images_changed:
        lines.append("✅ تم تحديث صور الخريطة.\n")

    if added_ids:
        lines.append("✅ تمت إضافة نقاط اهتمام جديدة:")
        for pid in added_ids[:15]:
            name = new_pois[pid].get("name") or pid
            lines.append(f"• {name}")
        if len(added_ids) > 15:
            lines.append(f"• ... وعدد إضافي: {len(added_ids) - 15}")
        lines.append("")

    if removed_ids:
        lines.append("❌ تم حذف نقاط الاهتمام التالية:")
        for pid in removed_ids[:15]:
            name = old_pois[pid].get("name") or pid
            lines.append(f"• {name}")
        if len(removed_ids) > 15:
            lines.append(f"• ... وعدد إضافي: {len(removed_ids) - 15}")
        lines.append("")

    lines.append("🗺️ تم تحديث الخريطة، الصورة في الرسالة التالية توضح شكل التحديث.")

    description = "\n".join(lines)

    embed = discord.Embed(
        title="🔔 تحديث جديد في فورتنايت – الخريطة",
        description=description,
    )
    await channel.send(embed=embed)

    # صورة الخريطة فقط
    img_url = (
        new_images.get("pois")
        or new_images.get("map")
        or new_images.get("blank")
    )
    if img_url:
        img_embed = discord.Embed()
        img_embed.set_image(url=img_url)
        await channel.send(embed=img_embed)


# ================== أطوار اللعب (PLAYLISTS) ==================

def playlists_to_dict(playlists):
    out = {}
    for pl in playlists:
        pid = pl.get("id") or pl.get("playlistId") or pl.get("name")
        if pid:
            out[pid] = pl
    return out


async def handle_playlists(channel, new_data, old_data):
    """
    يذكر الأطوار الجديدة بالاسم، ويرسل صورها إن وجدت.
    """
    if not isinstance(new_data, list):
        return

    old_data = old_data or []
    new_dict = playlists_to_dict(new_data)
    old_dict = playlists_to_dict(old_data)

    added_ids = [pid for pid in new_dict if pid not in old_dict]
    if not added_ids:
        return

    name_ar = ENDPOINT_NAMES_AR["playlists"]

    lines = []
    lines.append(f"تم اكتشاف **{len(added_ids)}** تغيير/تغيّرات في قسم `{name_ar}`.\n")
    lines.append("✅ تمت إضافة أطوار جديدة:")

    added_playlists = []
    for pid in added_ids:
        pl = new_dict[pid]
        title = pl.get("name") or pl.get("localizedName") or pid
        desc = pl.get("description") or ""
        lines.append(f"• {title}")
        added_playlists.append(pl)

    description = "\n".join(lines)

    embed = discord.Embed(
        title="🔔 تحديث جديد في فورتنايت – أطوار اللعب",
        description=description,
    )
    await channel.send(embed=embed)

    # الصور (إن وجدت)
    for pl in added_playlists:
        images = pl.get("images") or {}
        img_url = images.get("showcase") or images.get("missionIcon")
        if img_url:
            img_embed = discord.Embed()
            img_embed.set_image(url=img_url)
            await channel.send(embed=img_embed)


# ================== AES ==================

async def handle_aes(channel, new_data, old_data):
    """
    يكتب قيم build/mainKey/dynamicKeys/updated الجديدة بشكل واضح.
    """
    if not isinstance(new_data, dict):
        return

    old_data = old_data or {}

    new_build = new_data.get("build")
    old_build = old_data.get("build")

    new_main = new_data.get("mainKey")
    old_main = old_data.get("mainKey")

    new_dynamic = new_data.get("dynamicKeys") or []
    old_dynamic = old_data.get("dynamicKeys") or []

    new_updated = new_data.get("updated")
    old_updated = old_data.get("updated")

    # لو ما تغير شيء لا ترسل
    if (
        new_build == old_build
        and new_main == old_main
        and new_dynamic == old_dynamic
        and new_updated == old_updated
    ):
        return

    lines = []
    name_ar = ENDPOINT_NAMES_AR["aes"]
    change_count = 0

    if new_build != old_build:
        change_count += 1
        lines.append(f"✅ رقم البناء الجديد: `{new_build}`")

    if new_main != old_main:
        change_count += 1
        if new_main:
            lines.append("✅ المفتاح الرئيسي (Main Key):")
            lines.append(f"`{new_main}`")

    if new_dynamic != old_dynamic:
        change_count += 1
        count_dyn = len(new_dynamic)
        lines.append(f"✅ تم تحديث المفاتيح الديناميكية (Dynamic Keys)، العدد الحالي: **{count_dyn}**")
        if count_dyn:
            lines.append("أهم المفاتيح (أول 5):")
            for dk in new_dynamic[:5]:
                pak = dk.get("pakFilename") or "Pak"
                key = dk.get("key") or "???"
                lines.append(f"• `{pak}` → `{key}`")

    if new_updated != old_updated:
        change_count += 1
        if new_updated:
            lines.append(f"✅ وقت آخر تحديث: `{new_updated}`")

    if change_count == 0:
        return

    header = f"تم اكتشاف **{change_count}** تغيير/تغيّرات في قسم `{name_ar}`.\n\n"
    description = header + "\n".join(lines)

    embed = discord.Embed(
        title="🔔 تحديث جديد في فورتنايت – مفاتيح التشفير (AES)",
        description=description,
    )
    await channel.send(embed=embed)


# ================== السكنات (COSMETICS – Outfits فقط) ==================

def cosmetics_to_dict(cosmetics):
    out = {}
    for c in cosmetics:
        cid = c.get("id")
        if cid:
            out[cid] = c
    return out


async def handle_cosmetics(channel, new_data, old_data):
    """
    يحسب السكنات (Outfits) الجديدة فقط، ويعرض أسماءها وصورها.
    """
    if not isinstance(new_data, list):
        return

    old_data = old_data or []

    new_dict = cosmetics_to_dict(new_data)
    old_dict = cosmetics_to_dict(old_data)

    added_ids = [cid for cid in new_dict if cid not in old_dict]
    if not added_ids:
        return

    # نركز على Outfits فقط
    new_outfits = []
    for cid in added_ids:
        c = new_dict[cid]
        c_type = (c.get("type") or {}).get("value") or c.get("type")
        if isinstance(c_type, str) and c_type.lower() in ("outfit", "character"):
            new_outfits.append(c)

    if not new_outfits:
        return

    count = len(new_outfits)
    lines = []
    lines.append(f"تم إضافة **{count}** سكن/سكنات جديدة في قسم السكنات.\n")
    lines.append("✅ تمت إضافة السكنات التالية:")

    for c in new_outfits:
        name = c.get("name") or "سكن جديد"
        rarity = (c.get("rarity") or {}).get("displayValue") or ""
        if rarity:
            lines.append(f"• {name} ({rarity})")
        else:
            lines.append(f"• {name}")

    description = "\n".join(lines)

    embed = discord.Embed(
        title="🔔 تحديث جديد في فورتنايت – السكنات الجديدة",
        description=description,
    )
    await channel.send(embed=embed)

    # الصور
    for c in new_outfits[:10]:  # نكتفي بأول 10 لو كثير
        images = c.get("images") or {}
        icon_url = images.get("icon") or images.get("featured") or images.get("smallIcon")
        if not icon_url:
            continue
        img_embed = discord.Embed(title=c.get("name") or "سكن جديد")
        img_embed.set_image(url=icon_url)
        await channel.send(embed=img_embed)


# ================== أحداث الديسكورد ==================

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول باسم: {bot.user}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("✅ تم تشغيل نسخة ULTRA – تتابع التغييرات في الأخبار، الخريطة، السكنات، الأطوار و AES.")
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
            old_data = load_data(name)

            # طلب جديد من الـ API
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            json_res = resp.json()
            new_data = json_res.get("data")

            # أول مرة → نخزن فقط
            if old_data is None:
                save_data(name, new_data)
                continue

            # حسب نوع الـ endpoint نشغل المعالجة الخاصة
            if name == "news":
                await handle_news(channel, new_data, old_data)
            elif name == "map":
                await handle_map(channel, new_data, old_data)
            elif name == "playlists":
                await handle_playlists(channel, new_data, old_data)
            elif name == "aes":
                await handle_aes(channel, new_data, old_data)
            elif name == "cosmetics":
                # /v2/cosmetics/br يرجع {"data": [...]}
                await handle_cosmetics(channel, new_data, old_data)
            else:
                # للأشياء اللي ما بعد طورناها (مثل الشوب) نخزن فقط الآن
                pass

            # في النهاية نحدث النسخة المخزنة
            save_data(name, new_data)

        except Exception as e:
            print(f"خطأ أثناء فحص {name}: {e}")


# ================== تشغيل البوت ==================

if not TOKEN or CHANNEL_ID == 0:
    print("❌ تأكد إنك ضايف متغيرات TOKEN و CHANNEL_ID في Railway.")
else:
    bot.run(TOKEN)
