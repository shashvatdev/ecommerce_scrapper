"""
Flipkart Scraper — extends BaseScraper.
Combines JSON state extraction, script tags, and selector fallbacks.
"""

import re
import json
import asyncio
import random
import logging
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .base import BaseScraper, ScrapedProduct

logger = logging.getLogger(__name__)


class FlipkartScraper(BaseScraper):
    platform = "flipkart"

    def _parse_json_ld(self, data: dict, url: str, soup: BeautifulSoup) -> ScrapedProduct:
        # Fallback to direct page scraping as Flipkart obfuscates JSON-LD or skips price
        return self._parse_soup(soup, url)

    def _parse_soup(self, soup: BeautifulSoup, url: str) -> ScrapedProduct:
        html = str(soup)
        pid_match = re.search(r"pid=([A-Z0-9]+)", url)
        platform_id = pid_match.group(1) if pid_match else url.split("/")[-1].split("?")[0]

        # Extract title with all fallbacks
        title_el = soup.select_one("span.VU-ZEz, h1.yhB1nd span, h1._6EBuvT span, .B_NuCI, h1 span, h1")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            # Fallback to HTML title
            html_title = soup.find("title")
            if html_title:
                title = html_title.get_text(strip=True).replace("Online at Best Price On Flipkart.com", "").replace("Online at Best Price in India", "").strip()
        if not title:
            # Fallback to OpenGraph
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title.get("content", "").strip()

        # Image extraction with fallbacks
        image_url = None
        img_el = soup.select_one("img.DByuf4, img._2r_T1I, img.q6DClP, div._3kidJX img, img[src*='rukminim']")
        if img_el and img_el.get("src"):
            image_url = img_el["src"]
        if not image_url:
            og_img = soup.find("meta", property="og:image")
            if og_img:
                image_url = og_img.get("content", "").strip()
        
        # Price extraction from script tag window.__INITIAL_STATE__
        price = None
        mrp = None
        
        # Method 1: JSON script search
        state_match = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.+?});", html)
        if state_match:
            try:
                state = json.loads(state_match.group(1))
                # Deep query into structural data to get actual prices
                page_data = state.get("pageDataV4", {})
                for k, v in page_data.get("pageUriQueryParams", {}).items():
                    if k == "pid":
                        platform_id = v
            except Exception:
                pass

        # Method 2: regex parsing of numbers from specific selectors
        price_el = soup.select_one("div.Nx9bqj.CxhGGd, div._30jeq3._16Jk6d, div._30jeq3, .Nx9bqj")
        if price_el:
            price = self._parse_price(price_el.get_text())

        mrp_el = soup.select_one("div.yRaY8j.ZYYwLA, div._3I9_wc, .yRaY8j")
        if mrp_el:
            mrp = self._parse_price(mrp_el.get_text())

        if not price:
            # Fallback regex search
            p_m = re.search(r'"sellingPrice"\s*:\s*\{[^}]*"decimalValue"\s*:\s*(\d+)', html)
            if p_m:
                price = float(p_m.group(1))
            else:
                p_m2 = re.search(r'"price"\s*:\s*(\d{4,7})', html)
                if p_m2:
                    price = float(p_m2.group(1))

        # Check stock status
        availability = "In Stock"
        body_lower = soup.get_text().lower()
        if "out of stock" in body_lower or "currently unavailable" in body_lower or "notify me" in body_lower:
            availability = "Out of Stock"

        rating = None
        rating_el = soup.select_one("div.XQDdHH, div._3LWZlK")
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True))
            except Exception:
                pass

        return ScrapedProduct(
            platform="flipkart",
            platform_id=platform_id,
            title=title,
            brand=None,
            model_number=None,
            price=price,
            mrp=mrp,
            availability=availability,
            image_url=image_url,
            rating=rating,
            product_url=url,
            specs={},
            reviews_snippet=[]
        )

    async def _scrape_playwright(self, url: str) -> ScrapedProduct:
        async with async_playwright() as p:
            context = await self._make_browser_context(p)
            page = await context.new_page()
            await self._goto_with_retry(page, url)
            await asyncio.sleep(3.0)
            html = await page.content()
            await context.browser.close()
            return self._parse_soup(BeautifulSoup(html, "lxml"), url)
