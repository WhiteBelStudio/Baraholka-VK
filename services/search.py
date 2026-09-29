from __future__ import annotations

from database import clear_search_session, fetch_all, has_search_session, set_search_session


async def start_search(user_id: int) -> None:
    await set_search_session(user_id)


async def is_searching(user_id: int) -> bool:
    return await has_search_session(user_id)


async def cancel_search(user_id: int) -> None:
    await clear_search_session(user_id)


async def search_listings(query: str, limit: int = 20) -> list:
    query = " ".join((query or "").split()).strip()
    if not query:
        return []
    pattern = f"%{query}%"
    return await fetch_all(
        """SELECT l.id, l.title, l.category, l.description, l.price, l.city, l.status
        FROM listings l
        WHERE l.status IN ('approved', 'published')
          AND (
            l.title LIKE ? COLLATE NOCASE OR
            l.category LIKE ? COLLATE NOCASE OR
            l.description LIKE ? COLLATE NOCASE OR
            l.city LIKE ? COLLATE NOCASE OR
            l.price LIKE ? COLLATE NOCASE
          )
        ORDER BY l.id DESC
        LIMIT ?""",
        (pattern, pattern, pattern, pattern, pattern, limit),
    )


def format_search_results(results: list, query: str) -> str:
    if not results:
        return f"🔎 По запросу «{query}» ничего не найдено."
    lines = [f"🔎 Результаты поиска: «{query}»", ""]
    for item in results:
        lines.extend([
            f"№{item['id']} · {item['title']}",
            f"🏷 {item['category']} · 💰 {item['price']} ₽ · 📍 {item['city']}",
            f"📝 {str(item['description']).replace(chr(10), ' ')[:180]}",
            "",
        ])
    if len(results) == 20:
        lines.append("Показаны первые 20 результатов.")
    return "\n".join(lines).rstrip()
