from __future__ import annotations
import json
from typing import Any


def _button(label: str, command: str, color: str = "primary") -> dict[str, Any]:
    return {"action": {"type": "text", "label": label, "payload": json.dumps({"command": command}, ensure_ascii=False)}, "color": color}


def main_keyboard(role: str | None = None) -> dict[str, Any]:
    buttons = [
        [_button("🛍 Подать объявление", "create_listing")],
        [_button("📦 Мои объявления", "my_listings", "secondary")],
        [_button("📋 Правила", "rules", "secondary")],
        [_button("🔎 Поиск объявлений", "search", "secondary")],
        [_button("⚙️ Фильтры", "filter", "secondary")],
    ]
    if role in {"owner", "moderator", "support"}:\n        buttons.append([_button("⚙️ Админ-панель", "admin_panel", "primary")])\n    if role in {"owner", "moderator"}:
        buttons.append([_button("🛡 Очередь модерации", "moderation_queue", "secondary")])
        buttons.append([_button("🗄 Архив", "archive", "secondary")])
    return {"one_time": False, "inline": False, "buttons": buttons}
