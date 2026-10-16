from __future__ import annotations

from database import execute, fetch_all, fetch_one, get_db


async def init_telegram_storage() -> None:
    """Create Telegram and broadcast tables without changing existing marketplace data."""
    async with await get_db() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_subscribed INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS broadcast_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by_telegram_id INTEGER NOT NULL,
                campaign_type TEXT NOT NULL,
                message_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                total_targets INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS broadcast_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                recipient_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(campaign_id) REFERENCES broadcast_campaigns(id) ON DELETE CASCADE,
                UNIQUE(campaign_id, platform, recipient_id)
            );
            CREATE INDEX IF NOT EXISTS idx_tg_subscribers_active
                ON telegram_subscribers(is_subscribed, telegram_user_id);
            CREATE INDEX IF NOT EXISTS idx_broadcast_campaigns_created
                ON broadcast_campaigns(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_broadcast_deliveries_campaign
                ON broadcast_deliveries(campaign_id, status);
            """
        )
        await db.commit()


async def upsert_telegram_subscriber(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    await execute(
        """INSERT INTO telegram_subscribers
            (telegram_user_id, username, first_name, last_name, is_subscribed)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            is_subscribed=1,
            updated_at=CURRENT_TIMESTAMP""",
        (telegram_user_id, username, first_name, last_name),
    )


async def unsubscribe_telegram_subscriber(telegram_user_id: int) -> bool:
    return await execute(
        """UPDATE telegram_subscribers
        SET is_subscribed=0, updated_at=CURRENT_TIMESTAMP
        WHERE telegram_user_id=? AND is_subscribed=1""",
        (telegram_user_id,),
    ) > 0


async def create_campaign(creator_id: int, campaign_type: str, message_text: str) -> int:
    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO broadcast_campaigns
                (created_by_telegram_id, campaign_type, message_text, status)
            VALUES (?, ?, ?, 'draft')""",
            (creator_id, campaign_type, message_text),
        )
        await db.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Could not create broadcast campaign")
        return int(cursor.lastrowid)


async def get_active_telegram_subscribers() -> list:
    return await fetch_all(
        "SELECT telegram_user_id FROM telegram_subscribers WHERE is_subscribed=1 ORDER BY telegram_user_id"
    )


async def mark_campaign_started(campaign_id: int, total_targets: int) -> bool:
    return await execute(
        """UPDATE broadcast_campaigns
        SET status='sending', total_targets=?, started_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='draft'""",
        (total_targets, campaign_id),
    ) > 0


async def record_delivery(
    campaign_id: int,
    platform: str,
    recipient_id: int,
    status: str,
    error_code: str | None = None,
) -> None:
    await execute(
        """INSERT INTO broadcast_deliveries
            (campaign_id, platform, recipient_id, status, error_code)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(campaign_id, platform, recipient_id) DO UPDATE SET
            status=excluded.status, error_code=excluded.error_code""",
        (campaign_id, platform, recipient_id, status, error_code),
    )


async def finish_campaign(campaign_id: int, sent_count: int, failed_count: int) -> None:
    await execute(
        """UPDATE broadcast_campaigns
        SET status='completed', sent_count=?, failed_count=?, completed_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='sending'""",
        (sent_count, failed_count, campaign_id),
    )
