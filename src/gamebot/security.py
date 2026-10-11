"""Role and permission checks invoked by every sensitive handler."""
from .db import Database

PERMISSIONS = {
    "catalog": "🎮 Games",
    "content": "📝 Messages & menus",
    "appearance": "💎 Emojis & colors",
    "statistics": "📊 Statistics",
    "minigame": "🎲 Mini-game settings",
    "settings": "💬 Support & settings",
}
PERMISSIONS_FA = {
    "catalog": "🎮 بازی‌ها", "content": "📝 پیام‌ها و منوها",
    "appearance": "💎 ایموجی و رنگ‌ها", "statistics": "📊 آمار",
    "minigame": "🎲 تنظیمات دوز", "settings": "💬 پشتیبانی و تنظیمات",
}

DEFAULT_NEW_ADMIN = ("catalog", "content", "statistics")


async def allowed(db: Database, owners: frozenset[int], uid: int, permission: str) -> bool:
    if uid in owners:
        return True
    if permission not in PERMISSIONS:
        return False
    return await db.one(
        "SELECT 1 FROM admin_permissions WHERE admin_id=? AND permission=?", (uid, permission)
    ) is not None


async def is_admin(db: Database, owners: frozenset[int], uid: int) -> bool:
    if uid in owners:
        return True
    return await db.one("SELECT 1 FROM admins WHERE id=?", (uid,)) is not None


async def set_admin(db: Database, owner: int, uid: int, enabled: bool) -> None:
    if enabled:
        def add(con):
            con.execute("INSERT OR IGNORE INTO admins(id,added_at) VALUES(?,CURRENT_TIMESTAMP)", (uid,))
            for permission in DEFAULT_NEW_ADMIN:
                con.execute("INSERT OR IGNORE INTO admin_permissions VALUES(?,?)", (uid, permission))
        await db.transaction(add)
    else:
        await db.execute("DELETE FROM admins WHERE id=?", (uid,))
    await db.audit(owner, "admin.add" if enabled else "admin.remove", str(uid))


async def toggle_permission(db: Database, actor: int, uid: int, permission: str) -> bool:
    if permission not in PERMISSIONS:
        raise ValueError("Unrecognized permission")
    def change(con):
        if not con.execute("SELECT 1 FROM admins WHERE id=?", (uid,)).fetchone():
            raise ValueError("Admin not found")
        row = con.execute("SELECT 1 FROM admin_permissions WHERE admin_id=? AND permission=?", (uid, permission)).fetchone()
        if row:
            con.execute("DELETE FROM admin_permissions WHERE admin_id=? AND permission=?", (uid, permission))
            return False
        con.execute("INSERT INTO admin_permissions VALUES(?,?)", (uid, permission))
        return True
    result = await db.transaction(change)
    await db.audit(actor, "permission.toggle", f"{uid}:{permission}:{int(result)}")
    return result
