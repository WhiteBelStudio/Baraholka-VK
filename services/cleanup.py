from __future__ import annotations

import asyncio
import logging

from database import execute

logger = logging.getLogger(__name__)

STANDARD_RETENTION_DAYS = 3
VIP_RETENTION_DAYS = 14
CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


async def cleanup_old_archived_listings() -> int:
    result = await execute(
        """DELETE FROM listings
        WHERE status = 'archived'
          AND (
            (NOT EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = listings.user_id
                  AND u.vip_until IS NOT NULL
                  AND datetime(u.vip_until) > CURRENT_TIMESTAMP
             )
             AND datetime(updated_at) <= datetime('now', '-3 days'))
            OR
            (EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = listings.user_id
                  AND u.vip_until IS NOT NULL
                  AND datetime(u.vip_until) > CURRENT_TIMESTAMP
             )
             AND datetime(updated_at) <= datetime('now', '-14 days'))
          )"""
    )
    logger.info("Archived listing cleanup completed: %s removed", result)
    return result


async def cleanup_loop() -> None:
    while True:
        try:
            await cleanup_old_archived_listings()
        except Exception:
            logger.exception("Archived listing cleanup failed")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
