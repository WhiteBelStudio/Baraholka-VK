from __future__ import annotations

import json
from typing import Any

from config import settings
from database import add_admin_action_log, add_moderation_log, archive_listing, get_archived_listings, get_listing, get_listing_photos, get_user_by_vk_id, get_user_listings, restore_archived_listing
from services.listings import ListingStatus, ListingValidationError, set_listing_status, submit_for_moderation
from services.vk import VKClient


def moderation_keyboard(listing_id: int) -> dict[str, Any]:
    def button(label: str, command: str, color: str) -> dict[str, Any]:
        return {
            "action": {
                "type": "text",
                "label": label,
                "payload": json.dumps({"command": command, "listing_id": listing_id}, ensure_ascii=False),
            },
            "color": color,
        }

    return {
        "one_time": False,
        "inline": True,
        "buttons": [[
            button("Одобрить", "approve_listing", "positive"),
            button("Отклонить", "reject_listing", "negative"),
        ]],
    }


def _card(listing: Any, seller_vk_id: int) -> str:
    return (
        "Новое объявление на модерацию

"
        f"Объявление №{listing['id']}
"
        f"Название: {listing['title']}
"
        f"Категория: {listing['category']}

"
        f"Описание: {listing['description']}

"
        f"Цена: {listing['price']} ₽
"
        f"Город: {listing['city']}
"
        f"VK ID продавца: {seller_vk_id}"
    )


async def submit_listing_for_moderation(user_id: int, vk: VKClient) -> tuple[str, dict[str, Any]]:
    user = await get_user_by_vk_id(user_id)
    if user is None:
        return "Пользователь не найден. Нажмите «🛍 Подать объявление» ещё раз.", {}

    drafts = await get_user_listings(int(user["id"]), (ListingStatus.DRAFT,))
    if not drafts:
        return "Активного черновика нет.", {}

    listing = drafts[0]
    listing_id = int(listing["id"])
    photos = await get_listing_photos(listing_id)

    try:
        await submit_for_moderation(listing_id)
    except ListingValidationError as exc:
        return f"⚠️ {exc}", {}

    listing = await get_listing(listing_id)
    if listing is None:
        return "Не удалось загрузить объявление после отправки.", {}

    sent = 0
    attachments = ",".join(str(photo["vk_attachment"]) for photo in photos)
    for admin_id in sorted(settings.administrators):
        if not settings.can_moderate(admin_id):
            continue
        try:
            await vk.send_message(
                admin_id,
                _card(listing, user_id),
                keyboard=moderation_keyboard(listing_id),
                attachments=attachments or None,
            )
            sent += 1
        except Exception:
            continue

    if sent == 0:
        await set_listing_status(listing_id, ListingStatus.DRAFT)
        return "Не удалось передать объявление администраторам. Попробуйте ещё раз.", {}

    return (
        f"Объявление №{listing_id} отправлено на модерацию.

"
        "После проверки вы получите сообщение о результате.",
        {},
    )


async def log_moderation_action(
    listing_id: int,
    admin_vk_user_id: int,
    action: str,
    reason: str | None = None,
) -> None:
    await add_moderation_log(listing_id, admin_vk_user_id, action, reason)


async def archive_listing_for_admin(listing_id: int, admin_vk_user_id: int, vk: VKClient) -> tuple[str, dict[str, Any]]:
    if not settings.can_moderate(admin_vk_user_id):
        return "⛔ У вас нет прав для архивирования.", {}

    listing = await get_listing(listing_id)
    if listing is None:
        return "⚠️ Объявление не найдено.", {}

    if listing["status"] not in {ListingStatus.APPROVED, ListingStatus.PUBLISHED, ListingStatus.REJECTED}:
        return "⚠️ Это объявление нельзя отправить в архив в текущем статусе.", {}

    if listing["status"] == ListingStatus.PUBLISHED and listing["published_post_id"]:
        try:
            await vk.call(
                "wall.delete",
                owner_id=-settings.vk_group_id,
                post_id=int(listing["published_post_id"]),
            )
        except Exception:
            return "⚠️ Не удалось удалить опубликованную запись VK. Объявление оставлено без изменений.", {}

    if not await archive_listing(listing_id):
        return "⚠️ Не удалось переместить объявление в архив.", {}

    await add_moderation_log(listing_id, admin_vk_user_id, "archived")
    await add_admin_action_log(admin_vk_user_id, "listing_archived", listing_id=listing_id)
    try:
        await vk.send_message(
            int((await get_user_by_vk_id(int(listing["user_id"])))["vk_user_id"]),
            f"🗄 Объявление №{listing_id} перемещено в архив администрацией.",
        )
    except Exception:
        pass
    return f"🗄 Объявление №{listing_id} перемещено в архив.", {}


async def restore_listing_for_admin(listing_id: int, admin_vk_user_id: int) -> tuple[str, dict[str, Any]]:
    if not settings.can_moderate(admin_vk_user_id):
        return "⛔ У вас нет прав для восстановления.", {}

    if not await restore_archived_listing(listing_id):
        return "⚠️ Архивное объявление не найдено.", {}

    await add_moderation_log(listing_id, admin_vk_user_id, "restored")
    await add_admin_action_log(admin_vk_user_id, "listing_restored", listing_id=listing_id)
    return f"♻️ Объявление №{listing_id} восстановлено.", {}
