"""
Vijay Sales Scraper — extends BaseScraper.
vijaysales.com — JSON-LD + Playwright fallback.
"""

import re
import asyncio
import random
import logging

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .base import BaseScraper, ScrapedProduct

logger = logging.getLogger(__name__)


class VijaysSalesScraper(BaseScraper):
    platform = "vijaysales"

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

        specs = {}
        for prop in data.get("additionalProperty", []):
            if prop.get("name"):
                specs[prop["name"]] = prop.get("value", "")

        platform_id = url.rstrip("/").split("/")[-1].split("?")[0]
        model_number = data.get("mpn") or self._extract_model_number(specs, title)

        return ScrapedProduct(
            platform="vijaysales",
            platform_id=platform_id,
            title=title,
            brand=brand,
            model_number=model_number,
            gtin=gtin,
            price=price if price and price > 0 else None,
            mrp=mrp if mrp and mrp > 0 else None,
            availability=availability,
            image_url=image_url if isinstance(image_url, str) else None,
            product_url=url,
            specs=specs,
        )

    async def _scrape_playwright(self, url: str) -> ScrapedProduct:
        platform_id = url.rstrip("/").split("/")[-1].split("?")[0]

        async with async_playwright() as p:
            context = await self._make_browser_context(p)
            page = await context.new_page()
            await self._goto_with_retry(page, url)
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
            await asyncio.sleep(0.8)

            title = await self._get_text(page, [
                ".product-title h1", "h1.prod-title", ".pdp-title", "h1",
            ])
            brand = await self._get_text(page, [".brand-name", ".product-brand"])
            price_text = await self._get_text(page, [
                ".offer-price", ".selling-price", ".product-price .price",
            ])
            mrp_text = await self._get_text(page, [
                ".mrp", ".original-price", ".cut-price del",
            ])
            image_url = await self._get_attr(page, [
                ".product-gallery img", ".main-product-image img",
            ], "src")

            specs = {}
            try:
                rows = await page.query_selector_all(".spec-row, .specification tr")
                for row in rows:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 2:
                        k = (await cells[0].inner_text()).strip()
                        v = (await cells[1].inner_text()).strip()
                        if k and v:
                            specs[k] = v
            except Exception:
                pass

            await context.browser.close()

            return ScrapedProduct(
                platform="vijaysales",
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
