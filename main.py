import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from config import settings
from database import create_or_update_user, get_user_by_vk_id, init_db
from handlers.listings import START_BUTTON, handle_listing_message, start_listing
from keyboards.main import main_keyboard
from services.vk import VKClient, VKAPIError

logger = logging.getLogger(__name__)
app = FastAPI(title="Baraholka VK", version="0.3.0")
vk = VKClient()


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "baraholka-vk"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/vk/callback", response_class=PlainTextResponse)
async def vk_callback(request: Request) -> str:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if settings.vk_callback_secret and payload.get("secret") != settings.vk_callback_secret:
        raise HTTPException(status_code=403, detail="Invalid callback secret")

    event_type = payload.get("type")
    if event_type == "confirmation":
        if not settings.vk_confirmation_token:
            raise HTTPException(status_code=503, detail="Confirmation token is not configured")
        return settings.vk_confirmation_token

    if event_type == "message_new":
        obj = payload.get("object") or {}
        message = obj.get("message") or obj
        user_id = message.get("from_id") or message.get("user_id")
        text = (message.get("text") or "").strip()
        if user_id and text.lower() in {"/start", "начать"}:
            user = await create_or_update_user(
                int(user_id),
                first_name=message.get("first_name"),
                last_name=message.get("last_name"),
            )
            logger.info("Registered VK user %s as local user %s", user_id, user)
            current_user = await get_user_by_vk_id(int(user_id))
            if current_user and current_user["is_blocked"]:
                await vk.send_message(int(user_id), "Ваш аккаунт заблокирован и не может использовать барахолку.")
                return "ok"
            try:
                await vk.send_message(
                    int(user_id),
                    "Привет! Добро пожаловать в Барахолку VK.\n\n"
                    "Здесь можно подать объявление на модерацию.",
                    keyboard=main_keyboard(),
                )
            except VKAPIError:
                logger.exception("VK API error while replying to user %s", user_id)
            return "ok"

        if text.lower() == START_BUTTON.lower():
            try:
                reply, keyboard = await start_listing(int(user_id))
                await vk.send_message(int(user_id), reply, keyboard=keyboard)
            except Exception:
                logger.exception("Failed to start listing dialog for user %s", user_id)
                await vk.send_message(int(user_id), "Не удалось начать создание объявления. Попробуйте ещё раз.")
            return "ok"

        try:
            reply, keyboard = await handle_listing_message(int(user_id), text)
            if reply:
                await vk.send_message(int(user_id), reply, keyboard=keyboard)
        except VKAPIError:
            logger.exception("VK API error while processing listing for user %s", user_id)
        except Exception:
            logger.exception("Unexpected listing dialog error for user %s", user_id)
            await vk.send_message(int(user_id), "Произошла ошибка. Попробуйте ещё раз.") 

    return "ok"


@app.on_event("startup")
async def startup_event() -> None:
    await init_db()
    logger.info("Baraholka VK Callback API initialized")


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    uvicorn.run(app, host=settings.host, port=settings.port)
