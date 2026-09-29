from __future__ import annotations

import re

from database import (
    clear_filter_session,
    clear_search_session,
    fetch_all,
    has_filter_session,
    has_search_session,
    set_filter_session,
    set_search_session,
)


async def start_search(user_id: int) -> None:
    await set_search_session(user_id)


async def is_searching(user_id: int) -> bool:
    return await has_search_session(user_id)


async def cancel_search(user_id: int) -> None:
    await clear_search_session(user_id)


async def start_filter(user_id: int) -> None:
    await set_filter_session(user_id)


async def is_filtering(user_id: int) -> bool:
    return await has_filter_session(user_id)


async def cancel_filter(user_id: int) -> None:
    await clear_filter_session(user_id)


async def filter_listings(
    category: str | None = None,
    city: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 20,
) -> list:
    clauses = ["l.status IN ('approved', 'published')"]
    params: list = []

    category = " ".join((category or "").split()).strip()
    city = " ".join((city or "").split()).strip()

    if category:
        clauses.append("l.category LIKE ? COLLATE NOCASE")
        params.append(f"%{category}%")
    if city:
        clauses.append("l.city LIKE ? COLLATE NOCASE")
        params.append(f"%{city}%")
    if min_price is not None:
        clauses.append("CAST(l.price AS REAL) >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("CAST(l.price AS REAL) <= ?")
        params.append(max_price)

    params.append(limit)
    return await fetch_all(
        f"""SELECT l.id, l.title, l.category, l.description, l.price, l.city, l.status
        FROM listings l
        WHERE {" AND ".join(clauses)}
        ORDER BY l.id DESC
        LIMIT ?""",
        tuple(params),
    )


def parse_filter_input(text: str) -> tuple[str | None, str | None, float | None, float | None]:
    parts = [part.strip() for part in (text or "").split("|")]
    if len(parts) != 4:
        raise ValueError("Нужно указать 4 поля через символ |")
    values = [None if part in {"", "-", "—"} else part for part in parts]
    category, city, min_raw, max_raw = values

    def price(value: str | None) -> float | None:
        if value is None:
            return None
        normalized = value.lower().replace("₽", "").replace("руб.", "").replace("руб", "").replace(" ", "").replace(",", ".")
        result = float(normalized)
        if result < 0:
            raise ValueError("Цена не может быть отрицательной")
        return result

    min_price = price(min_raw)
    max_price = price(max_raw)
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("Минимальная цена не может быть больше максимальной цены")
    if category and len(category) > 100:
        raise ValueError("Категория слишком длинная")
    if city and len(city) > 100:
        raise ValueError("Город слишком длинный")
    return category, city, min_price, max_price


def format_filter_results(results: list, category: str | None, city: str | None, min_price: float | None, max_price: float | None) -> str:
    parts = []
    if category:
        parts.append(f"категория: {category}")
    if city:
        parts.append(f"город: {city}")
    if min_price is not None:
        parts.append(f"от {min_price:g} ₽")
    if max_price is not None:
        parts.append(f"до {max_price:g} ₽")
    description = ", ".join(parts) if parts else "без ограничений"

    if not results:
        return f"🔎 По фильтрам ({description}) ничего не найдено."

    lines = [f"🔎 Результаты фильтрации ({description})", ""]
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
