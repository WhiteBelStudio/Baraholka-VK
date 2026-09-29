from __future__ import annotations

import json
from typing import Any


def moderation_queue_keyboard(listing_ids: list[int] | None = None) -> dict[str, Any]:
    buttons = []
    for listing_id in listing_ids or []:
        buttons.append([{
            "action": {
                "type": "text",
                "label": f"📄 Открыть №{listing_id}",
                "payload": json.dumps(
                    {"command": "open_moderation", "listing_id": listing_id},
                    ensure_ascii=False,
                ),
            },
            "color": "primary",
        }])
    buttons.append([{
        "action": {
            "type": "text",
            "label": "📊 Статистика",
            "payload": json.dumps({"command": "statistics"}, ensure_ascii=False),
        },
        "color": "secondary",
    }])
    buttons.append([{
        "action": {
            "type": "text",
            "label": "🔄 Обновить очередь",
            "payload": json.dumps({"command": "moderation_queue"}, ensure_ascii=False),
        },
        "color": "secondary",
    }])
    return {"one_time": False, "inline": True, "buttons": buttons}


def moderation_item_keyboard(listing_id: int) -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": True,
        "buttons": [[
            {
                "action": {
                    "type": "text",
                    "label": "🔄 Вернуться к очереди",
                    "payload": json.dumps({"command": "moderation_queue"}, ensure_ascii=False),
                },
                "color": "secondary",
            }
        ]],
    }


def archive_candidates_keyboard(listing_ids: list[int] | None = None) -> dict[str, Any]:
    buttons = []
    for listing_id in listing_ids or []:
        buttons.append([{
            "action": {
                "type": "text",
                "label": f"🗄 Архивировать №{listing_id}",
                "payload": json.dumps({"command": "archive_listing", "listing_id": listing_id}, ensure_ascii=False),
            },
            "color": "secondary",
        }])
    buttons.append([{
        "action": {
            "type": "text",
            "label": "📦 Открыть архив",
            "payload": json.dumps({"command": "archive_list"}, ensure_ascii=False),
        },
        "color": "primary",
    }])
    buttons.append([{
        "action": {
            "type": "text",
            "label": "🔄 Обновить",
            "payload": json.dumps({"command": "archive"}, ensure_ascii=False),
        },
        "color": "secondary",
    }])
    return {"one_time": False, "inline": True, "buttons": buttons}


def archive_keyboard(listing_ids: list[int] | None = None) -> dict[str, Any]:
    buttons = []
    for listing_id in listing_ids or []:
        buttons.append([{
            "action": {
                "type": "text",
                "label": f"📄 Архив №{listing_id}",
                "payload": json.dumps({"command": "open_archived", "listing_id": listing_id}, ensure_ascii=False),
            },
            "color": "primary",
        }])
    buttons.append([{
        "action": {
            "type": "text",
            "label": "🔄 Обновить архив",
            "payload": json.dumps({"command": "archive"}, ensure_ascii=False),
        },
        "color": "secondary",
    }])
    return {"one_time": False, "inline": True, "buttons": buttons}


def archived_listing_keyboard(listing_id: int) -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": True,
        "buttons": [[{
            "action": {
                "type": "text",
                "label": "♻️ Восстановить",
                "payload": json.dumps({"command": "restore_listing", "listing_id": listing_id}, ensure_ascii=False),
            },
            "color": "positive",
        }]],
    }
