"""
Flipkart Scraper — uses async Playwright for real browser rendering.
Each data field is extracted in its own function for easy maintenance.
"""

import re
import asyncio
import random
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
]


# ── URL Helpers ───────────────────────────────────────────────────────────────
def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("http"):
        return raw
    # Try treating as product ID
    return f"https://www.flipkart.com/product/p/itm?pid={raw}"


def extract_product_id(url: str) -> str:
    m = re.search(r"pid=([A-Z0-9]+)", url)
    if m:
        return m.group(1)
    # Try extracting from /p/itm... path
    m = re.search(r"/([A-Z0-9]{16})", url)
    if m:
        return m.group(1)
    return url.split("/")[-1].split("?")[0]


# ── Field Extractors ──────────────────────────────────────────────────────────
async def extract_title(page: Page) -> Optional[str]:
    selectors = [
        "span.VU-ZEz",
        "h1.yhB1nd span",
        "h1._6EBuvT span",
        ".B_NuCI",
        "h1 span",
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
    return None


async def extract_brand(page: Page) -> Optional[str]:
    selectors = [
        "span.mEh187",
        ".G6XhRU",
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
    return None


async def extract_price(page: Page) -> Optional[float]:
    selectors = [
        "div.Nx9bqj.CxhGGd",
        "div._30jeq3._16Jk6d",
        "div._30jeq3",
        "._25b18cr ._30jeq3",
        ".CEmiEU div.Nx9bqj",
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
        "div.yRaY8j.ZYYwLA",
        "div._3I9_wc._2p6lqe",
        "div._3I9_wc",
        "._25b18cr ._3I9_wc",
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
        "div.XQDdHH",
        "div._3LWZlK",
        "div._2d4LTz",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                m = re.search(r"(\d+\.?\d*)", text)
                if m:
                    return float(m.group(1))
        except Exception:
            continue
    return None


async def extract_review_count(page: Page) -> Optional[int]:
    selectors = [
        "span.Wphh3N",
        "span._2_R_DZ",
        "span._13vcmD",
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
        "div#sellerName span span",
        "div.KRD_UC span",
        "._3an_dv .vFw0gD",
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
    return None


async def extract_availability(page: Page) -> Optional[str]:
    try:
        # If add-to-cart button is present → in stock
        btn = await page.query_selector("button._2KpZ6l._2U9uOA.ihZ75k")
        if btn:
            return "In Stock"
        # Check for out-of-stock message
        oos = await page.query_selector("._16FRp0")
        if oos:
            return "Out of Stock"
    except Exception:
        pass
    return "In Stock"


async def extract_image(page: Page) -> Optional[str]:
    selectors = [
        "img._396cs4._2amPTt._3qGmMb",
        "img.DByuf4",
        "img._2r_T1I",
        "img.q6DClP",
        "._3kidJX img",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                src = await el.get_attribute("src")
                if src and src.startswith("http"):
                    # Get full-size image
                    src = re.sub(r"/\d+/\d+/", "/832/832/", src)
                    return src
        except Exception:
            continue
    return None


# ── Main Scraper ──────────────────────────────────────────────────────────────
async def scrape_flipkart(input_str: str, input_type: str = "url") -> dict:
    """
    Scrape a single Flipkart product.
    input_str: URL or Product ID
    Returns a dict with product data.
    """
    url = normalize_url(input_str)
    product_id = extract_product_id(url)

    logger.info(f"[Flipkart] Scraping pid={product_id} url={url}")

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

            # Handle Flipkart login popup by dismissing it
            page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))

            for attempt in range(3):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                    # Close login popup if it appears
                    try:
                        close_btn = await page.query_selector("button._2KpZ6l.AHkbns")
                        if close_btn:
                            await close_btn.click()
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass

                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    await asyncio.sleep(2 ** attempt)

            # Human-like scroll
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.4)")
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

            discount = None
            if price and mrp and mrp > price:
                discount = round(((mrp - price) / mrp) * 100, 1)

            return {
                "platform":     "flipkart",
                "product_id":   product_id,
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
