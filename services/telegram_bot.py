from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings
from services.broadcasts import CAMPAIGN_LABELS, send_campaign
from services.telegram_storage import init_telegram_storage, unsubscribe_telegram_subscriber, upsert_telegram_subscriber

logger = logging.getLogger(__name__)
router = Router()


class BroadcastFlow(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirmation = State()


def _is_admin(user_id: int) -> bool:
    return settings.role_for_telegram(user_id) in {"owner", "moderator"}


def _campaign_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=CAMPAIGN_LABELS["important"], callback_data="broadcast:type:important")],
        [InlineKeyboardButton(text=CAMPAIGN_LABELS["news"], callback_data="broadcast:type:news")],
        [InlineKeyboardButton(text=CAMPAIGN_LABELS["new_listings"], callback_data="broadcast:type:new_listings")],
        [InlineKeyboardButton(text=CAMPAIGN_LABELS["custom"], callback_data="broadcast:type:custom")],
    ])


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
        ]
    ])


@router.message(CommandStart())
async def start(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    await upsert_telegram_subscriber(user.id, user.username, user.first_name, user.last_name)
    await message.answer(
        "🦆 <b>Добро пожаловать в «Скрудж Макдак»!</b>\n\n"
        "Здесь можно следить за объявлениями барахолки и получать важные новости.\n"
        "Нажимая /start, вы разрешаете боту присылать новости и уведомления. "
        "Отключить их можно командой /stop.\n\n"
        "Размещение объявлений подключим к общей модерации следующим этапом."
    )


@router.message(Command("stop"))
async def stop_notifications(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    changed = await unsubscribe_telegram_subscriber(user.id)
    await message.answer(
        "🔕 Рассылки отключены. Чтобы снова подписаться, отправьте /start."
        if changed else
        "Вы уже отключили рассылки. Для повторной подписки отправьте /start."
    )


@router.message(Command("admin"))
async def admin_menu(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id):
        await message.answer("⛔ Доступ к административной панели закрыт.")
        return
    await state.clear()
    await message.answer(
        "⚙️ <b>Админ-панель «Скрудж Макдак»</b>\n\n"
        "Выберите тип рассылки. Перед отправкой будет показан предпросмотр и запрос подтверждения.",
        reply_markup=_campaign_keyboard(),
    )


@router.callback_query(F.data.startswith("broadcast:type:"))
async def choose_campaign_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    campaign_type = (callback.data or "").split(":")[-1]
    if campaign_type not in CAMPAIGN_LABELS:
        await callback.answer("Неизвестный тип рассылки.", show_alert=True)
        return
    await state.set_state(BroadcastFlow.waiting_for_text)
    await state.update_data(campaign_type=campaign_type)
    if callback.message:
        await callback.message.answer(
            f"Вы выбрали: <b>{CAMPAIGN_LABELS[campaign_type]}</b>\n\n"
            "Отправьте одним сообщением текст рассылки. Он будет сохранён в журнале кампаний."
        )
    await callback.answer()


@router.message(BroadcastFlow.waiting_for_text, F.text)
async def receive_campaign_text(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id):
        await state.clear()
        return
    content = (message.text or "").strip()
    if len(content) < 3:
        await message.answer("Текст слишком короткий. Напишите сообщение длиной не менее 3 символов.")
        return
    if len(content) > 4000:
        await message.answer("Текст слишком длинный. Максимум — 4000 символов.")
        return
    data = await state.get_data()
    campaign_type = data.get("campaign_type", "custom")
    await state.update_data(message_text=content)
    await state.set_state(BroadcastFlow.waiting_for_confirmation)
    await message.answer(
        f"👀 <b>Предпросмотр рассылки</b>\n"
        f"Тип: {CAMPAIGN_LABELS[campaign_type]}\n"
        "Аудитория: подписчики Telegram-бота и активные пользователи VK-бота.\n\n"
        f"{content}\n\n"
        "Запустить отправку?",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_campaign(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.answer("❌ Рассылка отменена.")
    await callback.answer("Отменено")


@router.callback_query(F.data == "broadcast:confirm")
async def confirm_campaign(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    if await state.get_state() != BroadcastFlow.waiting_for_confirmation.state:
        await callback.answer("Нет подготовленной рассылки.", show_alert=True)
        return
    data = await state.get_data()
    campaign_type = data.get("campaign_type", "custom")
    message_text = data.get("message_text", "")
    if not message_text:
        await state.clear()
        await callback.answer("Текст рассылки не найден.", show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.answer("⏳ Рассылка запущена. По завершении пришлю отчёт.")
    await callback.answer("Запускаю")
    try:
        campaign_id, sent, failed = await send_campaign(bot, callback.from_user.id, campaign_type, message_text)
        if callback.message:
            await callback.message.answer(
                f"✅ <b>Рассылка завершена</b>\nКампания №{campaign_id}\n"
                f"Успешно: {sent}\nОшибок: {failed}"
            )
    except Exception:
        logger.exception("Broadcast campaign failed")
        if callback.message:
            await callback.message.answer("⚠️ Рассылка завершилась с ошибкой. Проверьте журнал сервера.")


async def run_telegram_bot() -> None:
    if not settings.telegram_bot_token.strip():
        logger.info("Telegram bot disabled: TELEGRAM_BOT_TOKEN is not configured")
        return

    await init_telegram_storage()
    bot = Bot(
        token=settings.telegram_bot_token.strip(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    try:
        logger.info("Starting Scrooge McDuck Telegram bot polling")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
