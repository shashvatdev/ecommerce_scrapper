"""
Pydantic Models — request/response schemas for FastAPI.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Requests ──────────────────────────────────────────────────────────────────

class IngestURLRequest(BaseModel):
    url: str = Field(..., description="Product URL from any supported platform")


class SearchRequest(BaseModel):
    q: str = Field(..., description="Search query or product name")


class AlertRequest(BaseModel):
    canonical_id: int
    target_price: float
    email: str
    platform: Optional[str] = None


# ── Responses ─────────────────────────────────────────────────────────────────

class PriceEntry(BaseModel):
    platform: str
    price: Optional[float]
    mrp: Optional[float]
    discount: Optional[float]
    seller: Optional[str]
    availability: str
    product_url: str
    last_scraped: Optional[str]

    class Config:
        from_attributes = True


class PriceHistoryPoint(BaseModel):
    price: float
    recorded_at: str
    platform: Optional[str] = None


class AISummary(BaseModel):
    pros: list[str] = []
    cons: list[str] = []
    verdict: str = ""
    best_for: list[str] = []
    avoid_if: list[str] = []
    ai_score: float = 0.0
    value_rating: str = ""
    summary_one_line: str = ""
    generated_at: Optional[str] = None


class CanonicalProduct(BaseModel):
    id: int
    brand: str
    model_name: str
    model_number: Optional[str]
    category: Optional[str]
    image_url: Optional[str]
    created_at: str


class CompareResponse(BaseModel):
    canonical: CanonicalProduct
    stores: list[PriceEntry]
    best_price: Optional[PriceEntry]
    highest_price: Optional[PriceEntry]
    savings: Optional[float]             # difference between highest and lowest
    price_history: list[PriceHistoryPoint]
    ai_summary: Optional[AISummary]


class SearchResult(BaseModel):
    id: int
    brand: str
    model_name: str
    category: Optional[str]
    image_url: Optional[str]
    best_price: Optional[float]
    best_platform: Optional[str]
    store_count: int
    ai_score: Optional[float]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    ai_hint: Optional[str] = None


class AlertResponse(BaseModel):
    id: int
    canonical_id: int
    target_price: float
    email: str
    platform: Optional[str]
    triggered: bool
    created_at: str


class StatsResponse(BaseModel):
    total_products: int
    total_listings: int
    platform_counts: dict
    average_price: float
    pending_alerts: int


class MetricsResponse(BaseModel):
    crawler: dict
    queue_depth: int
    db_stats: dict
