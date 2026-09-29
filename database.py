from __future__ import annotations

from typing import Any

import aiosqlite

from config import settings


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_user_id INTEGER NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    is_blocked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    price TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    editing_field TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_post_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    vk_attachment TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS moderation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    admin_vk_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    reporter_user_id INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
    FOREIGN KEY(reporter_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_blocked ON users(is_blocked);
CREATE INDEX IF NOT EXISTS idx_listings_user_status ON listings(user_id, status);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
CREATE INDEX IF NOT EXISTS idx_listing_photos_listing ON listing_photos(listing_id, position);
CREATE INDEX IF NOT EXISTS idx_moderation_logs_listing ON moderation_logs(listing_id, created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status, created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_listing ON complaints(listing_id, created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_reporter ON complaints(reporter_user_id, created_at);

CREATE TABLE IF NOT EXISTS admin_action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_vk_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_vk_user_id INTEGER,
    listing_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_action_logs_created ON admin_action_logs(created_at);

"""


async def get_db() -> aiosqlite.Connection:
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.database_file)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_db() -> None:
    async with await get_db() as db:
        await db.executescript(SCHEMA)
        columns = await db.execute_fetchall("PRAGMA table_info(listings)")
        column_names = {row[1] for row in columns}
        if "editing_field" not in column_names:
            await db.execute("ALTER TABLE listings ADD COLUMN editing_field TEXT")
        await db.commit()


async def execute(query: str, parameters: tuple[Any, ...] = ()) -> int:
    async with await get_db() as db:
        cursor = await db.execute(query, parameters)
        await db.commit()
        return cursor.rowcount


async def fetch_one(query: str, parameters: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
    async with await get_db() as db:
        cursor = await db.execute(query, parameters)
        return await cursor.fetchone()


async def fetch_all(query: str, parameters: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
    async with await get_db() as db:
        cursor = await db.execute(query, parameters)
        return await cursor.fetchall()


async def create_or_update_user(vk_user_id: int, first_name: str | None = None, last_name: str | None = None) -> int:
    async with await get_db() as db:
        await db.execute(
            """INSERT INTO users (vk_user_id, first_name, last_name) VALUES (?, ?, ?)
            ON CONFLICT(vk_user_id) DO UPDATE SET first_name=excluded.first_name, last_name=excluded.last_name, updated_at=CURRENT_TIMESTAMP""",
            (vk_user_id, first_name, last_name),
        )
        await db.commit()
        cursor = await db.execute("SELECT id FROM users WHERE vk_user_id = ?", (vk_user_id,))
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create or load user")
        return int(row["id"])


async def get_user_by_vk_id(vk_user_id: int) -> aiosqlite.Row | None:
    return await fetch_one("SELECT * FROM users WHERE vk_user_id = ?", (vk_user_id,))


async def set_user_blocked(vk_user_id: int, blocked: bool) -> None:
    await execute("UPDATE users SET is_blocked = ?, updated_at = CURRENT_TIMESTAMP WHERE vk_user_id = ?", (int(blocked), vk_user_id))


async def create_listing(user_id: int) -> int:
    async with await get_db() as db:
        cursor = await db.execute("INSERT INTO listings (user_id) VALUES (?)", (user_id,))
        await db.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create listing")
        return int(cursor.lastrowid)


async def get_listing(listing_id: int) -> aiosqlite.Row | None:
    return await fetch_one("SELECT * FROM listings WHERE id = ?", (listing_id,))


async def get_listing_for_user(listing_id: int, user_id: int) -> aiosqlite.Row | None:
    return await fetch_one("SELECT * FROM listings WHERE id = ? AND user_id = ?", (listing_id, user_id))


async def get_user_listings(user_id: int, statuses: tuple[str, ...] | None = None) -> list[aiosqlite.Row]:
    if not statuses:
        return await fetch_all("SELECT * FROM listings WHERE user_id = ? ORDER BY id DESC", (user_id,))
    placeholders = ",".join("?" for _ in statuses)
    return await fetch_all(f"SELECT * FROM listings WHERE user_id = ? AND status IN ({placeholders}) ORDER BY id DESC", (user_id, *statuses))


async def get_listings_by_status(status: str) -> list[aiosqlite.Row]:
    return await fetch_all("SELECT * FROM listings WHERE status = ? ORDER BY id ASC", (status,))


async def update_listing(listing_id: int, **fields: Any) -> None:
    allowed = {"title", "category", "description", "price", "city", "status", "editing_field", "published_post_id"}
    changes = [(key, value) for key, value in fields.items() if key in allowed]
    if not changes:
        return
    assignments = ", ".join(f"{key} = ?" for key, _ in changes)
    values = [value for _, value in changes]
    values.append(listing_id)
    await execute(f"UPDATE listings SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", tuple(values))


async def delete_listing(listing_id: int, user_id: int | None = None) -> bool:
    if user_id is None:
        query, params = "DELETE FROM listings WHERE id = ?", (listing_id,)
    else:
        query, params = "DELETE FROM listings WHERE id = ? AND user_id = ?", (listing_id, user_id)
    return await execute(query, params) > 0


async def add_listing_photo(listing_id: int, vk_attachment: str, position: int = 0) -> int:
    async with await get_db() as db:
        cursor = await db.execute("INSERT INTO listing_photos (listing_id, vk_attachment, position) VALUES (?, ?, ?)", (listing_id, vk_attachment, position))
        await db.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to add listing photo")
        return int(cursor.lastrowid)


async def get_listing_photos(listing_id: int) -> list[aiosqlite.Row]:
    return await fetch_all("SELECT * FROM listing_photos WHERE listing_id = ? ORDER BY position, id", (listing_id,))


async def delete_listing_photo(photo_id: int, listing_id: int | None = None) -> bool:
    if listing_id is None:
        query, params = "DELETE FROM listing_photos WHERE id = ?", (photo_id,)
    else:
        query, params = "DELETE FROM listing_photos WHERE id = ? AND listing_id = ?", (photo_id, listing_id)
    return await execute(query, params) > 0


async def clear_listing_photos(listing_id: int) -> int:
    return await execute("DELETE FROM listing_photos WHERE listing_id = ?", (listing_id,))


async def add_moderation_log(listing_id: int, admin_vk_user_id: int, action: str, reason: str | None = None) -> None:
    await execute("INSERT INTO moderation_logs (listing_id, admin_vk_user_id, action, reason) VALUES (?, ?, ?, ?)", (listing_id, admin_vk_user_id, action, reason))


async def add_admin_action_log(
    admin_vk_user_id: int,
    action: str,
    target_vk_user_id: int | None = None,
    listing_id: int | None = None,
    details: str | None = None,
) -> None:
    await execute(
        "INSERT INTO admin_action_logs (admin_vk_user_id, action, target_vk_user_id, listing_id, details) VALUES (?, ?, ?, ?, ?)",
        (admin_vk_user_id, action, target_vk_user_id, listing_id, details),
    )


async def create_complaint(listing_id: int, reporter_user_id: int) -> int:
    existing = await fetch_one(
        "SELECT id FROM complaints WHERE listing_id = ? AND reporter_user_id = ? AND status = 'pending_reason' ORDER BY id DESC LIMIT 1",
        (listing_id, reporter_user_id),
    )
    if existing:
        return int(existing["id"])
    async with await get_db() as db:
        cursor = await db.execute(
            "INSERT INTO complaints (listing_id, reporter_user_id, reason, status) VALUES (?, ?, '', 'pending_reason')",
            (listing_id, reporter_user_id),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_pending_complaint(reporter_user_id: int) -> aiosqlite.Row | None:
    return await fetch_one("SELECT * FROM complaints WHERE reporter_user_id = ? AND status = 'pending_reason' ORDER BY id DESC LIMIT 1", (reporter_user_id,))


async def finish_complaint(complaint_id: int, reporter_user_id: int, reason: str) -> bool:
    return await execute(
        "UPDATE complaints SET reason = ?, status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND reporter_user_id = ? AND status = 'pending_reason'",
        (reason, complaint_id, reporter_user_id),
    ) > 0


async def cancel_complaint(complaint_id: int, reporter_user_id: int) -> bool:
    return await execute(
        "DELETE FROM complaints WHERE id = ? AND reporter_user_id = ? AND status = 'pending_reason'",
        (complaint_id, reporter_user_id),
    ) > 0


async def get_complaint(complaint_id: int) -> aiosqlite.Row | None:
    return await fetch_one("SELECT * FROM complaints WHERE id = ?", (complaint_id,))


async def get_pending_complaints() -> list[aiosqlite.Row]:
    return await fetch_all(
        "SELECT c.*, l.title, l.status AS listing_status "
        "FROM complaints c JOIN listings l ON l.id = c.listing_id "
        "WHERE c.status = 'pending' ORDER BY c.id ASC"
    )


async def update_complaint_status(complaint_id: int, status: str) -> bool:
    if status not in {"pending", "resolved", "rejected"}:
        raise ValueError("Invalid complaint status")
    return await execute(
        "UPDATE complaints SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
        (status, complaint_id),
    ) > 0


async def complaint_exists_for_user(listing_id: int, reporter_user_id: int) -> bool:
    row = await fetch_one(
        "SELECT id FROM complaints WHERE listing_id = ? AND reporter_user_id = ? AND status IN ('pending_reason','pending','resolved','rejected') ORDER BY id DESC LIMIT 1",
        (listing_id, reporter_user_id),
    )
    return row is not None
