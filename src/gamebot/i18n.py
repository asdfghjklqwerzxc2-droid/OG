"""Per-update UI language for user messages and administrator workflows.

The language is activated at the beginning of each Telegram update, and is
isolated between concurrent asyncio tasks through ContextVar. No process-wide
mutable language setting is used.
"""
from contextvars import ContextVar

_current_language: ContextVar[str] = ContextVar("ui_language", default="en")


def activate(lang: str) -> None:
    _current_language.set(lang if lang in ("fa", "en") else "en")


def language() -> str:
    return _current_language.get()


def t(en: str, fa: str) -> str:
    return fa if language() == "fa" else en

# Domain-validation messages exposed to users by the guided admin workflows.
# Keep validation itself language-independent and localize only at the UI edge.
ERROR_FA = {
    "Malformed button identifier": "شناسه دکمه نامعتبر است",
    "Invalid game/field": "بازی یا فیلد نامعتبر است",
    "Choose a date status from the editor": "وضعیت تاریخ را از ویرایشگر انتخاب کنید",
    "Unexpected field": "فیلد غیرمنتظره است",
    "No valid game draft": "پیش‌نویس معتبری وجود ندارد",
    "A confirmed date is required": "تاریخ تأییدشده الزامی است",
    "Add the official HTTPS source before confirming": "قبل از تأیید، لینک HTTPS منبع رسمی را اضافه کنید",
    "A game with this title already exists": "بازی دیگری با همین نام وجود دارد",
    "Game not found": "بازی پیدا نشد",
    "Unknown message": "پیام ناشناخته است",
    "No template preview": "پیش‌نمایش پیام وجود ندارد",
    "Unexpected action": "عملکرد غیرمنتظره است",
    "No button draft": "پیش‌نویس دکمه وجود ندارد",
    "Choose row 1–6": "ردیف ۱ تا ۶ را انتخاب کنید",
    "Invalid style": "سبک دکمه نامعتبر است",
    "No icon prompt": "بخش آیکن فعال نیست",
    "No button ready to publish": "دکمه آماده انتشار نیست",
    "Invalid button": "دکمه نامعتبر است",
    "Unsupported action": "عملکرد پشتیبانی نمی‌شود",
    "Invalid color": "رنگ نامعتبر است",
    "Unsupported movement": "جابجایی پشتیبانی نمی‌شود",
    "Invalid color group": "گروه رنگ نامعتبر است",
    "Admin not found": "ادمین پیدا نشد",
    "Cannot modify an owner": "نمی‌توان دسترسی مالک را تغییر داد",
    "Owner cannot be removed": "مالک قابل حذف نیست",
    "Unrecognized permission": "دسترسی ناشناخته است",
    "Unsupported game field": "فیلد بازی پشتیبانی نمی‌شود",
    "Invalid length": "طول متن نامعتبر است",
    "Use YYYY-MM-DD, or - for unknown": "تاریخ را به شکل YYYY-MM-DD وارد کنید؛ برای نامعلوم - بفرستید",
    "Choose confirmed, unconfirmed or unknown": "یکی از حالت‌های تأییدشده، تأییدنشده یا نامعلوم را انتخاب کنید",
    "Priority must be 0..999": "اولویت باید بین ۰ تا ۹۹۹ باشد",
    "Only valid HTTPS links are allowed": "فقط لینک معتبر HTTPS پذیرفته می‌شود",
    "Send a photo, a Telegram file ID, or HTTPS URL": "عکس، شناسه فایل تلگرام یا لینک HTTPS بفرستید",
    "Exactly one button action is required": "فقط یک عملکرد برای دکمه لازم است",
    "Invalid button URL": "لینک دکمه نامعتبر است",
    "Button labels must be 1–55 characters on one line": "عنوان دکمه باید یک‌خطی و بین ۱ تا ۵۵ نویسه باشد",
    "Unsupported button action": "عملکرد دکمه پشتیبانی نمی‌شود",
    "Provide a valid HTTPS URL": "لینک معتبر HTTPS وارد کنید",
    "Row must be between 1 and 6": "ردیف باید بین ۱ تا ۶ باشد",
    "Custom emoji ID must contain 10–25 digits": "شناسه ایموجی باید بین ۱۰ تا ۲۵ رقم داشته باشد",
    "This row already has four buttons": "این ردیف چهار دکمه دارد",
    "Keyboard limit is 20 buttons": "حداکثر تعداد دکمه‌ها ۲۰ عدد است",
    "Invalid button field": "فیلد دکمه نامعتبر است",
    "Button no longer exists": "دکمه دیگر وجود ندارد",
    "Button not found": "دکمه پیدا نشد",
    "Cannot move outside the keyboard": "نمی‌توان دکمه را بیرون از صفحه‌کلید برد",
    "Target row is full": "ردیف مقصد پر است",
    "Cannot move button in this direction": "جابجایی در این جهت ممکن نیست",
    "Use a valid public Telegram username": "نام کاربری عمومی و معتبر تلگرام وارد کنید",
    "Send text, or a photo for the image field": "متن بفرستید؛ برای کاور می‌توانید عکس ارسال کنید",
    "Use the provided date-status buttons": "از دکمه‌های انتخاب وضعیت تاریخ استفاده کنید",
    "Please send text with Telegram formatting": "متن را با قالب‌بندی تلگرام ارسال کنید",
    "Telegram rejected the formatting; revise your message": "تلگرام قالب‌بندی پیام را نپذیرفت؛ متن را اصلاح کنید",
    "Use a one-line label of up to 55 characters": "عنوان یک‌خطی با حداکثر ۵۵ نویسه بفرستید",
    "Enter a valid HTTPS URL": "لینک HTTPS معتبر وارد کنید",
    "Send 10–25 numeric digits or press Skip icon": "شناسه ۱۰ تا ۲۵ رقمی بفرستید یا ردکردن آیکن را بزنید",
    "Use the buttons for the next step": "برای مرحله بعد از دکمه‌ها استفاده کنید",
    "Please send a text value": "متن ارسال کنید",
    "Only HTTPS URLs are supported": "فقط لینک HTTPS پشتیبانی می‌شود",
    "Send a username or -": "نام کاربری یا - را ارسال کنید",
    "Send a numeric ID or a forwarded message with visible sender": "شناسه عددی یا پیام فورواردی با فرستنده قابل‌مشاهده بفرستید",
    "Invalid ID or already an owner": "شناسه نامعتبر است یا شخص از قبل مالک است",
    "Send an emoji or 'emoji ID'": "ایموجی یا «ایموجی شناسه» ارسال کنید",
    "Send one custom emoji or emoji plus ID": "یک ایموجی سفارشی یا ایموجی همراه با شناسه بفرستید",
    "Invalid emoji or custom emoji ID": "ایموجی یا شناسه ایموجی نامعتبر است",
}


def error_text(message: str) -> str:
    if language() != "fa" or any("\u0600" <= ch <= "\u06ff" for ch in message):
        return message
    return ERROR_FA.get(message, "درخواست نامعتبر است؛ اطلاعات را بررسی کنید")
