from __future__ import annotations

from dataclasses import dataclass

from database import (
    add_listing_photo,
    clear_listing_photos,
    create_listing,
    delete_listing,
    delete_listing_photo,
    get_listing,
    get_listing_for_user,
    get_listing_photos,
    get_listings_by_status,
    get_user_listings,
    update_listing,
)


class ListingError(ValueError):
    """Base error for invalid listing operations."""


class ListingNotFoundError(ListingError):
    pass


class ListingPermissionError(ListingError):
    pass


class ListingValidationError(ListingError):
    pass


class ListingStatus:
    DRAFT = "draft"
    MODERATION = "moderation"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    DELETED = "deleted"


ALLOWED_STATUSES = {
    ListingStatus.DRAFT,
    ListingStatus.MODERATION,
    ListingStatus.APPROVED,
    ListingStatus.REJECTED,
    ListingStatus.PUBLISHED,
    ListingStatus.ARCHIVED,
    ListingStatus.DELETED,
}


@dataclass(frozen=True)
class ListingData:
    title: str
    category: str
    description: str
    price: str
    city: str


def _clean(value: str, field: str, max_length: int = 2000) -> str:
    value = " ".join((value or "").strip().split())
    if not value:
        raise ListingValidationError(f"{field} must not be empty")
    if len(value) > max_length:
        raise ListingValidationError(f"{field} is too long (maximum {max_length} characters)")
    return value


def validate_title(value: str) -> str:
    title = " ".join((value or "").strip().split())
    if not title:
        raise ListingValidationError("Название товара не может быть пустым")
    if len(title) < 2:
        raise ListingValidationError("Название товара должно содержать минимум 2 символа")
    if len(title) > 120:
        raise ListingValidationError("Название товара не должно превышать 120 символов")
    return title


def validate_listing(data: ListingData) -> ListingData:
    return ListingData(
        title=validate_title(data.title),
        category=_clean(data.category, "category", 100),
        description=_clean(data.description, "description", 4000),
        price=_clean(data.price, "price", 50),
        city=_clean(data.city, "city", 100),
    )


FIELD_LIMITS = {
    "title": 120,
    "category": 100,
    "description": 4000,
    "price": 50,
    "city": 100,
}


def validate_field(field: str, value: str) -> str:
    if field == "title":
        return validate_title(value)
    if field not in FIELD_LIMITS:
        raise ListingValidationError(f"Unsupported listing field: {field}")
    return _clean(value, field, FIELD_LIMITS[field])


async def save_draft_field(listing_id: int, field: str, value: str) -> None:
    clean_value = validate_field(field, value)
    listing = await get_listing_or_raise(listing_id)
    if listing["status"] != ListingStatus.DRAFT:
        raise ListingValidationError("Only draft listings can be edited through the creation dialog")
    await update_listing(listing_id, **{field: clean_value})


async def create_draft(user_id: int) -> int:
    if user_id <= 0:
        raise ListingValidationError("Invalid user_id")
    return await create_listing(user_id)


async def get_listing_or_raise(listing_id: int):
    listing = await get_listing(listing_id)
    if listing is None:
        raise ListingNotFoundError(f"Listing {listing_id} not found")
    return listing


async def get_owned_listing_or_raise(listing_id: int, user_id: int):
    listing = await get_listing_for_user(listing_id, user_id)
    if listing is None:
        raise ListingPermissionError("Listing does not exist or does not belong to the user")
    return listing


async def save_listing_data(listing_id: int, data: ListingData) -> None:
    data = validate_listing(data)
    await get_listing_or_raise(listing_id)
    await update_listing(
        listing_id,
        title=data.title,
        category=data.category,
        description=data.description,
        price=data.price,
        city=data.city,
    )


async def set_listing_status(listing_id: int, status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise ListingValidationError(f"Unsupported listing status: {status}")
    await get_listing_or_raise(listing_id)
    await update_listing(listing_id, status=status)


async def submit_for_moderation(listing_id: int) -> None:
    listing = await get_listing_or_raise(listing_id)
    data = ListingData(
        title=listing["title"],
        category=listing["category"],
        description=listing["description"],
        price=listing["price"],
        city=listing["city"],
    )
    validate_listing(data)
    await set_listing_status(listing_id, ListingStatus.MODERATION)


async def attach_photo(listing_id: int, vk_attachment: str, position: int = 0) -> int:
    await get_listing_or_raise(listing_id)
    attachment = (vk_attachment or "").strip()
    if not attachment:
        raise ListingValidationError("vk_attachment must not be empty")
    if position < 0:
        raise ListingValidationError("position must be >= 0")
    return await add_listing_photo(listing_id, attachment, position)


async def replace_photos(listing_id: int, attachments: list[str]) -> None:
    await get_listing_or_raise(listing_id)
    clean = [item.strip() for item in attachments if item and item.strip()]
    await clear_listing_photos(listing_id)
    for position, attachment in enumerate(clean):
        await add_listing_photo(listing_id, attachment, position)


async def remove_photo(photo_id: int, listing_id: int) -> bool:
    await get_listing_or_raise(listing_id)
    return await delete_listing_photo(photo_id, listing_id)


async def get_photos(listing_id: int):
    await get_listing_or_raise(listing_id)
    return await get_listing_photos(listing_id)


async def delete_owned_listing(listing_id: int, user_id: int) -> None:
    await get_owned_listing_or_raise(listing_id, user_id)
    if not await delete_listing(listing_id, user_id):
        raise ListingNotFoundError(f"Listing {listing_id} not found")


async def list_user_listings(user_id: int, statuses: tuple[str, ...] | None = None):
    if user_id <= 0:
        raise ListingValidationError("Invalid user_id")
    return await get_user_listings(user_id, statuses)


async def list_moderation_queue():
    return await get_listings_by_status(ListingStatus.MODERATION)
