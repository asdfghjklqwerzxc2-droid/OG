"""Database-backed keyboard layouts and presentation helpers."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .catalog import valid_url
from .db import Database
from .i18n import language, t

ACTIONS = {
    "games": "📚 Catalog", "upcoming": "⏳ Upcoming", "search": "🔎 Search",
    "support": "💬 Support", "help": "ℹ️ Help", "language": "🌐 Languages",
    "minigame": "🎲 Tic-Tac-Toe", "url": "🔗 HTTPS link",
}
ACTIONS_FA = {
    "games": "📚 فهرست بازی‌ها", "upcoming": "⏳ به‌زودی", "search": "🔎 جستجو",
    "support": "💬 پشتیبانی", "help": "ℹ️ راهنما", "language": "🌐 انتخاب زبان",
    "minigame": "🎲 دوز", "url": "🔗 لینک HTTPS",
}


def action_name(key: str) -> str:
    return t(ACTIONS[key], ACTIONS_FA[key])


STYLES = ("none", "primary", "success", "danger")
COLORS = {
    "prev": "primary", "next": "primary", "lang_en": "primary", "lang_fa": "success",
    "support": "success", "panel": "primary", "add": "success", "delete": "danger",
}
COLOR_GROUP_NAMES = {
    "prev": ("⬅️ Previous", "⬅️ قبلی"),
    "next": ("➡️ Next", "➡️ بعدی"),
    "lang_en": ("🇬🇧 English language", "🇬🇧 زبان انگلیسی"),
    "lang_fa": ("🇮🇷 Persian language", "🇮🇷 زبان فارسی"),
    "support": ("💬 Support", "💬 پشتیبانی"),
    "panel": ("⚙️ Admin panel", "⚙️ پنل مدیریت"),
    "add": ("➕ Add", "➕ افزودن"),
    "delete": ("🗑 Delete", "🗑 حذف"),
}


def color_group_name(key: str) -> str:
    return t(*COLOR_GROUP_NAMES[key])


DEFAULT_BUTTONS = (
    (0, 0, "🎮 Games", "🎮 بازی‌ها", "games", "", "primary"),
    (0, 1, "⏳ Upcoming", "⏳ به‌زودی", "upcoming", "", "none"),
    (1, 0, "🔎 Search", "🔎 جستجو", "search", "", "none"),
    (1, 1, "🎲 Tic-Tac-Toe", "🎲 دوز", "minigame", "", "success"),
    (2, 0, "💬 Support", "💬 پشتیبانی", "support", "", "none"),
    (2, 1, "📚 Help", "📚 راهنما", "help", "", "none"),
    (3, 0, "🌐 Language", "🌐 زبان", "language", "", "primary"),
)


def seed_buttons(db: Database) -> None:
    def seed(con):
        if con.execute("SELECT 1 FROM keyboard_buttons WHERE menu='home'").fetchone():
            return
        for row_no, pos, label, label_fa, action, target, style in DEFAULT_BUTTONS:
            con.execute(
                "INSERT INTO keyboard_buttons(menu,row_no,pos,label,label_fa,action,target,style) VALUES('home',?,?,?,?,?,?,?)",
                (row_no, pos, label, label_fa, action, target, style),
            )
    db._transaction(seed)


async def setting(db: Database, key: str, default: str = "") -> str:
    data = await db.one("SELECT value FROM settings WHERE key=?", (key,))
    return data["value"] if data is not None else default


async def set_setting(db: Database, key: str, value: str | None):
    if value is None:
        await db.execute("DELETE FROM settings WHERE key=?", (key,))
    else:
        await db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


async def feature_enabled(db: Database) -> bool:
    return await setting(db, "minigame_enabled", "true") == "true"


async def button_style(db: Database, key: str) -> str:
    val = await setting(db, "color:" + key, COLORS.get(key, "none"))
    return val if val in STYLES else "none"


def button(label: str, *, action: str | None = None, url: str | None = None,
           style: str = "none", icon_id: str = "", custom_enabled: bool = False) -> InlineKeyboardButton:
    if (action is None) == (url is None):
        raise ValueError("Exactly one button action is required")
    if url is not None and not valid_url(url):
        raise ValueError("Invalid button URL")
    kw = {"callback_data": action} if action is not None else {"url": url}
    if style in STYLES and style != "none":
        kw["style"] = style
    if custom_enabled and icon_id and icon_id.isdecimal():
        kw["icon_custom_emoji_id"] = icon_id
    return InlineKeyboardButton(label, **kw)


def keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


async def home_keyboard(db: Database, custom_enabled: bool = False) -> InlineKeyboardMarkup:
    entries = await db.all("SELECT * FROM keyboard_buttons WHERE menu='home' ORDER BY row_no,pos")
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        row_id = entry["row_no"]
        while len(rows) <= row_id:
            rows.append([])
        a = entry["action"]
        try:
            rows[row_id].append(button(entry["label_fa"] or entry["label"] if language() == "fa" else entry["label"], action="nav:" + a if a != "url" else None,
                                       url=entry["target"] if a == "url" else None,
                                       style=entry["style"], icon_id=entry["icon_id"],
                                       custom_enabled=custom_enabled))
        except ValueError:
            continue
    return keyboard([r for r in rows if r] or [[button(t("🎮 Games", "🎮 بازی‌ها"), action="nav:games")]])


async def language_keyboard(db: Database) -> InlineKeyboardMarkup:
    return keyboard([[
        button("🇬🇧 English", action="lang:en", style=await button_style(db, "lang_en")),
        button("🇮🇷 فارسی", action="lang:fa", style=await button_style(db, "lang_fa")),
    ]])


async def page_keyboard(db: Database, category: str, page: int, total: int,
                        filters: str = "") -> InlineKeyboardMarkup:
    # Filter/search parameters are stored per-user in context.user_data, never in callback text.
    from .catalog import PAGE_SIZE
    from .texts import message_text
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows = []
    nav = []
    if page > 0:
        nav.append(button(await message_text(db, "prev", language()), action=f"pg:{category}:{page-1}", style=await button_style(db, "prev")))
    nav.append(button(f"📄 {page+1}/{pages}", action="noop"))
    if page < pages - 1:
        nav.append(button(await message_text(db, "next", language()), action=f"pg:{category}:{page+1}", style=await button_style(db, "next")))
    rows.append(nav)
    rows.append([
        button(t("⭐ Popular", "⭐ محبوب"), action="pg:popular:0"),
        button(t("⏳ Upcoming", "⏳ به‌زودی"), action="pg:upcoming:0"),
    ])
    rows.append([
        button(t("✅ Released", "✅ منتشرشده"), action="pg:recent:0"),
        button(t("❔ Unverified", "❔ تأییدنشده"), action="pg:unknown:0"),
    ])
    rows.append([button(t("🔎 Filter", "🔎 فیلتر"), action="nav:filter"), button(t("🏠 Home", "🏠 خانه"), action="nav:home")])
    return keyboard(rows)


def validate_button(label: str, action: str, target: str, row: int, style: str = "none", icon_id: str = "") -> None:
    if not label.strip() or len(label) > 55 or "\n" in label:
        raise ValueError("Button labels must be 1–55 characters on one line")
    if action not in ACTIONS:
        raise ValueError("Unsupported button action")
    if action == "url" and not valid_url(target):
        raise ValueError("Provide a valid HTTPS URL")
    if not 0 <= row <= 5:
        raise ValueError("Row must be between 1 and 6")
    if style not in STYLES:
        raise ValueError("Invalid color")
    if icon_id and (not icon_id.isdecimal() or not 10 <= len(icon_id) <= 25):
        raise ValueError("Custom emoji ID must contain 10–25 digits")


async def add_keyboard_button(db: Database, actor: int, label: str, action: str,
                              target: str, row: int, style: str = "none", icon_id: str = "", label_fa: str = ""):
    validate_button(label, action, target, row, style, icon_id)
    if label_fa:
        validate_button(label_fa, action, target, row, style, icon_id)
    def insert(con):
        pos = con.execute("SELECT COALESCE(MAX(pos),-1)+1 FROM keyboard_buttons WHERE menu='home' AND row_no=?", (row,)).fetchone()[0]
        if pos >= 4:
            raise ValueError("This row already has four buttons")
        if con.execute("SELECT COUNT(*) FROM keyboard_buttons WHERE menu='home'").fetchone()[0] >= 20:
            raise ValueError("Keyboard limit is 20 buttons")
        con.execute("INSERT INTO keyboard_buttons(menu,row_no,pos,label,label_fa,action,target,style,icon_id) VALUES('home',?,?,?,?,?,?,?,?)",
                    (row, pos, label.strip(), label_fa.strip(), action, target if action == "url" else "", style, icon_id))
    await db.transaction(insert)
    await db.audit(actor, "keyboard.add", label)


async def change_button(db: Database, actor: int, bid: int, **updates):
    allowed = {"label", "label_fa", "style", "icon_id", "action", "target"}
    if not updates or set(updates) - allowed:
        raise ValueError("Invalid button field")
    def change(con):
        current = con.execute("SELECT * FROM keyboard_buttons WHERE id=?", (bid,)).fetchone()
        if current is None:
            raise ValueError("Button no longer exists")
        values = {k: updates.get(k, current[k]) for k in ("label", "label_fa", "action", "target", "style", "icon_id")}
        validate_button(values["label"], values["action"], values["target"], current["row_no"],
                        values["style"], values["icon_id"])
        if values["label_fa"]:
            validate_button(values["label_fa"], values["action"], values["target"], current["row_no"],
                            values["style"], values["icon_id"])
        keys = tuple(updates)
        con.execute("UPDATE keyboard_buttons SET " + ",".join(f"{field}=?" for field in keys) + " WHERE id=?",
                    (*[updates[k] for k in keys], bid))
    await db.transaction(change)
    await db.audit(actor, "keyboard.edit", str(bid))


async def reorder_button(db: Database, actor: int, bid: int, movement: str):
    def move(con):
        row = con.execute("SELECT * FROM keyboard_buttons WHERE id=?", (bid,)).fetchone()
        if not row:
            raise ValueError("Button not found")
        entries = con.execute("SELECT id FROM keyboard_buttons WHERE menu='home' ORDER BY row_no,pos").fetchall()
        positions = [r[0] for r in entries]
        idx = positions.index(bid)
        if movement == "left" and row["pos"] > 0:
            other = con.execute("SELECT id,pos FROM keyboard_buttons WHERE menu='home' AND row_no=? AND pos=?", (row["row_no"], row["pos"]-1)).fetchone()
            if other:
                con.execute("UPDATE keyboard_buttons SET pos=4 WHERE id=?", (bid,))
                con.execute("UPDATE keyboard_buttons SET pos=? WHERE id=?", (row["pos"], other["id"]))
                con.execute("UPDATE keyboard_buttons SET pos=? WHERE id=?", (row["pos"]-1, bid))
        elif movement in ("up", "down"):
            dest = row["row_no"] + (-1 if movement == "up" else 1)
            if dest < 0 or dest > 5:
                raise ValueError("Cannot move outside the keyboard")
            count = con.execute("SELECT COUNT(*) FROM keyboard_buttons WHERE menu='home' AND row_no=?", (dest,)).fetchone()[0]
            if count >= 4:
                raise ValueError("Target row is full")
            con.execute("UPDATE keyboard_buttons SET row_no=?,pos=? WHERE id=?", (dest, count, bid))
            # Compact source row positions after removing button.
            source = con.execute("SELECT id FROM keyboard_buttons WHERE menu='home' AND row_no=? ORDER BY pos", (row["row_no"],)).fetchall()
            for i, r in enumerate(source):
                con.execute("UPDATE keyboard_buttons SET pos=? WHERE id=?", (i, r["id"]))
        else:
            raise ValueError("Cannot move button in this direction")
    await db.transaction(move)
    await db.audit(actor, "keyboard.move", f"{bid}:{movement}")


async def remove_button(db: Database, actor: int, bid: int) -> None:
    def remove(con):
        row = con.execute("SELECT row_no FROM keyboard_buttons WHERE id=?", (bid,)).fetchone()
        if not row:
            raise ValueError("Button not found")
        con.execute("DELETE FROM keyboard_buttons WHERE id=?", (bid,))
        left = con.execute("SELECT id FROM keyboard_buttons WHERE menu='home' AND row_no=? ORDER BY pos", (row[0],)).fetchall()
        for i, entry in enumerate(left):
            con.execute("UPDATE keyboard_buttons SET pos=? WHERE id=?", (i, entry[0]))
    await db.transaction(remove)
    await db.audit(actor, "keyboard.delete", str(bid))
