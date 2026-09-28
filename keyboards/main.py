from __future__ import annotations

import json
from typing import Any


def main_keyboard() -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": False,
        "buttons": [[
            {
                "action": {
                    "type": "text",
                    "label": "🛍 Подать объявление",
                    "payload": json.dumps({"command": "create_listing"}, ensure_ascii=False),
                },
                "color": "primary",
            }
        ]],
    }

