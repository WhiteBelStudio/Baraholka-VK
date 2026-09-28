import asyncio
from typing import Any

import aiohttp

from config import settings


class VKAPIError(RuntimeError):
    pass


class VKClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.vk_token
        self.version = settings.vk_api_version
        self.base_url = "https://api.vk.com/method"

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        payload = {**params, "access_token": self.token, "v": self.version}
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/{method}", data=payload) as response:
                    response.raise_for_status()
                    data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise VKAPIError(f"VK API request failed: {exc}") from exc

        if "error" in data:
            error = data["error"]
            raise VKAPIError(f"VK API error {error.get('error_code')}: {error.get('error_msg')}")
        return data.get("response", {})

    async def send_message(self, user_id: int, message: str) -> int:
        result = await self.call("messages.send", peer_id=user_id, random_id=0, message=message)
        return int(result)

    async def wall_post(self, message: str, attachments: str | None = None) -> int:
        params: dict[str, Any] = {
            "owner_id": -settings.vk_group_id,
            "from_group": 1,
            "message": message,
            "random_id": 0,
        }
        if attachments:
            params["attachments"] = attachments
        result = await self.call("wall.post", **params)
        return int(result["post_id"])
