from __future__ import annotations

from typing import Any

from config import settings
from keyboards.admin import admin_keyboard


async def show_admin_menu(user_id: int) -> tuple[str, dict[str, Any]]:
    role = settings.role_for(user_id)
    if role is None:
        return "⛔ У вас нет доступа к админ-панели.", {}

    role_label = {"owner": "Владелец", "moderator": "Модератор", "support": "Поддержка"}.get(role, role)
    return (
        "⚙️ Админ-панель\n\n"
        f"👤 Роль: {role_label}\n\n"
        "Выберите нужный раздел:",
        admin_keyboard(role),
    )
