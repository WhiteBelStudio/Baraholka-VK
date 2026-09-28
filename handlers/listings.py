from __future__ import annotations

from typing import Any

from database import delete_listing, get_user_listings
from keyboards.listings import listing_creation_keyboard
from services.listings import ListingStatus, create_draft, save_draft_field
from states import FIELD_PROMPTS, ListingState

START_BUTTON = "🛍 Подать объявление"
CANCEL_BUTTON = "❌ Отмена"

_ORDER = (
    ListingState.TITLE,
    ListingState.CATEGORY,
    ListingState.DESCRIPTION,
    ListingState.PRICE,
    ListingState.CITY,
)
_FIELDS = {
    ListingState.TITLE: "title",
    ListingState.CATEGORY: "category",
    ListingState.DESCRIPTION: "description",
    ListingState.PRICE: "price",
    ListingState.CITY: "city",
}


def _next_state(listing: Any) -> ListingState | None:
    for state in _ORDER:
        if not str(listing[state.value] or "").strip():
            return state
    return None


async def _draft(user_id: int) -> Any:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if drafts:
        return drafts[0]
    listing_id = await create_draft(user_id)
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    return next(item for item in drafts if int(item["id"]) == listing_id)


async def start_listing(user_id: int) -> tuple[str, dict[str, Any]]:
    listing = await _draft(user_id)
    state = _next_state(listing)
    if state is None:
        return (
            f"Черновик объявления №{listing['id']} уже заполнен. "
            "Следующий этап — фотографии и предпросмотр.",
            listing_creation_keyboard(),
        )
    return (
        "🛍 Создание объявления\n\n"
        f"{FIELD_PROMPTS[state]}\n\n"
        "Отправьте одно значение сообщением. В любой момент можно нажать «❌ Отмена».",
        listing_creation_keyboard(),
    )


async def cancel_listing(user_id: int) -> tuple[str, dict[str, Any]]:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if not drafts:
        return "Активного черновика нет.", {}
    await delete_listing(int(drafts[0]["id"]), user_id)
    return "❌ Создание объявления отменено. Черновик удалён.", {}


async def handle_listing_message(
    user_id: int,
    text: str,
    attachments: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    text = (text or "").strip()
    if text.lower() in {CANCEL_BUTTON.lower(), "/cancel", "отмена"}:
        return await cancel_listing(user_id)

    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if not drafts:
        return "Чтобы начать создание объявления, нажмите «🛍 Подать объявление».", {}

    listing = drafts[0]
    state = _next_state(listing)
    if state is None:
        return (
            f"Основные данные объявления №{listing['id']} уже заполнены. "
            "Следующий этап — фотографии и предпросмотр.",
            listing_creation_keyboard(),
        )

    if not text:
        return f"⚠️ Поле не может быть пустым.\n\n{FIELD_PROMPTS[state]}", listing_creation_keyboard()

    try:
        await save_draft_field(int(listing["id"]), _FIELDS[state], text)
    except ValueError as exc:
        return f"⚠️ {exc}\n\n{FIELD_PROMPTS[state]}", listing_creation_keyboard()

    updated = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    listing = updated[0]
    next_state = _next_state(listing)
    if next_state is None:
        return (
            f"✅ Основные данные объявления №{listing['id']} сохранены.\n\n"
            "Заполнены: название, категория, описание, цена и город.\n"
            "Следующие этапы: фотографии → предпросмотр → отправка на модерацию.",
            listing_creation_keyboard(),
        )

    return f"✅ Сохранено.\n\n{FIELD_PROMPTS[next_state]}", listing_creation_keyboard()

