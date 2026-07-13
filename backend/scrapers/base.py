"""
BaseScraper — Abstract base class for all e-commerce scrapers.
Strategy:
  1. Try httpx + JSON-LD (fast, no browser, free) — covers 70-80% of sites
  2. Playwright fallback for sites with heavy JS or anti-bot

All scrapers inherit from BaseScraper and implement:
  - _parse_json_ld(data, url) -> ScrapedProduct
  - _scrape_playwright(url) -> ScrapedProduct
"""

import re
import json
import asyncio
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, BrowserContext

logger = logging.getLogger(__name__)


# ── ScrapedProduct Dataclass ──────────────────────────────────────────────────

@dataclass
class ScrapedProduct:
    platform: str
    platform_id: str
    title: str
    product_url: str
    brand: Optional[str] = None
    model_number: Optional[str] = None     # Most reliable matcher
    gtin: Optional[str] = None             # EAN / UPC / barcode
    price: Optional[float] = None
    mrp: Optional[float] = None
    discount: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    seller: Optional[str] = None
    availability: str = "Unknown"
    image_url: Optional[str] = None
    category: Optional[str] = None
    specs: dict = field(default_factory=dict)
    reviews_snippet: list[str] = field(default_factory=list)  # sample review texts

    def __post_init__(self):
        if self.price and self.mrp and self.mrp > self.price:
            self.discount = round(((self.mrp - self.price) / self.mrp) * 100, 1)


# ── User-Agent Pool ───────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


# ── Base Scraper ──────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    """
    All scrapers inherit from this. Call scrape(url) — it handles strategy selection.
    """

    platform: str = "unknown"

    def _headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    async def scrape(self, url: str) -> ScrapedProduct:
        """
        Main entry point. Tries JSON-LD first, falls back to Playwright.
        """
        logger.info(f"[{self.platform}] Scraping: {url[:80]}")

        # Strategy 1: JSON-LD (httpx + BeautifulSoup) — fast, no browser
        try:
            result = await self._try_json_ld(url)
            if result and result.title:
                logger.info(f"[{self.platform}] ✓ JSON-LD/OpenGraph succeeded (Title: {result.title[:40]})")
                return result
        except Exception as e:
            logger.debug(f"[{self.platform}] JSON-LD failed: {e}")

        # Strategy 2: Playwright (real browser) — slower but reliable
        logger.info(f"[{self.platform}] Falling back to Playwright")
        return await self._scrape_playwright(url)

    async def _try_json_ld(self, url: str) -> Optional[ScrapedProduct]:
        """Fetch page with curl_cffi, parse JSON-LD structured data."""
        try:
            async with AsyncSession(impersonate="chrome110") as client:
                r = await client.get(
                    url,
                    headers=self._headers(),
                    timeout=15.0,
                )
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logger.debug(f"[{self.platform}] Request failed: {e}")
            return None

            # Look for JSON-LD Product schema
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or "")
                    # Handle @graph array
                    if "@graph" in data:
                        for item in data["@graph"]:
                            if item.get("@type") in ("Product", "IndividualProduct"):
                                return self._parse_json_ld(item, url, soup)
                    elif data.get("@type") in ("Product", "IndividualProduct"):
                        return self._parse_json_ld(data, url, soup)
                except Exception:
                    continue

            # Try OpenGraph as fallback
            og = self._parse_opengraph(soup, url)
            return og

    def _parse_opengraph(self, soup: BeautifulSoup, url: str) -> Optional[ScrapedProduct]:
        """Parse OpenGraph meta tags as a last resort."""
        def og(prop):
            tag = soup.find("meta", property=f"og:{prop}") or soup.find("meta", attrs={"name": f"og:{prop}"})
            return tag.get("content", "").strip() if tag else None

        title = og("title")
        image = og("image")
        price_str = og("price:amount") or og("price")

        if not title:
            return None

        price = None
        if price_str:
            try:
                price = float(re.sub(r"[^\d.]", "", price_str))
            except Exception:
                pass

        platform_id = url.split("/")[-1].split("?")[0] or "unknown"
        return ScrapedProduct(
            platform=self.platform,
            platform_id=platform_id,
            title=title,
            product_url=url,
            image_url=image,
            price=price,
        )

    @abstractmethod
    def _parse_json_ld(self, data: dict, url: str, soup: BeautifulSoup) -> ScrapedProduct:
        """Parse JSON-LD Product object into ScrapedProduct. Implement per platform."""
        ...

    @abstractmethod
    async def _scrape_playwright(self, url: str) -> ScrapedProduct:
        """Playwright browser scraping. Implement per platform."""
        ...

    # ── Playwright Helpers ─────────────────────────────────────────────────────

    async def _make_browser_context(self, playwright) -> BrowserContext:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        return context

    async def _goto_with_retry(self, page: Page, url: str, retries: int = 3) -> None:
        for attempt in range(retries):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(1.5, 2.5))
                return
            except Exception as e:
                if attempt == retries - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)

    async def _get_text(self, page: Page, selectors: list[str]) -> Optional[str]:
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text:
                        return text
            except Exception:
                continue
        return None

    async def _get_attr(self, page: Page, selectors: list[str], attr: str) -> Optional[str]:
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    val = await el.get_attribute(attr)
                    if val:
                        return val
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        if not text:
            return None
        try:
            cleaned = re.sub(r"[^\d.]", "", text)
            val = float(cleaned)
            return val if val > 0 else None
        except Exception:
            return None

    @staticmethod
    def _parse_int(text: str) -> Optional[int]:
        if not text:
            return None
        try:
            return int(re.sub(r"[^\d]", "", text))
        except Exception:
            return None

    @staticmethod
    def _parse_rating(text: str) -> Optional[float]:
        if not text:
            return None
        m = re.search(r"(\d+\.?\d*)", text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_model_number(specs: dict, title: str = "") -> Optional[str]:
        """Try to find a model number from specs dict or title."""
        for key in ("Model Number", "Model", "Part Number", "SKU", "model_number", "mpn"):
            if key in specs and specs[key]:
                return str(specs[key]).strip()
        # Try to find in title (e.g., "B0C4XYZ" or "SM-G991B")
        m = re.search(r"\b([A-Z]{1,3}[-_]?[A-Z0-9]{4,12})\b", title)
        if m:
            return m.group(1)
        return None
