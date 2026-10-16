from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from config import settings
from database import fetch_all
from services.telegram_storage import (
    create_campaign,
    finish_campaign,
    get_active_telegram_subscribers,
    mark_campaign_started,
    record_delivery,
)
from services.vk import VKAPIError, VKClient

logger = logging.getLogger(__name__)

CAMPAIGN_LABELS = {
    "important": "📣 Важная новость",
    "news": "📰 Новости проекта",
    "new_listings": "🛍 Новые товары",
    "custom": "✍️ Другая рассылка",
}


async def send_campaign(
    bot: Bot,
    creator_id: int,
    campaign_type: str,
    message_text: str,
) -> tuple[int, int, int]:
    """Persist and deliver one administrator-approved campaign across both platforms."""
    campaign_id = await create_campaign(creator_id, campaign_type, message_text)
    telegram_targets = await get_active_telegram_subscribers()
    vk_targets = await fetch_all(
        "SELECT vk_user_id FROM users WHERE is_blocked=0 AND vk_user_id > 0 ORDER BY vk_user_id"
    )
    total_targets = len(telegram_targets) + len(vk_targets)
    await mark_campaign_started(campaign_id, total_targets)

    sent = 0
    failed = 0
    vk = VKClient()

    for target in telegram_targets:
        recipient_id = int(target["telegram_user_id"])
        try:
            await bot.send_message(recipient_id, message_text)
            await record_delivery(campaign_id, "telegram", recipient_id, "sent")
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            try:
                await bot.send_message(recipient_id, message_text)
                await record_delivery(campaign_id, "telegram", recipient_id, "sent")
                sent += 1
            except TelegramAPIError as retry_exc:
                await record_delivery(campaign_id, "telegram", recipient_id, "failed", type(retry_exc).__name__)
                failed += 1
        except TelegramForbiddenError as exc:
            await record_delivery(campaign_id, "telegram", recipient_id, "failed", type(exc).__name__)
            failed += 1
        except TelegramAPIError as exc:
            await record_delivery(campaign_id, "telegram", recipient_id, "failed", type(exc).__name__)
            failed += 1
        await asyncio.sleep(0.05)

    for target in vk_targets:
        recipient_id = int(target["vk_user_id"])
        try:
            await vk.send_message(recipient_id, message_text)
            await record_delivery(campaign_id, "vk", recipient_id, "sent")
            sent += 1
        except VKAPIError as exc:
            logger.warning("VK broadcast delivery failed for recipient %s: %s", recipient_id, exc)
            await record_delivery(campaign_id, "vk", recipient_id, "failed", "VKAPIError")
            failed += 1
        await asyncio.sleep(0.35)

    await finish_campaign(campaign_id, sent, failed)
    return campaign_id, sent, failed
