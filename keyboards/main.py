from __future__ import annotations
import json
from typing import Any


def _button(label: str, command: str, color: str = "primary") -> dict[str, Any]:
    return {"action": {"type": "text", "label": label, "payload": json.dumps({"command": command}, ensure_ascii=False)}, "color": color}


def main_keyboard(is_admin: bool = False) -> dict[str, Any]:
    buttons = [[_button("🛍 Подать объявление", "create_listing")], [_button("📦 Мои объявления", "my_listings", "secondary")]]
    if is_admin:
        buttons.append([_button("🛡 Очередь модерации", "moderation_queue", "secondary")])
    return {"one_time": False, "inline": False, "buttons": buttons}
