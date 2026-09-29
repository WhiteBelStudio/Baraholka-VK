from __future__ import annotations

from typing import Any

from database import (
    cancel_complaint,
    complaint_exists_for_user,
    create_complaint,
    finish_complaint,
    get_complaint,
    get_pending_complaint,
    get_pending_complaints,
    get_listing,
    update_complaint_status,
)
from keyboards.complaints import complaint_confirm_keyboard
from services.listings import ListingStatus

REPORTABLE_STATUSES = {ListingStatus.APPROVED, ListingStatus.PUBLISHED, ListingStatus.ARCHIVED}


def _is_admin(user_id: int) -> bool:
    from config import settings
    return settings.can_moderate(user_id)


async def start_complaint(user_id: int, listing_id: int) -> tuple[str, dict[str, Any]]:
    listing = await get_listing(listing_id)
    if listing is None or listing["status"] not in REPORTABLE_STATUSES:
        return "⚠️ Это объявление недоступно для жалобы.", {}
    if int(listing["user_id"]) == user_id:
        return "⚠️ Нельзя пожаловаться на собственное объявление.", {}
    if await complaint_exists_for_user(listing_id, user_id):
        return "ℹ️ Вы уже отправляли жалобу на это объявление.", {}
    complaint_id = await create_complaint(listing_id, user_id)
    return (
        f"🚨 Жалоба на объявление №{listing_id}\n\n"
        "Опишите причину жалобы одним сообщением.\n"
        "Минимум 5 символов, максимум 1000.",
        complaint_confirm_keyboard(listing_id, complaint_id),
    )


async def handle_complaint_reason(user_id: int, text: str) -> tuple[str, dict[str, Any]]:
    pending = await get_pending_complaint(user_id)
    if pending is None:
        return "", {}
    reason = " ".join((text or "").split())
    if len(reason) < 5:
        return (
            "⚠️ Причина должна содержать минимум 5 символов. Опишите проблему подробнее.",
            complaint_confirm_keyboard(int(pending["listing_id"]), int(pending["id"])),
        )
    if len(reason) > 1000:
        return (
            "⚠️ Причина слишком длинная. Максимум 1000 символов.",
            complaint_confirm_keyboard(int(pending["listing_id"]), int(pending["id"])),
        )
    if await finish_complaint(int(pending["id"]), user_id, reason):
        return f"✅ Жалоба №{pending['id']} отправлена администрации на рассмотрение.", {}
    return "⚠️ Не удалось отправить жалобу. Попробуйте ещё раз.", {}


async def cancel_user_complaint(user_id: int, complaint_id: int | None = None) -> tuple[str, dict[str, Any]]:
    pending = await get_pending_complaint(user_id)
    if pending is None:
        return "ℹ️ Активной жалобы нет.", {}
    if complaint_id is not None and int(pending["id"]) != complaint_id:
        return "⚠️ Жалоба не найдена.", {}
    if not await cancel_complaint(int(pending["id"]), user_id):
        return "⚠️ Не удалось отменить жалобу. Попробуйте ещё раз.", {}
    return "❌ Жалоба отменена.", {}


async def show_complaints_queue(admin_id: int) -> tuple[str, dict[str, Any]]:
    from keyboards.complaints import complaints_queue_keyboard
    if not _is_admin(admin_id):
        return "⛔ Недостаточно прав.", {}
    complaints = await get_pending_complaints()
    if not complaints:
        return "🚨 Жалоб на рассмотрении нет.", complaints_queue_keyboard([])
    lines = ["🚨 Жалобы на объявления", ""]
    for c in complaints[:30]:
        lines += [
            f"№{c['id']} · объявление №{c['listing_id']}",
            f"🛍 {c['title']}",
            f"📝 {c['reason']}",
            "",
        ]
    return "\n".join(lines).rstrip(), complaints_queue_keyboard([int(c["id"]) for c in complaints[:30]])


async def open_complaint(admin_id: int, complaint_id: int) -> tuple[str, dict[str, Any]]:
    from keyboards.complaints import complaint_admin_keyboard
    if not _is_admin(admin_id):
        return "⛔ Недостаточно прав.", {}
    complaint = await get_complaint(complaint_id)
    if complaint is None:
        return "⚠️ Жалоба не найдена.", {}
    status = str(complaint["status"])
    status_label = {"pending": "на рассмотрении", "resolved": "принята", "rejected": "отклонена"}.get(status, status)
    text = (
        f"🚨 Жалоба №{complaint['id']}\n\n"
        f"Объявление №{complaint['listing_id']}\n"
        f"Причина: {complaint['reason']}\n"
        f"Статус: {status_label}"
    )
    keyboard = complaint_admin_keyboard(complaint_id) if status == "pending" else {}
    return text, keyboard


async def resolve_complaint(admin_id: int, complaint_id: int) -> tuple[str, dict[str, Any]]:
    if not _is_admin(admin_id):
        return "⛔ Недостаточно прав.", {}
    complaint = await get_complaint(complaint_id)
    if complaint is None:
        return "⚠️ Жалоба не найдена.", {}
    if str(complaint["status"]) != "pending":
        return "ℹ️ Эта жалоба уже обработана.", {}
    if await update_complaint_status(complaint_id, "resolved"):
        return f"✅ Жалоба №{complaint_id} принята и закрыта.", {}
    return "⚠️ Не удалось обработать жалобу.", {}


async def reject_complaint(admin_id: int, complaint_id: int) -> tuple[str, dict[str, Any]]:
    if not _is_admin(admin_id):
        return "⛔ Недостаточно прав.", {}
    complaint = await get_complaint(complaint_id)
    if complaint is None:
        return "⚠️ Жалоба не найдена.", {}
    if str(complaint["status"]) != "pending":
        return "ℹ️ Эта жалоба уже обработана.", {}
    if await update_complaint_status(complaint_id, "rejected"):
        return f"❌ Жалоба №{complaint_id} отклонена.", {}
    return "⚠️ Не удалось обработать жалобу.", {}
