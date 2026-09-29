from __future__ import annotations

from config import settings
from database import get_listing, get_listings_by_status
from keyboards.admin import archive_candidates_keyboard, archive_keyboard, archived_listing_keyboard, moderation_item_keyboard, moderation_queue_keyboard
from services.listings import list_moderation_queue


def _is_admin(vk_user_id: int) -> bool:
    return settings.can_moderate(vk_user_id)


async def show_moderation_queue(vk_user_id: int) -> tuple[str, dict]:
    if not _is_admin(vk_user_id):
        return "⛔ У вас нет прав для доступа к очереди модерации.", {}

    listings = await list_moderation_queue()
    if not listings:
        return "🛡 Очередь модерации пуста.", moderation_queue_keyboard()

    lines = [
        "🛡 Очередь модерации",
        "",
        f"Ожидают проверки: {len(listings)}",
        "",
    ]
    for listing in listings:
        title = str(listing["title"]).strip() or "Без названия"
        lines.append(f"• №{listing['id']} — {title} — {listing['price']} ₽")

    lines.extend(["", "Нажмите кнопку ниже, чтобы обновить очередь."])
    return "\n".join(lines), moderation_queue_keyboard([int(item["id"]) for item in listings])


async def open_moderation_listing(
    vk_user_id: int,
    listing_id: int,
) -> tuple[str, dict]:
    if not _is_admin(vk_user_id):
        return "⛔ У вас нет прав для просмотра очереди модерации.", {}

    listing = await get_listing(listing_id)
    if listing is None or listing["status"] != "moderation":
        return "Объявление уже обработано или не найдено.", {}

    text = (
        "📄 Объявление на модерации\n\n"
        f"№{listing['id']}\n"
        f"Название: {listing['title']}\n"
        f"Категория: {listing['category']}\n"
        f"Описание: {listing['description']}\n"
        f"Цена: {listing['price']} ₽\n"
        f"Город: {listing['city']}"
    )
    return text, moderation_item_keyboard(listing_id)


async def show_archive(vk_user_id: int) -> tuple[str, dict]:
    if not _is_admin(vk_user_id):
        return "⛔ У вас нет прав для управления архивом.", {}
    candidates = []
    for status in ("approved", "published", "rejected"):
        candidates.extend(await get_listings_by_status(status))
    archived = await get_listings_by_status("archived")
    lines = ["🗄 Управление архивом", ""]
    if candidates:
        lines.append("Доступны для архивирования:")
        for item in candidates[:20]:
            title = str(item["title"]).strip() or "Без названия"
            lines.append(f"• №{item['id']} — {title} — {item['status']}")
        lines.append("")
    else:
        lines.append("Активных объявлений для архивирования нет.")
        lines.append("")
    lines.append(f"Архивных объявлений: {len(archived)}")
    return "\n".join(lines), archive_candidates_keyboard([int(x["id"]) for x in candidates[:20]])


async def open_archived_listing(vk_user_id: int, listing_id: int) -> tuple[str, dict]:
    if not _is_admin(vk_user_id):
        return "⛔ У вас нет прав для просмотра архива.", {}
    listing = await get_listing(listing_id)
    if listing is None or listing["status"] != "archived":
        return "⚠️ Архивное объявление не найдено.", {}
    text = (
        "🗄 Архивное объявление\n\n"
        f"№{listing['id']}\n"
        f"Название: {listing['title']}\n"
        f"Категория: {listing['category']}\n"
        f"Описание: {listing['description']}\n"
        f"Цена: {listing['price']} ₽\n"
        f"Город: {listing['city']}"
    )
    return text, archived_listing_keyboard(listing_id)


async def show_archived_listings(vk_user_id: int) -> tuple[str, dict]:
    if not _is_admin(vk_user_id):
        return "⛔ У вас нет прав для просмотра архива.", {}
    archived = await get_listings_by_status("archived")
    if not archived:
        return "🗄 Архив объявлений пуст.", archive_keyboard()
    lines = ["🗄 Архив объявлений", "", f"Всего: {len(archived)}", ""]
    for item in archived[:20]:
        title = str(item["title"]).strip() or "Без названия"
        lines.append(f"• №{item['id']} — {title} — {item['price']} ₽")
    return "\n".join(lines), archive_keyboard([int(x["id"]) for x in archived[:20]])
