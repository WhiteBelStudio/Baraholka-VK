from __future__ import annotations

import json
from typing import Any


def _button(label: str, command: str, color: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"command": command}
    if extra:
        payload.update(extra)
    return {"action": {"type": "text", "label": label, "payload": json.dumps(payload, ensure_ascii=False)}, "color": color}


def listing_creation_keyboard(with_preview: bool = False) -> dict[str, Any]:
    buttons = []
    if with_preview:
        buttons.append(_button("👀 Предпросмотр", "listing_preview", "primary"))
    buttons.append(_button("❌ Отмена", "cancel_listing", "secondary"))
    return {"one_time": False, "inline": False, "buttons": [buttons]}


def listing_preview_keyboard() -> dict[str, Any]:
    return {"one_time": False, "inline": False, "buttons": [[_button("✏️ Изменить", "edit_listing", "secondary"), _button("🚀 Отправить на модерацию", "submit_listing", "primary")], [_button("❌ Отмена", "cancel_listing", "secondary")]]}


def listing_edit_keyboard() -> dict[str, Any]:
    return {"one_time": False, "inline": False, "buttons": [[_button("📝 Название", "edit_title", "secondary"), _button("🏷 Категория", "edit_category", "secondary")], [_button("📄 Описание", "edit_description", "secondary"), _button("💰 Цена", "edit_price", "secondary")], [_button("📍 Город", "edit_city", "secondary")], [_button("👀 Вернуться к предпросмотру", "listing_preview", "primary")], [_button("❌ Отмена", "cancel_listing", "secondary")]]}


def my_listings_keyboard(listings: list[Any]) -> dict[str, Any]:
    buttons = [[_button(f"№{listing['id']} · {str(listing['title'] or 'Без названия')[:32]}", "open_my_listing", "secondary", {"listing_id": int(listing['id'])})] for listing in listings]
    buttons.append([_button("🏠 Главное меню", "main_menu", "secondary")])
    return {"one_time": False, "inline": False, "buttons": buttons}


def listing_detail_keyboard(listing_id: int, status: str) -> dict[str, Any]:
    buttons = []
    if status == "draft":
        buttons.append([_button("✏️ Редактировать", "edit_listing", "secondary")])
    if status in {"approved", "published", "rejected", "archived"}:
        buttons.append([_button("🗑 Удалить объявление", "delete_my_listing", "negative", {"listing_id": listing_id})])
    buttons.append([_button("⬅️ Мои объявления", "my_listings", "secondary")])
    return {"one_time": False, "inline": False, "buttons": buttons}


def delete_listing_confirm_keyboard(listing_id: int) -> dict[str, Any]:
    return {"one_time": False, "inline": False, "buttons": [[_button("🗑 Да, удалить", "confirm_delete_my_listing", "negative", {"listing_id": listing_id}), _button("↩️ Отмена", "cancel_delete_my_listing", "secondary", {"listing_id": listing_id})]]}
