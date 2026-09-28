from __future__ import annotations

import json
from typing import Any


def listing_creation_keyboard() -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": False,
        "buttons": [[
            {
                "action": {
                    "type": "text",
                    "label": "❌ Отмена",
                    "payload": json.dumps({"command": "cancel_listing"}, ensure_ascii=False),
                },
                "color": "secondary",
            }
        ]],
    }

