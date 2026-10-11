"""Permission-checked admin callback router and transactional mutations."""
from telegram import Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import catalog, security, texts
from .db import utcnow
from .handlers import display, services, prepare
from .i18n import t, error_text
from .menus import (ACTIONS, COLORS, STYLES, add_keyboard_button, button,
                    change_button, feature_enabled, keyboard, remove_button,
                    reorder_button, set_setting, setting, action_name, color_group_name)
from .admin_views import (GAME_FIELDS, EDIT_FIELDS, FIELD_HINT, COLOR_NAMES,
                          back, cancel_button, permitted, admin_cmd, admin_home,
                          admin_games, game_settings, ask_field, advance_game,
                          text_options, keyboard_editor, kb_item, kb_draft_preview,
                          admins_panel, admin_member, admin_statistics, choose_kb_row, color_name)
from .admin_wizards import process_admin_input, cancel


async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not isinstance(q.data, str):
        return
    await prepare(update, ctx)
    await q.answer()
    db, cfg = services(ctx)
    uid = q.from_user.id
    if update.effective_chat.type != ChatType.PRIVATE:
        return await q.message.reply_text(t("⛔ Admin panel is private only", "⛔ پنل مدیریت فقط در گفت‌وگوی خصوصی در دسترس است"))
    if not await security.is_admin(db, cfg.owners, uid):
        return await q.message.reply_text(t("⛔ Access denied", "⛔ دسترسی ندارید"))
    parts = q.data.split(":")
    if not 2 <= len(parts) <= 5 or any(len(x) > 150 for x in parts):
        return
    act = parts[1]
    # Explicit per-operation authorization, independent of panel button visibility.
    owners_only = {"admins", "admin", "adminadd", "perm", "admindelask", "admindel", "audit", "adminsave"}
    by_permission = {
        "games": "catalog", "game": "catalog", "add": "catalog", "savegame": "catalog",
        "edit": "catalog", "date": "catalog", "hide": "catalog", "delask": "catalog", "del": "catalog",
        "texts": "content", "text": "content", "textedit": "content", "textsave": "content",
        "textresetask": "content", "textreset": "content", "keyboard": "content",
        "kb": "content", "kbadd": "content", "kba": "content", "kbr": "content",
        "kbs": "content", "kbi": "content", "kbpublish": "content", "kbf": "content",
        "kbactions": "content", "kbaction": "content", "kbcolors": "content",
        "kbcolor": "content", "kbmove": "content", "kbdelask": "content", "kbdelete": "content",
        "colors": "appearance", "color": "appearance", "setcolor": "appearance",
        "emojis": "appearance", "emojiadd": "appearance", "emojidelask": "appearance", "emojidel": "appearance",
        "stats": "statistics", "minigame": "minigame", "togglemini": "minigame",
        "support": "settings", "supportset": "settings",
    }
    if act in owners_only and uid not in cfg.owners:
        return await q.message.reply_text(t("⛔ Owner only", "⛔ فقط مالک ربات اجازه دارد"))
    if act in by_permission and not await permitted(ctx, uid, by_permission[act]):
        return await q.message.reply_text(t("⛔ This permission has been revoked", "⛔ این دسترسی لغو شده است"))
    try:
        await _dispatch(update, ctx, parts)
    except (ValueError, IndexError, KeyError, OverflowError) as exc:
        await q.message.reply_text("⚠️ " + error_text(str(exc))[:150])
    except TelegramError:
        await q.message.reply_text(t("⚠️ Telegram could not complete the request. Try /admin again.", "⚠️ تلگرام نتوانست درخواست را انجام دهد؛ دوباره /admin را بزنید."))


async def _dispatch(update, ctx, parts):
    q = update.callback_query
    db, cfg = services(ctx)
    uid = q.from_user.id
    act = parts[1]
    args = parts[2:]
    job = ctx.user_data.get("admin_job") or {}

    def numeric(i=0):
        if len(args) <= i or not args[i].isdigit() or len(args[i]) > 19:
            raise ValueError("Malformed button identifier")
        return int(args[i])

    if act == "home":
        return await admin_home(update, ctx)
    if act == "canceljob":
        ctx.user_data.pop("admin_job", None)
        return await admin_home(update, ctx)

    if act == "games":
        page = numeric() if args else 0
        return await admin_games(update, ctx, page)
    if act == "game":
        return await game_settings(update, ctx, numeric())
    if act == "add":
        ctx.user_data["admin_job"] = {"kind": "add_game", "permission": "catalog", "index": 0, "data": {}}
        return await ask_field(update, GAME_FIELDS[0])
    if act == "edit":
        gid = numeric()
        field = args[1]
        if field not in EDIT_FIELDS or not await catalog.get_game(db, gid, include_hidden=True):
            raise ValueError("Invalid game/field")
        ctx.user_data["admin_job"] = {"kind": "edit_game", "permission": "catalog", "field": field, "id": gid}
        return await ask_field(update, field)
    if act == "date":
        if not job or job["kind"] not in ("add_game", "edit_game") or args[0] not in ("confirmed", "unconfirmed", "unknown"):
            raise ValueError("Choose a date status from the editor")
        if job["kind"] == "add_game":
            if GAME_FIELDS[job["index"]] != "date_status":
                raise ValueError("Unexpected field")
            return await advance_game(update, ctx, args[0])
        if job["field"] != "date_status":
            raise ValueError("Unexpected field")
        await db.execute("UPDATE games SET date_status=?,updated_at=? WHERE id=?", (args[0], utcnow(), job["id"]))
        await db.audit(uid, "game.edit", f"{job['id']}:date_status")
        ctx.user_data.pop("admin_job", None)
        return await game_settings(update, ctx, job["id"])
    if act == "savegame":
        if job.get("kind") != "add_game" or len(job.get("data", {})) != len(GAME_FIELDS):
            raise ValueError("No valid game draft")
        game = job["data"]
        if game["date_status"] == "confirmed" and not game["release_date"]:
            raise ValueError("A confirmed date is required")
        if game["date_status"] == "confirmed" and not game["source_url"]:
            raise ValueError("Add the official HTTPS source before confirming")
        fields = GAME_FIELDS
        def insert(con):
            if con.execute("SELECT 1 FROM games WHERE title=? COLLATE NOCASE", (game["title"],)).fetchone():
                raise ValueError("A game with this title already exists")
            return con.execute("INSERT INTO games(" + ",".join(fields) + ") VALUES(" + ",".join("?" for _ in fields) + ")",
                               tuple(game[f] for f in fields)).lastrowid
        new_id = await db.transaction(insert)
        await db.audit(uid, "game.add", str(new_id))
        ctx.user_data.pop("admin_job", None)
        return await game_settings(update, ctx, new_id)
    if act == "hide":
        gid = numeric()
        await db.execute("UPDATE games SET visible=CASE WHEN visible=1 THEN 0 ELSE 1 END WHERE id=?", (gid,))
        await db.audit(uid, "game.visibility", str(gid))
        return await game_settings(update, ctx, gid)
    if act == "delask":
        gid = numeric()
        g = await catalog.get_game(db, gid, include_hidden=True)
        if not g:
            raise ValueError("Game not found")
        return await display(update, t(f"⚠️ Delete <b>{texts.esc(g['title'])}</b> permanently?",
                                  f"⚠️ بازی <b>{texts.esc(g['title'])}</b> برای همیشه حذف شود؟"), keyboard([
            [button(t("🗑 Yes, delete", "🗑 بله، حذف شود"), action=f"adm:del:{gid}", style="danger")], [back(f"adm:game:{gid}")],
        ]))
    if act == "del":
        gid = numeric()
        def erase(con):
            con.execute("DELETE FROM views WHERE game_id=?", (gid,))
            con.execute("DELETE FROM games WHERE id=?", (gid,))
        await db.transaction(erase)
        await db.audit(uid, "game.delete", str(gid))
        return await admin_games(update, ctx)

    if act == "texts":
        rows = [[button(f"{texts.template_name(key)} · {'🇬🇧 EN' if lang == 'en' else '🇮🇷 FA'}", action=f"adm:text:{key}:{lang}") for lang in ("en", "fa")]
                for key in texts.DEFAULTS]
        rows.append([back()])
        return await display(update, t("📝 <b>Message templates</b>\nSelect a message and language:",
                                   "📝 <b>متن‌های ربات</b>\nپیام و زبان را انتخاب کنید:"), keyboard(rows))
    if act in ("text", "textedit", "textresetask", "textreset"):
        if len(args) != 2 or args[0] not in texts.DEFAULTS or args[1] not in ("en", "fa"):
            raise ValueError("Unknown message")
        key, lang = args
        if act == "text":
            return await text_options(update, ctx, key, lang)
        if act == "textedit":
            ctx.user_data["admin_job"] = {"kind": "edit_text", "permission": "content", "key": key, "lang": lang}
            return await display(update, t("📝 Send new formatted text using Telegram's formatting toolbar.\n"
                                 "Bold, italic, underline, links and custom emoji will be preserved.",
                                 "📝 متن جدید را با ابزار قالب‌بندی تلگرام بفرستید.\n"
                                 "بولد، ایتالیک، زیرخط، لینک و ایموجی پرمیوم حفظ می‌شوند."),
                                 keyboard([[cancel_button()]]))
        if act == "textresetask":
            return await display(update, t("Restore the factory template?", "متن پیش‌فرض بازگردانده شود؟"), keyboard([
                [button(t("♻️ Confirm restore", "♻️ تأیید بازگردانی"), action=f"adm:textreset:{key}:{lang}", style="danger")],
                [back(f"adm:text:{key}:{lang}")],
            ]))
        await db.execute("DELETE FROM texts WHERE key=? AND lang=?", (key, lang))
        await db.audit(uid, "text.restore", f"{key}:{lang}")
        return await text_options(update, ctx, key, lang)
    if act == "textsave":
        if job.get("kind") != "edit_text" or not job.get("preview"):
            raise ValueError("No template preview")
        await db.execute("INSERT INTO texts(key,lang,value) VALUES(?,?,?) ON CONFLICT(key,lang) DO UPDATE SET value=excluded.value",
                         (job["key"], job["lang"], job["preview"]))
        await db.audit(uid, "text.save", f"{job['key']}:{job['lang']}")
        key, lang = job["key"], job["lang"]
        ctx.user_data.pop("admin_job", None)
        return await text_options(update, ctx, key, lang)

    if act == "keyboard":
        return await keyboard_editor(update, ctx)
    if act == "kb":
        return await kb_item(update, ctx, numeric())
    if act == "kbadd":
        ctx.user_data["admin_job"] = {"kind": "kb_add", "permission": "content", "stage": "label", "draft": {}}
        return await display(update, t("🎛 Send the ENGLISH button label (1–55 characters, one line).",
                       "🎛 عنوان انگلیسی دکمه را بفرستید (۱ تا ۵۵ نویسه، یک خط)."), keyboard([[cancel_button()]]))
    if act == "kba":
        if job.get("kind") != "kb_add" or job.get("stage") != "action" or args[0] not in ACTIONS:
            raise ValueError("Unexpected action")
        job["draft"]["action"] = args[0]
        if args[0] == "url":
            job["stage"] = "target"
            return await display(update, t("🔗 Send the HTTPS address.", "🔗 آدرس HTTPS را بفرستید."), keyboard([[cancel_button()]]))
        job["draft"]["target"] = ""
        return await choose_kb_row(update, ctx)
    if act == "kbr":
        if job.get("kind") != "kb_add" or job.get("stage") != "row":
            raise ValueError("No button draft")
        row = numeric()
        if not 0 <= row <= 5:
            raise ValueError("Choose row 1–6")
        job["draft"]["row"] = row
        job["stage"] = "style"
        return await display(update, t("🎨 Choose the button color:", "🎨 رنگ دکمه را انتخاب کنید:"), keyboard([
            [button(color_name(color), action=f"adm:kbs:{color}")]
            for color, name in COLOR_NAMES.items()
        ] + [[cancel_button()]]))
    if act == "kbs":
        if job.get("kind") != "kb_add" or job.get("stage") != "style" or args[0] not in STYLES:
            raise ValueError("Invalid style")
        job["draft"]["style"] = args[0]
        job["stage"] = "icon"
        return await display(update, t("💎 Optional: send a custom emoji ID (10–25 digits), or skip.\n"
                             "Custom icon display requires Telegram eligibility.",
                             "💎 در صورت تمایل شناسه ۱۰ تا ۲۵ رقمی ایموجی سفارشی را بفرستید یا رد کنید.\n"
                             "نمایش آیکن سفارشی به شرایط حساب تلگرام بستگی دارد."), keyboard([
                                 [button(t("Skip icon", "ردکردن آیکن"), action="adm:kbi:skip")], [cancel_button()],
                             ]))
    if act == "kbi":
        if job.get("kind") != "kb_add" or job.get("stage") != "icon" or args[0] != "skip":
            raise ValueError("No icon prompt")
        job["draft"]["icon_id"] = ""
        job["stage"] = "preview"
        return await kb_draft_preview(update, ctx)
    if act == "kbpublish":
        if job.get("kind") != "kb_add" or job.get("stage") != "preview":
            raise ValueError("No button ready to publish")
        d = job["draft"]
        await add_keyboard_button(db, uid, d["label"], d["action"], d["target"], d["row"], d["style"], d.get("icon_id", ""), d.get("label_fa", ""))
        ctx.user_data.pop("admin_job", None)
        return await keyboard_editor(update, ctx)
    if act == "kbf":
        bid = numeric()
        field = args[1] if len(args) > 1 else ""
        if field not in ("label", "label_fa", "icon_id") or not await db.one("SELECT 1 FROM keyboard_buttons WHERE id=?", (bid,)):
            raise ValueError("Invalid button")
        ctx.user_data["admin_job"] = {"kind": "kb_edit", "permission": "content", "id": bid, "field": field}
        return await display(update, t("✏️ Send new " + field + " (use - to remove the optional icon).",
                              "✏️ " + {"label": "عنوان انگلیسی", "label_fa": "عنوان فارسی",
                                        "icon_id": "شناسه آیکن"}[field] + " را بفرستید (برای حذف آیکن -)."), keyboard([[cancel_button()]]))
    if act == "kbactions":
        bid = numeric()
        return await display(update, t("🎯 Choose button action:", "🎯 عملکرد دکمه را انتخاب کنید:"), keyboard([
            [button(action_name(key), action=f"adm:kbaction:{bid}:{key}")]
            for key, name in ACTIONS.items()
        ] + [[back(f"adm:kb:{bid}")]]))
    if act == "kbaction":
        bid = numeric()
        a = args[1]
        if a not in ACTIONS:
            raise ValueError("Unsupported action")
        if a == "url":
            ctx.user_data["admin_job"] = {"kind": "kb_edit", "permission": "content", "id": bid, "field": "target"}
            return await display(update, t("🔗 Send an HTTPS URL.", "🔗 لینک HTTPS بفرستید."), keyboard([[cancel_button()]]))
        await change_button(db, uid, bid, action=a, target="")
        return await kb_item(update, ctx, bid)
    if act == "kbcolors":
        bid = numeric()
        return await display(update, t("🎨 Choose color:", "🎨 رنگ را انتخاب کنید:"), keyboard([
            [button(color_name(color), action=f"adm:kbcolor:{bid}:{color}")]
            for color, name in COLOR_NAMES.items()
        ] + [[back(f"adm:kb:{bid}")]]))
    if act == "kbcolor":
        bid = numeric()
        if args[1] not in STYLES:
            raise ValueError("Invalid color")
        await change_button(db, uid, bid, style=args[1])
        return await kb_item(update, ctx, bid)
    if act == "kbmove":
        bid = numeric()
        if args[1] not in ("left", "up", "down"):
            raise ValueError("Unsupported movement")
        await reorder_button(db, uid, bid, args[1])
        return await kb_item(update, ctx, bid)
    if act == "kbdelask":
        bid = numeric()
        return await display(update, t("⚠️ Delete this button?", "⚠️ این دکمه حذف شود؟"), keyboard([
            [button(t("🗑 Confirm", "🗑 تأیید حذف"), action=f"adm:kbdelete:{bid}", style="danger")],
            [back(f"adm:kb:{bid}")],
        ]))
    if act == "kbdelete":
        await remove_button(db, uid, numeric())
        return await keyboard_editor(update, ctx)

    if act == "colors":
        rows = [[button(color_group_name(k), action=f"adm:color:{k}")]
                for k in COLORS]
        rows.append([back()])
        return await display(update, t("🎨 <b>Button colors</b>\nApplies to the user navigation and panels.",
                             "🎨 <b>رنگ دکمه‌ها</b>\nروی منوهای کاربری و پنل مدیریت اعمال می‌شود."), keyboard(rows))
    if act == "color":
        if args[0] not in COLORS:
            raise ValueError("Invalid color group")
        return await display(update, t(f"🎨 Color of {color_group_name(args[0])}", f"🎨 رنگ بخش {color_group_name(args[0])}"), keyboard([
            [button(color_name(color), action=f"adm:setcolor:{args[0]}:{color}")]
            for color, name in COLOR_NAMES.items()
        ] + [[back("adm:colors")]]))
    if act == "setcolor":
        if len(args) != 2 or args[0] not in COLORS or args[1] not in STYLES:
            raise ValueError("Invalid color")
        await set_setting(db, "color:" + args[0], args[1])
        await db.audit(uid, "appearance.color", args[0] + ":" + args[1])
        return await display(update, t("✅ Updated", "✅ ذخیره شد"), keyboard([[back("adm:colors")]]))

    if act == "emojis":
        items = await db.all("SELECT id,ch,cid FROM emojis ORDER BY id LIMIT 30")
        rows = [[button("🗑 " + r["ch"], action=f"adm:emojidelask:{r['id']}", style="danger")]
                for r in items]
        rows += [[button(t("➕ Add or replace emoji", "➕ افزودن یا تعویض ایموجی"), action="adm:emojiadd", style="success")], [back()]]
        return await display(update, t(f"💎 <b>Custom emoji mapping</b> ({len(items)} shown)\n"
                             "Tap one to remove it. Custom emoji rendering is opt-in.",
                             f"💎 <b>ایموجی‌های سفارشی</b> ({len(items)} مورد)\n"
                             "برای حذف، روی یک مورد بزنید. نمایش ایموجی سفارشی اختیاری است."), keyboard(rows))
    if act == "emojiadd":
        ctx.user_data["admin_job"] = {"kind": "emoji", "permission": "appearance"}
        return await display(update, t("💎 Send one regular emoji followed by its numeric Telegram custom emoji ID.\n"
                             "Example: <code>🎮 5368324170671202286</code>\n"
                             "Or send a single custom emoji using your Telegram account.",
                             "💎 یک ایموجی عادی و شناسه عددی ایموجی سفارشی را ارسال کنید.\n"
                             "مثال: <code>🎮 5368324170671202286</code>\n"
                             "یا مستقیماً یک ایموجی پرمیوم ارسال کنید."), keyboard([[cancel_button()]]))
    if act == "emojidelask":
        bid = numeric()
        return await display(update, t("Remove this emoji mapping?", "این ایموجی حذف شود؟"), keyboard([
            [button(t("🗑 Confirm", "🗑 تأیید حذف"), action=f"adm:emojidel:{bid}", style="danger")], [back("adm:emojis")],
        ]))
    if act == "emojidel":
        bid = numeric()
        await db.execute("DELETE FROM emojis WHERE id=?", (bid,))
        await db.audit(uid, "emoji.remove", str(bid))
        return await _dispatch(update, ctx, ["adm", "emojis"])

    if act == "minigame":
        enabled = await feature_enabled(db)
        return await display(update, t(f"🎲 <b>Tic-Tac-Toe</b>\nStatus: {'✅ Enabled' if enabled else '⛔ Disabled'}\n"
                             "Scores are retained while disabled.",
                             f"🎲 <b>بازی دوز</b>\nوضعیت: {'✅ فعال' if enabled else '⛔ غیرفعال'}\n"
                             "امتیازها هنگام غیرفعال‌بودن حفظ می‌شوند."), keyboard([
            [button(t("⛔ Disable", "⛔ غیرفعال‌کردن") if enabled else t("✅ Enable", "✅ فعال‌کردن"), action="adm:togglemini",
                    style="danger" if enabled else "success")],
            [back()],
        ]))
    if act == "togglemini":
        enabled = await feature_enabled(db)
        await set_setting(db, "minigame_enabled", "false" if enabled else "true")
        await db.audit(uid, "minigame.toggle", "off" if enabled else "on")
        return await _dispatch(update, ctx, ["adm", "minigame"])
    if act == "stats":
        return await admin_statistics(update, ctx)
    if act == "support":
        value = await setting(db, "support")
        return await display(update, t(f"💬 <b>Support</b>\nCurrent: {texts.esc(value or 'Not set')}",
                              f"💬 <b>پشتیبانی</b>\nفعلی: {texts.esc(value or 'تنظیم‌نشده')}"), keyboard([
            [button(t("✏️ Change username", "✏️ تغییر نام کاربری"), action="adm:supportset")], [back()],
        ]))
    if act == "supportset":
        ctx.user_data["admin_job"] = {"kind": "support", "permission": "settings"}
        return await display(update, t("Send @username or https://t.me/username. Send - to remove.",
                                  "آیدی @username یا لینک https://t.me/username را بفرستید. برای حذف - بزنید."), keyboard([[cancel_button()]]))

    if act == "admins":
        return await admins_panel(update, ctx)
    if act == "admin":
        member = numeric()
        if not await db.one("SELECT 1 FROM admins WHERE id=?", (member,)):
            raise ValueError("Admin not found")
        return await admin_member(update, ctx, member)
    if act == "adminadd":
        ctx.user_data["admin_job"] = {"kind": "admin_add", "permission": "owner"}
        return await display(update, t("👮 Send numeric Telegram user ID, or forward their message (when sender isn't hidden).",
                                  "👮 شناسه عددی تلگرام کاربر یا پیام فورواردی او را بفرستید (اگر فرستنده مخفی نباشد)."),
                             keyboard([[cancel_button()]]))
    if act == "perm":
        member = numeric()
        if member in cfg.owners or len(args) < 2:
            raise ValueError("Cannot modify an owner")
        await security.toggle_permission(db, uid, member, args[1])
        return await admin_member(update, ctx, member)
    if act == "admindelask":
        member = numeric()
        if member in cfg.owners:
            raise ValueError("Owner cannot be removed")
        return await display(update, t(f"Remove administrator {member}?", f"ادمین {member} حذف شود؟"), keyboard([
            [button(t("🗑 Confirm", "🗑 تأیید حذف"), action=f"adm:admindel:{member}", style="danger")],
            [back(f"adm:admin:{member}")],
        ]))
    if act == "admindel":
        member = numeric()
        if member in cfg.owners:
            raise ValueError("Owner cannot be removed")
        await security.set_admin(db, uid, member, False)
        return await admins_panel(update, ctx)
    if act == "audit":
        data = await db.all("SELECT actor_id,action,target,outcome,at FROM audit_logs ORDER BY id DESC LIMIT 15")
        lines = [f"{texts.esc(r['at'])} · {r['actor_id']} · {texts.esc(r['action'])} ({texts.esc(r['target'])})"
                 for r in data]
        return await display(update, t("📜 <b>Recent administrative actions</b>\n\n",
                                   "📜 <b>آخرین فعالیت‌های مدیریت</b>\n\n") +
                             ("\n".join(lines) or t("No actions", "هنوز فعالیتی ثبت نشده است")),
                             keyboard([[back("adm:admins")]]))

