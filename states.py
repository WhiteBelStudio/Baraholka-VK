from enum import Enum

class ListingState(str, Enum):
    TITLE="title"
    CATEGORY="category"
    DESCRIPTION="description"
    PRICE="price"
    CITY="city"
    PHOTOS="photos"
    PREVIEW="preview"
