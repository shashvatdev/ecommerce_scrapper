"""
Crawler Pipeline — background price refresh engine.
APScheduler runs workers every 4 hours.
Processes a queue of store_product URLs and updates prices.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import json_db
from scrapers import SCRAPERS
from product_matcher import find_or_create_canonical

logger = logging.getLogger(__name__)


class ScrapeMetrics:
    def __init__(self):
        self.success = 0
        self.failure = 0
        self.total_ms = 0.0
        self.last_run: Optional[str] = None

    def record(self, platform: str, url: str, success: bool, duration_ms: float):
        if success:
            self.success += 1
        else:
            self.failure += 1
        self.total_ms += duration_ms
        logger.info(
            f"[Crawler] {'✓' if success else '✗'} [{platform}] {url[:60]} "
            f"({duration_ms:.0f}ms)"
        )

    @property
    def success_rate(self) -> float:
        total = self.success + self.failure
        return round(self.success / total * 100, 1) if total else 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "failure": self.failure,
            "success_rate": self.success_rate,
            "avg_duration_ms": round(self.total_ms / max(self.success + self.failure, 1), 1),
            "last_run": self.last_run,
        }


metrics = ScrapeMetrics()
queue: deque = deque()
_scheduler: Optional[AsyncIOScheduler] = None


# ── Queue Management ──────────────────────────────────────────────────────────

def enqueue_url(platform: str, url: str, store_id: Optional[int] = None):
    """Add a single URL to the crawler queue."""
    queue.append({"platform": platform, "url": url, "store_id": store_id})


def enqueue_all():
    """Enqueue all known store product URLs for refresh."""
    urls = json_db.get_all_urls_to_crawl()
    for item in urls:
        queue.append(item)
    logger.info(f"[Crawler] Enqueued {len(urls)} URLs for refresh")
    metrics.last_run = datetime.utcnow().isoformat()


# ── Single URL Refresh ────────────────────────────────────────────────────────

async def refresh_url(platform: str, url: str, store_id: Optional[int] = None):
    """Scrape one URL and update the database."""
    if platform not in SCRAPERS:
        logger.warning(f"[Crawler] Unknown platform: {platform}")
        return

    start = asyncio.get_event_loop().time()
    try:
        scraped = await SCRAPERS[platform].scrape(url)

        # Update or insert store product
        store_data = {
            "platform": scraped.platform,
            "platform_id": scraped.platform_id,
            "title": scraped.title,
            "price": scraped.price,
            "mrp": scraped.mrp,
            "discount": scraped.discount,
            "seller": scraped.seller,
            "availability": scraped.availability,
            "image_url": scraped.image_url,
            "product_url": scraped.product_url,
            "specs": scraped.specs,
            "reviews_snippet": scraped.reviews_snippet,
        }

        # Link to canonical
        canon = find_or_create_canonical(scraped)
        store_data["canonical_id"] = canon["id"]

        json_db.upsert_store_product(store_data)

        # Check price alerts after update
        from alerts import check_alerts_for_canonical
        await check_alerts_for_canonical(canon["id"])

        duration_ms = (asyncio.get_event_loop().time() - start) * 1000
        metrics.record(platform, url, True, duration_ms)

    except Exception as e:
        duration_ms = (asyncio.get_event_loop().time() - start) * 1000
        metrics.record(platform, url, False, duration_ms)
        logger.error(f"[Crawler] Error scraping {platform} {url}: {e}")


# ── Batch Processor ───────────────────────────────────────────────────────────

async def process_queue(batch_size: int = 5):
    """Process up to batch_size items from the queue."""
    if not queue:
        return

    batch = []
    for _ in range(min(batch_size, len(queue))):
        batch.append(queue.popleft())

    logger.info(f"[Crawler] Processing batch of {len(batch)} (queue remaining: {len(queue)})")
    await asyncio.gather(*[
        refresh_url(item["platform"], item["url"], item.get("store_id"))
        for item in batch
    ], return_exceptions=True)


# ── Ingestion (New Product URL) ───────────────────────────────────────────────

async def ingest_url(url: str, platform: str) -> dict:
    """
    Scrape a NEW product URL, match to canonical, save to DB.
    Returns the canonical product dict.
    """
    logger.info(f"[Crawler] Ingesting new URL: {platform} — {url[:80]}")
    scraped = await SCRAPERS[platform].scrape(url)

    canon = find_or_create_canonical(scraped)

    store_data = {
        "canonical_id": canon["id"],
        "platform": scraped.platform,
        "platform_id": scraped.platform_id,
        "title": scraped.title,
        "price": scraped.price,
        "mrp": scraped.mrp,
        "discount": scraped.discount,
        "seller": scraped.seller,
        "availability": scraped.availability,
        "image_url": scraped.image_url,
        "product_url": scraped.product_url,
        "specs": scraped.specs,
        "reviews_snippet": scraped.reviews_snippet,
    }
    json_db.upsert_store_product(store_data)

    # Update canonical image if not set
    if not canon.get("image_url") and scraped.image_url:
        json_db.update_canonical(canon["id"], {"image_url": scraped.image_url})
        canon["image_url"] = scraped.image_url

    return canon


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = AsyncIOScheduler()

    # Refresh all prices every 4 hours
    _scheduler.add_job(enqueue_all, "interval", hours=4, id="enqueue_all")

    # Process queue every 60 seconds (5 items per cycle = ~300/hour)
    import asyncio
    loop = asyncio.get_event_loop()
    _scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(process_queue(), loop),
        "interval",
        seconds=60,
        id="process_queue",
    )

    _scheduler.start()
    logger.info("[Crawler] Scheduler started (refresh every 4h, process every 60s)")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("[Crawler] Scheduler stopped")
