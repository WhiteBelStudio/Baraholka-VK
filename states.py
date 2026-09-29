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
    ListingState.CATEGORY: "🏷 Введите категорию товара вручную.\n\nНапример: «Электроника», «Одежда», «Инструменты».\nКатегория не выбирается из готового списка — её указывает продавец.",
    ListingState.DESCRIPTION: "📄 Введите описание товара.",
    ListingState.PRICE: "💰 Введите цену товара.\n\nМожно указать копейки: 199.99₽ или 199,99 руб.\nТакже принимаются целые суммы: 199₽.",
    ListingState.CITY: "📍 Введите город.\n\nНапример: Белореченск.",
    ListingState.PHOTOS: "📷 Добавьте от 1 до 3 фотографий товара.\n\nТакже можно добавить не более 1 видео.",
    ListingState.PREVIEW: "👀 Проверьте объявление перед отправкой.",
}
