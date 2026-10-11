CREATE INDEX IF NOT EXISTS ix_games_date ON games(visible, date_status, release_date);
CREATE INDEX IF NOT EXISTS ix_games_priority ON games(visible, priority DESC, title);
CREATE INDEX IF NOT EXISTS ix_views_game ON views(game_id);
CREATE INDEX IF NOT EXISTS ix_audit_at ON audit_logs(at DESC);
CREATE INDEX IF NOT EXISTS ix_admin_permissions ON admin_permissions(permission);
