import json
import logging
import time
import asyncio

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from config import settings
from database import add_admin_action_log, check_rate_limit, clear_filter_session, clear_search_session, create_or_update_user, get_user_by_vk_id, has_filter_session, has_search_session, init_db, set_user_blocked
from handlers.moderation import open_moderation_listing, show_moderation_queue
from handlers.complaints import (
    cancel_user_complaint,
    handle_complaint_reason,
    open_complaint,
    reject_complaint,
    resolve_complaint,
    show_complaints_queue,
    start_complaint,
)
from handlers.listings import START_BUTTON, MY_LISTINGS_BUTTON, handle_listing_message, open_listing_editor, open_my_listing, select_edit_field, show_my_listings, start_listing
from keyboards.main import main_keyboard
from services.cleanup import cleanup_loop
from services.moderation import submit_listing_for_moderation
from services.rate_limit import check_publication_submission
from services.rules import POLICY_TEXT, RULES_TEXT
from services.search import (
    filter_listings,
    format_filter_results,
    format_search_results,
    parse_filter_input,
    search_listings,
    start_filter,
    start_search,
)
from services.statistics import format_statistics, get_statistics
from services.vk import VKClient, VKAPIError

logger = logging.getLogger(__name__)
app = FastAPI(title="Baraholka VK", version="0.5.3")
vk = VKClient()


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "baraholka-vk"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _payload(message: dict) -> dict:
    raw = message.get("payload")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


@app.post("/vk/callback", response_class=PlainTextResponse)
async def vk_callback(request: Request) -> str:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if settings.vk_callback_secret and payload.get("secret") != settings.vk_callback_secret:
        raise HTTPException(status_code=403, detail="Invalid callback secret")
    if payload.get("type") == "confirmation":
        if not settings.vk_confirmation_token:
            raise HTTPException(status_code=503, detail="Confirmation token is not configured")
        return settings.vk_confirmation_token
    if payload.get("type") != "message_new":
        return "ok"

    obj = payload.get("object") or {}
    message = obj.get("message") or obj
    user_id = message.get("from_id") or message.get("user_id")
    if not user_id:
        return "ok"
    user_id = int(user_id)
    text = (message.get("text") or "").strip()
    data = _payload(message)
    command = str(data.get("command") or "").strip()

    try:
        allowed, retry_after = await check_rate_limit(
            user_id,
            time.time(),
            settings.spam_window_seconds,
            settings.spam_max_messages,
            settings.spam_cooldown_seconds,
        )
        if not allowed:
            await vk.send_message(user_id, f"⚠️ Слишком много сообщений подряд. Попробуйте снова через {retry_after} сек.")
            return "ok"

        if command in {"ban_user", "unban_user"}:
            if not settings.can_manage_users(user_id):
                await vk.send_message(user_id, "⛔ У вас нет прав для этого действия.")
                return "ok"
            target_id = int(data.get("target_vk_user_id", 0) or 0)
            if target_id <= 0 or target_id == user_id:
                await vk.send_message(user_id, "⚠️ Некорректный пользователь.")
                return "ok"
            target = await get_user_by_vk_id(target_id)
            if target is None:
                await vk.send_message(user_id, "⚠️ Пользователь не найден в базе.")
                return "ok"
            want_block = command == "ban_user"
            if bool(target["is_blocked"]) == want_block:
                await vk.send_message(user_id, "ℹ️ Статус пользователя уже такой.")
                return "ok"
            await set_user_blocked(target_id, want_block)
            await add_admin_action_log(user_id, "user_banned" if want_block else "user_unbanned", target_vk_user_id=target_id)
            action = "заблокирован" if want_block else "разблокирован"
            await vk.send_message(user_id, f"✅ Пользователь VK ID {target_id} {action}.")
            return "ok"

        user = await create_or_update_user(user_id, message.get("first_name"), message.get("last_name"))
        current_user = await get_user_by_vk_id(user_id)
        if current_user and current_user["is_blocked"]:
            await vk.send_message(user_id, "Ваш аккаунт заблокирован и не может использовать барахолку.")
            return "ok"

        if command == "search":
            await clear_filter_session(user_id)
            await start_search(user_id)
            await vk.send_message(user_id, "🔎 Введите запрос для поиска: название, категорию, описание, цену или город.")
            return "ok"

        if command == "filter":
            await clear_search_session(user_id)
            await start_filter(user_id)
            await vk.send_message(
                user_id,
                "⚙️ Введите фильтры одной строкой через |\n"
                "Формат: категория | город | от | до\n"
                "Пример: телефоны | Белореченск | 1000 | 30000\n"
                "Если параметр не нужен, поставьте -.",
            )
            return "ok"

        session_handled = False
        if await has_search_session(user_id):
            session_handled = True
            if text.lower() in {"отмена", "/cancel", "❌ отмена"}:
                await clear_search_session(user_id)
                reply, keyboard = "❌ Поиск отменён.", main_keyboard(settings.role_for(user_id))
            else:
                results = await search_listings(text)
                await clear_search_session(user_id)
                reply, keyboard = format_search_results(results, text), main_keyboard(settings.role_for(user_id))
        elif await has_filter_session(user_id):
            session_handled = True
            if text.lower() in {"отмена", "/cancel", "❌ отмена"}:
                await clear_filter_session(user_id)
                reply, keyboard = "❌ Фильтрация отменена.", main_keyboard(settings.role_for(user_id))
            else:
                try:
                    category, city, min_price, max_price = parse_filter_input(text)
                except ValueError as exc:
                    reply, keyboard = f"⚠️ {exc}\n\nФормат: категория | город | от | до\nПример: телефоны | Белореченск | 1000 | 30000", {}
                else:
                    results = await filter_listings(category, city, min_price, max_price)
                    await clear_filter_session(user_id)
                    reply, keyboard = format_filter_results(results, category, city, min_price, max_price), main_keyboard(settings.role_for(user_id))
        elif text.lower() in {"/start", "начать"}:
            await vk.send_message(
                user_id,
                "Привет! Добро пожаловать в Барахолку VK.\n\nЗдесь можно подать объявление на модерацию.",
                keyboard=main_keyboard(settings.role_for(user_id)),
            )
            return "ok"

        if session_handled:
            pass
        elif command == "my_listings" or text == MY_LISTINGS_BUTTON:
            reply, keyboard = await show_my_listings(user)
        elif command == "open_my_listing":
            listing_id = int(data.get("listing_id", 0) or 0)
            reply, keyboard = await open_my_listing(user, listing_id)
        elif command == "start_complaint":
            reply, keyboard = await start_complaint(user, int(data.get("listing_id", 0) or 0))
        elif command == "complaint_reason_mode":
            pending = await handle_complaint_reason(user, "")
            reply, keyboard = "📝 Напишите причину жалобы одним сообщением.", {}
        elif command == "complaints_queue":
            reply, keyboard = await show_complaints_queue(user_id)
        elif command == "open_complaint":
            reply, keyboard = await open_complaint(user_id, int(data.get("complaint_id", 0) or 0))
        elif command == "resolve_complaint":
            reply, keyboard = await resolve_complaint(user_id, int(data.get("complaint_id", 0) or 0))
        elif command == "reject_complaint":
            reply, keyboard = await reject_complaint(user_id, int(data.get("complaint_id", 0) or 0))
        elif command == "cancel_complaint":
            reply, keyboard = await cancel_user_complaint(user, int(data.get("complaint_id", 0) or 0))
            if not keyboard:
                keyboard = main_keyboard(settings.role_for(user_id))
        elif command == "main_menu":
            reply, keyboard = "🏠 Главное меню", main_keyboard(settings.role_for(user_id))
        elif command == "rules" or text == "📋 Правила":
            reply, keyboard = RULES_TEXT, main_keyboard(settings.role_for(user_id))
        elif command == "policy":
            reply, keyboard = POLICY_TEXT, main_keyboard(settings.role_for(user_id))
        elif command == "statistics":
            if not settings.can_moderate(user_id):
                reply, keyboard = "⛔ У вас нет прав для просмотра статистики.", {}
            else:
                stats = await get_statistics()
                reply, keyboard = format_statistics(stats), main_keyboard(settings.role_for(user_id))
        elif command == "moderation_queue" or text == "🛡 Очередь модерации":
            reply, keyboard = await show_moderation_queue(user_id)
        elif command == "open_moderation":
            reply, keyboard = await open_moderation_listing(user_id, int(data.get("listing_id", 0) or 0))
        elif text.lower() == START_BUTTON.lower() or command == "create_listing":
            reply, keyboard = await start_listing(user)
        elif command == "edit_listing" or text == "✏️ Изменить":
            reply, keyboard = await open_listing_editor(user)
        elif command in {"edit_title", "edit_category", "edit_description", "edit_price", "edit_city"}:
            reply, keyboard = await select_edit_field(user, command)
        elif command == "submit_listing" or text == "🚀 Отправить на модерацию":
            allowed, retry_after = await check_publication_submission(user_id)
            if not allowed:
                reply, keyboard = f"⚠️ Лимит публикаций достигнут. Повторите примерно через {retry_after} сек.", {}
            else:
                reply, keyboard = await submit_listing_for_moderation(user_id, vk)
        elif command == "listing_preview" or text == "👀 Предпросмотр":
            reply, keyboard = await handle_listing_message(user, "👀 Предпросмотр")
        elif command == "cancel_listing" or text == "❌ Отмена":
            reply, keyboard = await handle_listing_message(user, "❌ Отмена")
        elif command in {"search", "filter"}:
            reply, keyboard = "", {}
        else:
            complaint_reply, complaint_keyboard = await handle_complaint_reason(user, text)
            if complaint_reply:
                reply, keyboard = complaint_reply, complaint_keyboard
                await vk.send_message(user_id, reply, keyboard=keyboard)
                return "ok"
            attachments = []
            for attachment in message.get("attachments") or []:
                if attachment.get("type") != "photo":
                    continue
                photo = attachment.get("photo") or {}
                owner_id, photo_id, access_key = photo.get("owner_id"), photo.get("id"), photo.get("access_key")
                if owner_id is None or photo_id is None:
                    continue
                value = f"photo{owner_id}_{photo_id}"
                if access_key:
                    value += f"_{access_key}"
                attachments.append(value)
            reply, keyboard = await handle_listing_message(user, text, attachments=attachments)

        if reply:
            await vk.send_message(user_id, reply, keyboard=keyboard)
    except VKAPIError:
        logger.exception("VK API error while processing user %s", user_id)
    except Exception:
        logger.exception("Unexpected callback error for user %s", user_id)
        try:
            await vk.send_message(user_id, "Произошла ошибка. Попробуйте ещё раз.")
        except VKAPIError:
            logger.exception("Failed to send error message to user %s", user_id)
    return "ok"


cleanup_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global cleanup_task
    await init_db()
    cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info("Baraholka VK Callback API initialized")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global cleanup_task
    if cleanup_task is not None:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        cleanup_task = None


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    uvicorn.run(app, host=settings.host, port=settings.port)
