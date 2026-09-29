from __future__ import annotations
import json
from typing import Any


def _button(label: str, command: str, color: str = "primary") -> dict[str, Any]:
    return {"action": {"type": "text", "label": label, "payload": json.dumps({"command": command}, ensure_ascii=False)}, "color": color}


def main_keyboard(role: str | None = None) -> dict[str, Any]:
    buttons = [[_button("🛍 Подать объявление", "create_listing")], [_button("📦 Мои объявления", "my_listings", "secondary")]]
    if role in {"owner", "moderator"}:
        buttons.append([_button("🛡 Очередь модерации", "moderation_queue", "secondary")])
    if role == "owner":
        buttons.append([_button("⚙️ Управление", "admin_menu", "secondary")])
    return {"one_time": False, "inline": False, "buttons": buttons}
