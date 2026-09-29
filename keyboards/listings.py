from __future__ import annotations

import json
from typing import Any


def _button(label: str, command: str, color: str) -> dict[str, Any]:
    return {
        "action": {
            "type": "text",
            "label": label,
            "payload": json.dumps({"command": command}, ensure_ascii=False),
        },
        "color": color,
    }


def listing_creation_keyboard(with_preview: bool = False) -> dict[str, Any]:
    buttons = []
    if with_preview:
        buttons.append(_button("👀 Предпросмотр", "listing_preview", "primary"))
    buttons.append(_button("❌ Отмена", "cancel_listing", "secondary"))
    return {
        "one_time": False,
        "inline": False,
        "buttons": [buttons],
    }


def listing_preview_keyboard() -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": False,
        "buttons": [[
            _button("✏️ Изменить", "edit_listing", "secondary"),
            _button("🚀 Отправить на модерацию", "submit_listing", "primary"),
        ], [
            _button("❌ Отмена", "cancel_listing", "secondary"),
        ]],
    }
