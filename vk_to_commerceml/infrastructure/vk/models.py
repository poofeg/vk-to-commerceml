from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, HttpUrl


class VkBaseModel(BaseModel):
    pass


class GroupItem(VkBaseModel):
    id: int
    name: str


class Price(VkBaseModel):
    amount: Decimal
    old_amount: Decimal | None = None


class Category(VkBaseModel):
    id: int
    name: str


class Availability(IntEnum):
    PRESENTED = 0
    DELETED = 1
    INACCESSIBLE = 2


class PhotoSize(VkBaseModel):
    width: int
    url: HttpUrl


class Photo(VkBaseModel):
    id: int
    sizes: list[PhotoSize] = []


class Video(VkBaseModel):
    id: int
    title: str
    duration: int


class OwnerInfo(VkBaseModel):
    category: str


class MarketItem(VkBaseModel):
    id: int
    owner_id: int
    title: str
    description: str
    price: Price
    category: Category
    availability: Availability
    sku: str = ''
    photos: list[Photo] = []
    videos: list[Video] = []
    owner_info: OwnerInfo
    date: datetime | None = None


class GroupsGetResponse(VkBaseModel):
    count: int
    items: list[GroupItem] = []


class GroupsGetRoot(VkBaseModel):
    response: GroupsGetResponse


class MarketGetResponse(VkBaseModel):
    count: int
    items: list[MarketItem] = []


class MarketGetRoot(VkBaseModel):
    response: MarketGetResponse


class MarketEditRoot(VkBaseModel):
    response: int


class ErrorResponse(VkBaseModel):
    error: dict[str, Any]
