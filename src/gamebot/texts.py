"""Bilingual text templates and safe Telegram HTML serialization."""
import html
import re
from html.parser import HTMLParser

from .db import Database

DEFAULTS = {
 "welcome": {
  "en": "👋 Welcome to <b>Game Release</b>!\nBrowse games, check verified release dates, or play a match.\n\n/games · /upcoming · /search · /play · /support",
  "fa": "👋 به <b>Game Release</b> خوش آمدید!\nبازی‌ها، تاریخ انتشار تأییدشده و بازی کوتاه را دنبال کنید.\n\n/games · /upcoming · /search · /play · /support"},
 "notfound": {"en": "😕 No matching games found.", "fa": "😕 بازی مورد نظر پیدا نشد."},
 "empty": {"en": "📭 No games found.", "fa": "📭 بازی‌ای پیدا نشد."},
 "released": {"en": "✅ Released", "fa": "✅ منتشرشده"},
 "support": {"en": "💬 Contact support:", "fa": "💬 با پشتیبانی در تماس باشید:"},
 "support_btn": {"en": "💬 Support", "fa": "💬 پشتیبانی"},
 "prev": {"en": "⬅️ Previous", "fa": "⬅️ قبلی"},
 "next": {"en": "Next ➡️", "fa": "بعدی ➡️"},
 "disabled": {"en": "🎲 The mini-game is currently disabled.", "fa": "🎲 مینی‌گیم فعلاً غیرفعال است."},
 "support_none": {"en": "Support isn't configured yet.", "fa": "پشتیبانی هنوز تنظیم نشده است."},
 "help": {"en": "📚 <b>Commands</b>\n/start · /games · /upcoming · /search name · /play · /top · /support · /lang\nAdmin: /admin and /cancel",
          "fa": "📚 <b>راهنما</b>\n/start · /games · /upcoming · /search نام · /play · /top · /support · /lang\nمدیریت: /admin و /cancel"},
 "search": {"en": "🔎 Send a game title to search.", "fa": "🔎 نام بازی را ارسال کنید."},
}

TEMPLATE_LABELS = {
    "welcome": ("👋 Welcome", "👋 خوش‌آمدگویی"),
    "search": ("🔎 Search prompt", "🔎 درخواست جستجو"),
    "notfound": ("😕 No results", "😕 نتیجه‌ای یافت نشد"),
    "empty": ("📭 Empty catalog", "📭 فهرست خالی"),
    "released": ("✅ Released category", "✅ منتشرشده‌ها"),
    "support": ("💬 Support text", "💬 متن پشتیبانی"),
    "support_btn": ("💬 Support button", "💬 دکمه پشتیبانی"),
    "support_none": ("⛔ Support unavailable", "⛔ پشتیبانی ناموجود"),
    "prev": ("⬅️ Previous button", "⬅️ دکمه قبلی"),
    "next": ("➡️ Next button", "➡️ دکمه بعدی"),
    "disabled": ("🎲 Mini-game disabled", "🎲 پیام غیرفعال بودن دوز"),
    "help": ("📚 Help text", "📚 متن راهنما"),
}


def template_name(key: str) -> str:
    from .i18n import t
    return t(*TEMPLATE_LABELS[key])


ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
           "code", "pre", "a", "tg-spoiler", "tg-emoji", "blockquote"}
TAG_PATTERN = re.compile(r"(<[^>]*>)")


class TelegramHTMLValidator(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.visible_length = 0

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            raise ValueError(f"Unsupported HTML tag: {tag}")
        attributes = dict(attrs)
        if tag == "a":
            from .catalog import valid_url
            if not valid_url(attributes.get("href", "")) and not attributes.get("href", "").startswith("tg://user?id="):
                raise ValueError("Links must be safe HTTPS URLs")
        elif tag == "tg-emoji":
            if not re.fullmatch(r"\d{10,25}", attributes.get("emoji-id", "")):
                raise ValueError("Invalid custom emoji ID")
        elif attrs:
            is_code_language = (tag == "code" and set(attributes) == {"class"}
                and re.fullmatch(r"language-[a-zA-Z0-9_+#-]{1,40}", attributes["class"] or ""))
            is_expandable_quote = tag == "blockquote" and set(attributes) == {"expandable"}
            if not (is_code_language or is_expandable_quote):
                raise ValueError("Unsupported HTML attributes")
        if tag in ("a", "tg-emoji") and set(attributes) != ({"href"} if tag == "a" else {"emoji-id"}):
            raise ValueError("Unexpected HTML attribute")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError("Unbalanced HTML formatting")
        self.stack.pop()

    def handle_data(self, data):
        self.visible_length += len(data)

    def handle_entityref(self, name):
        self.visible_length += 1


def validate_html(content: str, limit: int = 4096) -> str:
    if len(content) > 16000:
        raise ValueError("Message source is too long")
    parser = TelegramHTMLValidator()
    parser.feed(content)
    parser.close()
    if parser.stack:
        raise ValueError("Unclosed HTML formatting")
    if not 0 < parser.visible_length <= limit:
        raise ValueError(f"Message must contain between 1 and {limit} visible characters")
    return content


def normalize(ch: str) -> str:
    return ch.replace("\ufe0f", "").strip()


def custom_emoji(html_text: str, mapping: dict[str, str], enabled: bool) -> str:
    """Replace in TEXT NODES only; do not break HTML attributes or existing emoji tags."""
    if not enabled or not mapping:
        return html_text
    normalized = {normalize(k): v for k, v in mapping.items() if normalize(k)}
    if not normalized:
        return html_text
    rx = re.compile("(" + "|".join(re.escape(k) for k in sorted(normalized, key=len, reverse=True)) + ")\ufe0f?")
    inside = 0
    out = []
    for chunk in TAG_PATTERN.split(html_text):
        if chunk.startswith("<") and chunk.endswith(">"):
            if chunk.startswith("<tg-emoji"):
                inside += 1
            elif chunk.startswith("</tg-emoji"):
                inside = max(0, inside - 1)
            out.append(chunk)
        elif inside:
            out.append(chunk)
        else:
            out.append(rx.sub(lambda m: f'<tg-emoji emoji-id="{normalized[normalize(m.group(1))]}">{m.group(0)}</tg-emoji>', chunk))
    return "".join(out)


async def message_text(db: Database, key: str, lang: str) -> str:
    if key not in DEFAULTS or lang not in ("en", "fa"):
        raise ValueError("Unknown text key or language")
    override = await db.one("SELECT value FROM texts WHERE key=? AND lang=?", (key, lang))
    return override["value"] if override is not None else DEFAULTS[key][lang]


async def emoji_map(db: Database) -> dict[str, str]:
    return {r["ch"]: r["cid"] for r in await db.all("SELECT ch,cid FROM emojis")}


async def render(db: Database, key: str, lang: str, custom_enabled: bool = False) -> str:
    return custom_emoji(await message_text(db, key, lang), await emoji_map(db), custom_enabled)


def esc(value: str | None) -> str:
    return html.escape(str(value or ""), quote=True)
