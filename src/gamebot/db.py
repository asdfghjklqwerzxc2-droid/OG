"""SQLite storage with versioned migrations and nonblocking thread offloading.

Transactions always use their *own* connection; BEGIN IMMEDIATE makes multi-step
mutations atomic, even with overlapping asyncio updates in one process.
"""
import asyncio
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, TypeVar

T = TypeVar("T")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def _query(self, sql: str, args: tuple, mode: str):
        with closing(self.connect()) as con:
            rows = con.execute(sql, args)
            if mode == "one":
                row = rows.fetchone()
                return dict(row) if row else None
            return [dict(row) for row in rows.fetchall()]

    async def one(self, sql: str, args: tuple = ()) -> dict | None:
        return await asyncio.to_thread(self._query, sql, args, "one")

    async def all(self, sql: str, args: tuple = ()) -> list[dict]:
        return await asyncio.to_thread(self._query, sql, args, "all")

    def _transaction(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        with closing(self.connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                result = fn(con)
                con.commit()
                return result
            except Exception:
                con.rollback()
                raise

    async def transaction(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.to_thread(self._transaction, fn)

    async def execute(self, sql: str, args: tuple = ()) -> int:
        return await self.transaction(lambda con: con.execute(sql, args).lastrowid)

    async def audit(self, actor: int, action: str, target: str = "", outcome: str = "ok") -> None:
        await self.execute(
            "INSERT INTO audit_logs(actor_id,action,target,outcome) VALUES(?,?,?,?)",
            (actor, action[:64], target[:120], outcome[:50]),
        )

    def migrate(self) -> None:
        """Idempotent and safe for old gaoo66mmp.db deployments."""
        root = Path(__file__).parent / "migrations"
        with closing(self.connect()) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)")
            applied = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
            if 1 not in applied:
                # SQLite executescript performs an implicit commit. Do not wrap it
                # in a separate transaction; DDL is idempotent on retry.
                con.executescript((root / "001_core.sql").read_text(encoding="utf-8"))
            self._upgrade_legacy(con, grant_old_admins=1 not in applied)
            if 1 not in applied:
                con.execute("INSERT INTO schema_migrations VALUES(1,?)", (utcnow(),))
                con.commit()
            if 2 not in applied:
                con.executescript((root / "002_indexes.sql").read_text(encoding="utf-8"))
                con.execute("INSERT INTO schema_migrations VALUES(2,?)", (utcnow(),))
                con.commit()
            if 3 not in applied:
                script = (root / "003_bilingual_keyboard.sql").read_text(encoding="utf-8")
                columns = {col[1] for col in con.execute("PRAGMA table_info(keyboard_buttons)")}
                if "label_fa" in columns:
                    # An interrupted migration may have added the column before
                    # recording version 3. The data backfill itself is idempotent.
                    script = script.replace("ALTER TABLE keyboard_buttons ADD COLUMN label_fa TEXT NOT NULL DEFAULT '';", "")
                con.executescript(script)
                con.execute("INSERT INTO schema_migrations VALUES(3,?)", (utcnow(),))
                con.commit()

    @staticmethod
    def _upgrade_legacy(con: sqlite3.Connection, grant_old_admins: bool = False) -> None:
        existing = {r[1] for r in con.execute("PRAGMA table_info(games)")}
        game_cols = {
            "original_title": "TEXT DEFAULT ''", "localized_title": "TEXT DEFAULT ''",
            "publisher": "TEXT DEFAULT ''", "genre": "TEXT DEFAULT ''",
            "series": "TEXT DEFAULT ''", "date_status": "TEXT DEFAULT 'unconfirmed'",
            "source_url": "TEXT DEFAULT ''", "priority": "INTEGER DEFAULT 0",
            "visible": "INTEGER DEFAULT 1", "created_at": "TEXT DEFAULT ''",
            "updated_at": "TEXT DEFAULT ''",
        }
        for name, kind in game_cols.items():
            if name not in existing:
                con.execute(f"ALTER TABLE games ADD COLUMN {name} {kind}")
        existing = {r[1] for r in con.execute("PRAGMA table_info(users)")}
        for name, kind in (("joined_at", "TEXT"), ("last_seen", "TEXT"), ("display_name", "TEXT DEFAULT ''")):
            if name not in existing:
                con.execute(f"ALTER TABLE users ADD COLUMN {name} {kind}")
        # Old timestamps were often fabricated or time-of-day was guessed. Keep
        # their dates without claiming they are officially confirmed.
        con.execute("UPDATE games SET date_status='unconfirmed' WHERE date_status IS NULL OR date_status=''")
        con.execute("UPDATE games SET visible=1 WHERE visible IS NULL")
        con.execute("UPDATE games SET priority=100 WHERE title LIKE 'GTA%' AND priority=0")
        con.execute("UPDATE users SET lang='en' WHERE lang IS NULL OR lang NOT IN ('en','fa')")
        # Preserve old administrators' effective access (owner management excluded).
        permissions = ("catalog", "content", "appearance", "statistics", "minigame", "settings")
        for (aid,) in (con.execute("SELECT id FROM admins").fetchall() if grant_old_admins else []):
            for perm in permissions:
                con.execute(
                    "INSERT OR IGNORE INTO admin_permissions(admin_id,permission) VALUES(?,?)", (aid, perm)
                )
        con.commit()

    def backup(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
