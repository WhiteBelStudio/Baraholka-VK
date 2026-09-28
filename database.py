from __future__ import annotations

from pathlib import Path
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT,
    category TEXT,
    description TEXT,
    price TEXT,
    city TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    vk_attachment TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(listing_id) REFERENCES listings(id)
);

CREATE TABLE IF NOT EXISTS moderation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    admin_vk_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
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
        await db.commit()


async def execute(query: str, parameters: tuple[Any, ...] = ()) -> None:
    async with await get_db() as db:
        await db.execute(query, parameters)
        await db.commit()


async def fetch_one(query: str, parameters: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
    async with await get_db() as db:
        cursor = await db.execute(query, parameters)
        return await cursor.fetchone()


async def fetch_all(query: str, parameters: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
    async with await get_db() as db:
        cursor = await db.execute(query, parameters)
        return await cursor.fetchall()
