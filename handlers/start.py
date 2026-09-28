from __future__ import annotations

import logging

from database import create_or_update_user, get_user_by_vk_id, set_user_blocked

logger = logging.getLogger(__name__)


async def register_user(
    vk_user_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
) -> int:
    """Create or update a local user record and return its database ID."""
    return await create_or_update_user(
        vk_user_id=vk_user_id,
        first_name=first_name,
        last_name=last_name,
    )


async def get_user(vk_user_id: int):
    """Return a local user by VK ID."""
    return await get_user_by_vk_id(vk_user_id)


async def block_user(vk_user_id: int) -> None:
    """Block a user from using marketplace features."""
    await set_user_blocked(vk_user_id, True)
    logger.info("User %s blocked", vk_user_id)


async def unblock_user(vk_user_id: int) -> None:
    """Remove a marketplace block from a user."""
    await set_user_blocked(vk_user_id, False)
    logger.info("User %s unblocked", vk_user_id)


async def is_user_blocked(vk_user_id: int) -> bool:
    """Check whether a user exists and is blocked."""
    user = await get_user_by_vk_id(vk_user_id)
    return bool(user and user["is_blocked"])


async def ensure_user(
    vk_user_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
):
    """Register the user when needed and return the current record."""
    await register_user(vk_user_id, first_name, last_name)
    return await get_user_by_vk_id(vk_user_id)
