from __future__ import annotations

from database import fetch_all, fetch_one


async def get_statistics() -> dict[str, int]:
    users = await fetch_one("SELECT COUNT(*) AS value FROM users")
    blocked = await fetch_one("SELECT COUNT(*) AS value FROM users WHERE is_blocked = 1")
    listings = await fetch_one("SELECT COUNT(*) AS value FROM listings")
    published = await fetch_one("SELECT COUNT(*) AS value FROM listings WHERE status = 'published'")
    moderation = await fetch_one("SELECT COUNT(*) AS value FROM listings WHERE status = 'moderation'")
    rejected = await fetch_one("SELECT COUNT(*) AS value FROM listings WHERE status = 'rejected'")
    archived = await fetch_one("SELECT COUNT(*) AS value FROM listings WHERE status = 'archived'")
    deleted = await fetch_one("SELECT COUNT(*) AS value FROM listings WHERE status = 'deleted'")
    complaints = await fetch_one("SELECT COUNT(*) AS value FROM complaints")
    pending_complaints = await fetch_one("SELECT COUNT(*) AS value FROM complaints WHERE status = 'pending'")
    admin_actions = await fetch_one("SELECT COUNT(*) AS value FROM admin_action_logs")
    return {
        "users": int(users["value"]),
        "blocked_users": int(blocked["value"]),
        "listings": int(listings["value"]),
        "published": int(published["value"]),
        "moderation": int(moderation["value"]),
        "rejected": int(rejected["value"]),
        "archived": int(archived["value"]),
        "deleted": int(deleted["value"]),
        "complaints": int(complaints["value"]),
        "pending_complaints": int(pending_complaints["value"]),
        "admin_actions": int(admin_actions["value"]),
    }


def format_statistics(stats: dict[str, int]) -> str:
    return (
        "📊 СТАТИСТИКА БАРАХОЛКИ VK\n\n"
        f"👥 Пользователи: {stats['users']}\n"
        f"🚫 Заблокировано: {stats['blocked_users']}\n\n"
        f"📦 Всего объявлений: {stats['listings']}\n"
        f"🟢 Опубликовано: {stats['published']}\n"
        f"🟡 На модерации: {stats['moderation']}\n"
        f"🔴 Отклонено: {stats['rejected']}\n"
        f"🗄 В архиве: {stats['archived']}\n"
        f"🗑 Удалено: {stats['deleted']}\n\n"
        f"⚠️ Всего жалоб: {stats['complaints']}\n"
        f"⏳ Жалоб ожидает решения: {stats['pending_complaints']}\n"
        f"🛡 Действий администрации: {stats['admin_actions']}"
    )
