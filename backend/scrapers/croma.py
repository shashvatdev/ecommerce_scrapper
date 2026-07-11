"""
Croma Scraper — extends BaseScraper.
croma.com uses JSON-LD well. Playwright fallback for dynamic pricing.
"""

import re
import asyncio
import random
import logging
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .base import BaseScraper, ScrapedProduct

logger = logging.getLogger(__name__)


class CromaScraper(BaseScraper):
    platform = "croma"

    def _parse_json_ld(self, data: dict, url: str, soup: BeautifulSoup) -> ScrapedProduct:
        title = data.get("name", "")
        brand_raw = data.get("brand", {})
        brand = brand_raw.get("name") if isinstance(brand_raw, dict) else brand_raw
        image_url = data.get("image")
        if isinstance(image_url, list):
            image_url = image_url[0]
        gtin = data.get("gtin13") or data.get("gtin8")

        offers = data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = None
        mrp = None
        availability = "Unknown"
        if offers:
            try:
                price = float(str(offers.get("price", "0")).replace(",", ""))
            except Exception:
                pass
            try:
                mrp = float(str(offers.get("highPrice", "0")).replace(",", ""))
            except Exception:
                pass
            avail = offers.get("availability", "")
            availability = "In Stock" if "InStock" in avail else "Out of Stock" if "OutOfStock" in avail else "Unknown"

        agg = data.get("aggregateRating", {})
        rating = None
        review_count = None
        if agg:
            try:
                rating = float(agg.get("ratingValue", 0))
                review_count = int(str(agg.get("reviewCount", "0")).replace(",", ""))
            except Exception:
                pass

        specs = {}
        for prop in data.get("additionalProperty", []):
            if prop.get("name"):
                specs[prop["name"]] = prop.get("value", "")

        # Extract product ID from URL: /p/NNNNN
        pid_match = re.search(r"[/-]p[/-](\d+)", url)
        platform_id = pid_match.group(1) if pid_match else url.rstrip("/").split("/")[-1]

        model_number = data.get("mpn") or self._extract_model_number(specs, title)

        return ScrapedProduct(
            platform="croma",
            platform_id=platform_id,
            title=title,
            brand=brand,
            model_number=model_number,
            gtin=gtin,
            price=price if price and price > 0 else None,
            mrp=mrp if mrp and mrp > 0 else None,
            availability=availability,
            image_url=image_url if isinstance(image_url, str) else None,
            rating=rating,
            review_count=review_count,
            product_url=url,
            specs=specs,
        )

    async def _scrape_playwright(self, url: str) -> ScrapedProduct:
        pid_match = re.search(r"[/-]p[/-](\d+)", url)
        platform_id = pid_match.group(1) if pid_match else url.rstrip("/").split("/")[-1]

        async with async_playwright() as p:
            context = await self._make_browser_context(p)
            page = await context.new_page()
            await self._goto_with_retry(page, url)
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
            await asyncio.sleep(0.8)

            title = await self._get_text(page, [
                "h1.pdp-title", "h1[data-testid='pdp-product-title']", "h1.product-title", "h1",
            ])
            brand = await self._get_text(page, [
                ".pdp-brand-name", "[data-testid='pdp-brand-name']", ".brand-name",
            ])
            price_text = await self._get_text(page, [
                ".pdp-price strong", ".amount", "[data-testid='pdp-selling-price']",
                ".new-price", ".selling-price",
            ])
            mrp_text = await self._get_text(page, [
                ".pdp-price del", ".old-price", "[data-testid='pdp-mrp']",
            ])
            image_url = await self._get_attr(page, [
                ".pdp-image img", ".product-image img", "[data-testid='pdp-image'] img",
            ], "src")

            specs = {}
            try:
                rows = await page.query_selector_all(".specification-row, .pdp-spec-row, tr.spec-row")
                for row in rows:
                    cells = await row.query_selector_all("td, th, .spec-key, .spec-value")
                    if len(cells) >= 2:
                        k = (await cells[0].inner_text()).strip()
                        v = (await cells[1].inner_text()).strip()
                        if k and v:
                            specs[k] = v
            except Exception:
                pass

            await context.browser.close()

            return ScrapedProduct(
                platform="croma",
                platform_id=platform_id,
                title=(title or "").strip(),
                brand=brand,
                model_number=self._extract_model_number(specs, title or ""),
                price=self._parse_price(price_text),
                mrp=self._parse_price(mrp_text),
                availability="In Stock",
                image_url=image_url,
                product_url=url,
                specs=specs,
            )
