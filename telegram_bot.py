from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import settings
from database import (
    execute,
    fetch_all,
    fetch_one,
    get_listing,
    get_listing_photos,
    get_listings_by_status,
    update_listing,
)
from services.listings import (
    ListingData,
    ListingValidationError,
    validate_category,
    validate_city,
    validate_description,
    validate_price,
    validate_title,
    validate_listing,
)
from services.vk import VKAPIError, VKClient
from telegram_store import (
    create_broadcast_campaign,
    create_telegram_listing,
    finish_broadcast_campaign,
    finish_telegram_publication,
    get_telegram_broadcast_recipients,
    get_vk_broadcast_recipients,
    get_telegram_listing,
    get_telegram_listings_by_status,
    get_telegram_statistics,
    get_telegram_user_listings,
    init_telegram_schema,
    log_cross_platform_action,
    record_broadcast_delivery,
    reject_telegram_listing,
    set_news_subscription,
    transition_telegram_listing,
    upsert_telegram_user,
)

logger = logging.getLogger(__name__)
router = Router()


class ListingForm(StatesGroup):
    title = State()
    category = State()
    description = State()
    price = State()
    city = State()
    photos = State()


class RejectionForm(StatesGroup):
    reason = State()


class BroadcastForm(StatesGroup):
    message = State()


def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛍 Подать объявление"), KeyboardButton(text="📦 Мои объявления")],
        [KeyboardButton(text="🔔 Новости"), KeyboardButton(text="🔕 Отключить новости")],
    ]
    if settings.telegram_can_moderate(user_id):
        rows.append([KeyboardButton(text="🛡 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="Выберите действие")


def listing_actions(platform: str, listing_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить и опубликовать", callback_data=f"sc:approve:{platform}:{listing_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"sc:reject:{platform}:{listing_id}"),
        ],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Очередь объявлений", callback_data="sc:queue")],
        [InlineKeyboardButton(text="📣 Создать рассылку", callback_data="sc:broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="sc:stats")],
    ])


def broadcast_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 Важная новость", callback_data="sc:btype:important")],
        [InlineKeyboardButton(text="📣 Обычная новость", callback_data="sc:btype:news")],
        [InlineKeyboardButton(text="🛍 Новость о товаре", callback_data="sc:btype:listing")],
    ])


def broadcast_platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram", callback_data="sc:bplatform:telegram")],
        [InlineKeyboardButton(text="ВКонтакте", callback_data="sc:bplatform:vk")],
        [InlineKeyboardButton(text="Telegram + ВКонтакте", callback_data="sc:bplatform:both")],
    ])


def _listing_text(listing: Any, platform: str) -> str:
    prefix = "Telegram" if platform == "telegram" else "ВКонтакте"
    photos = listing.get("photo_file_ids", "[]") if isinstance(listing, dict) else "[]"
    if platform == "telegram":
        try:
            photo_count = len(json.loads(photos or "[]"))
        except (TypeError, ValueError):
            photo_count = 0
    else:
        photo_count = 0
    return (
        f"🆕 Объявление №{listing['id']} · {prefix}\n\n"
        f"🛍 {listing['title']}\n"
        f"🏷 {listing['category']}\n"
        f"📝 {listing['description']}\n\n"
        f"💰 {listing['price']} ₽\n"
        f"📍 {listing['city']}\n"
        + (f"📷 Фото: {photo_count}\n" if platform == "telegram" else "")
        + f"👤 Продавец ID: {listing['telegram_user_id'] if platform == 'telegram' else listing['user_id']}"
    )


def _published_text(listing: Any, platform: str) -> str:
    seller = (
        f"@{listing['username']}" if platform == "telegram" and listing.get("username")
        else str(listing["telegram_user_id"]) if platform == "telegram"
        else str(listing["vk_user_id"])
    )
    return (
        f"🦆 СКРУДЖ МАКДАК — БАРАХОЛКА\n\n"
        f"🛍 {listing['title']}\n"
        f"🏷 Категория: {listing['category']}\n"
        f"📝 {listing['description']}\n\n"
        f"💰 Цена: {listing['price']} ₽\n"
        f"📍 Город: {listing['city']}\n"
        f"✉️ Продавец: {seller}"
    )


async def _notify_telegram_admins(bot: Bot, listing_id: int) -> None:
    listing = await get_telegram_listing(listing_id)
    if listing is None:
        return
    for admin_id in settings.telegram_administrators:
        try:
            await bot.send_message(
                admin_id,
                _listing_text(dict(listing), "telegram"),
                reply_markup=listing_actions("telegram", listing_id),
            )
        except TelegramAPIError:
            logger.warning("Could not notify Telegram admin %s about listing %s", admin_id, listing_id)


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    user = message.from_user
    await upsert_telegram_user(user.id, user.username, user.first_name, user.last_name)
    await message.answer(
        "🦆 Добро пожаловать в «Скрудж Макдак»!\n\n"
        "Создавайте объявления, находите товары и следите за новостями барахолки. "
        "Объявления публикуются после проверки администрацией.",
        reply_markup=main_keyboard(user.id),
    )


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user:
        await message.answer("Действие отменено.", reply_markup=main_keyboard(message.from_user.id))


@router.message(F.text.in_({"🛍 Подать объявление", "/new"}))
async def new_listing_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ListingForm.title)
    await message.answer("🛍 Создание объявления\n\nШаг 1 из 6. Напишите название товара (2–120 символов). Для отмены: /cancel")


@router.message(ListingForm.title)
async def listing_title_handler(message: Message, state: FSMContext) -> None:
    try:
        value = validate_title(message.text or "")
    except ListingValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(title=value)
    await state.set_state(ListingForm.category)
    await message.answer("Шаг 2 из 6. Укажите категорию товара.")


@router.message(ListingForm.category)
async def listing_category_handler(message: Message, state: FSMContext) -> None:
    try:
        value = validate_category(message.text or "")
    except ListingValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(category=value)
    await state.set_state(ListingForm.description)
    await message.answer("Шаг 3 из 6. Опишите товар (10–4000 символов).")


@router.message(ListingForm.description)
async def listing_description_handler(message: Message, state: FSMContext) -> None:
    try:
        value = validate_description(message.text or "")
    except ListingValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(description=value)
    await state.set_state(ListingForm.price)
    await message.answer("Шаг 4 из 6. Укажите цену в рублях, например 1500 или 1500,50.")


@router.message(ListingForm.price)
async def listing_price_handler(message: Message, state: FSMContext) -> None:
    try:
        value = validate_price(message.text or "")
    except ListingValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(price=value)
    await state.set_state(ListingForm.city)
    await message.answer("Шаг 5 из 6. Укажите город.")


@router.message(ListingForm.city)
async def listing_city_handler(message: Message, state: FSMContext) -> None:
    try:
        city = validate_city(message.text or "")
    except ListingValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(city=city, photo_file_ids=[])
    await state.set_state(ListingForm.photos)
    await message.answer(
        "Шаг 6 из 6. Отправьте от 1 до 5 фотографий товара по одной. "
        "Когда закончите, напишите «Готово». Для отмены: /cancel."
    )


@router.message(ListingForm.photos, F.photo)
async def listing_photo_handler(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photo_file_ids", [])
    if len(photos) >= 5:
        await message.answer("Можно добавить максимум 5 фотографий. Напишите «Готово», чтобы отправить объявление.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photo_file_ids=photos)
    await message.answer(f"Фото добавлено: {len(photos)}/5. Отправьте ещё или напишите «Готово».")


@router.message(ListingForm.photos, F.text.casefold() == "готово")
async def listing_finish_handler(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photo_file_ids", [])
    if not photos:
        await message.answer("Добавьте хотя бы одну фотографию перед отправкой.")
        return
    try:
        validated = validate_listing(ListingData(
            title=data["title"],
            category=data["category"],
            description=data["description"],
            price=data["price"],
            city=data["city"],
        ))
        payload = {
            "title": validated.title,
            "category": validated.category,
            "description": validated.description,
            "price": validated.price,
            "city": validated.city,
            "photo_file_ids": photos[:5],
        }
        listing_id = await create_telegram_listing(message.from_user.id, payload)
    except (KeyError, ListingValidationError, RuntimeError):
        logger.exception("Failed to save Telegram listing for user %s", message.from_user.id)
        await message.answer("Не удалось сохранить объявление. Попробуйте начать заново через /new.")
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ Объявление №{listing_id} отправлено на модерацию.\n"
        "Мы сообщим вам о результате проверки.",
        reply_markup=main_keyboard(message.from_user.id),
    )
    await _notify_telegram_admins(bot, listing_id)


@router.message(F.text == "📦 Мои объявления")
async def my_listings_handler(message: Message) -> None:
    if not message.from_user:
        return
    listings = await get_telegram_user_listings(message.from_user.id)
    if not listings:
        await message.answer("У вас пока нет объявлений. Нажмите «🛍 Подать объявление».")
        return
    labels = {
        "moderation": "🟡 На модерации",
        "publishing": "⏳ Публикуется",
        "published": "🟢 Опубликовано",
        "rejected": "🔴 Отклонено",
        "archived": "📦 Архив",
        "deleted": "🗑 Удалено",
    }
    lines = ["📦 Ваши объявления:"]
    for item in listings:
        lines.append(f"\n№{item['id']} · {labels.get(item['status'], item['status'])}\n{item['title']} · {item['price']} ₽")
        if item["status"] == "rejected" and item["rejection_reason"]:
            lines.append(f"Причина: {item['rejection_reason']}")
    await message.answer("\n".join(lines))


@router.message(F.text == "🔕 Отключить новости")
async def unsubscribe_handler(message: Message) -> None:
    if message.from_user:
        await set_news_subscription(message.from_user.id, False)
        await message.answer("🔕 Рассылка новостей отключена. Включить её снова можно кнопкой «🔔 Новости».")


@router.message(F.text == "🔔 Новости")
async def subscribe_handler(message: Message) -> None:
    if message.from_user:
        await set_news_subscription(message.from_user.id, True)
        await message.answer("🔔 Вы подписаны на новости «Скрудж Макдак».")


@router.message(F.text == "🛡 Админ-панель")
@router.message(Command("admin"))
async def admin_panel_handler(message: Message) -> None:
    if not message.from_user or not settings.telegram_can_moderate(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к административной панели.")
        return
    await message.answer("🛡 «Скрудж Макдак» — административная панель", reply_markup=admin_keyboard())


@router.callback_query(F.data == "sc:queue")
async def queue_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    vk_rows = await get_listings_by_status("moderation")
    tg_rows = await get_telegram_listings_by_status("moderation")
    total = len(vk_rows) + len(tg_rows)
    await callback.message.answer(f"📥 Очередь модерации: {total} объявлений.")
    for listing in tg_rows:
        await callback.message.answer(
            _listing_text(dict(listing), "telegram"),
            reply_markup=listing_actions("telegram", int(listing["id"])),
        )
    for listing in vk_rows:
        seller = await fetch_one("SELECT vk_user_id FROM users WHERE id = ?", (int(listing["user_id"]),))
        row = dict(listing)
        row["vk_user_id"] = int(seller["vk_user_id"]) if seller else 0
        await callback.message.answer(
            _listing_text(row, "vk"),
            reply_markup=listing_actions("vk", int(listing["id"])),
        )


async def _publish_telegram_listing(bot: Bot, listing_id: int, admin_id: int) -> str:
    channel = settings.telegram_channel_id.strip()
    if not channel:
        return "Публикация не выполнена: задайте TELEGRAM_CHANNEL_ID в .env."
    listing = await get_telegram_listing(listing_id)
    if listing is None or listing["status"] != "moderation":
        return "Объявление не найдено или уже обработано."
    if not await transition_telegram_listing(listing_id, "moderation", "publishing"):
        return "Объявление уже обрабатывается другим администратором."
    data = dict(listing)
    photos = json.loads(data.get("photo_file_ids") or "[]")
    if not photos:
        await transition_telegram_listing(listing_id, "publishing", "moderation")
        return "У объявления нет фотографий. Оно возвращено в очередь."
    user = await fetch_one("SELECT username FROM telegram_users WHERE telegram_user_id = ?", (int(data["telegram_user_id"]),))
    data["username"] = user["username"] if user else None
    caption = _published_text(data, "telegram")
    try:
        if len(photos) == 1:
            sent = await bot.send_photo(channel, photo=photos[0], caption=caption)
            message_id = sent.message_id
        else:
            media = [
                InputMediaPhoto(media=photo, caption=caption if index == 0 else None)
                for index, photo in enumerate(photos[:5])
            ]
            sent_messages = await bot.send_media_group(channel, media=media)
            message_id = sent_messages[0].message_id
    except TelegramAPIError as exc:
        await transition_telegram_listing(listing_id, "publishing", "moderation")
        logger.warning("Telegram publication failed for listing %s: %s", listing_id, exc)
        return "Не удалось опубликовать в Telegram-канале. Объявление возвращено в очередь."
    await finish_telegram_publication(listing_id, message_id)
    await log_cross_platform_action("telegram", admin_id, "listing_published", "telegram", listing_id)
    try:
        await bot.send_message(int(data["telegram_user_id"]), f"✅ Ваше объявление №{listing_id} опубликовано в барахолке!")
    except TelegramAPIError:
        logger.info("Could not notify Telegram seller for listing %s", listing_id)
    return f"✅ Объявление Telegram №{listing_id} опубликовано."


async def _publish_vk_listing(bot: Bot, listing_id: int, admin_id: int) -> str:
    listing = await get_listing(listing_id)
    if listing is None or listing["status"] != "moderation":
        return "VK-объявление не найдено или уже обработано."
    photos = await get_listing_photos(listing_id)
    if not photos:
        return "У VK-объявления нет фотографий. Публикация отменена."
    reserved = await execute(
        "UPDATE listings SET status = 'publishing', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'moderation'",
        (listing_id,),
    )
    if reserved != 1:
        return "VK-объявление уже обрабатывается другим администратором."
    vk = VKClient()
    attachments = ",".join(str(photo["vk_attachment"]) for photo in photos)
    text = (
        f"🦆 СКРУДЖ МАКДАК — БАРАХОЛКА\n\n"
        f"🛍 {listing['title']}\n🏷 {listing['category']}\n\n"
        f"📝 {listing['description']}\n\n💰 {listing['price']} ₽\n📍 {listing['city']}"
    )
    try:
        post_id = await vk.wall_post(text, attachments=attachments)
    except (VKAPIError, Exception) as exc:
        await update_listing(listing_id, status="moderation", published_post_id=None)
        logger.warning("VK publication failed for listing %s: %s", listing_id, exc)
        return "Не удалось опубликовать в VK. Объявление возвращено в очередь."
    await update_listing(listing_id, status="published", published_post_id=post_id)
    await log_cross_platform_action("telegram", admin_id, "listing_published", "vk", listing_id, f"post_id={post_id}")
    seller = await fetch_one("SELECT vk_user_id FROM users WHERE id = ?", (int(listing["user_id"]),))
    if seller:
        try:
            await vk.send_message(int(seller["vk_user_id"]), f"✅ Объявление №{listing_id} одобрено и опубликовано в сообществе.")
        except VKAPIError:
            logger.info("Could not notify VK seller for listing %s", listing_id)
    return f"✅ Объявление VK №{listing_id} опубликовано. ID записи: {post_id}"


@router.callback_query(F.data.startswith("sc:approve:"))
async def approve_handler(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer("Обрабатываю объявление…")
    _, _, platform, raw_id = callback.data.split(":", 3)
    try:
        listing_id = int(raw_id)
        if platform == "telegram":
            result = await _publish_telegram_listing(bot, listing_id, callback.from_user.id)
        elif platform == "vk":
            result = await _publish_vk_listing(bot, listing_id, callback.from_user.id)
        else:
            result = "Неизвестная платформа объявления."
    except (ValueError, KeyError, json.JSONDecodeError):
        logger.exception("Invalid approval callback data: %s", callback.data)
        result = "Некорректные данные объявления."
    await callback.message.answer(result)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass


@router.callback_query(F.data.startswith("sc:reject:"))
async def reject_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, platform, raw_id = callback.data.split(":", 3)
    try:
        listing_id = int(raw_id)
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return
    await state.update_data(reject_platform=platform, reject_listing_id=listing_id)
    await state.set_state(RejectionForm.reason)
    await callback.answer()
    await callback.message.answer("Напишите причину отклонения (от 5 до 1000 символов). Для отмены: /cancel.")


@router.message(RejectionForm.reason)
async def reject_reason_handler(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not settings.telegram_can_moderate(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Нет доступа.")
        return
    reason = " ".join((message.text or "").split())
    if reason.lower() == "/cancel":
        await state.clear()
        await message.answer("Отклонение отменено.")
        return
    if not 5 <= len(reason) <= 1000:
        await message.answer("Причина должна содержать от 5 до 1000 символов.")
        return
    data = await state.get_data()
    platform = data.get("reject_platform")
    listing_id = int(data.get("reject_listing_id", 0))
    if platform == "telegram":
        listing = await get_telegram_listing(listing_id)
        if listing is None or not await reject_telegram_listing(listing_id, reason):
            result = "Объявление не найдено или уже обработано."
        else:
            await log_cross_platform_action("telegram", message.from_user.id, "listing_rejected", "telegram", listing_id, reason)
            try:
                await bot.send_message(int(listing["telegram_user_id"]), f"❌ Объявление №{listing_id} отклонено.\nПричина: {reason}")
            except TelegramAPIError:
                pass
            result = f"Объявление Telegram №{listing_id} отклонено."
    elif platform == "vk":
        listing = await get_listing(listing_id)
        if listing is None or listing["status"] != "moderation":
            result = "Объявление VK не найдено или уже обработано."
        else:
            changed = await execute(
                "UPDATE listings SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'moderation'",
                (listing_id,),
            )
            if changed != 1:
                result = "Объявление VK уже обработано другим администратором."
            else:
                await log_cross_platform_action("telegram", message.from_user.id, "listing_rejected", "vk", listing_id, reason)
                seller = await fetch_one("SELECT vk_user_id FROM users WHERE id = ?", (int(listing["user_id"]),))
                if seller:
                    try:
                        await VKClient().send_message(int(seller["vk_user_id"]), f"❌ Объявление №{listing_id} отклонено.\nПричина: {reason}")
                    except VKAPIError:
                        pass
                result = f"Объявление VK №{listing_id} отклонено."
    else:
        result = "Неизвестная платформа объявления."
    await state.clear()
    await message.answer(result, reply_markup=main_keyboard(message.from_user.id))


@router.callback_query(F.data == "sc:broadcast")
async def broadcast_start_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer("Выберите тип рассылки:", reply_markup=broadcast_type_keyboard())


@router.callback_query(F.data.startswith("sc:btype:"))
async def broadcast_type_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    message_type = callback.data.rsplit(":", 1)[-1]
    await state.update_data(broadcast_type=message_type)
    await state.set_state(BroadcastForm.message)
    await callback.answer()
    await callback.message.answer("Отправьте текст сообщения для рассылки. Для отмены: /cancel.")


@router.message(BroadcastForm.message)
async def broadcast_message_handler(message: Message, state: FSMContext) -> None:
    if not message.from_user or not settings.telegram_can_moderate(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Нет доступа.")
        return
    text = (message.text or "").strip()
    if text.lower() == "/cancel":
        await state.clear()
        await message.answer("Создание рассылки отменено.")
        return
    if not text or len(text) > 4000:
        await message.answer("Текст должен содержать от 1 до 4000 символов.")
        return
    await state.update_data(broadcast_text=text)
    await message.answer("Выберите, куда отправить рассылку:", reply_markup=broadcast_platform_keyboard())


@router.callback_query(F.data.startswith("sc:bplatform:"))
async def broadcast_send_handler(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    platform = callback.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    text = str(data.get("broadcast_text") or "").strip()
    message_type = str(data.get("broadcast_type") or "news")
    if not text:
        await callback.answer("Текст рассылки не найден. Создайте её заново.", show_alert=True)
        await state.clear()
        return
    if platform not in {"telegram", "vk", "both"}:
        await callback.answer("Неизвестная платформа", show_alert=True)
        return
    await callback.answer("Запускаю рассылку…")
    campaign_id = await create_broadcast_campaign(callback.from_user.id, message_type, text, platform)
    sent_count = 0
    failed_count = 0
    prefix = {"important": "🚨 ВАЖНАЯ НОВОСТЬ", "news": "📣 НОВОСТИ БАРАХОЛКИ", "listing": "🛍 НОВОСТЬ О ТОВАРЕ"}.get(message_type, "📣 НОВОСТИ БАРАХОЛКИ")
    payload = f"{prefix}\n\n{text}\n\n🦆 Скрудж Макдак"
    if platform in {"telegram", "both"}:
        recipients = await get_telegram_broadcast_recipients()
        for recipient_id in recipients:
            try:
                await bot.send_message(recipient_id, payload)
                await record_broadcast_delivery(campaign_id, "telegram", recipient_id, "sent")
                sent_count += 1
            except TelegramAPIError as exc:
                await record_broadcast_delivery(campaign_id, "telegram", recipient_id, "failed", str(exc))
                failed_count += 1
            await asyncio.sleep(0.04)
    if platform in {"vk", "both"}:
        recipients = await get_vk_broadcast_recipients()
        vk = VKClient()
        for recipient_id in recipients:
            recipient_id = int(recipient_id)
            try:
                await vk.send_message(recipient_id, payload)
                await record_broadcast_delivery(campaign_id, "vk", recipient_id, "sent")
                sent_count += 1
            except Exception as exc:
                await record_broadcast_delivery(campaign_id, "vk", recipient_id, "failed", str(exc))
                failed_count += 1
            await asyncio.sleep(0.04)
    await finish_broadcast_campaign(campaign_id, sent_count, failed_count)
    await state.clear()
    await callback.message.answer(
        f"✅ Рассылка №{campaign_id} завершена.\n📨 Доставлено: {sent_count}\n⚠️ Ошибок доставки: {failed_count}",
        reply_markup=main_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "sc:stats")
async def stats_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not settings.telegram_can_moderate(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    tg_stats = await get_telegram_statistics()
    vk_pending = len(await get_listings_by_status("moderation"))
    await callback.message.answer(
        "📊 Статистика «Скрудж Макдак»\n\n"
        f"👤 Telegram-пользователей: {tg_stats['users']}\n"
        f"🔔 Подписаны на новости: {tg_stats['subscribed']}\n"
        f"🟡 Объявлений Telegram на модерации: {tg_stats['pending']}\n"
        f"🟡 Объявлений VK на модерации: {vk_pending}"
    )


async def start_telegram_bot() -> None:
    if not settings.telegram_bot_token.strip():
        logger.info("Telegram bot disabled: TELEGRAM_BOT_TOKEN is empty")
        return
    await init_telegram_schema()
    bot = Bot(token=settings.telegram_bot_token.strip())
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    try:
        logger.info("Starting Scrooge McDuck Telegram bot polling")
        await dispatcher.start_polling(bot, close_bot_session=True)
    except asyncio.CancelledError:
        logger.info("Telegram bot polling cancelled")
        raise
    except Exception:
        logger.exception("Telegram bot stopped unexpectedly")
        raise
