"""
Product Matcher — finds or creates a canonical product.

Matching priority (as per architecture review):
  1. Model Number exact match  → 100% confidence
  2. GTIN / EAN exact match    → 100% confidence
  3. Brand + fuzzy title       → high confidence (rapidfuzz ≥ 90)
  4. Title-only fuzzy          → medium confidence (rapidfuzz ≥ 85)
  5. Create new canonical      → default if nothing matches
"""

import re
import logging
from typing import Optional

from rapidfuzz import fuzz

import json_db
from scrapers.base import ScrapedProduct

logger = logging.getLogger(__name__)


# ── Title Normalization ───────────────────────────────────────────────────────

_NOISE = re.compile(
    r"\b(buy|online|india|with|and|for|the|in|of|"
    r"best|cheap|new|latest|official|genuine|"
    r"gb|tb|mb|inch|cm|mm|hz|mah|mp|w)\b",
    re.I,
)
_WHITESPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, remove noise words, collapse whitespace."""
    t = title.lower()
    t = _NOISE.sub(" ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return _WHITESPACE.sub(" ", t).strip()


def normalize_brand(brand: str) -> str:
    return (brand or "").lower().strip()


# ── Matcher ───────────────────────────────────────────────────────────────────

def find_or_create_canonical(scraped: ScrapedProduct) -> dict:
    """
    Given a freshly scraped product, find the matching canonical product
    or create a new one. Returns the canonical product dict.
    """

    # ── Step 1: Model Number exact match ─────────────────────────────────────
    if scraped.model_number:
        canon = json_db.find_canonical_by_model_number(scraped.model_number)
        if canon:
            logger.info(f"[Matcher] Model# match: '{scraped.model_number}' → canonical #{canon['id']}")
            return canon

    # ── Step 2: GTIN / EAN exact match ───────────────────────────────────────
    if scraped.gtin:
        canon = json_db.find_canonical_by_gtin(scraped.gtin)
        if canon:
            logger.info(f"[Matcher] GTIN match: '{scraped.gtin}' → canonical #{canon['id']}")
            return canon

    # ── Step 3: Brand + fuzzy title match ────────────────────────────────────
    all_canonicals = json_db.get_all_canonicals()
    scraped_normalized = normalize_title(scraped.title or "")
    scraped_brand = normalize_brand(scraped.brand or "")

    best_score = 0
    best_match = None

    for canon in all_canonicals:
        # Brand filter (if both have brand, they should roughly match)
        if scraped_brand and canon.get("brand"):
            canon_brand = normalize_brand(canon["brand"])
            brand_score = fuzz.ratio(scraped_brand, canon_brand)
            if brand_score < 60:
                continue  # Different brands, skip

        canon_normalized = normalize_title(canon.get("model_name", ""))
        score = fuzz.token_sort_ratio(scraped_normalized, canon_normalized)

        if score > best_score:
            best_score = score
            best_match = canon

    threshold = 88 if scraped_brand else 92  # Stricter without brand
    if best_match and best_score >= threshold:
        logger.info(
            f"[Matcher] Fuzzy match (score={best_score}): "
            f"'{scraped.title}' → '{best_match.get('model_name')}' (#{best_match['id']})"
        )
        return best_match

    # ── Step 4: Create new canonical ─────────────────────────────────────────
    logger.info(f"[Matcher] No match found. Creating new canonical for '{scraped.title}'")
    canon = json_db.create_canonical({
        "brand": scraped.brand or "Unknown",
        "model_name": scraped.title or "Unknown Product",
        "model_number": scraped.model_number,
        "gtin": scraped.gtin,
        "category": scraped.category or _guess_category(scraped.title or ""),
        "image_url": scraped.image_url,
    })
    return canon


def _guess_category(title: str) -> str:
    """Naive category detection from title keywords."""
    t = title.lower()
    if any(k in t for k in ["phone", "iphone", "samsung", "oneplus", "pixel", "redmi", "poco"]):
        return "smartphones"
    if any(k in t for k in ["laptop", "macbook", "thinkpad", "notebook"]):
        return "laptops"
    if any(k in t for k in ["tv", "television", "oled", "qled"]):
        return "televisions"
    if any(k in t for k in ["earbuds", "airpods", "headphone", "earphone", "speaker"]):
        return "audio"
    if any(k in t for k in ["tablet", "ipad"]):
        return "tablets"
    if any(k in t for k in ["camera", "dslr", "mirrorless"]):
        return "cameras"
    if any(k in t for k in ["watch", "smartwatch", "band"]):
        return "wearables"
    if any(k in t for k in ["refrigerator", "fridge", "washing", "ac ", "air condition"]):
        return "appliances"
    return "electronics"


def get_match_confidence(score: int) -> str:
    if score >= 95:
        return "very_high"
    if score >= 88:
        return "high"
    if score >= 75:
        return "medium"
    return "low"
