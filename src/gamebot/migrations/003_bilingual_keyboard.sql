-- English text stays in label; separate localized text preserves user edits.
ALTER TABLE keyboard_buttons ADD COLUMN label_fa TEXT NOT NULL DEFAULT '';
-- Assign Persian translations only to unchanged legacy default English labels.
UPDATE keyboard_buttons SET label='🎮 Games', label_fa='🎮 بازی‌ها'
 WHERE action='games' AND label='🎮 Games / بازی‌ها';
UPDATE keyboard_buttons SET label_fa='⏳ به‌زودی'
 WHERE action='upcoming' AND label='⏳ Upcoming';
UPDATE keyboard_buttons SET label_fa='🔎 جستجو'
 WHERE action='search' AND label='🔎 Search';
UPDATE keyboard_buttons SET label_fa='🎲 دوز'
 WHERE action='minigame' AND label='🎲 Tic-Tac-Toe';
UPDATE keyboard_buttons SET label_fa='💬 پشتیبانی'
 WHERE action='support' AND label='💬 Support';
UPDATE keyboard_buttons SET label_fa='📚 راهنما'
 WHERE action='help' AND label='📚 Help';
UPDATE keyboard_buttons SET label='🌐 Language', label_fa='🌐 زبان'
 WHERE action='language' AND label='🌐 Language / زبان';
