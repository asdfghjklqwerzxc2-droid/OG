"""Admin UI screens, labels, and guided preview layouts."""
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from . import catalog, security, texts
from .handlers import display, services, prepare
from .i18n import t, language, error_text
from .menus import (ACTIONS, COLORS, STYLES, button, button_style,
                    home_keyboard, keyboard, setting, validate_button, action_name)

GAME_FIELDS = ("title", "release_date", "date_status", "platforms", "company", "publisher",
               "genre", "series", "description", "image", "source_url", "priority")
EDIT_FIELDS = (*GAME_FIELDS, "original_title", "localized_title")
FIELD_HINT = {
    "title": "🎮 Title / نام بازی",
    "release_date": "📅 Release day YYYY-MM-DD; - if unknown (do not guess a time)",
    "date_status": "📅 Confirmed only with a trustworthy source; otherwise unconfirmed/unknown",
    "platforms": "🕹 Platforms / پلتفرم‌ها (or -)",
    "company": "👾 Developer / سازنده (or -)", "publisher": "🏢 Publisher / ناشر (or -)",
    "genre": "🎭 Genre / ژانر (or -)", "series": "📚 Franchise / مجموعه (or -)",
    "description": "📝 Description / توضیحات (or -)",
    "image": "🏞 Send a cover photo, HTTPS URL, or - to skip",
    "source_url": "🔗 Official HTTPS source or - to skip",
    "priority": "⭐ Listing priority 0–999 (GTA 200, typical 50), or 0",
    "original_title": "🈺 Original title or -",
    "localized_title": "🇮🇷 Localized title or -",
}
COLOR_NAMES = {"none": "⚪ Default", "primary": "🔵 Blue", "success": "🟢 Green", "danger": "🔴 Red"}

FIELD_HINT_FA = {
    "title": "🎮 نام بازی را ارسال کنید",
    "release_date": "📅 تاریخ انتشار (YYYY-MM-DD) را بفرستید؛ اگر نامعلوم است - بزنید",
    "date_status": "📅 تاریخ فقط با منبع معتبر تأییدشده محسوب می‌شود؛ در غیر این صورت تأییدنشده یا نامعلوم",
    "platforms": "🕹 پلتفرم‌ها را بنویسید (یا -)",
    "company": "👾 سازنده بازی را بنویسید (یا -)",
    "publisher": "🏢 ناشر بازی را بنویسید (یا -)",
    "genre": "🎭 ژانر بازی را بنویسید (یا -)",
    "series": "📚 مجموعه/فرنچایز را بنویسید (یا -)",
    "description": "📝 توضیحات بازی را بنویسید (یا -)",
    "image": "🏞 عکس کاور را ارسال کنید، نشانی HTTPS بدهید یا - بزنید",
    "source_url": "🔗 نشانی HTTPS منبع رسمی را ارسال کنید (یا -)",
    "priority": "⭐ اولویت نمایش را بین ۰ تا ۹۹۹ بفرستید (GTA: 200، معمولی: 50)",
    "original_title": "🈺 عنوان اصلی بازی را بنویسید (یا -)",
    "localized_title": "🇮🇷 عنوان ترجمه‌شده بازی را بنویسید (یا -)",
}
FIELD_LABEL_FA = {
    "title": "نام", "release_date": "تاریخ", "date_status": "وضعیت تاریخ",
    "platforms": "پلتفرم‌ها", "company": "سازنده", "publisher": "ناشر",
    "genre": "ژانر", "series": "مجموعه", "description": "توضیحات",
    "image": "کاور", "source_url": "منبع رسمی", "priority": "اولویت",
    "original_title": "عنوان اصلی", "localized_title": "عنوان فارسی",
}
COLOR_NAMES_FA = {"none": "⚪ پیش‌فرض", "primary": "🔵 آبی", "success": "🟢 سبز", "danger": "🔴 قرمز"}


def hint(field):
    return t(FIELD_HINT[field], FIELD_HINT_FA[field])


def field_label(field):
    return t(field.replace("_", " "), FIELD_LABEL_FA[field])


def color_name(code):
    return t(COLOR_NAMES[code], COLOR_NAMES_FA[code])



def back(action="adm:home"):
    return button(t("⬅️ Back", "⬅️ بازگشت"), action=action)


def cancel_button():
    return button(t("❌ Cancel", "❌ لغو"), action="adm:canceljob", style="danger")


async def permitted(ctx, uid: int, perm: str) -> bool:
    db, cfg = services(ctx)
    return await security.allowed(db, cfg.owners, uid, perm)


async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, cfg = services(ctx)
    await prepare(update, ctx)
    if update.effective_chat.type != ChatType.PRIVATE:
        return await update.message.reply_text(t("🔐 Use /admin in the bot's private chat.", "🔐 دستور /admin را در گفت‌وگوی خصوصی ربات بفرستید."))
    if not await security.is_admin(db, cfg.owners, update.effective_user.id):
        return await update.message.reply_text(t("⛔ Access denied", "⛔ دسترسی ندارید"))
    await admin_home(update, ctx)


async def admin_home(update, ctx):
    db, cfg = services(ctx)
    uid = update.effective_user.id
    rows = []
    if await permitted(ctx, uid, "catalog"):
        rows.append([button(t("🎮 Manage games", "🎮 مدیریت بازی‌ها"), action="adm:games", style="success")])
    if await permitted(ctx, uid, "content"):
        rows.append([button(t("📝 Message editor", "📝 ویرایش پیام‌ها"), action="adm:texts"),
                     button(t("🎛 Keyboard editor", "🎛 ویرایش دکمه‌ها"), action="adm:keyboard")])
    if await permitted(ctx, uid, "appearance"):
        rows.append([button(t("🎨 Colors", "🎨 رنگ‌ها"), action="adm:colors"), button(t("💎 Premium emoji", "💎 ایموجی پرمیوم"), action="adm:emojis")])
    if await permitted(ctx, uid, "minigame"):
        rows.append([button(t("🎲 Mini-game toggle", "🎲 تنظیمات دوز"), action="adm:minigame")])
    if await permitted(ctx, uid, "statistics"):
        rows.append([button(t("📊 Statistics", "📊 آمار"), action="adm:stats")])
    if await permitted(ctx, uid, "settings"):
        rows.append([button(t("💬 Support", "💬 پشتیبانی"), action="adm:support")])
    if uid in cfg.owners:
        rows.append([button(t("👮 Administrators & permissions", "👮 ادمین‌ها و دسترسی‌ها"), action="adm:admins")])
        rows.append([button(t("📜 Audit history", "📜 تاریخچه مدیریت"), action="adm:audit")])
    rows.append([button(t("🏠 User home", "🏠 صفحه اصلی"), action="nav:home")])
    await display(update, t("⚙️ <b>Game Release · Admin panel</b>\nChoose a section:",
                             "⚙️ <b>پنل مدیریت Game Release</b>\nیک بخش را انتخاب کنید:"), keyboard(rows))


async def admin_games(update, ctx, page=0):
    db, _ = services(ctx)
    total = (await db.one("SELECT COUNT(*) n FROM games"))["n"]
    page = min(max(page, 0), max(0, (total-1)//8))
    rows = await db.all("SELECT id,title,visible FROM games ORDER BY priority DESC,title LIMIT 8 OFFSET ?", (page*8,))
    buttons = [[button(("✅ " if r["visible"] else "🙈 ") + r["title"][:45], action=f"adm:game:{r['id']}")]
               for r in rows]
    nav = []
    if page:
        nav.append(button("⬅️", action=f"adm:games:{page-1}"))
    nav.append(button(f"📄 {page+1}/{max(1,(total+7)//8)}", action="noop"))
    if page*8+8 < total:
        nav.append(button("➡️", action=f"adm:games:{page+1}"))
    buttons += [nav, [button(t("➕ Add a game", "➕ افزودن بازی"), action="adm:add", style="success")], [back()]]
    await display(update, t(f"🎮 <b>Games ({total})</b>\nSelect an entry to edit:",
                  f"🎮 <b>بازی‌ها ({total})</b>\nبرای ویرایش یک بازی را انتخاب کنید:"), keyboard(buttons))


async def game_settings(update, ctx, gid):
    db, _ = services(ctx)
    g = await catalog.get_game(db, gid, include_hidden=True)
    if not g:
        return await display(update, t("Game no longer exists.", "این بازی دیگر وجود ندارد."), keyboard([[back("adm:games")]]))
    rows = [[button("✏️ " + field_label(f), action=f"adm:edit:{gid}:{f}") for f in EDIT_FIELDS[i:i+2]]
            for i in range(0, len(EDIT_FIELDS), 2)]
    rows.append([button(t("🙈 Hide", "🙈 مخفی‌کردن") if g["visible"] else t("✅ Show", "✅ نمایش"), action=f"adm:hide:{gid}")])
    rows.append([button(t("🗑 Delete", "🗑 حذف"), action=f"adm:delask:{gid}", style="danger")])
    rows.append([back("adm:games")])
    await display(update, f"🎮 <b>{texts.esc(g['title'])}</b>\n📅 {texts.esc(catalog.release_label(g,language()))}\n" +
                  t("Edit any field below.", "برای ویرایش، یکی از بخش‌های زیر را انتخاب کنید." ), keyboard(rows))


async def ask_field(update, field):
    if field == "date_status":
        await display(update, hint(field), keyboard([
            [button(t("✅ Confirmed", "✅ تأییدشده"), action="adm:date:confirmed"),
             button(t("⚠️ Unconfirmed", "⚠️ تأییدنشده"), action="adm:date:unconfirmed")],
            [button(t("❔ Unknown", "❔ نامعلوم"), action="adm:date:unknown")], [cancel_button()],
        ]))
    else:
        await display(update, hint(field) + t("\n/cancel to abort", "\nبرای لغو /cancel را بزنید"), keyboard([[cancel_button()]]))


async def advance_game(update, ctx, value):
    job = ctx.user_data.get("admin_job", {})
    if job.get("kind") != "add_game":
        return
    field = GAME_FIELDS[job["index"]]
    job["data"][field] = value
    job["index"] += 1
    if job["index"] < len(GAME_FIELDS):
        return await ask_field(update, GAME_FIELDS[job["index"]])
    data = job["data"]
    preview = [t("🎮 <b>Game preview</b>", "🎮 <b>پیش‌نمایش بازی</b>")]
    for key in GAME_FIELDS:
        preview.append(f"<b>{field_label(key)}</b>: {texts.esc(str(data.get(key) or '—')[:140])}")
    await display(update, "\n".join(preview)[:3800], keyboard([
        [button(t("✅ Publish game", "✅ ثبت بازی"), action="adm:savegame", style="success")],
        [cancel_button()],
    ]))


async def text_options(update, ctx, key, lang):
    db, _ = services(ctx)
    content = await texts.message_text(db, key, lang)
    await display(update, f"📝 <b>{texts.template_name(key)} [{lang}]</b>\n\n" + t("Preview:", "پیش‌نمایش:") + f"\n{content}", keyboard([
        [button(t("✏️ Edit with Telegram formatting", "✏️ ویرایش با قالب‌بندی تلگرام"), action=f"adm:textedit:{key}:{lang}")],
        [button(t("♻️ Restore default", "♻️ بازگردانی پیش‌فرض"), action=f"adm:textresetask:{key}:{lang}")],
        [back("adm:texts")],
    ]))


async def keyboard_editor(update, ctx):
    db, cfg = services(ctx)
    preview = await home_keyboard(db, cfg.custom_emoji_enabled)
    # Show the published keyboard in its actual arrangement, followed by edit actions.
    await display(update, t("🎛 <b>Published home keyboard</b>\nTap a button to test it:",
                   "🎛 <b>دکمه‌های منتشرشده صفحه اصلی</b>\nبرای آزمایش روی دکمه بزنید:"), preview)
    items = await db.all("SELECT id,label,label_fa,row_no,pos FROM keyboard_buttons WHERE menu='home' ORDER BY row_no,pos")
    rows = [[button(f"{r['row_no']+1}.{r['pos']+1}  {(r['label_fa'] or r['label'])[:40] if language() == 'fa' else r['label'][:40]}", action=f"adm:kb:{r['id']}")]
            for r in items]
    rows.extend([[button(t("➕ Add button", "➕ افزودن دکمه"), action="adm:kbadd", style="success")], [back()]])
    await update.effective_message.reply_text(t("Select a button to modify, or add a new one:",
                                                  "برای ویرایش یک دکمه را انتخاب کنید یا دکمه تازه بسازید:"), reply_markup=keyboard(rows))


async def kb_item(update, ctx, bid):
    db, _ = services(ctx)
    r = await db.one("SELECT * FROM keyboard_buttons WHERE id=?", (bid,))
    if not r:
        return await display(update, t("Button not found.", "دکمه پیدا نشد."), keyboard([[back("adm:keyboard")]]))
    info = (f"🎛 <b>{texts.esc(r['label'])}</b> / {texts.esc(r['label_fa'] or '—')}\n"
            + t(f"Row: {r['row_no']+1}; position: {r['pos']+1}", f"ردیف: {r['row_no']+1}؛ جایگاه: {r['pos']+1}")
            + "\n" + t("Action:", "عملکرد:") + f" {action_name(r['action'])} {texts.esc(r['target'])}"
            + "\n" + t("Color:", "رنگ:") + f" {color_name(r['style'])}\n"
            + t("Icon ID:", "شناسه آیکن:") + f" {texts.esc(r['icon_id'] or '—')}")
    await display(update, info, keyboard([
        [button(t("✏️ English label", "✏️ عنوان انگلیسی"), action=f"adm:kbf:{bid}:label"),
         button(t("✏️ Persian label", "✏️ عنوان فارسی"), action=f"adm:kbf:{bid}:label_fa"),
         button(t("🎯 Action", "🎯 عملکرد"), action=f"adm:kbactions:{bid}")],
        [button(t("🎨 Color", "🎨 رنگ"), action=f"adm:kbcolors:{bid}"),
         button(t("💎 Icon", "💎 آیکن"), action=f"adm:kbf:{bid}:icon_id")],
        [button(t("⬅️ Left", "⬅️ چپ"), action=f"adm:kbmove:{bid}:left"),
         button(t("⬆️ Up", "⬆️ بالا"), action=f"adm:kbmove:{bid}:up"),
         button(t("⬇️ Down", "⬇️ پایین"), action=f"adm:kbmove:{bid}:down")],
        [button(t("🗑 Delete", "🗑 حذف"), action=f"adm:kbdelask:{bid}", style="danger")],
        [back("adm:keyboard")],
    ]))


async def kb_draft_preview(update, ctx):
    db, cfg = services(ctx)
    job = ctx.user_data.get("admin_job", {})
    draft = job.get("draft")
    if not draft:
        return
    try:
        validate_button(draft["label"], draft["action"], draft.get("target", ""), draft["row"],
                        draft["style"], draft.get("icon_id", ""))
        validate_button(draft["label_fa"], draft["action"], draft.get("target", ""), draft["row"],
                        draft["style"], draft.get("icon_id", ""))
    except ValueError as exc:
        return await display(update, f"❌ {texts.esc(error_text(str(exc)))}")
    published = await home_keyboard(db, cfg.custom_emoji_enabled)
    rows = [list(r) for r in published.inline_keyboard]
    while len(rows) <= draft["row"]:
        rows.append([])
    try:
        rows[draft["row"]].append(button(t(draft["label"], draft["label_fa"]), action="noop" if draft["action"] != "url" else None,
                                          url=draft.get("target", "") if draft["action"] == "url" else None,
                                          style=draft["style"], icon_id=draft.get("icon_id", ""),
                                          custom_enabled=cfg.custom_emoji_enabled))
        if len(rows[draft["row"]]) > 4:
            raise ValueError(t("The selected row is full", "ردیف انتخاب‌شده پر است"))
    except ValueError as exc:
        return await display(update, f"❌ {texts.esc(error_text(str(exc)))}")
    await display(update, t("🎛 <b>Preview</b> · New button shown at end of chosen row:",
               "🎛 <b>پیش‌نمایش</b> · دکمه جدید در انتهای ردیف انتخابی:"), keyboard([r for r in rows if r]))
    await update.effective_message.reply_text(t("Publish this layout?", "این چیدمان منتشر شود؟"), reply_markup=keyboard([
        [button(t("✅ Publish", "✅ انتشار"), action="adm:kbpublish", style="success")],
        [cancel_button()],
    ]))


async def admins_panel(update, ctx):
    db, cfg = services(ctx)
    members = await db.all("SELECT id FROM admins ORDER BY id LIMIT 30")
    rows = [[button(f"👮 {r['id']}", action=f"adm:admin:{r['id']}")] for r in members]
    rows += [[button(t("➕ Add administrator", "➕ افزودن ادمین"), action="adm:adminadd", style="success")],
             [button(t("📜 Audit history", "📜 تاریخچه مدیریت"), action="adm:audit")], [back()]]
    await display(update, t("👑 <b>Owners</b>\n", "👑 <b>مالک‌ها</b>\n") + ", ".join(str(x) for x in sorted(cfg.owners)) +
                  t("\n\n👮 Administrators (first 30)", "\n\n👮 ادمین‌ها (۳۰ نفر اول)"), keyboard(rows))


async def admin_member(update, ctx, uid):
    db, _ = services(ctx)
    perms = {r["permission"] for r in await db.all("SELECT permission FROM admin_permissions WHERE admin_id=?", (uid,))}
    rows = [[button(("✅ " if p in perms else "◻️ ") + t(label, security.PERMISSIONS_FA[p]), action=f"adm:perm:{uid}:{p}")]
            for p, label in security.PERMISSIONS.items()]
    rows += [[button(t("🗑 Remove admin", "🗑 حذف ادمین"), action=f"adm:admindelask:{uid}", style="danger")],
             [back("adm:admins")]]
    await display(update, f"👮 <b>{uid}</b>\n" + t("Tap a permission to grant/revoke:", "برای دادن یا گرفتن دسترسی روی آن بزنید:"), keyboard(rows))


async def admin_statistics(update, ctx):
    db, _ = services(ctx)
    queries = {
        t("👥 Users", "👥 کاربران"): "SELECT COUNT(*) n FROM users",
        t("🏘 Active groups", "🏘 گروه‌های فعال"): "SELECT COUNT(*) n FROM groups WHERE active=1",
        t("🎮 Games", "🎮 بازی‌ها"): "SELECT COUNT(*) n FROM games",
        t("⏳ Confirmed upcoming", "⏳ در راه تأییدشده"): "SELECT COUNT(*) n FROM games WHERE date_status='confirmed' AND substr(release_date,1,10)>=date('now')",
        t("👁 Unique game views", "👁 بازدیدهای یکتا"): "SELECT COUNT(*) n FROM views",
        t("🎲 Total finished mini-games", "🎲 بازی‌های دوز پایان‌یافته"): "SELECT COALESCE(SUM(wins+draws+losses),0) n FROM ttt_scores",
    }
    lines = [f"{label}: <b>{(await db.one(sql))['n']}</b>" for label, sql in queries.items()]
    await display(update, t("📊 <b>Statistics</b>\n\n", "📊 <b>آمار</b>\n\n") + "\n".join(lines), keyboard([
        [button(t("🔄 Refresh", "🔄 تازه‌سازی"), action="adm:stats")], [back()],
    ]))


async def choose_kb_row(update, ctx):
    ctx.user_data["admin_job"]["stage"] = "row"
    return await display(update, t("📐 Choose a row (top to bottom):", "📐 ردیف دکمه را از بالا به پایین انتخاب کنید:"), keyboard([
        [button(t(f"Row {i+1}", f"ردیف {i+1}"), action=f"adm:kbr:{i}") for i in range(j, j+3)]
        for j in (0, 3)
    ] + [[cancel_button()]]))

