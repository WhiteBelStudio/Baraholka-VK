import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from config import settings
from database import init_db
from services.vk import VKClient, VKAPIError

logger = logging.getLogger(__name__)
app = FastAPI(title="Baraholka VK", version="0.2.0")
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
            try:
                await vk.send_message(int(user_id), "Привет! Барахолка VK подключена. 🛍")
            except VKAPIError:
                logger.exception("VK API error while replying to user %s", user_id)

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
