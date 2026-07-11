from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ScrapeRequest(BaseModel):
    input: str          # URL or ASIN/product ID
    type: str = "url"   # "url" | "asin" | "id"


class PricePoint(BaseModel):
    price: float
    recorded_at: datetime

    class Config:
        from_attributes = True


class Product(BaseModel):
    id:           int
    platform:     str
    product_id:   str
    title:        Optional[str]
    brand:        Optional[str]
    price:        Optional[float]
    mrp:          Optional[float]
    discount:     Optional[float]
    rating:       Optional[float]
    review_count: Optional[int]
    seller:       Optional[str]
    availability: Optional[str]
    image_url:    Optional[str]
    product_url:  str
    scraped_at:   datetime
    last_updated: datetime
    price_history: list[PricePoint] = []

    class Config:
        from_attributes = True


class ProductListItem(BaseModel):
    id:           int
    platform:     str
    product_id:   str
    title:        Optional[str]
    brand:        Optional[str]
    price:        Optional[float]
    mrp:          Optional[float]
    discount:     Optional[float]
    rating:       Optional[float]
    review_count: Optional[int]
    availability: Optional[str]
    image_url:    Optional[str]
    product_url:  str
    scraped_at:   datetime

    class Config:
        from_attributes = True


class ScrapeResponse(BaseModel):
    success:  bool
    message:  str
    product:  Optional[Product] = None
    error:    Optional[str] = None
