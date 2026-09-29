from __future__ import annotations

from typing import Any

from database import delete_listing, get_user_listings, update_listing
from keyboards.listings import listing_creation_keyboard, listing_edit_keyboard, listing_preview_keyboard, my_listings_keyboard, listing_detail_keyboard
from services.listings import ListingStatus, create_draft, get_photos, save_draft_field
from states import FIELD_PROMPTS, ListingState

START_BUTTON = "🛍 Подать объявление"
MY_LISTINGS_BUTTON = "📦 Мои объявления"
CANCEL_BUTTON = "❌ Отмена"
PREVIEW_BUTTON = "👀 Предпросмотр"

_EDIT_FIELDS = {"edit_title": (ListingState.TITLE, "title"), "edit_category": (ListingState.CATEGORY, "category"), "edit_description": (ListingState.DESCRIPTION, "description"), "edit_price": (ListingState.PRICE, "price"), "edit_city": (ListingState.CITY, "city")}
_ORDER = (ListingState.TITLE, ListingState.CATEGORY, ListingState.DESCRIPTION, ListingState.PRICE, ListingState.CITY)
_FIELDS = {ListingState.TITLE: "title", ListingState.CATEGORY: "category", ListingState.DESCRIPTION: "description", ListingState.PRICE: "price", ListingState.CITY: "city"}
_STATUS_LABELS = {ListingStatus.DRAFT: "📝 Черновик", ListingStatus.MODERATION: "🟡 На модерации", ListingStatus.APPROVED: "🟢 Одобрено", ListingStatus.REJECTED: "🔴 Отклонено", ListingStatus.PUBLISHED: "📢 Опубликовано", ListingStatus.ARCHIVED: "📦 В архиве", ListingStatus.DELETED: "🗑 Удалено"}


def _next_state(listing: Any) -> ListingState | None:
    for state in _ORDER:
        if not str(listing[state.value] or "").strip():
            return state
    return None


def _cut(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else f"{text[:limit - 1].rstrip()}…"


async def show_my_listings(user_id: int) -> tuple[str, dict[str, Any]]:
    listings = await get_user_listings(user_id)
    visible = [x for x in listings if x["status"] != ListingStatus.DELETED]
    if not visible:
        return "📦 У вас пока нет объявлений.\n\nНажмите «🛍 Подать объявление», чтобы создать первое.", {}
    lines = ["📦 Ваши объявления", ""]
    for item in visible[:20]:
        lines += [f"№{item['id']} · {_STATUS_LABELS.get(item['status'], item['status'])}", f"🛍 {_cut(item['title'] or 'Без названия', 70)}", f"💰 {item['price'] or 'Цена не указана'} ₽ · 📍 {item['city'] or 'Город не указан'}", ""]
    if len(visible) > 20:
        lines.append(f"Показаны последние 20 из {len(visible)} объявлений.")
    return "\n".join(lines).rstrip(), my_listings_keyboard(visible[:20])


async def open_my_listing(user_id: int, listing_id: int) -> tuple[str, dict[str, Any]]:
    listing = next((x for x in await get_user_listings(user_id) if int(x["id"]) == listing_id), None)
    if listing is None or listing["status"] == ListingStatus.DELETED:
        return "⚠️ Объявление не найдено или вам недоступно.", {}
    photos = await get_photos(listing_id)
    text = (f"📦 Объявление №{listing['id']}\n\n🛍 {_cut(listing['title'], 120)}\n🏷 {listing['category']}\n\n📝 {_cut(listing['description'], 700)}\n\n💰 {listing['price']} ₽\n📍 {listing['city']}\n{_STATUS_LABELS.get(listing['status'], listing['status'])}\n📷 Фотографий: {len(photos)}")
    return text, listing_detail_keyboard(listing_id, listing["status"])


async def _draft(user_id: int) -> Any:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if drafts:
        return drafts[0]
    listing_id = await create_draft(user_id)
    return next(x for x in await get_user_listings(user_id, (ListingStatus.DRAFT,)) if int(x["id"]) == listing_id)


async def build_listing_preview(user_id: int) -> tuple[str, dict[str, Any]]:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if not drafts:
        return "Активного черновика нет.", {}
    listing = drafts[0]
    missing = _next_state(listing)
    if missing is not None:
        return f"⚠️ Сначала заполните поле «{missing.value}».\n\n{FIELD_PROMPTS[missing]}", listing_creation_keyboard()
    photos = await get_photos(int(listing["id"]))
    if not photos:
        return "📷 Добавьте хотя бы 1 фотографию для предпросмотра.", listing_creation_keyboard()
    return (f"✨ Предпросмотр объявления\n\n🛍 {_cut(listing['title'], 120)}\n🏷 {listing['category']}\n\n📝 {_cut(listing['description'], 500)}\n\n💰 {listing['price']} ₽\n📍 {listing['city']}\n📷 Фотографий: {len(photos)}/3\n\n🔢 Объявление №{listing['id']}\n\nПроверьте данные перед отправкой.", listing_preview_keyboard())


async def start_listing(user_id: int) -> tuple[str, dict[str, Any]]:
    listing = await _draft(user_id)
    state = _next_state(listing)
    if state is None:
        return await build_listing_preview(user_id)
    return f"🛍 Создание объявления\n\n{FIELD_PROMPTS[state]}\n\nОтправьте одно значение сообщением. В любой момент можно нажать «❌ Отмена».", listing_creation_keyboard()


async def open_listing_editor(user_id: int) -> tuple[str, dict[str, Any]]:
    if not await get_user_listings(user_id, (ListingStatus.DRAFT,)):
        return "Активного черновика нет.", {}
    return "✏️ Редактирование объявления\n\nВыберите поле, которое хотите изменить.", listing_edit_keyboard()


async def select_edit_field(user_id: int, command: str) -> tuple[str, dict[str, Any]]:
    data = _EDIT_FIELDS.get(command)
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if data is None or not drafts:
        return "⚠️ Активного черновика нет.", listing_edit_keyboard()
    state, field = data
    listing = drafts[0]
    await update_listing(int(listing["id"]), editing_field=field)
    return f"✏️ Изменение поля «{state.value}»\n\nТекущее значение:\n{listing[field] or '—'}\n\n{FIELD_PROMPTS[state]}\n\nОтправьте новое значение.", listing_edit_keyboard()


async def handle_listing_message(user_id: int, text: str, attachments: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    text = (text or "").strip()
    if text.lower() in {CANCEL_BUTTON.lower(), "/cancel", "отмена"}:
        return await cancel_listing(user_id)
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if attachments and drafts:
        from services.listings import replace_photos
        await replace_photos(int(drafts[0]["id"]), attachments)
        if not text:
            return await build_listing_preview(user_id)
    if text.lower() == PREVIEW_BUTTON.lower():
        return await build_listing_preview(user_id)
    if not drafts:
        return "Чтобы начать создание объявления, нажмите «🛍 Подать объявление».", {}
    listing = drafts[0]
    editing_field = str(listing["editing_field"] or "").strip()
    if editing_field:
        if not text:
            return "⚠️ Новое значение не может быть пустым.", listing_edit_keyboard()
        try:
            await save_draft_field(int(listing["id"]), editing_field, text)
        except ValueError as exc:
            return f"⚠️ {exc}", listing_edit_keyboard()
        await update_listing(int(listing["id"]), editing_field=None)
        return await build_listing_preview(user_id)
    state = _next_state(listing)
    if state is None:
        return await build_listing_preview(user_id)
    if not text:
        return f"⚠️ Поле не может быть пустым.\n\n{FIELD_PROMPTS[state]}", listing_creation_keyboard()
    try:
        await save_draft_field(int(listing["id"]), _FIELDS[state], text)
    except ValueError as exc:
        return f"⚠️ {exc}\n\n{FIELD_PROMPTS[state]}", listing_creation_keyboard()
    listing = (await get_user_listings(user_id, (ListingStatus.DRAFT,)))[0]
    next_state = _next_state(listing)
    if next_state is None:
        return f"✅ Основные данные объявления №{listing['id']} сохранены.\n\nТеперь добавьте фото и откройте предпросмотр.", listing_creation_keyboard(with_preview=True)
    return f"✅ Сохранено.\n\n{FIELD_PROMPTS[next_state]}", listing_creation_keyboard()


async def cancel_listing(user_id: int) -> tuple[str, dict[str, Any]]:
    drafts = await get_user_listings(user_id, (ListingStatus.DRAFT,))
    if not drafts:
        return "Активного черновика нет.", {}
    await delete_listing(int(drafts[0]["id"]), user_id)
    return "❌ Создание объявления отменено. Черновик удалён.", {}
