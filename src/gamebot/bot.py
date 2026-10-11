"""Application composition and entry point."""
import logging

from telegram import BotCommand, Update
from telegram.ext import (AIORateLimiter, Application, CallbackQueryHandler,
                          ChatMemberHandler, CommandHandler, MessageHandler, filters)

from .admin import admin_callback, admin_cmd, cancel
from .catalog import seed_if_empty
from .config import Config
from .db import Database
from .handlers import (catalog_page, chat_message, group_changed, help_cmd,
                       languages, play, route, search, start, support, top)
from .menus import seed_buttons
from .i18n import t
from .throttle import Throttle

log = logging.getLogger(__name__)


async def on_error(update: object, ctx):
    # Don't include the raw exception string: some network errors may include API paths.
    log.error("Update handler failure: %s", type(ctx.error).__name__)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(t("⚠️ Something went wrong. Please try again.",
                                                         "⚠️ خطایی رخ داد. دوباره تلاش کنید."))
        except Exception:
            pass


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "Home menu / صفحه اصلی"),
        BotCommand("games", "Browse catalog"),
        BotCommand("upcoming", "Confirmed future releases"),
        BotCommand("search", "Search games by title"),
        BotCommand("play", "Play Tic-Tac-Toe"),
        BotCommand("top", "Mini-game leaderboard"),
        BotCommand("lang", "Set language"),
        BotCommand("support", "Contact support"),
        BotCommand("help", "Help and commands"),
        BotCommand("admin", "Administration (authorized users)"),
        BotCommand("cancel", "Cancel current action"),
    ])
    await app.bot.set_my_commands([
        BotCommand("start", "صفحه اصلی"),
        BotCommand("games", "فهرست بازی‌ها"),
        BotCommand("upcoming", "بازی‌های در راه"),
        BotCommand("search", "جستجوی بازی"),
        BotCommand("play", "بازی دوز"),
        BotCommand("top", "جدول برترین‌ها"),
        BotCommand("lang", "انتخاب زبان"),
        BotCommand("support", "پشتیبانی"),
        BotCommand("help", "راهنما"),
        BotCommand("admin", "پنل مدیریت"),
        BotCommand("cancel", "لغو عملیات"),
    ], language_code="fa")
    identity = await app.bot.get_me()
    log.info("Bot online: @%s", identity.username)


async def games_command(update, ctx):
    ctx.user_data.pop("filter", None)
    await catalog_page(update, ctx)


async def upcoming_command(update, ctx):
    await catalog_page(update, ctx, "upcoming")


def build_application(config: Config, db: Database) -> Application:
    app = (Application.builder().token(config.token)
           .rate_limiter(AIORateLimiter(max_retries=2))
           .post_init(post_init).build())
    app.bot_data["db"] = db
    app.bot_data["config"] = config
    app.bot_data["throttle"] = Throttle()
    app.add_error_handler(on_error)
    for name, handler in (
        ("start", start), ("games", games_command), ("upcoming", upcoming_command),
        ("search", search), ("lang", languages), ("help", help_cmd),
        ("support", support), ("play", play), ("top", top),
        ("admin", admin_cmd), ("cancel", cancel),
    ):
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^adm:"))
    app.add_handler(CallbackQueryHandler(route, pattern=r"^(?:nav:|pg:|game:|lang:|flt:|ttt:|noop$)"))
    app.add_handler(ChatMemberHandler(group_changed, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO, chat_message))
    return app


def main() -> None:
    cfg = Config.from_env()
    logging.basicConfig(level=getattr(logging, cfg.log_level),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    db = Database(cfg.database_path)
    db.migrate()
    seed_if_empty(db)
    seed_buttons(db)
    log.info("SQLite database initialized: %s", cfg.database_path)
    app = build_application(cfg, db)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
