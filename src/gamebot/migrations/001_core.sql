CREATE TABLE IF NOT EXISTS games (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT NOT NULL,
 release_date TEXT,
 platforms TEXT DEFAULT '',
 company TEXT DEFAULT '',
 image TEXT DEFAULT '',
 description TEXT DEFAULT '',
 original_title TEXT DEFAULT '',
 localized_title TEXT DEFAULT '',
 publisher TEXT DEFAULT '',
 genre TEXT DEFAULT '',
 series TEXT DEFAULT '',
 date_status TEXT NOT NULL DEFAULT 'unknown',
 source_url TEXT DEFAULT '',
 priority INTEGER NOT NULL DEFAULT 0,
 visible INTEGER NOT NULL DEFAULT 1,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'en',
 joined_at TEXT, last_seen TEXT, display_name TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS groups (
 id INTEGER PRIMARY KEY, title TEXT, lang TEXT DEFAULT 'en',
 active INTEGER DEFAULT 1, added_by INTEGER, added_at TEXT
);
CREATE TABLE IF NOT EXISTS views (
 game_id INTEGER, user_id INTEGER, PRIMARY KEY(game_id, user_id)
);
CREATE TABLE IF NOT EXISTS texts (
 key TEXT, lang TEXT, value TEXT, PRIMARY KEY(key, lang)
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS admins (
 id INTEGER PRIMARY KEY, added_at TEXT
);
CREATE TABLE IF NOT EXISTS emojis (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ch TEXT UNIQUE, cid TEXT
);
CREATE TABLE IF NOT EXISTS admin_permissions (
 admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
 permission TEXT NOT NULL, PRIMARY KEY(admin_id, permission)
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 actor_id INTEGER NOT NULL, action TEXT NOT NULL,
 target TEXT NOT NULL DEFAULT '', outcome TEXT NOT NULL,
 at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS keyboard_buttons (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 menu TEXT NOT NULL DEFAULT 'home', row_no INTEGER NOT NULL,
 pos INTEGER NOT NULL, label TEXT NOT NULL, action TEXT NOT NULL,
 target TEXT DEFAULT '', style TEXT DEFAULT 'none', icon_id TEXT DEFAULT '',
 CHECK (row_no BETWEEN 0 AND 5), CHECK(pos BETWEEN 0 AND 4),
 CHECK(action IN ('games','upcoming','search','support','help','language','minigame','url')),
 CHECK(style IN ('primary','success','danger','none')),
 UNIQUE(menu,row_no,pos)
);
CREATE TABLE IF NOT EXISTS ttt_sessions (
 user_id INTEGER PRIMARY KEY,
 token TEXT NOT NULL, board TEXT NOT NULL, state TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ttt_scores (
 user_id INTEGER PRIMARY KEY, wins INTEGER NOT NULL DEFAULT 0,
 draws INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0,
 CHECK (wins>=0 AND draws>=0 AND losses>=0)
);
