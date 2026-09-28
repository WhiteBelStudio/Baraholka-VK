# Baraholka VK

VK community marketplace bot. Stage 2 provides the VK API client and Callback API server.

## Run

1. Copy `.env.example` to `.env` and fill in the VK credentials and Callback settings.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Start with `python start.py`.

## Endpoints

- `GET /health` — service health check.
- `POST /vk/callback` — VK Callback API endpoint.

The Callback API endpoint handles VK confirmation requests, validates the configured secret, acknowledges events with `ok`, and currently answers `/start` / `начать` messages.
