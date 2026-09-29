from enum import Enum


class ListingState(str, Enum):
    TITLE = "title"
    CATEGORY = "category"
    DESCRIPTION = "description"
    PRICE = "price"
    CITY = "city"
    PHOTOS = "photos"
    PREVIEW = "preview"


FIELD_PROMPTS = {
    ListingState.TITLE: "📝 Введите название товара.\n\nНапример: «Набор комплектующих»",
    ListingState.CATEGORY: "🏷 Введите категорию товара вручную.",
    ListingState.DESCRIPTION: "📄 Введите описание товара.",
    ListingState.PRICE: "💰 Введите цену товара.",
    ListingState.CITY: "📍 Введите город.",
    ListingState.PHOTOS: "📷 Отправьте фотографии товара.",
    ListingState.PREVIEW: "👀 Проверьте объявление перед отправкой.",
}
