from __future__ import annotations

import json
from typing import Any


def _button(label: str, command: str, color: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"command": command}
    if extra:
        payload.update(extra)
    return {
        "action": {"type": "text", "label": label, "payload": json.dumps(payload, ensure_ascii=False)},
        "color": color,
    }


def complaint_confirm_keyboard(listing_id: int, complaint_id: int) -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": False,
        "buttons": [[
            _button("🚨 Отправить жалобу", "complaint_reason_mode", "primary", {"listing_id": listing_id, "complaint_id": complaint_id}),
            _button("❌ Отмена", "cancel_complaint", "secondary", {"listing_id": listing_id, "complaint_id": complaint_id}),
        ]],
    }


def complaints_queue_keyboard(ids: list[int]) -> dict[str, Any]:
    buttons = [[_button(f"🚨 Жалоба №{i}", "open_complaint", "primary", {"complaint_id": i})] for i in ids]
    buttons.append([_button("🔄 Обновить", "complaints_queue", "secondary")])
    return {"one_time": False, "inline": True, "buttons": buttons}


def complaint_admin_keyboard(complaint_id: int) -> dict[str, Any]:
    return {
        "one_time": False,
        "inline": True,
        "buttons": [
            [
                _button("✅ Принять", "resolve_complaint", "positive", {"complaint_id": complaint_id}),
                _button("❌ Отклонить", "reject_complaint", "negative", {"complaint_id": complaint_id}),
            ],
            [_button("⬅️ К жалобам", "complaints_queue", "secondary")],
        ],
    }
