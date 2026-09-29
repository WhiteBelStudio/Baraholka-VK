from __future__ import annotations

import json
from typing import Any


def main_keyboard(is_admin: bool = False) -> dict[str, Any]:
    buttons = [[
        {
            "action": {
                "type": "text",
                "label": "🛍 Подать объявление",
                "payload": json.dumps({"command": "create_listing"}, ensure_ascii=False),
            },
            "color": "primary",
        }
    ]]
    if is_admin:
        buttons.append([{
            "action": {
                "type": "text",
                "label": "🛡 Очередь модерации",
                "payload": json.dumps({"command": "moderation_queue"}, ensure_ascii=False),
            },
            "color": "secondary",
        }])
    return {"one_time": False, "inline": False, "buttons": buttons}
