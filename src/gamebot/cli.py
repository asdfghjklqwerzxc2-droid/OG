"""Maintenance CLI: migrate, read-only smoke test, and online-safe database backups."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import os

from .catalog import seed_if_empty
from .db import Database
from .menus import seed_buttons


def main():
    parser = argparse.ArgumentParser(description="Game Release Bot database administration")
    parser.add_argument("action", choices=["migrate", "backup", "check"])
    parser.add_argument("--db", default=os.getenv("DATABASE_PATH") or (
        str(Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) / "gaoo66mmp.db") if "RAILWAY_VOLUME_MOUNT_PATH" in os.environ else "./gamebot.db"))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    db = Database(Path(args.db))
    if args.action == "migrate":
        db.migrate()
        seed_if_empty(db)
        seed_buttons(db)
        print("Database ready:", args.db)
    elif args.action == "backup":
        if not Path(args.db).is_file():
            raise SystemExit("Database file does not exist")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = Path(args.output or f"backup-{stamp}.db")
        db.backup(filename)
        print("SQLite backup written:", filename)
    else:
        if not Path(args.db).is_file():
            raise SystemExit("Database file does not exist")
        import sqlite3
        with sqlite3.connect(args.db) as con:
            result = con.execute("PRAGMA quick_check").fetchone()[0]
        print("SQLite quick_check:", result)
        if result != "ok":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
