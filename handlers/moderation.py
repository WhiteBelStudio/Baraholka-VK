from __future__ import annotations

from config import settings
from database import get_listing
from keyboards.admin import moderation_item_keyboard, moderation_queue_keyboard
from services.listings import list_moderation_queue


def _is_admin(vk_user_id: int) -> bool:
    return vk_user_id in settings.administrators


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
