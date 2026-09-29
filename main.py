import json
import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from config import settings
from database import create_or_update_user, get_user_by_vk_id, init_db
from handlers.moderation import open_moderation_listing, show_moderation_queue
from handlers.complaints import handle_complaint_reason, open_complaint, show_complaints_queue, start_complaint
from handlers.listings import START_BUTTON, MY_LISTINGS_BUTTON, handle_listing_message, open_listing_editor, open_my_listing, select_edit_field, show_my_listings, start_listing
from keyboards.main import main_keyboard
from services.moderation import submit_listing_for_moderation
from services.vk import VKClient, VKAPIError

logger = logging.getLogger(__name__)
app = FastAPI(title="Baraholka VK", version="0.5.1")
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
        user = await create_or_update_user(user_id, message.get("first_name"), message.get("last_name"))
        current_user = await get_user_by_vk_id(user_id)
        if current_user and current_user["is_blocked"]:
            await vk.send_message(user_id, "Ваш аккаунт заблокирован и не может использовать барахолку.")
            return "ok"

        if text.lower() in {"/start", "начать"}:
            await vk.send_message(user_id, "Привет! Добро пожаловать в Барахолку VK.\n\nЗдесь можно подать объявление на модерацию.", keyboard=main_keyboard(user_id in settings.administrators))
            return "ok"

        if command == "my_listings" or text == MY_LISTINGS_BUTTON:
            reply, keyboard = await show_my_listings(user)
        elif command == "open_my_listing":
            listing_id = int(data.get("listing_id", 0) or 0)
            reply, keyboard = await open_my_listing(user, listing_id)
        elif command == "start_complaint":
            reply, keyboard = await start_complaint(user, int(data.get("listing_id", 0) or 0))
        elif command == "complaints_queue":
            reply, keyboard = await show_complaints_queue(user_id)
        elif command == "open_complaint":
            reply, keyboard = await open_complaint(user_id, int(data.get("complaint_id", 0) or 0))
        elif command == "cancel_complaint":
            reply, keyboard = "❌ Жалоба отменена.", main_keyboard(user_id in settings.administrators)
        elif command == "main_menu":
            reply, keyboard = "🏠 Главное меню", main_keyboard(user_id in settings.administrators)
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
            reply, keyboard = await submit_listing_for_moderation(user_id, vk)
        elif command == "listing_preview" or text == "👀 Предпросмотр":
            reply, keyboard = await handle_listing_message(user, "👀 Предпросмотр")
        elif command == "cancel_listing" or text == "❌ Отмена":
            reply, keyboard = await handle_listing_message(user, "❌ Отмена")
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


@app.on_event("startup")
async def startup_event() -> None:
    await init_db()
    logger.info("Baraholka VK Callback API initialized")


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    uvicorn.run(app, host=settings.host, port=settings.port)
