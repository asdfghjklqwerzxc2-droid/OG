"""Run the bot from the project root: python main.py.

The same source modules are used by `python -m gamebot` when installed.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from gamebot.bot import main  # noqa: E402
except ModuleNotFoundError as exc:
    if exc.name in ("telegram", "dotenv", "aiolimiter", "httpx"):
        raise SystemExit(
            "Missing required packages. Run: python -m pip install -r requirements.txt"
        ) from exc
    raise


if __name__ == "__main__":
    main()
