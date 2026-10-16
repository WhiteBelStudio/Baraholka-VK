# Baraholka VK

Telegram + VK community marketplace bot for «Скрудж Макдак».

## Configuration

The application is configured through environment variables loaded from `.env`.

1. Copy `.env.example` to `.env`.
2. Set `VK_TOKEN` to the VK community access token.
3. Set `VK_GROUP_ID` to the numeric community ID without the `-` prefix.
4. Set `VK_CONFIRMATION_TOKEN` to the confirmation string configured for VK Callback API.
5. Set `VK_CALLBACK_SECRET` when a callback secret is configured in VK.
6. Add administrator VK user IDs to `ADMIN_IDS`, separated by commas.
7. To enable Telegram, set `TELEGRAM_BOT_TOKEN` and configure `TELEGRAM_ADMIN_IDS` / `TELEGRAM_MODERATOR_IDS` with Telegram numeric user IDs.
8. Adjust `HOST`, `PORT`, `DATABASE_PATH`, and `LOG_LEVEL` only if needed.

Real credentials must stay in `.env`; the repository contains only `.env.example`.

Telegram is optional during migration: without `TELEGRAM_BOT_TOKEN`, the existing VK service still starts. Configure the token to enable Telegram polling in the same process.

## Broadcasts

- Telegram users subscribe by sending `/start` and can opt out with `/stop`.
- VK users explicitly subscribe with `/subscribe` and opt out with `/unsubscribe`.
- A Telegram administrator opens `/admin`, chooses a campaign type, enters the text, reviews the preview, and confirms before delivery.
- Campaigns and per-recipient delivery results are recorded in SQLite.

## Project documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)

## Run

```bash
python -m pip install -r requirements.txt
python start.py
```

For Pterodactyl, use `python start.py` as the startup command.

## Configuration requirements

The service refuses to start when required settings are missing or invalid. `VK_TOKEN` and `VK_GROUP_ID` are required.

## Endpoints

- `GET /` — service status.
- `GET /health` — health check.
- `POST /vk/callback` — VK Callback API endpoint.

## Current stage

Stage 8 (product title) is complete. Product names are collected as the first field of the listing dialog, stored in the draft, normalized for excess whitespace, required to contain at least 2 characters, and limited to 120 characters. Invalid titles are rejected with a clear message and the user remains on the title step. The creation flow also has centralized prompts for every listing field.
