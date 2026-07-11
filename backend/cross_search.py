"""
Cross-Platform Search v5 — Network Interception approach.

What we learned:
  ✓ Amazon   — httpx works fine
  ✓ Flipkart — httpx works fine
  ✗ Croma    — bot protection blocks headless Chromium (body=214 chars)
  ✗ Reliance — bot protection blocks headless Chromium (body=1682 chars)
  ✗ VijayS  — JS rendered, products don't match query

Strategy v5:
  - Amazon/Flipkart: httpx (fast, works)
  - Croma/Reliance: Playwright + network interception (capture internal API calls)
  - VijayS: Playwright with longer wait + smarter link detection
"""

import re
import json
import asyncio
import logging
from typing import Optional
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext
from browser_utils import create_stealth_context, create_stealth_page

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


# ── Query Builder ─────────────────────────────────────────────────────────────

def build_search_query(title: str, brand: str = "", model_number: str = "") -> str:
    if model_number:
        return f"{brand} {model_number}".strip()[:60]
    clean = re.sub(r"\(.*?\)", "", title)
    clean = re.sub(r"[,|–—:].*", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return " ".join(clean.split()[:6])


def _url_relevant(url: str, query: str) -> bool:
    """Strict relevance check: URL must contain the primary keywords of the query (e.g. brand + product line/number)."""
    # Clean up and get significant words
    words = [re.sub(r'[^a-zA-Z0-9]', '', w).lower() for w in query.split() if len(w) >= 2]
    # Filter out generic words
    stop = {"with", "gb", "ram", "storage", "smart", "phone", "mobile", "display"}
    keywords = [w for w in words if w not in stop]
    
    if not keywords:
        return False
        
    url_l = url.lower()
    
    # Require at least the first two major keywords (or 70% of keywords) to match
    match_count = sum(1 for kw in keywords if kw in url_l)
    
    # Must match at least 60% of significant words OR both of the first two primary keywords (like 'oneplus' and 'nord')
    if len(keywords) >= 2:
        first_two = keywords[:2]
        if all(k in url_l for k in first_two):
            return True
            
    return (match_count / len(keywords)) >= 0.60


# ── httpx ─────────────────────────────────────────────────────────────────────

async def _get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=12) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        logger.debug(f"[CrossSearch] httpx error {url[:60]}: {e}")
    return None


# ── Amazon ────────────────────────────────────────────────────────────────────

async def find_amazon_url(query: str) -> list[str]:
    """Search Amazon using Playwright to bypass bot blocks."""
    urls = []
    url = f"https://www.amazon.in/s?k={quote_plus(query)}&i=electronics"
    try:
        async with async_playwright() as pw:
            browser, ctx = await create_stealth_context(pw)
            page = await create_stealth_page(ctx)
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(html, "lxml")
            for div in soup.select("[data-asin]"):
                asin = div.get("data-asin", "").strip()
                if asin and len(asin) == 10 and re.match(r"^[A-Z0-9]{10}$", asin):
                    found_url = f"https://www.amazon.in/dp/{asin}"
                    if found_url not in urls:
                        urls.append(found_url)
                    if len(urls) >= 5:
                        break
    except Exception as e:
        logger.error(f"[CrossSearch] Amazon search error: {e}")
    return urls


# ── Flipkart ──────────────────────────────────────────────────────────────────

async def find_flipkart_url(query: str) -> list[str]:
    """Search Flipkart using Playwright to bypass 403 Forbidden blocks."""
    urls = []
    url = f"https://www.flipkart.com/search?q={quote_plus(query)}&otracker=search"
    try:
        async with async_playwright() as pw:
            browser, ctx = await create_stealth_context(pw)
            page = await create_stealth_page(ctx)
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/p/" not in href:
                    continue
                full = ("https://www.flipkart.com" + href) if href.startswith("/") else href
                if not _url_relevant(full, query):
                    continue
                pid_m = re.search(r"pid=([A-Z0-9]+)", full)
                path_m = re.search(r"(https://www\.flipkart\.com/[^/?]+/p/[^/?]+)", full)
                
                final_url = None
                if path_m and pid_m:
                    final_url = f"{path_m.group(1)}?pid={pid_m.group(1)}"
                elif path_m:
                    final_url = path_m.group(1)
                    
                if final_url and final_url not in urls:
                    urls.append(final_url)
                
                if len(urls) >= 5:
                    break
    except Exception as e:
        logger.error(f"[CrossSearch] Flipkart search error: {e}")
    return urls


# ── Croma — Network Interception ─────────────────────────────────────────────

async def find_croma_url(query: str) -> Optional[str]:
    """
    Intercept Croma's internal search API call when Playwright loads the page.
    Croma calls something like api.croma.com/... with proper session cookies.
    """
    captured_url = None
    search_url = (
        f"https://www.croma.com/searchB?q={quote_plus(query)}&text={quote_plus(query)}"
    )

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(
                user_agent=UA,
                locale="en-IN",
                viewport={"width": 1366, "height": 768},
            )
            # Hide webdriver flag
            await ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = await ctx.new_page()

            # Intercept API responses
            api_data = []

            async def handle_response(response):
                url = response.url
                if ("api.croma.com" in url or "search" in url) and "croma" in url:
                    try:
                        body = await response.body()
                        data = json.loads(body)
                        api_data.append(data)
                        logger.debug(f"[Croma] Intercepted: {url[:60]}")
                    except Exception:
                        pass

            page.on("response", handle_response)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(5000)

            # Try to extract from intercepted API data
            for data in api_data:
                products = (data.get("products") or
                            data.get("result", {}).get("products") or
                            data.get("searchResult", {}).get("products") or [])
                for p in products:
                    slug = (p.get("url") or p.get("productUrl") or
                            p.get("canonicalUrl") or p.get("slug", ""))
                    if slug:
                        url = f"https://www.croma.com{slug}" if slug.startswith("/") else f"https://www.croma.com/{slug}"
                        if _url_relevant(url, query):
                            await browser.close()
                            return url.split("?")[0]

            # Fallback: parse rendered HTML
            html = await page.content()
            await browser.close()

            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/p/\d{4,}", href) and _url_relevant(href, query):
                    return ("https://www.croma.com" + href if href.startswith("/") else href).split("?")[0]

    except Exception as e:
        logger.warning(f"[CrossSearch] Croma error: {e}")
    return None


# ── Reliance Digital — Network Interception ───────────────────────────────────

async def find_reliance_url(query: str) -> Optional[str]:
    """
    Intercept Reliance Digital's internal API response.
    """
    search_url = f"https://www.reliancedigital.in/search?q={quote_plus(query)}"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(
                user_agent=UA, locale="en-IN", viewport={"width": 1366, "height": 768}
            )
            await ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = await ctx.new_page()

            api_data = []

            async def handle_response(response):
                url = response.url
                if any(k in url for k in ["productSearch", "search", "rildigital", "algolia"]):
                    try:
                        body = await response.body()
                        data = json.loads(body)
                        api_data.append((url, data))
                        logger.debug(f"[Reliance] Intercepted: {url[:80]}")
                    except Exception:
                        pass

            page.on("response", handle_response)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(5000)

            # Process intercepted data
            for (api_url, data) in api_data:
                # Navigate the response JSON tree looking for product URLs
                products = (
                    data.get("products") or
                    data.get("data", {}).get("products") or
                    data.get("response", {}).get("products") or
                    data.get("hits") or []   # Algolia format
                )
                if isinstance(products, list):
                    for p in products:
                        slug = (p.get("url") or p.get("productUrl") or
                                p.get("_source", {}).get("url") or "")
                        code = p.get("code") or p.get("id") or p.get("objectID", "")
                        if slug and _url_relevant(slug, query):
                            full = ("https://www.reliancedigital.in" + slug
                                    if slug.startswith("/") else slug)
                            await browser.close()
                            return full.split("?")[0]

            # Fallback: rendered HTML
            html = await page.content()
            await browser.close()

            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/p/\d{5,}", href) and _url_relevant(href, query):
                    return ("https://www.reliancedigital.in" + href if href.startswith("/") else href).split("?")[0]

    except Exception as e:
        logger.warning(f"[CrossSearch] Reliance error: {e}")
    return None


# ── Vijay Sales ───────────────────────────────────────────────────────────────

async def find_vijaysales_url(query: str) -> Optional[str]:
    """
    Vijay Sales with longer wait for JS rendering.
    Product URLs: /[brand-model-slug]  (no /p/ prefix in many cases)
    """
    search_url = f"https://www.vijaysales.com/search?q={quote_plus(query)}"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = await browser.new_context(
                user_agent=UA, locale="en-IN", viewport={"width": 1366, "height": 768}
            )
            page = await ctx.new_page()

            api_data = []

            async def handle_response(response):
                url = response.url
                if any(k in url for k in ["graphql", "search", "products", "algolia"]):
                    try:
                        body = await response.body()
                        data = json.loads(body)
                        api_data.append(data)
                    except Exception:
                        pass

            page.on("response", handle_response)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(6000)

            # Check intercepted GraphQL responses
            for data in api_data:
                items = (
                    data.get("data", {}).get("products", {}).get("items") or
                    data.get("products", {}).get("items") or []
                )
                for item in items:
                    url_key = item.get("url_key") or item.get("url_suffix", "").lstrip("/")
                    if url_key and _url_relevant(url_key, query):
                        await browser.close()
                        return f"https://www.vijaysales.com/{url_key}"

            # Fallback: rendered HTML product links
            html = await page.content()
            await browser.close()

            soup = BeautifulSoup(html, "lxml")
            # VS product URLs: /p/NNNNN/slug or /slug
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                combined = (href + " " + text).lower()
                # Must be a product link AND relevant to query
                if (re.search(r"^/p/\d+|^/[a-z0-9]+-[a-z0-9]+-[a-z0-9]+", href) and
                        _url_relevant(combined, query)):
                    full = "https://www.vijaysales.com" + href if href.startswith("/") else href
                    return full.split("?")[0]

    except Exception as e:
        logger.warning(f"[CrossSearch] VijayS error: {e}")
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

FINDERS = {
    "amazon":     find_amazon_url,
    "flipkart":   find_flipkart_url,
    "croma":      find_croma_url,
    "reliance":   find_reliance_url,
    "vijaysales": find_vijaysales_url,
}


async def cross_platform_search(
    title: str,
    brand: str = "",
    model_number: str = "",
    canonical_id: int = None,
    skip_platforms: list[str] = None,
) -> dict[str, Optional[str]]:
    skip = set(skip_platforms or [])
    query = build_search_query(title, brand, model_number)
    logger.info(f"[CrossSearch] Query='{query}' | skip={list(skip)}")

    # httpx searches run concurrently
    httpx_platforms = {p for p in ["amazon", "flipkart"] if p not in skip}
    tasks = {p: asyncio.create_task(FINDERS[p](query)) for p in httpx_platforms}

    # Playwright searches run concurrently (each has its own browser instance)
    pw_platforms = {p for p in ["croma", "reliance", "vijaysales"] if p not in skip}
    pw_tasks = {p: asyncio.create_task(FINDERS[p](query)) for p in pw_platforms}
    tasks.update(pw_tasks)

    results = {}
    for platform, task in tasks.items():
        try:
            url = await task
            results[platform] = url
            logger.info(f"[CrossSearch] {platform}: {'✓ ' + url[:70] if url else '✗ not found'}")
        except Exception as e:
            results[platform] = None
            logger.warning(f"[CrossSearch] {platform} error: {e}")

    return results


async def ingest_cross_platform(
    title: str,
    brand: str,
    model_number: str,
    canonical_id: int,
    skip_platforms: list[str],
):
    from scrapers import SCRAPERS
    import json_db

    urls = await cross_platform_search(title, brand, model_number, canonical_id, skip_platforms)

    for platform, url in urls.items():
        if not url or platform not in SCRAPERS:
            continue
        try:
            logger.info(f"[CrossSearch] Scraping {platform}: {url[:70]}")
            scraped = await SCRAPERS[platform].scrape(url)

            # Save even if out of stock (price=None), so we show all platforms in comparison
            json_db.upsert_store_product({
                "canonical_id":    canonical_id,
                "platform":        scraped.platform,
                "platform_id":     scraped.platform_id,
                "title":           scraped.title,
                "price":           scraped.price,
                "mrp":             scraped.mrp,
                "discount":        scraped.discount,
                "seller":          scraped.seller,
                "availability":    scraped.availability or ("Out of Stock" if not scraped.price else "Unknown"),
                "image_url":       scraped.image_url,
                "product_url":     scraped.product_url,
                "specs":           scraped.specs,
                "reviews_snippet": scraped.reviews_snippet,
            })
            price_str = f'₹{scraped.price:,.0f}' if scraped.price else 'Out of Stock'
            logger.info(f"[CrossSearch] ✓ {platform} saved — {price_str}")

        except Exception as e:
            logger.error(f"[CrossSearch] ✗ {platform} failed: {e}")
