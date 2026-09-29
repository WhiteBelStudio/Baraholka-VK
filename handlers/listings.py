from __future__ import annotations

from typing import Any

from database import delete_listing, get_user_listings
from keyboards.listings import listing_creation_keyboard, listing_preview_keyboard
from services.listings import ListingStatus, create_draft, get_photos, save_draft_field
from states import FIELD_PROMPTS, ListingState

START_BUTTON = "🛍 Подать объявление"
CANCEL_BUTTON = "❌ Отмена"
PREVIEW_BUTTON = "👀 Предпросмотр"

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


def _cut(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else f"{text[:limit - 1].rstrip()}…"


async def _draft(user_id: int) -> Any:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if drafts:
        return drafts[0]
    listing_id = await create_draft(user_id)
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    return next(item for item in drafts if int(item["id"]) == listing_id)


async def build_listing_preview(user_id: int) -> tuple[str, dict[str, Any]]:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if not drafts:
        return "Активного черновика нет.", {}

    listing = drafts[0]
    missing = _next_state(listing)
    if missing is not None:
        return f"⚠️ Сначала заполните поле «{missing.value}».

{FIELD_PROMPTS[missing]}", listing_creation_keyboard()

    photos = await get_photos(int(listing["id"]))
    if not photos:
        return (
            "📷 Добавьте хотя бы 1 фотографию, чтобы открыть предпросмотр.

"
            "Можно использовать от 1 до 3 фотографий и до 1 видео.",
            listing_creation_keyboard(),
        )

    preview = (
        "✨ Предпросмотр объявления

"
        f"🛍 {_cut(listing['title'], 120)}
"
        f"🏷 {listing['category']}

"
        f"📝 {_cut(listing['description'], 500)}

"
        f"💰 {listing['price']} ₽
"
        f"📍 {listing['city']}
"
        f"📷 Фотографии: {len(photos)}/3
"
        "🎥 Видео: до 1

"
        f"🔢 Объявление №{listing['id']}

"
        "Проверьте данные перед продолжением. В предпросмотре нет декоративных рамок — "
        "только чистая карточка объявления."
    )
    return preview, listing_preview_keyboard()


async def start_listing(user_id: int) -> tuple[str, dict[str, Any]]:
    listing = await _draft(user_id)
    state = _next_state(listing)
    if state is None:
        return await build_listing_preview(user_id)
    return (
        "🛍 Создание объявления

"
        f"{FIELD_PROMPTS[state]}

"
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

    if text.lower() == PREVIEW_BUTTON.lower():
        return await build_listing_preview(user_id)

    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if not drafts:
        return "Чтобы начать создание объявления, нажмите «🛍 Подать объявление».", {}

    listing = drafts[0]
    state = _next_state(listing)
    if state is None:
        return await build_listing_preview(user_id)

    if not text:
        return f"⚠️ Поле не может быть пустым.

{FIELD_PROMPTS[state]}", listing_creation_keyboard()

    try:
        await save_draft_field(int(listing["id"]), _FIELDS[state], text)
    except ValueError as exc:
        return f"⚠️ {exc}

{FIELD_PROMPTS[state]}", listing_creation_keyboard()

    updated = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    listing = updated[0]
    next_state = _next_state(listing)
    if next_state is None:
        return (
            f"✅ Основные данные объявления №{listing['id']} сохранены.

"
            "Теперь добавьте фото, затем можно открыть красивый предпросмотр.
"
            "📷 От 1 до 3 фото · 🎥 до 1 видео",
            listing_creation_keyboard(with_preview=True),
        )

    return f"✅ Сохранено.

{FIELD_PROMPTS[next_state]}", listing_creation_keyboard()
