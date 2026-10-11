"""Server-authoritative native Telegram Tic-Tac-Toe. No untrusted score API."""
import secrets
from datetime import datetime, timedelta, timezone

from .db import Database, utcnow

LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
         (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))


def winner(board: str) -> str | None:
    for a, b, c in LINES:
        if board[a] != "." and board[a] == board[b] == board[c]:
            return board[a]
    return "D" if "." not in board else None


def bot_move(board: str) -> int:
    """Prioritize immediate win/block, then center, then corners."""
    if winner(board):
        raise ValueError("Game is over")
    for piece in ("O", "X"):
        for pos, char in enumerate(board):
            if char == "." and winner(board[:pos] + piece + board[pos+1:]) == piece:
                return pos
    for pos in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if board[pos] == ".":
            return pos
    raise ValueError("No legal move")


async def start_game(db: Database, user_id: int) -> dict:
    token = secrets.token_hex(8)
    stamp = utcnow()
    def create(con):
        flag = con.execute("SELECT value FROM settings WHERE key='minigame_enabled'").fetchone()
        if flag and flag[0] == "false":
            raise ValueError("The mini-game is disabled")
        con.execute(
            """INSERT INTO ttt_sessions(user_id,token,board,state,updated_at)
            VALUES(?,?,'.........','active',?) ON CONFLICT(user_id)
            DO UPDATE SET token=excluded.token,board=excluded.board,
            state=excluded.state,updated_at=excluded.updated_at""",
            (user_id, token, stamp),
        )
    await db.transaction(create)
    return {"user_id": user_id, "token": token, "board": ".........", "state": "active"}


async def play_move(db: Database, user_id: int, token: str, position: int) -> dict:
    if not 0 <= position < 9 or not token or len(token) > 20:
        raise ValueError("Invalid move")

    def move(con):
        flag = con.execute("SELECT value FROM settings WHERE key='minigame_enabled'").fetchone()
        if flag and flag[0] == "false":
            raise ValueError("The mini-game is disabled")
        row = con.execute("SELECT * FROM ttt_sessions WHERE user_id=?", (user_id,)).fetchone()
        if not row or row["token"] != token or row["state"] != "active":
            raise ValueError("This game has expired. Start a new game")
        try:
            last = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid session") from exc
        if datetime.now(timezone.utc) - last > timedelta(hours=24):
            raise ValueError("Game expired")
        board = row["board"]
        if len(board) != 9 or any(x not in "XO." for x in board) or board[position] != ".":
            raise ValueError("That square is already taken")
        board = board[:position] + "X" + board[position+1:]
        result = winner(board)
        if not result:
            spot = bot_move(board)
            board = board[:spot] + "O" + board[spot+1:]
            result = winner(board)
        state = {"X": "won", "O": "lost", "D": "draw"}.get(result, "active")
        con.execute("UPDATE ttt_sessions SET board=?,state=?,updated_at=? WHERE user_id=?",
                    (board, state, utcnow(), user_id))
        if state != "active":
            column = {"won": "wins", "lost": "losses", "draw": "draws"}[state]
            con.execute("INSERT OR IGNORE INTO ttt_scores(user_id) VALUES(?)", (user_id,))
            con.execute(f"UPDATE ttt_scores SET {column}={column}+1 WHERE user_id=?", (user_id,))
        return {"user_id": user_id, "token": token, "board": board, "state": state}

    return await db.transaction(move)


def game_keyboard(session: dict):
    from .menus import button, keyboard
    from .i18n import t
    symbols = {".": "▫️", "X": "❎", "O": "⭕"}
    rows = []
    for row in range(3):
        buttons = []
        for col in range(3):
            i = row * 3 + col
            token = session["token"]
            action = f"ttt:{token}:{i}" if session["state"] == "active" and session["board"][i] == "." else "noop"
            buttons.append(button(symbols[session["board"][i]], action=action))
        rows.append(buttons)
    rows.append([button(t("🔄 Restart", "🔄 شروع دوباره"), action="ttt:new"), button(t("🏆 Scores", "🏆 امتیازها"), action="ttt:top")])
    return keyboard(rows)


def game_text(session: dict, lang: str) -> str:
    status = session["state"]
    if lang == "fa":
        feedback = {"active": "نوبت شماست: ❎", "won": "🎉 برنده شدید!", "lost": "🤖 ربات برنده شد!", "draw": "🤝 مساوی!"}[status]
        return f"🎲 <b>دوز (Tic-Tac-Toe)</b>\n{feedback}\nسه علامت ❎ را در یک خط بگذارید."
    feedback = {"active": "Your turn: ❎", "won": "🎉 You win!", "lost": "🤖 Bot wins!", "draw": "🤝 Draw!"}[status]
    return f"🎲 <b>Tic-Tac-Toe</b>\n{feedback}\nMake a row of three ❎ marks."


async def leaderboard(db: Database) -> list[dict]:
    return await db.all(
        """SELECT s.user_id,COALESCE(NULLIF(u.display_name,''),'Player') name,
        s.wins,s.draws,s.losses,(s.wins*3+s.draws) points FROM ttt_scores s
        LEFT JOIN users u ON u.id=s.user_id ORDER BY points DESC,s.wins DESC,s.user_id ASC LIMIT 10"""
    )
