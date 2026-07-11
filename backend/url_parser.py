"""
URL Parser — detect platform and extract product ID from any e-commerce URL.
Supports: Amazon, Flipkart, Croma, Reliance Digital, Vijay Sales.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs


@dataclass
class ParsedURL:
    platform: str           # "amazon" | "flipkart" | "croma" | "reliance" | "vijaysales" | "unknown"
    product_id: str         # ASIN, PID, SKU, slug
    canonical_url: str      # cleaned, canonical product URL
    is_valid: bool


# ── Platform Detection ────────────────────────────────────────────────────────

PLATFORM_PATTERNS = [
    ("amazon",     r"amazon\.(in|com)"),
    ("flipkart",   r"flipkart\.com"),
    ("croma",      r"croma\.com"),
    ("reliance",   r"reliancedigital\.in"),
    ("vijaysales", r"vijaysales\.com"),
    ("nykaa",      r"nykaa\.com"),
    ("myntra",     r"myntra\.com"),
    ("meesho",     r"meesho\.com"),
]


def detect_platform(url: str) -> Optional[str]:
    for platform, pattern in PLATFORM_PATTERNS:
        if re.search(pattern, url, re.I):
            return platform
    return None


# ── Product ID Extractors (per platform) ─────────────────────────────────────

def _extract_amazon_id(url: str) -> Optional[str]:
    # /dp/ASIN or /gp/product/ASIN
    m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    if m:
        return m.group(1)
    # Query param
    qs = parse_qs(urlparse(url).query)
    if "asin" in qs:
        return qs["asin"][0]
    return None


def _extract_flipkart_id(url: str) -> Optional[str]:
    qs = parse_qs(urlparse(url).query)
    if "pid" in qs:
        return qs["pid"][0]
    # /p/itm slug
    m = re.search(r"/p/([a-zA-Z0-9]+)", url)
    if m:
        return m.group(1)
    return None


def _extract_croma_id(url: str) -> Optional[str]:
    # URL ends with /p/NNNNN or contains -p-NNNNN
    m = re.search(r"[/-]p[/-](\d+)", url)
    if m:
        return m.group(1)
    # Last path segment
    path = urlparse(url).path.rstrip("/").split("/")[-1]
    return path if path else None


def _extract_reliance_id(url: str) -> Optional[str]:
    # /product-name/p/NNNNN
    m = re.search(r"/p/(\d+)", url)
    if m:
        return m.group(1)
    qs = parse_qs(urlparse(url).query)
    if "id" in qs:
        return qs["id"][0]
    return None


def _extract_vijaysales_id(url: str) -> Optional[str]:
    # Last slug segment or product ID in URL
    path = urlparse(url).path.rstrip("/").split("/")[-1]
    return path if path else None


ID_EXTRACTORS = {
    "amazon":     _extract_amazon_id,
    "flipkart":   _extract_flipkart_id,
    "croma":      _extract_croma_id,
    "reliance":   _extract_reliance_id,
    "vijaysales": _extract_vijaysales_id,
}


# ── Canonical URL Builders ────────────────────────────────────────────────────

def build_canonical_url(platform: str, product_id: str, original_url: str) -> str:
    if platform == "amazon" and len(product_id) == 10:
        return f"https://www.amazon.in/dp/{product_id}"
    if platform == "flipkart" and product_id:
        # Try to reconstruct from original
        m = re.match(r"(https://www\.flipkart\.com/[^?]+)", original_url)
        if m:
            return f"{m.group(1)}?pid={product_id}"
    return original_url.split("?")[0]  # Strip query params for other platforms


# ── Main Parse Function ───────────────────────────────────────────────────────

def parse_url(url: str) -> ParsedURL:
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    platform = detect_platform(url)
    if not platform:
        return ParsedURL(
            platform="unknown",
            product_id="",
            canonical_url=url,
            is_valid=False,
        )

    extractor = ID_EXTRACTORS.get(platform)
    product_id = extractor(url) if extractor else None

    if not product_id:
        # Fallback: use last path segment
        product_id = urlparse(url).path.rstrip("/").split("/")[-1]

    canonical = build_canonical_url(platform, product_id, url)

    return ParsedURL(
        platform=platform,
        product_id=product_id or "",
        canonical_url=canonical,
        is_valid=bool(product_id),
    )


def is_product_url(url: str) -> bool:
    return parse_url(url).is_valid


# ── Search Query Normalizer ───────────────────────────────────────────────────

def normalize_search_query(query: str) -> str:
    """Clean user search query."""
    query = query.strip()
    # Remove common noise words for better matching
    noise = ["buy", "online", "price", "india", "best", "cheap", "discount"]
    words = query.lower().split()
    words = [w for w in words if w not in noise]
    return " ".join(words)
