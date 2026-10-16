from __future__ import annotations

import json
from typing import Any

import aiosqlite

from config import settings


async def _connect() -> aiosqlite.Connection:
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.database_file)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_telegram_schema() -> None:
    """Additive schema only: preserve all existing VK marketplace tables and records."""
    async with await _connect() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS telegram_users (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_blocked INTEGER NOT NULL DEFAULT 0,
                subscribed_to_news INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS telegram_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                price TEXT NOT NULL,
                city TEXT NOT NULL,
                photo_file_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'moderation',
                published_message_id INTEGER,
                rejection_reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_telegram_listings_status
                ON telegram_listings(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_telegram_listings_user
                ON telegram_listings(telegram_user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_telegram_users_subscribed
                ON telegram_users(subscribed_to_news, is_blocked);

            CREATE TABLE IF NOT EXISTS vk_news_subscriptions (
                vk_user_id INTEGER PRIMARY KEY,
                subscribed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_vk_news_subscriptions_subscribed
                ON vk_news_subscriptions(subscribed);

            CREATE TABLE IF NOT EXISTS broadcast_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by_telegram_id INTEGER NOT NULL,
                message_type TEXT NOT NULL,
                message_text TEXT NOT NULL,
                target_platform TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS broadcast_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                recipient_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(campaign_id) REFERENCES broadcast_campaigns(id) ON DELETE CASCADE,
                UNIQUE(campaign_id, platform, recipient_id)
            );

            CREATE TABLE IF NOT EXISTS cross_platform_action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_platform TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                listing_platform TEXT,
                listing_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await db.commit()


async def upsert_telegram_user(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    async with await _connect() as db:
        await db.execute(
            """
            INSERT INTO telegram_users
                (telegram_user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_user_id, username, first_name, last_name),
        )
        await db.commit()


async def set_news_subscription(telegram_user_id: int, enabled: bool) -> None:
    async with await _connect() as db:
        await db.execute(
            "UPDATE telegram_users SET subscribed_to_news = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_user_id = ?",
            (int(enabled), telegram_user_id),
        )
        await db.commit()


async def create_telegram_listing(telegram_user_id: int, data: dict[str, Any]) -> int:
    photos = json.dumps(data.get("photo_file_ids", []), ensure_ascii=False)
    async with await _connect() as db:
        cursor = await db.execute(
            """
            INSERT INTO telegram_listings
                (telegram_user_id, title, category, description, price, city, photo_file_ids, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'moderation')
            """,
            (
                telegram_user_id,
                data["title"],
                data["category"],
                data["description"],
                data["price"],
                data["city"],
                photos,
            ),
        )
        await db.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create Telegram listing")
        return int(cursor.lastrowid)


async def get_telegram_listing(listing_id: int) -> aiosqlite.Row | None:
    async with await _connect() as db:
        cursor = await db.execute("SELECT * FROM telegram_listings WHERE id = ?", (listing_id,))
        return await cursor.fetchone()


async def get_telegram_listings_by_status(status: str, limit: int = 50) -> list[aiosqlite.Row]:
    async with await _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM telegram_listings WHERE status = ? ORDER BY id ASC LIMIT ?",
            (status, max(1, min(limit, 200))),
        )
        return await cursor.fetchall()


async def get_telegram_user_listings(telegram_user_id: int, limit: int = 20) -> list[aiosqlite.Row]:
    async with await _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM telegram_listings WHERE telegram_user_id = ? ORDER BY id DESC LIMIT ?",
            (telegram_user_id, max(1, min(limit, 100))),
        )
        return await cursor.fetchall()


async def transition_telegram_listing(listing_id: int, expected_status: str, new_status: str) -> bool:
    allowed = {"draft", "moderation", "publishing", "published", "rejected", "archived", "deleted"}
    if expected_status not in allowed or new_status not in allowed:
        raise ValueError("Invalid listing status transition")
    async with await _connect() as db:
        cursor = await db.execute(
            """
            UPDATE telegram_listings
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = ?
            """,
            (new_status, listing_id, expected_status),
        )
        await db.commit()
        return cursor.rowcount == 1


async def finish_telegram_publication(listing_id: int, message_id: int) -> None:
    async with await _connect() as db:
        await db.execute(
            """
            UPDATE telegram_listings
            SET status = 'published', published_message_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'publishing'
            """,
            (message_id, listing_id),
        )
        await db.commit()


async def reject_telegram_listing(listing_id: int, reason: str) -> bool:
    async with await _connect() as db:
        cursor = await db.execute(
            """
            UPDATE telegram_listings
            SET status = 'rejected', rejection_reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'moderation'
            """,
            (reason, listing_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def log_cross_platform_action(
    admin_platform: str,
    admin_id: int,
    action: str,
    listing_platform: str | None = None,
    listing_id: int | None = None,
    details: str | None = None,
) -> None:
    async with await _connect() as db:
        await db.execute(
            """
            INSERT INTO cross_platform_action_logs
                (admin_platform, admin_id, action, listing_platform, listing_id, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_platform, admin_id, action, listing_platform, listing_id, details),
        )
        await db.commit()


async def create_broadcast_campaign(
    created_by: int,
    message_type: str,
    message_text: str,
    target_platform: str,
) -> int:
    async with await _connect() as db:
        cursor = await db.execute(
            """
            INSERT INTO broadcast_campaigns
                (created_by_telegram_id, message_type, message_text, target_platform)
            VALUES (?, ?, ?, ?)
            """,
            (created_by, message_type, message_text, target_platform),
        )
        await db.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create broadcast campaign")
        return int(cursor.lastrowid)


async def record_broadcast_delivery(
    campaign_id: int,
    platform: str,
    recipient_id: int,
    status: str,
    error: str | None = None,
) -> None:
    async with await _connect() as db:
        await db.execute(
            """
            INSERT INTO broadcast_deliveries (campaign_id, platform, recipient_id, status, error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, platform, recipient_id) DO UPDATE SET
                status = excluded.status, error = excluded.error
            """,
            (campaign_id, platform, recipient_id, status, (error or "")[:500] or None),
        )
        await db.commit()


async def finish_broadcast_campaign(campaign_id: int, sent_count: int, failed_count: int) -> None:
    async with await _connect() as db:
        await db.execute(
            """
            UPDATE broadcast_campaigns
            SET status = 'finished', sent_count = ?, failed_count = ?,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (sent_count, failed_count, campaign_id),
        )
        await db.commit()


async def get_telegram_broadcast_recipients() -> list[int]:
    async with await _connect() as db:
        cursor = await db.execute(
            "SELECT telegram_user_id FROM telegram_users WHERE subscribed_to_news = 1 AND is_blocked = 0"
        )
        return [int(row[0]) for row in await cursor.fetchall()]


async def get_telegram_statistics() -> dict[str, int]:
    async with await _connect() as db:
        users = await (await db.execute("SELECT COUNT(*) FROM telegram_users")).fetchone()
        subscribed = await (await db.execute(
            "SELECT COUNT(*) FROM telegram_users WHERE subscribed_to_news = 1 AND is_blocked = 0"
        )).fetchone()
        pending = await (await db.execute(
            "SELECT COUNT(*) FROM telegram_listings WHERE status = 'moderation'"
        )).fetchone()
        return {"users": int(users[0]), "subscribed": int(subscribed[0]), "pending": int(pending[0])}


async def set_vk_news_subscription(vk_user_id: int, enabled: bool) -> None:
    async with await _connect() as db:
        await db.execute(
            """
            INSERT INTO vk_news_subscriptions (vk_user_id, subscribed)
            VALUES (?, ?)
            ON CONFLICT(vk_user_id) DO UPDATE SET
                subscribed = excluded.subscribed,
                updated_at = CURRENT_TIMESTAMP
            """,
            (vk_user_id, int(enabled)),
        )
        await db.commit()


async def get_vk_broadcast_recipients() -> list[int]:
    async with await _connect() as db:
        cursor = await db.execute(
            """
            SELECT s.vk_user_id
            FROM vk_news_subscriptions s
            JOIN users u ON u.vk_user_id = s.vk_user_id
            WHERE s.subscribed = 1 AND u.is_blocked = 0
            """
        )
        return [int(row[0]) for row in await cursor.fetchall()]
