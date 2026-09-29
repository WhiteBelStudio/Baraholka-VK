from __future__ import annotations

import json
from typing import Any


def moderation_queue_keyboard() -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": True,
        "buttons": [[
            {
                "action": {
                    "type": "text",
                    "label": "🔄 Обновить очередь",
                    "payload": json.dumps({"command": "moderation_queue"}, ensure_ascii=False),
                },
                "color": "primary",
            }
        ]],
    }


def moderation_item_keyboard(listing_id: int) -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": True,
        "buttons": [[
            {
                "action": {
                    "type": "text",
                    "label": f"📄 Открыть объявление №{listing_id}",
                    "payload": json.dumps(
                        {"command": "open_moderation", "listing_id": listing_id},
                        ensure_ascii=False,
                    ),
                },
                "color": "primary",
            }
        ]],
    }
