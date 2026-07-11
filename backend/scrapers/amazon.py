"""
Amazon Scraper — uses async Playwright for real browser rendering.
Each data field is extracted in its own function so a single selector
change only requires updating one function.
"""

import re
import asyncio
import random
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)

# ── User-Agent Pool ──────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


# ── URL Helpers ───────────────────────────────────────────────────────────────
def asin_to_url(asin: str) -> str:
    return f"https://www.amazon.in/dp/{asin.strip()}"


def normalize_url(raw: str) -> str:
    """Accept full URL or bare ASIN and return a clean Amazon product URL."""
    raw = raw.strip()
    if raw.startswith("http"):
        # Extract ASIN from URL if present
        m = re.search(r"/dp/([A-Z0-9]{10})", raw)
        if m:
            return asin_to_url(m.group(1))
        return raw
    # Treat as bare ASIN
    if re.match(r"^[A-Z0-9]{10}$", raw):
        return asin_to_url(raw)
    return raw


def extract_asin_from_url(url: str) -> str:
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    return m.group(1) if m else url.split("/")[-1].split("?")[0]


# ── Field Extractors (one function per field) ─────────────────────────────────
async def extract_title(page: Page) -> Optional[str]:
    try:
        el = await page.query_selector("#productTitle")
        if el:
            return (await el.inner_text()).strip()
    except Exception:
        pass
    return None


async def extract_brand(page: Page) -> Optional[str]:
    selectors = [
        "#bylineInfo",
        "#brand",
        "a#bylineInfo",
        ".po-brand .po-break-word",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                text = re.sub(r"^(Visit the |Brand:\s*)", "", text, flags=re.I)
                return text.replace(" Store", "").strip()
        except Exception:
            continue
    return None


async def extract_price(page: Page) -> Optional[float]:
    selectors = [
        ".priceToPay .a-price-whole",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen",
        "#corePrice_feature_div .a-price-whole",
        ".reinventPricePriceToPayMargin .a-price-whole",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                price = float(re.sub(r"[^\d.]", "", text))
                if price > 0:
                    return price
        except Exception:
            continue
    return None


async def extract_mrp(page: Page) -> Optional[float]:
    selectors = [
        ".basisPrice .a-price .a-offscreen",
        "#listPrice",
        ".priceBlockStrikePriceString",
        ".a-text-strike",
        "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                mrp = float(re.sub(r"[^\d.]", "", text))
                if mrp > 0:
                    return mrp
        except Exception:
            continue
    return None


async def extract_rating(page: Page) -> Optional[float]:
    selectors = [
        "#acrPopover",
        "span[data-hook='rating-out-of-text']",
        ".a-icon-star .a-icon-alt",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.get_attribute("title") or await el.inner_text()).strip()
                m = re.search(r"(\d+\.?\d*)", text)
                if m:
                    return float(m.group(1))
        except Exception:
            continue
    return None


async def extract_review_count(page: Page) -> Optional[int]:
    selectors = [
        "#acrCustomerReviewText",
        "span[data-hook='total-review-count']",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                m = re.search(r"([\d,]+)", text)
                if m:
                    return int(m.group(1).replace(",", ""))
        except Exception:
            continue
    return None


async def extract_seller(page: Page) -> Optional[str]:
    selectors = [
        "#sellerProfileTriggerId",
        "#merchant-info a",
        "#tabular-buybox .tabular-buybox-text[tabular-attribute-name='Sold by'] span",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            continue
    return None


async def extract_availability(page: Page) -> Optional[str]:
    selectors = [
        "#availability span",
        "#outOfStock .a-color-price",
        "#availability",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return "Unknown"


async def extract_image(page: Page) -> Optional[str]:
    selectors = [
        "#landingImage",
        "#imgBlkFront",
        "#main-image",
        ".a-dynamic-image",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                src = await el.get_attribute("src") or await el.get_attribute("data-old-hires")
                if src and src.startswith("http"):
                    return src
        except Exception:
            continue
    return None


# ── Main Scraper ──────────────────────────────────────────────────────────────
async def scrape_amazon(input_str: str, input_type: str = "url") -> dict:
    """
    Scrape a single Amazon product.
    input_str: URL or ASIN
    input_type: 'url' | 'asin'
    Returns a dict with product data.
    """
    url = normalize_url(input_str)
    asin = extract_asin_from_url(url)

    logger.info(f"[Amazon] Scraping ASIN={asin} url={url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={
                    "width": random.randint(1280, 1920),
                    "height": random.randint(720, 1080),
                },
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )

            page = await context.new_page()

            # Block images/fonts to speed up scraping
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}",
                lambda route: route.abort()
            )

            # Navigate with retry
            for attempt in range(3):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    await asyncio.sleep(2 ** attempt)

            # Human-like scroll
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Extract all fields
            title        = await extract_title(page)
            brand        = await extract_brand(page)
            price        = await extract_price(page)
            mrp          = await extract_mrp(page)
            rating       = await extract_rating(page)
            review_count = await extract_review_count(page)
            seller       = await extract_seller(page)
            availability = await extract_availability(page)
            image_url    = await extract_image(page)

            # Re-enable images so the actual image URL is available
            await page.unroute("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}")
            if not image_url:
                image_url = await extract_image(page)

            # Calculate discount
            discount = None
            if price and mrp and mrp > price:
                discount = round(((mrp - price) / mrp) * 100, 1)

            return {
                "platform":     "amazon",
                "product_id":   asin,
                "title":        title,
                "brand":        brand,
                "price":        price,
                "mrp":          mrp,
                "discount":     discount,
                "rating":       rating,
                "review_count": review_count,
                "seller":       seller,
                "availability": availability,
                "image_url":    image_url,
                "product_url":  url,
            }

        finally:
            await browser.close()
