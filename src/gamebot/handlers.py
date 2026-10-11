"""User-facing commands, bilingual navigation, searches and group lifecycle."""
from datetime import datetime, timezone
import logging

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from . import catalog, minigame, texts
from .db import Database, utcnow
from .i18n import activate, t
from .menus import button, feature_enabled, home_keyboard, keyboard, language_keyboard, page_keyboard, setting

log = logging.getLogger(__name__)


def services(ctx: ContextTypes.DEFAULT_TYPE):
    return ctx.application.bot_data["db"], ctx.application.bot_data["config"]


async def prepare(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> str:
    db, _ = services(ctx)
    chat, user = update.effective_chat, update.effective_user
    if not chat or not user:
        activate("en")
        return "en"
    if chat.type != ChatType.PRIVATE:
        row = await db.one("SELECT lang FROM groups WHERE id=?", (chat.id,))
        lang = row["lang"] if row and row["lang"] in ("en", "fa") else "en"
        activate(lang)
        return lang
    await db.execute(
        """INSERT INTO users(id,lang,joined_at,last_seen,display_name) VALUES(?,'en',?,?,?)
        ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,display_name=excluded.display_name""",
        (user.id, utcnow(), utcnow(), (getattr(user, "full_name", "") or "")[:100]),
    )
    row = await db.one("SELECT lang FROM users WHERE id=?", (user.id,))
    lang = row["lang"] if row and row["lang"] in ("en", "fa") else "en"
    activate(lang)
    return lang


async def display(update: Update, text: str, markup=None, photo: str = ""):
    """Edit callback text or reply with safe fallback for outdated callbacks/media."""
    q = update.callback_query
    if q and q.message:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            log.debug("Callback edit fallback: %s", type(exc).__name__)
    if update.effective_message:
        if photo and len(text) <= 950:
            try:
                await update.effective_message.reply_photo(photo, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return
            except TelegramError:
                log.info("Invalid cover; falling back to text")
        await update.effective_message.reply_html(text, reply_markup=markup)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    await display(update, await texts.render(db, "welcome", lang, config.custom_emoji_enabled),
                  await home_keyboard(db, config.custom_emoji_enabled))


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    await display(update, await texts.render(db, "help", lang, config.custom_emoji_enabled),
                  keyboard([[button(t("🏠 Home", "🏠 خانه"), action="nav:home")]]))


async def support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    username = await setting(db, "support")
    if not username:
        return await display(update, await texts.render(db, "support_none", lang, config.custom_emoji_enabled))
    msg = await texts.render(db, "support", lang, config.custom_emoji_enabled)
    label = await texts.message_text(db, "support_btn", lang)
    await display(update, msg, keyboard([[button(label, url=f"https://t.me/{username}")]]))


async def languages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, _ = services(ctx)
    await prepare(update, ctx)
    await display(update, t("🌐 Select your language:", "🌐 زبان خود را انتخاب کنید:"), await language_keyboard(db))


async def set_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE, lang: str):
    db, _ = services(ctx)
    chat, user = update.effective_chat, update.effective_user
    if lang not in ("en", "fa"):
        return
    if chat.type == ChatType.PRIVATE:
        await prepare(update, ctx)
        await db.execute("UPDATE users SET lang=? WHERE id=?", (lang, user.id))
    else:
        member = await ctx.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            await update.callback_query.answer("Group admins only / فقط ادمین‌ها", show_alert=True)
            return
        await db.execute("UPDATE groups SET lang=? WHERE id=?", (lang, chat.id))
    await update.callback_query.answer()
    activate(lang)
    await start(update, ctx)


def game_line(game: dict, lang: str) -> str:
    title = texts.esc(game["title"])
    if game["priority"] >= 110 or "grand theft auto" in game["title"].lower() or game["title"].lower().startswith("gta"):
        title = f"<b>{title}</b>"
    return f"🎮 {title}\n   📅 {texts.esc(catalog.release_label(game, lang))}"


async def catalog_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE, category: str = "popular", page: int = 0):
    db, _ = services(ctx)
    lang = await prepare(update, ctx)
    if category not in ("popular", "upcoming", "recent", "unknown"):
        return
    filters = ctx.user_data.get("filter", {}) if category == "popular" else {}
    page = min(100000, max(0, page))
    rows, total = await catalog.list_games(db, category=category, page=page, **filters)
    if total and page * catalog.PAGE_SIZE >= total:
        page = (total - 1) // catalog.PAGE_SIZE
        rows, _ = await catalog.list_games(db, category=category, page=page, **filters)
    heading = {"popular": t("⭐ Popular", "⭐ محبوب"), "upcoming": t("⏳ Upcoming", "⏳ به‌زودی"),
               "recent": await texts.message_text(db, "released", lang), "unknown": t("❔ Unverified", "❔ تأییدنشده")}[category]
    if filters.get("term"):
        heading += f" · 🔎 {texts.esc(filters['term'][:60])}"
    elif filters.get("year") or filters.get("platform"):
        heading += " · " + texts.esc(filters.get("year") or filters.get("platform"))
    info = "\n\n".join(game_line(game, lang) for game in rows) if rows else await texts.render(db, "empty", lang)
    nav = await page_keyboard(db, category, page, total)
    buttons = list(nav.inline_keyboard)
    if rows:
        detail_buttons = [button(f"🎮 {g['title'][:30]}", action=f"game:{g['id']}") for g in rows]
        buttons.insert(0, detail_buttons[:2])
        if len(detail_buttons) > 2:
            buttons.insert(1, detail_buttons[2:4])
        if len(detail_buttons) > 4:
            buttons.insert(2, detail_buttons[4:])
    await display(update, f"<b>{heading}</b>  ({total})\n\n{info}", keyboard(buttons))


async def game_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE, gid: int):
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    game = await catalog.get_game(db, gid)
    if game is None:
        return await display(update, t("Game not found.", "بازی پیدا نشد."))
    await db.execute("INSERT OR IGNORE INTO views(game_id,user_id) VALUES(?,?)", (gid, update.effective_user.id))
    fields = [f"🎮 <b>{texts.esc(game['title'])}</b>",
              f"📅 {texts.esc(catalog.release_label(game, lang))}"]
    for icon, col in (("🕹", "platforms"), ("👾", "company"), ("🏢", "publisher"),
                      ("🎭", "genre"), ("🧩", "series")):
        if game.get(col):
            fields.append(f"{icon} {texts.esc(game[col])}")
    if game["description"]:
        fields.append("\n" + texts.esc(game["description"][:800]))
    if game.get("source_url") and catalog.valid_url(game["source_url"]):
        fields.append(f'🔗 <a href="{texts.esc(game["source_url"])}">{t("Official source", "منبع رسمی")}</a>')
    rendered = texts.custom_emoji("\n".join(fields), await texts.emoji_map(db), config.custom_emoji_enabled)
    back = keyboard([[button(t("⬅️ Catalog", "⬅️ فهرست"), action="pg:popular:0")]])
    await display(update, rendered, back, photo=game["image"] if game.get("image") else "")


async def search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    term = " ".join(ctx.args).strip() if ctx.args else ""
    if term:
        return await search_for(update, ctx, term)
    if update.effective_chat.type == ChatType.PRIVATE:
        ctx.user_data["await_search"] = True
    await display(update, await texts.render(db, "search", lang, config.custom_emoji_enabled))


async def search_for(update: Update, ctx: ContextTypes.DEFAULT_TYPE, term: str, silent: bool = False):
    term = term.strip()
    if not term or len(term) > 120 or (silent and len(term) < 3):
        return
    if not silent and update.effective_chat.type == ChatType.PRIVATE:
        ctx.user_data["filter"] = {"term": term}
        return await catalog_page(update, ctx)
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    rows, _ = await catalog.list_games(db, term=term, page=0)
    if not rows:
        if not silent:
            await display(update, await texts.render(db, "notfound", lang, config.custom_emoji_enabled))
        return
    await display(update, f"🔎 <b>{texts.esc(term)}</b>\n\n" + "\n\n".join(game_line(g, lang) for g in rows),
                  keyboard([[button(g["title"][:40], action=f"game:{g['id']}")] for g in rows]))


async def filters_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await prepare(update, ctx)
    db, _ = services(ctx)
    years = await db.all("SELECT DISTINCT substr(release_date,1,4) y FROM games "
                         "WHERE visible=1 AND release_date IS NOT NULL AND length(release_date)>=10 "
                         "ORDER BY y DESC LIMIT 18")
    items = [button("📅 " + x["y"], action=f"flt:year:{x['y']}") for x in years
             if x["y"].isdigit() and len(x["y"]) == 4]
    rows = [items[i:i+3] for i in range(0, len(items), 3)]
    rows += [[button("🕹 PS5", action="flt:platform:PS5"), button("🖥 PC", action="flt:platform:PC")],
             [button("🎮 Xbox", action="flt:platform:Xbox"), button("🔀 Switch", action="flt:platform:Switch")],
             [button(t("📱 Mobile", "📱 موبایل"), action="flt:platform:Mobile"), button(t("🧹 Clear filters", "🧹 حذف فیلترها"), action="flt:clear:0")]]
    rows.append([button(t("⬅️ Catalog", "⬅️ فهرست"), action="pg:popular:0")])
    await display(update, t("🔎 Choose a year or platform. Filters apply to the Popular catalog.",
                    "🔎 سال یا پلتفرم را انتخاب کنید. فیلترها روی فهرست محبوب اعمال می‌شوند."), keyboard(rows))


async def play(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, config = services(ctx)
    lang = await prepare(update, ctx)
    if update.effective_chat.type != ChatType.PRIVATE:
        await display(update, t("🎲 Open a private chat with the bot to play.", "🎲 برای بازی وارد گفت‌وگوی خصوصی ربات شوید."))
        return
    if not await feature_enabled(db):
        return await display(update, await texts.render(db, "disabled", lang, config.custom_emoji_enabled))
    session = await minigame.start_game(db, update.effective_user.id)
    await display(update, minigame.game_text(session, lang), minigame.game_keyboard(session))


async def top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db, _ = services(ctx)
    lang = await prepare(update, ctx)
    results = await minigame.leaderboard(db)
    lines = [f"{i}. {texts.esc("بازیکن" if lang == "fa" and r['name'] == "Player" else r['name'])} — 🏆 {r['wins']} · ⭐ {r['points']}" for i, r in enumerate(results, 1)]
    await display(update, t("🏆 <b>Tic-Tac-Toe leaderboard</b>", "🏆 <b>جدول برترین‌های دوز</b>") + "\n\n" + ("\n".join(lines) or t("No games recorded yet.", "هنوز نتیجه‌ای ثبت نشده است.")),
                  keyboard([[button(t("🎲 Play", "🎲 بازی"), action="ttt:new")]]))


async def route(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not isinstance(q.data, str):
        return
    await prepare(update, ctx)
    parts = q.data.split(":")
    if len(q.data.encode()) > 64:
        return await q.answer(t("Invalid button", "دکمه نامعتبر است"), show_alert=True)
    if parts[0] == "noop":
        return await q.answer()
    # All queries are acknowledged promptly, except language's admin-group check.
    if parts[0] != "lang":
        await q.answer()
    if parts[0] == "lang" and len(parts) == 2:
        if parts[1] not in ("en", "fa"):
            return await q.answer(t("Invalid language", "زبان نامعتبر است"), show_alert=True)
        await set_language(update, ctx, parts[1])
        return
    if parts[0] == "nav" and len(parts) == 2:
        action = parts[1]
        funcs = {"home": start, "games": catalog_page, "upcoming": catalog_page,
                 "search": search, "support": support, "help": help_cmd,
                 "language": languages, "minigame": play, "filter": filters_menu}
        if action not in funcs:
            return
        if action == "games":
            return await catalog_page(update, ctx)
        if action == "upcoming":
            return await catalog_page(update, ctx, "upcoming")
        return await funcs[action](update, ctx)
    if parts[0] == "pg" and len(parts) == 3:
        if parts[1] not in ("popular", "upcoming", "recent", "unknown") or not parts[2].isdigit():
            return
        return await catalog_page(update, ctx, parts[1], int(parts[2]))
    if parts[0] == "game" and len(parts) == 2 and parts[1].isdigit():
        return await game_detail(update, ctx, int(parts[1]))
    if parts[0] == "flt" and len(parts) == 3:
        k, val = parts[1:]
        if k == "clear":
            ctx.user_data["filter"] = {}
        elif k == "year" and len(val) == 4 and val.isdigit() and 2000 <= int(val) <= 2099:
            ctx.user_data["filter"] = {"year": val}
        elif k == "platform" and val in catalog.PLATFORMS:
            ctx.user_data["filter"] = {"platform": val}
        else:
            return
        return await catalog_page(update, ctx)
    if parts[0] == "ttt":
        limiter = ctx.application.bot_data.get("throttle")
        if limiter is not None and not limiter.allow(update.effective_user.id):
            return
        db, config = services(ctx)
        lang = await prepare(update, ctx)
        if update.effective_chat.type != ChatType.PRIVATE:
            return await display(update, t("Play in a private chat with the bot.", "برای بازی وارد گفت‌وگوی خصوصی ربات شوید."))
        if not await feature_enabled(db):
            return await display(update, await texts.render(db, "disabled", lang, config.custom_emoji_enabled))
        if len(parts) == 2 and parts[1] == "new":
            return await play(update, ctx)
        if len(parts) == 2 and parts[1] == "top":
            return await top(update, ctx)
        if len(parts) == 3 and parts[2].isdigit():
            try:
                session = await minigame.play_move(db, update.effective_user.id, parts[1], int(parts[2]))
            except ValueError as exc:
                return await q.message.reply_text(t("⚠️ This move is no longer valid. Start a new game.",
                                                    "⚠️ این حرکت دیگر معتبر نیست. بازی جدیدی شروع کنید."))
            return await display(update, minigame.game_text(session, lang), minigame.game_keyboard(session))


async def chat_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m:
        return
    await prepare(update, ctx)
    from .admin import process_admin_input
    if await process_admin_input(update, ctx):
        return
    if not m.text:
        return
    limiter = ctx.application.bot_data.get("throttle")
    if limiter is not None and not limiter.allow(update.effective_user.id):
        return
    is_private = update.effective_chat.type == ChatType.PRIVATE
    if is_private and ctx.user_data.pop("await_search", False):
        return await search_for(update, ctx, m.text)
    if is_private:
        await search_for(update, ctx, m.text)
    else:
        await search_for(update, ctx, m.text, silent=True)


async def group_changed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    event = update.my_chat_member
    if not event or event.chat.type == ChatType.PRIVATE:
        return
    db, config = services(ctx)
    status = event.new_chat_member.status
    if status in ("member", "administrator"):
        await db.execute(
            """INSERT INTO groups(id,title,added_by,added_at,active) VALUES(?,?,?,?,1)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,active=1""",
            (event.chat.id, event.chat.title, event.from_user.id, utcnow()),
        )
        row = await db.one("SELECT lang FROM groups WHERE id=?", (event.chat.id,))
        lang = row["lang"] if row else "en"
        activate(lang)
        try:
            await ctx.bot.send_message(event.chat.id, await texts.render(db, "welcome", lang, config.custom_emoji_enabled),
                                       parse_mode=ParseMode.HTML, reply_markup=await language_keyboard(db))
        except TelegramError:
            log.warning("Cannot send group welcome to %s", event.chat.id)
    elif status in ("left", "kicked"):
        await db.execute("UPDATE groups SET active=0 WHERE id=?", (event.chat.id,))
