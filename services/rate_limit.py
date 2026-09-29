from __future__ import annotations

import time

from config import settings
from database import check_publication_rate_limit


async def check_publication_submission(user_id: int) -> tuple[bool, int]:
    return await check_publication_rate_limit(
        user_id,
        time.time(),
        settings.publication_window_seconds,
        settings.publication_max_count,
        settings.publication_cooldown_seconds,
    )
