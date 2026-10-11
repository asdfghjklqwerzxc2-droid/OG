"""Environment configuration. No embedded owner identities or credentials."""
from dataclasses import dataclass
from pathlib import Path
import logging
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    token: str
    owners: frozenset[int]
    database_path: Path
    log_level: str = "INFO"
    custom_emoji_enabled: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.environ.get("BOT_TOKEN", "").strip()
        raw = os.environ.get("OWNERS", "")
        try:
            owners = frozenset(int(part.strip()) for part in raw.split(",") if part.strip())
        except ValueError as exc:
            raise ValueError("OWNERS must contain numeric Telegram user IDs") from exc
        if not token or ":" not in token or token.startswith("replace-"):
            raise ValueError("Set a valid BOT_TOKEN environment variable")
        if not owners or min(owners) <= 0:
            raise ValueError("Set OWNERS to at least one positive numeric user ID")
        volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        default_path = str(Path(volume) / "gaoo66mmp.db") if volume else "./gamebot.db"
        path = Path(os.environ.get("DATABASE_PATH", default_path)).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError("Invalid LOG_LEVEL")
        return cls(token, owners, path, level, os.getenv("CUSTOM_EMOJI_ENABLED", "false").lower() == "true")
