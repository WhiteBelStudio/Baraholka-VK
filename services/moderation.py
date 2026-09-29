from __future__ import annotations

import json
from typing import Any

from config import settings
from database import (
    add_admin_action_log,
    add_moderation_log,
    archive_listing,
    get_archived_listings,
    get_listing,
    get_listing_photos,
    get_user_by_vk_id,
    clear_rejection_session,
    get_rejection_session,
    set_rejection_session,
    get_user_listings,
    restore_archived_listing,
    update_listing,
)
from services.listings import ListingStatus, ListingValidationError, set_listing_status, submit_for_moderation
from services.vk import VKClient


async def _notify_seller(vk: VKClient, seller_vk_id: int, message: str) -> bool:
    for attempt in range(2):
        try:
            await vk.send_message(seller_vk_id, message)
            return True
        except Exception:
            if attempt == 0:
                continue
    return False


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
        "🛡 ОБЪЯВЛЕНИЕ НА МОДЕРАЦИЮ\n\n"
        f"📦 Объявление №{listing['id']}\n"
        f"🛍 Название: {listing['title']}\n"
        f"🏷 Категория: {listing['category']}\n\n"
        f"📝 Описание:\n{listing['description']}\n\n"
        f"💰 Цена: {listing['price']} ₽\n"
        f"📍 Город: {listing['city']}\n"
        f"👤 VK ID продавца: {seller_vk_id}\n"
        "📌 Статус: На модерации"
    )


def _published_card(listing: Any) -> str:
    return (
        f"🛍 {listing['title']}\n\n"
        f"🏷 Категория: {listing['category']}\n"
        f"📝 {listing['description']}\n\n"
        f"💰 Цена: {listing['price']} ₽\n"
        f"📍 Город: {listing['city']}\n\n"
        f"📦 Объявление №{listing['id']}"
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
        f"Объявление №{listing_id} отправлено на модерацию.\n\n"
        "После проверки вы получите сообщение о результате.",
        {},
    )


async def start_rejection_for_admin(
    listing_id: int,
    admin_vk_user_id: int,
) -> tuple[str, dict[str, Any]]:
    if not settings.can_moderate(admin_vk_user_id):
        return "⛔ У вас нет прав для отклонения объявлений.", {}

    listing = await get_listing(listing_id)
    if listing is None:
        return "⚠️ Объявление не найдено.", {}
    if listing["status"] != ListingStatus.MODERATION:
        return "ℹ️ Это объявление уже обработано или не находится на модерации.", {}

    await set_rejection_session(admin_vk_user_id, listing_id)
    return (
        f"❌ Отклонение объявления №{listing_id}\n\n"
        "📝 Напишите причину отклонения одним сообщением.\n"
        "Причина обязательна, минимум 5 символов, максимум 1000.",
        {},
    )


async def reject_listing_for_admin(
    listing_id: int,
    admin_vk_user_id: int,
    reason: str,
    vk: VKClient,
) -> tuple[str, dict[str, Any]]:
    if not settings.can_moderate(admin_vk_user_id):
        return "⛔ У вас нет прав для отклонения объявлений.", {}

    listing = await get_listing(listing_id)
    if listing is None:
        await clear_rejection_session(admin_vk_user_id)
        return "⚠️ Объявление не найдено.", {}

    if listing["status"] != ListingStatus.MODERATION:
        await clear_rejection_session(admin_vk_user_id)
        return "ℹ️ Это объявление уже обработано или не находится на модерации.", {}

    clean_reason = " ".join((reason or "").split())
    if len(clean_reason) < 5:
        return "⚠️ Причина должна содержать минимум 5 символов.", {}
    if len(clean_reason) > 1000:
        return "⚠️ Причина слишком длинная. Максимум 1000 символов.", {}

    seller = await get_user_by_internal_id(int(listing["user_id"]))
    if seller is None:
        return "⚠️ Не удалось определить продавца.", {}

    await update_listing(listing_id, status=ListingStatus.REJECTED)
    await clear_rejection_session(admin_vk_user_id)
    await add_moderation_log(listing_id, admin_vk_user_id, "rejected", clean_reason)
    await add_admin_action_log(
        admin_vk_user_id,
        "listing_rejected",
        target_vk_user_id=int(seller["vk_user_id"]),
        listing_id=listing_id,
        details=clean_reason,
    )

    notified = await _notify_seller(vk, int(seller["vk_user_id"]), f"❌ Объявление №{listing_id} отклонено.\n\nПричина: {clean_reason}")
    if not notified:
        await add_admin_action_log(admin_vk_user_id, "seller_notification_failed", target_vk_user_id=int(seller["vk_user_id"]), listing_id=listing_id, details="rejection notification failed after retry")

    return f"❌ Объявление №{listing_id} отклонено.\nПричина: {clean_reason}", {}


async def handle_rejection_reason(
    admin_vk_user_id: int,
    text: str,
    vk: VKClient,
) -> tuple[str, dict[str, Any]]:
    session = await get_rejection_session(admin_vk_user_id)
    if session is None:
        return "", {}

    if (text or "").strip().lower() in {"отмена", "/cancel", "❌ отмена"}:
        await clear_rejection_session(admin_vk_user_id)
        return "❌ Отклонение отменено.", {}
    listing_id = int(session["listing_id"])
    return await reject_listing_for_admin(listing_id, admin_vk_user_id, text, vk)


async def publish_listing_for_admin(
    listing_id: int,
    admin_vk_user_id: int,
    vk: VKClient,
) -> tuple[str, dict[str, Any]]:
    if not settings.can_moderate(admin_vk_user_id):
        return "⛔ У вас нет прав для публикации объявлений.", {}

    listing = await get_listing(listing_id)
    if listing is None:
        return "⚠️ Объявление не найдено.", {}

    if listing["status"] != ListingStatus.MODERATION:
        return "ℹ️ Это объявление уже обрабатывается или обработано.", {}

    photos = await get_listing_photos(listing_id)
    if not photos:
        return "⚠️ У объявления нет фотографий. Публикация отменена.", {}

    seller = await get_user_by_internal_id(int(listing["user_id"]))
    if seller is None:
        return "⚠️ Не удалось определить продавца.", {}

    # Reserve the listing before calling VK so two moderators cannot publish it twice.
    reserved = await _reserve_for_publication(listing_id)
    if not reserved:
        return "ℹ️ Это объявление уже обрабатывается или обработано.", {}

    attachments = ",".join(str(photo["vk_attachment"]) for photo in photos)
    try:
        post_id = await vk.wall_post(_published_card(listing), attachments=attachments)
    except Exception:
        await update_listing(listing_id, status=ListingStatus.MODERATION, published_post_id=None)
        return "⚠️ Не удалось опубликовать объявление в VK. Оно возвращено на модерацию.", {}

    await update_listing(
        listing_id,
        status=ListingStatus.PUBLISHED,
        published_post_id=post_id,
    )
    await add_moderation_log(listing_id, admin_vk_user_id, "approved")
    await add_admin_action_log(
        admin_vk_user_id,
        "listing_approved",
        target_vk_user_id=int(seller["vk_user_id"]),
        listing_id=listing_id,
        details=f"published_post_id={post_id}",
    )

    notified = await _notify_seller(vk, int(seller["vk_user_id"]), f"✅ Объявление №{listing_id} одобрено и опубликовано.\n\nВаше объявление теперь доступно в группе.")
    if not notified:
        await add_admin_action_log(admin_vk_user_id, "seller_notification_failed", target_vk_user_id=int(seller["vk_user_id"]), listing_id=listing_id, details=f"approval notification failed after retry; published_post_id={post_id}")

    return f"✅ Объявление №{listing_id} одобрено и опубликовано.\nVK post ID: {post_id}", {}


async def _reserve_for_publication(listing_id: int) -> bool:
    from database import execute
    return await execute(
        "UPDATE listings SET status = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND status = ?",
        (ListingStatus.PUBLISHING, listing_id, ListingStatus.MODERATION),
    ) > 0


async def approve_listing_for_admin(
    listing_id: int,
    admin_vk_user_id: int,
    vk: VKClient,
) -> tuple[str, dict[str, Any]]:
    return await publish_listing_for_admin(listing_id, admin_vk_user_id, vk)


async def _get_listing_seller_vk_id(listing: Any) -> int | None:
    # listings.user_id is the internal users.id, not VK ID.
    seller = await get_user_by_internal_id(int(listing["user_id"]))
    return int(seller["vk_user_id"]) if seller else None


async def get_user_by_internal_id(user_id: int):
    from database import fetch_one
    return await fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


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
        seller = await get_user_by_internal_id(int(listing["user_id"]))
        if seller:
            await vk.send_message(
                int(seller["vk_user_id"]),
                f"🗄 Объявление №{listing_id} перемещено в архив администрацией.",
            )
    except Exception:
        pass
    return f"🗄 Объявление №{listing_id} перемещено в архив.", {}


async def restore_listing_for_admin(listing_id: int, admin_vk_user_id: int) -> tuple[str, dict[str, Any]]:
    if not settings.can_moderate(admin_vk_user_id):
        return "⛔ У вас нет прав для восстановления.", {}

    listing = await get_listing(listing_id)
    if listing is None or listing["status"] != ListingStatus.ARCHIVED:
        return "⚠️ Архивное объявление не найдено.", {}

    if not await restore_archived_listing(listing_id):
        return "⚠️ Не удалось восстановить объявление.", {}

    await add_moderation_log(listing_id, admin_vk_user_id, "restored")
    await add_admin_action_log(admin_vk_user_id, "listing_restored", listing_id=listing_id)
    return (
        f"♻️ Объявление №{listing_id} восстановлено.

"
        "Статус: готово к повторной модерации/публикации.",
        {},
    )
