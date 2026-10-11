"""Validated per-admin guided message inputs (in-memory draft state)."""
import re

from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from . import catalog, security, texts
from .db import utcnow
from .handlers import services, prepare
from .i18n import t, error_text
from .menus import button, change_button, keyboard, set_setting, ACTIONS, action_name
from .admin_views import (GAME_FIELDS, FIELD_HINT, advance_game, choose_kb_row,
                          kb_draft_preview, cancel_button, permitted)


def _parse_support(raw: str) -> str:
    value = re.sub(r"^(?:https://)?(?:t\.me/|telegram\.me/)", "", raw.strip()).lstrip("@")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", value):
        raise ValueError("Use a valid public Telegram username")
    return value


def _field_input(message, field: str) -> str:
    if field == "image" and message.photo:
        return message.photo[-1].file_id
    if not message.text:
        raise ValueError("Send text, or a photo for the image field")
    raw = message.text.strip()
    if raw == "-" and field not in ("date_status", "priority", "title"):
        raw = ""
    return catalog.validate_game(field, raw)


async def process_admin_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True only if this update was consumed by an authorized admin wizard."""
    job = ctx.user_data.get("admin_job")
    if not job:
        return False
    m = update.message
    db, cfg = services(ctx)
    uid = update.effective_user.id
    if update.effective_chat.type != ChatType.PRIVATE or not await security.is_admin(db, cfg.owners, uid):
        ctx.user_data.pop("admin_job", None)
        return False
    permission = job.get("permission")
    if permission == "owner":
        valid = uid in cfg.owners
    else:
        valid = await permitted(ctx, uid, permission)
    if not valid:
        ctx.user_data.pop("admin_job", None)
        await m.reply_text(t("⛔ Permission revoked. Workflow cancelled.", "⛔ دسترسی شما لغو شده و عملیات متوقف شد."))
        return True
    kind = job["kind"]
    try:
        if kind in ("add_game", "edit_game"):
            field = GAME_FIELDS[job["index"]] if kind == "add_game" else job["field"]
            if field == "date_status":
                raise ValueError("Use the provided date-status buttons")
            value = _field_input(m, field)
            if kind == "add_game":
                await advance_game(update, ctx, value)
            else:
                if field == "release_date" and not value:
                    # A removed date must not remain 'confirmed'.
                    await db.execute("UPDATE games SET release_date=NULL,date_status='unknown',updated_at=? WHERE id=?",
                                     (utcnow(), job["id"]))
                else:
                    await db.execute(f"UPDATE games SET {field}=?,updated_at=? WHERE id=?", (value, utcnow(), job["id"]))
                await db.audit(uid, "game.edit", f"{job['id']}:{field}")
                ctx.user_data.pop("admin_job", None)
                await m.reply_text(t("✅ Game updated. /admin", "✅ بازی ویرایش شد. /admin"))
        elif kind == "edit_text":
            if not m.text:
                raise ValueError("Please send text with Telegram formatting")
            new_text = texts.validate_html(m.text_html)
            # Preview by sending to Telegram BEFORE offering to commit.
            try:
                await m.reply_html(t("📝 Preview:\n", "📝 پیش‌نمایش:\n") + new_text)
            except TelegramError as exc:
                raise ValueError("Telegram rejected the formatting; revise your message") from exc
            job["preview"] = new_text
            await m.reply_text(t("Save this template?", "این متن ذخیره شود؟"), reply_markup=keyboard([
                [button(t("✅ Save", "✅ ذخیره"), action="adm:textsave", style="success")],
                [button(t("✏️ Send revised text", "✏️ ارسال متن اصلاح‌شده"), action=f"adm:textedit:{job['key']}:{job['lang']}")],
                [cancel_button()],
            ]))
        elif kind == "kb_add":
            draft = job["draft"]
            if job["stage"] == "label":
                if not m.text or not 0 < len(m.text.strip()) <= 55 or "\n" in m.text:
                    raise ValueError("Use a one-line label of up to 55 characters")
                draft["label"] = m.text.strip()
                job["stage"] = "label_fa"
                await m.reply_text(t("🇮🇷 Now send the PERSIAN button label (1–55 characters).",
                                     "🇮🇷 حالا عنوان فارسی دکمه را بفرستید (۱ تا ۵۵ نویسه)."),
                                   reply_markup=keyboard([[cancel_button()]]))
            elif job["stage"] == "label_fa":
                if not m.text or not 0 < len(m.text.strip()) <= 55 or "\n" in m.text:
                    raise ValueError("Use a one-line label of up to 55 characters")
                draft["label_fa"] = m.text.strip()
                job["stage"] = "action"
                await m.reply_text(t("🎯 Select button action:", "🎯 عملکرد دکمه را انتخاب کنید:"),
                                   reply_markup=keyboard([
                    [button(action_name(key), action=f"adm:kba:{key}")] for key in ACTIONS
                ] + [[cancel_button()]]))
            elif job["stage"] == "target":
                if not m.text or not catalog.valid_url(m.text.strip()):
                    raise ValueError("Enter a valid HTTPS URL")
                draft["target"] = m.text.strip()
                await choose_kb_row(update, ctx)
            elif job["stage"] == "icon":
                if not m.text or not re.fullmatch(r"\d{10,25}", m.text.strip()):
                    raise ValueError("Send 10–25 numeric digits or press Skip icon")
                draft["icon_id"] = m.text.strip()
                job["stage"] = "preview"
                await kb_draft_preview(update, ctx)
            else:
                raise ValueError("Use the buttons for the next step")
        elif kind == "kb_edit":
            bid, field = job["id"], job["field"]
            if not m.text:
                raise ValueError("Please send a text value")
            value = m.text.strip()
            if field in ("icon_id", "label_fa") and value == "-":
                value = ""
            if field == "target":
                if not catalog.valid_url(value):
                    raise ValueError("Only HTTPS URLs are supported")
                await change_button(db, uid, bid, action="url", target=value)
            else:
                await change_button(db, uid, bid, **{field: value})
            ctx.user_data.pop("admin_job", None)
            await m.reply_text(t("✅ Button updated. /admin → Keyboard editor",
                                 "✅ دکمه ویرایش شد. /admin ← ویرایش دکمه‌ها"))
        elif kind == "support":
            if not m.text:
                raise ValueError("Send a username or -")
            value = None if m.text.strip() == "-" else _parse_support(m.text)
            await set_setting(db, "support", value)
            await db.audit(uid, "settings.support", "updated" if value else "deleted")
            ctx.user_data.pop("admin_job", None)
            await m.reply_text(t("✅ Support updated", "✅ پشتیبانی تنظیم شد"))
        elif kind == "admin_add":
            sender = getattr(getattr(m, "forward_origin", None), "sender_user", None)
            if sender:
                new_uid = sender.id
            elif m.text and re.fullmatch(r"\d{1,19}", m.text.strip()):
                new_uid = int(m.text.strip())
            else:
                raise ValueError("Send a numeric ID or a forwarded message with visible sender")
            if new_uid <= 0 or new_uid in cfg.owners:
                raise ValueError("Invalid ID or already an owner")
            await security.set_admin(db, uid, new_uid, True)
            ctx.user_data.pop("admin_job", None)
            await m.reply_text(t(f"✅ Added administrator {new_uid}. Configure permissions in /admin.",
                                 f"✅ کاربر {new_uid} ادمین شد؛ دسترسی‌هایش را در /admin تنظیم کنید."))
        elif kind == "emoji":
            if not m.text:
                raise ValueError("Send an emoji or 'emoji ID'")
            found = re.fullmatch(r"\s*(\S{1,8})\s+(\d{10,25})\s*", m.text)
            if found:
                symbol, cid = texts.normalize(found[1]), found[2]
            else:
                entities = [e for e in (m.entities or []) if e.type == "custom_emoji"]
                if len(entities) != 1:
                    raise ValueError("Send one custom emoji or emoji plus ID")
                item = entities[0]
                cid = item.custom_emoji_id
                symbol = texts.normalize(m.text.replace(m.parse_entity(item), "", 1)) or texts.normalize(m.parse_entity(item))
            if len(symbol) > 8 or not symbol or not cid.isdecimal():
                raise ValueError("Invalid emoji or custom emoji ID")
            await db.execute("INSERT INTO emojis(ch,cid) VALUES(?,?) ON CONFLICT(ch) DO UPDATE SET cid=excluded.cid", (symbol, cid))
            await db.audit(uid, "emoji.save", symbol)
            ctx.user_data.pop("admin_job", None)
            await m.reply_text(t("✅ Custom emoji mapping saved", "✅ ایموجی پرمیوم ذخیره شد"))
        else:
            ctx.user_data.pop("admin_job", None)
            return False
    except (ValueError, BadRequest) as exc:
        await m.reply_text("⚠️ " + error_text(str(exc))[:200] +
                           t("\nTry again, or /cancel.", "\nدوباره تلاش کنید یا /cancel را بزنید."))
    return True


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await prepare(update, ctx)
    ctx.user_data.pop("admin_job", None)
    ctx.user_data.pop("await_search", None)
    await update.message.reply_text(t("❎ Cancelled. /admin", "❎ لغو شد. /admin"))
