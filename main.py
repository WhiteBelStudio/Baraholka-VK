import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from config import settings
from database import init_db
from services.vk import VKClient

logger = logging.getLogger(__name__)
app = FastAPI(title="Baraholka VK", version="0.1.0")
vk = VKClient()

@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "baraholka-vk"}

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/vk/callback")
async def vk_callback(request: Request):
    payload = await request.json()
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
        if user_id and text == "/start":
            await vk.send_message(int(user_id), "Привет! Барахолка VK подключена. 🛍")
    return "ok"

@app.on_event("startup")
async def startup_event() -> None:
    await init_db()
    logger.info("Baraholka VK API/Callback server initialized")

if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    uvicorn.run(app, host=settings.host, port=settings.port)
