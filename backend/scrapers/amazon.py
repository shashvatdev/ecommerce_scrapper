"""
Amazon Scraper — extends BaseScraper.
JSON-LD first (fast), Playwright fallback.
"""

import re
import asyncio
import random
import logging
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .base import BaseScraper, ScrapedProduct
from browser_utils import create_stealth_context, create_stealth_page

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    platform = "amazon"

    def _parse_json_ld(self, data: dict, url: str, soup: BeautifulSoup) -> ScrapedProduct:
        title = data.get("name", "")
        brand = data.get("brand", {}).get("name") if isinstance(data.get("brand"), dict) else data.get("brand")
        image_url = data.get("image") or (data.get("image", [None])[0] if isinstance(data.get("image"), list) else None)
        gtin = data.get("gtin13") or data.get("gtin8") or data.get("gtin")

        # Offers
        offers = data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = None
        mrp = None
        seller = None
        availability = "Unknown"
        if offers:
            try:
                price = float(str(offers.get("price", "0")).replace(",", ""))
            except Exception:
                pass
            mrp_str = offers.get("priceValidUntil") or offers.get("highPrice")
            if mrp_str:
                try:
                    mrp = float(str(mrp_str).replace(",", ""))
                except Exception:
                    pass
            seller_info = offers.get("seller", {})
            seller = seller_info.get("name") if isinstance(seller_info, dict) else seller_info
            avail = offers.get("availability", "")
            if "InStock" in avail or "InStoreOnly" in avail:
                availability = "In Stock"
            elif "OutOfStock" in avail:
                availability = "Out of Stock"

        rating = None
        review_count = None
        agg = data.get("aggregateRating", {})
        if agg:
            try:
                rating = float(agg.get("ratingValue", 0))
                review_count = int(str(agg.get("reviewCount", "0")).replace(",", ""))
            except Exception:
                pass

        # Specs from additionalProperty
        specs = {}
        for prop in data.get("additionalProperty", []):
            if prop.get("name"):
                specs[prop["name"]] = prop.get("value", "")

        asin = re.search(r"/dp/([A-Z0-9]{10})", url)
        platform_id = asin.group(1) if asin else url.split("/")[-1]

        model_number = data.get("mpn") or self._extract_model_number(specs, title)

        return ScrapedProduct(
            platform="amazon",
            platform_id=platform_id,
            title=title,
            brand=brand,
            model_number=model_number,
            gtin=gtin,
            price=price if price and price > 0 else None,
            mrp=mrp if mrp and mrp > 0 else None,
            seller=seller,
            availability=availability,
            image_url=image_url if isinstance(image_url, str) else None,
            rating=rating,
            review_count=review_count,
            product_url=f"https://www.amazon.in/dp/{platform_id}",
            specs=specs,
        )

    async def _scrape_playwright(self, url: str) -> ScrapedProduct:
        # Normalize URL
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
        asin = asin_match.group(1) if asin_match else url.split("/")[-1].split("?")[0]
        url = f"https://www.amazon.in/dp/{asin}"

        logger.info(f"[Amazon] Falling back to Playwright for {url}")
        async with async_playwright() as pw:
            browser, context = await create_stealth_context(pw)
            page = await create_stealth_page(context)

            # Block images/fonts to speed up
            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}",
                             lambda route: route.abort())

            await self._goto_with_retry(page, url)
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
            await asyncio.sleep(random.uniform(0.5, 1.2))

            title = await self._get_text(page, ["#productTitle"])
            brand = await self._get_text(page, ["#bylineInfo", "#brand", ".po-brand .po-break-word"])
            if brand:
                brand = re.sub(r"^(Visit the |Brand:\s*)", "", brand, flags=re.I).replace(" Store", "").strip()

            price_text = await self._get_text(page, [
                ".priceToPay .a-price-whole",
                "#priceblock_ourprice",
                "#corePrice_feature_div .a-price-whole",
                ".reinventPricePriceToPayMargin .a-price-whole",
            ])
            mrp_text = await self._get_text(page, [
                ".basisPrice .a-price .a-offscreen",
                "#listPrice",
                ".priceBlockStrikePriceString",
                "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
            ])
            rating_text = await self._get_attr(page, ["#acrPopover"], "title") or \
                          await self._get_text(page, ["#acrPopover"])
            review_text = await self._get_text(page, ["#acrCustomerReviewText"])
            seller = await self._get_text(page, [
                "#sellerProfileTriggerId",
                "#merchant-info a",
            ])
            avail_text = await self._get_text(page, ["#availability span", "#availability"])

            # Re-enable images to get real image URL
            await page.unroute("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}")
            image_url = await self._get_attr(page, [
                "#landingImage", "#imgBlkFront", ".a-dynamic-image"
            ], "src")

            # Specs from product details table
            specs = {}
            try:
                rows = await page.query_selector_all("#productDetails_techSpec_section_1 tr, #prodDetails tr")
                for row in rows:
                    cells = await row.query_selector_all("td, th")
                    if len(cells) >= 2:
                        k = (await cells[0].inner_text()).strip()
                        v = (await cells[1].inner_text()).strip()
                        if k and v:
                            specs[k] = v
            except Exception:
                pass

            await context.browser.close()

            return ScrapedProduct(
                platform="amazon",
                platform_id=asin,
                title=(title or "").strip(),
                brand=brand,
                model_number=self._extract_model_number(specs, title or ""),
                price=self._parse_price(price_text),
                mrp=self._parse_price(mrp_text),
                rating=self._parse_rating(rating_text),
                review_count=self._parse_int(review_text),
                seller=seller,
                availability="In Stock" if avail_text and "stock" in avail_text.lower() else (avail_text or "Unknown"),
                image_url=image_url,
                product_url=url,
                specs=specs,
            )
