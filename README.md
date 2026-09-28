# Baraholka VK

VK community marketplace bot.

## Configuration

The application is configured through environment variables loaded from `.env`.

1. Copy `.env.example` to `.env`.
2. Set `VK_TOKEN` to the VK community access token.
3. Set `VK_GROUP_ID` to the numeric community ID without the `-` prefix.
4. Set `VK_CONFIRMATION_TOKEN` to the confirmation string configured for VK Callback API.
5. Set `VK_CALLBACK_SECRET` when a callback secret is configured in VK.
6. Add administrator VK user IDs to `ADMIN_IDS`, separated by commas.
7. Adjust `HOST`, `PORT`, `DATABASE_PATH`, and `LOG_LEVEL` only if needed.

Real credentials must stay in `.env`; the repository contains only `.env.example`.

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

Stage 6 (listing system) is complete. The project now has a complete listing data layer and service layer: drafts, ownership checks, CRUD operations, statuses, validation, photos, moderation submission, user listing queries, moderation queue queries, and safe owner-only deletion. The next development stage is the listing creation dialog.
