"""Release catalog: verified metadata, searching, paging, and validation."""
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from .db import Database

PAGE_SIZE = 5
PLATFORMS = ("PS5", "Xbox", "PC", "Switch", "Mobile")

# Sources were checked against the publisher's store or official announcement.
# Unknown release dates remain NULL; an unknown time is NEVER interpreted as midnight.
# (title, date, platforms, developer, publisher, genre, franchise, official URL, priority)
VERIFIED = [
    ("Grand Theft Auto VI", "2026-11-19", "PS5, Xbox Series X|S", "Rockstar Games", "Rockstar Games", "Action-adventure", "Grand Theft Auto", "https://store.rockstargames.com/game/buy-gta-vi", 200),
    ("Fable", "2027-02-23", "Xbox Series X|S, PC", "Playground Games", "Xbox Game Studios", "RPG", "Fable", "https://www.xbox.com/en-us/games/fable", 130),
    ("Marvel's Wolverine", "2026-09-15", "PS5", "Insomniac Games", "Sony Interactive Entertainment", "Action-adventure", "Marvel", "https://www.playstation.com/en-us/games/marvels-wolverine/", 105),
    ("Ghost of Yōtei", "2025-10-02", "PS5", "Sucker Punch", "Sony Interactive Entertainment", "Action-adventure", "Ghost", "https://www.playstation.com/en-us/games/ghost-of-yotei/", 95),
    ("Elden Ring", "2022-02-24", "PC, PS5, PS4, Xbox", "FromSoftware", "Bandai Namco", "Action RPG", "Elden Ring", "https://store.steampowered.com/app/1245620/ELDEN_RING/", 95),
    ("Cyberpunk 2077", "2020-12-09", "PC", "CD PROJEKT RED", "CD PROJEKT RED", "Action RPG", "Cyberpunk", "https://store.steampowered.com/app/1091500/Cyberpunk_2077/", 100),
    ("The Witcher 3: Wild Hunt", "2015-05-18", "PC", "CD PROJEKT RED", "CD PROJEKT RED", "Action RPG", "The Witcher", "https://store.steampowered.com/app/292030/The_Witcher_3_Wild_Hunt/", 100),
    ("Red Dead Redemption 2", "2019-12-05", "PC", "Rockstar Games", "Rockstar Games", "Action-adventure", "Red Dead Redemption", "https://store.steampowered.com/app/1174180/Red_Dead_Redemption_2/", 105),
    ("Hogwarts Legacy", "2023-02-10", "PC, PS5, Xbox Series X|S", "Avalanche Software", "Warner Bros. Games", "Action RPG", "Wizarding World", "https://store.steampowered.com/app/990080/Hogwarts_Legacy/", 80),
    ("God of War Ragnarök", "2022-11-09", "PS5, PS4", "Santa Monica Studio", "Sony Interactive Entertainment", "Action-adventure", "God of War", "https://www.playstation.com/en-us/games/god-of-war-ragnarok/", 100),
    ("Death Stranding 2: On the Beach", "2025-06-26", "PS5", "Kojima Productions", "Sony Interactive Entertainment", "Action-adventure", "Death Stranding", "https://www.playstation.com/en-us/games/death-stranding-2-on-the-beach/", 75),
    ("Stardew Valley", "2016-02-26", "PC", "ConcernedApe", "ConcernedApe", "Simulation", "Stardew Valley", "https://store.steampowered.com/app/413150/Stardew_Valley/", 85),
    ("Halo Infinite", "2021-11-15", "PC", "343 Industries", "Xbox Game Studios", "Shooter", "Halo", "https://store.steampowered.com/app/1240440/Halo_Infinite/", 85),
    ("Baldur's Gate 3", "2023-08-03", "PC", "Larian Studios", "Larian Studios", "RPG", "Baldur's Gate", "https://forums.larian.com/ubbthreads.php?Number=874803&ubb=showflat", 90),
    ("Marvel's Spider-Man 2", "2023-10-20", "PS5", "Insomniac Games", "Sony Interactive Entertainment", "Action-adventure", "Marvel", "https://www.playstation.com/en-us/games/marvels-spider-man-2/", 90),
]

# Recognizable existing titles with dates intentionally not asserted without
# a verified per-title edition/platform source. This is NOT a release schedule.
UNDATED = [
    ("Grand Theft Auto V", "Grand Theft Auto", 170),
    ("Ghost of Tsushima", "Ghost", 75),
    ("The Last of Us Part II", "The Last of Us", 85),
    ("Alan Wake 2", "Alan Wake", 75),
    ("Resident Evil 4", "Resident Evil", 90),
    ("Minecraft", "Minecraft", 110),
    ("Starfield", "Starfield", 70),
    ("DOOM Eternal", "DOOM", 75),
    ("Persona 5 Royal", "Persona", 70),
    ("The Legend of Zelda: Tears of the Kingdom", "Zelda", 90),
    ("Call of Duty: Black Ops 6", "Call of Duty", 80),
    ("Final Fantasy VII Rebirth", "Final Fantasy", 95),
    ("Hollow Knight: Silksong", "Hollow Knight", 75),
    ("Forza Horizon 5", "Forza Horizon", 60),
    ("Assassin's Creed Shadows", "Assassin's Creed", 70),
    ("Monster Hunter Wilds", "Monster Hunter", 70),
    ("Metaphor: ReFantazio", "Metaphor", 60),
]


def seed_if_empty(db: Database) -> None:
    """One-time catalog installation, preserving every legacy row without rewriting it.

    Legacy installs receive additional verified titles ONLY once. A deleted game
    stays deleted after a restart because catalog_seeded is a persistent marker.
    """
    def install(con):
        if con.execute("SELECT 1 FROM settings WHERE key='catalog_seeded'").fetchone():
            return
        has_legacy = bool(con.execute("SELECT 1 FROM games LIMIT 1").fetchone())
        for title, when, platforms, dev, publisher, genre, series, url, priority in VERIFIED:
            if con.execute("SELECT 1 FROM games WHERE title=? COLLATE NOCASE", (title,)).fetchone():
                continue
            cur = con.execute(
                """INSERT INTO games(title,release_date,platforms,company,publisher,
                    genre,series,date_status,source_url,priority) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (title, when, platforms, dev, publisher, genre, series, "confirmed", url, priority),
            )
            if title in ("Red Dead Redemption 2", "Cyberpunk 2077", "The Witcher 3: Wild Hunt", "Halo Infinite", "Baldur's Gate 3"):
                con.execute("UPDATE games SET description=? WHERE id=?", (
                    "Release date and platform refer specifically to the PC edition shown in the official source; other platforms may have different release dates.", cur.lastrowid))
        if not has_legacy:
            for title, series, priority in UNDATED:
                con.execute("INSERT INTO games(title,series,date_status,priority) VALUES(?,?,?,?)",
                            (title, series, "unknown", priority))
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('catalog_seeded','2026-10-initial')")
    db._transaction(install)


def release_day(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None


def release_label(game: dict, lang: str, today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    when = release_day(game.get("release_date"))
    status = game.get("date_status", "unknown")
    if status == "unknown" or not when:
        return "تاریخ نامشخص" if lang == "fa" else "Date unconfirmed"
    stamp = when.isoformat()
    if status != "confirmed":
        return (f"{stamp} (تایید نشده)" if lang == "fa" else f"{stamp} (unconfirmed)")
    # Only show hour/minute countdown when a time was explicitly confirmed.
    if (game.get("release_date") and
            re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", game["release_date"])):
        try:
            instant = datetime.strptime(game["release_date"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            left = int((instant - datetime.now(timezone.utc)).total_seconds())
            if left > 0:
                days_left, hrs = divmod(left, 86400)
                hours, minutes = divmod(hrs, 3600)
                if lang == "fa":
                    return f"{stamp} · {days_left} روز {hours:02} ساعت {minutes//60:02} دقیقه (UTC)"
                return f"{stamp} · {days_left}d {hours:02}h {minutes//60:02}m (UTC)"
        except ValueError:
            pass
    days = (when - today).days
    if days > 0:
        return f"{stamp} · {days} {'روز مانده' if lang == 'fa' else 'days left'}"
    if days == 0:
        return f"{stamp} · {'امروز' if lang == 'fa' else 'today'}"
    return f"{stamp} · {'منتشر شده' if lang == 'fa' else 'released'}"


def valid_url(value: str) -> bool:
    try:
        u = urlparse(value)
        return u.scheme == "https" and bool(u.hostname) and not u.username and not u.password \
            and len(value) <= 500 and not any(ord(c) < 32 for c in value)
    except ValueError:
        return False


def validate_game(field: str, raw: str) -> str:
    raw = raw.strip()
    sizes = {"title": 130, "original_title": 130, "localized_title": 130,
             "platforms": 180, "company": 140, "publisher": 140,
             "genre": 90, "series": 90, "description": 1500,
             "image": 500, "source_url": 500, "release_date": 20,
             "date_status": 12, "priority": 5}
    if field not in sizes:
        raise ValueError("Unsupported game field")
    if len(raw) > sizes[field] or (not raw and field == "title"):
        raise ValueError("Invalid length")
    if field == "release_date":
        if raw in ("-", ""):
            return ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) or not release_day(raw):
            raise ValueError("Use YYYY-MM-DD, or - for unknown")
    if field == "date_status" and raw not in ("confirmed", "unconfirmed", "unknown"):
        raise ValueError("Choose confirmed, unconfirmed or unknown")
    if field == "priority":
        try:
            val = int(raw)
        except ValueError as exc:
            raise ValueError("Priority must be 0..999") from exc
        if not 0 <= val <= 999:
            raise ValueError("Priority must be 0..999")
        return str(val)
    if field == "source_url" and raw not in ("", "-") and not valid_url(raw):
        raise ValueError("Only valid HTTPS links are allowed")
    if field == "image" and raw not in ("", "-") and not (valid_url(raw) or re.fullmatch(r"[\w-]{30,500}", raw)):
        raise ValueError("Send a photo, a Telegram file ID, or HTTPS URL")
    return "" if raw == "-" and field in ("source_url", "image") else raw


async def list_games(db: Database, *, category: str = "popular", term: str = "",
                     platform: str = "", year: str = "", page: int = 0) -> tuple[list[dict], int]:
    where = ["visible=1"]
    args: list[str | int] = []
    if category == "upcoming":
        where += ["date_status='confirmed'", "substr(release_date,1,10)>=?"]
        args.append(datetime.now(timezone.utc).date().isoformat())
    elif category == "recent":
        where += ["date_status='confirmed'", "substr(release_date,1,10)<?"]
        args.append(datetime.now(timezone.utc).date().isoformat())
    elif category == "unknown":
        where += ["date_status!='confirmed' OR release_date IS NULL"]
    if term:
        where.append("(title LIKE ? OR original_title LIKE ? OR localized_title LIKE ? OR series LIKE ?)")
        like = "%" + term.replace("%", "\\%").replace("_", "\\_") + "%"
        args.extend([like] * 4)
        where[-1] = where[-1].replace(" LIKE ?", " LIKE ? ESCAPE '\\'")
    if platform:
        where.append("platforms LIKE ?")
        args.append(f"%{platform}%")
    if year:
        if not re.fullmatch(r"20\d{2}", year):
            raise ValueError("Invalid year")
        where.append("substr(release_date,1,4)=?")
        args.append(year)
    clause = " AND ".join(where)
    order = ("release_date ASC, priority DESC" if category == "upcoming" else
             "release_date DESC" if category == "recent" else
             "priority DESC, title COLLATE NOCASE")
    total = await db.one(f"SELECT COUNT(*) n FROM games WHERE {clause}", tuple(args))
    page = max(0, page)
    rows = await db.all(
        f"SELECT * FROM games WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
        (*args, PAGE_SIZE, page * PAGE_SIZE),
    )
    return rows, total["n"]


async def get_game(db: Database, gid: int, *, include_hidden: bool = False) -> dict | None:
    return await db.one("SELECT * FROM games WHERE id=?" + ("" if include_hidden else " AND visible=1"), (gid,))
