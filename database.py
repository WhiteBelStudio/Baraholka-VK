from pathlib import Path
import aiosqlite
from config import settings

async def init_db() -> None:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript('''
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, vk_user_id INTEGER NOT NULL UNIQUE, first_name TEXT, last_name TEXT, is_blocked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS listings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT, category TEXT, description TEXT, price TEXT, city TEXT, status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS listing_photos (id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, vk_attachment TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(listing_id) REFERENCES listings(id));
CREATE TABLE IF NOT EXISTS moderation_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, admin_vk_user_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
''')
        await db.commit()
