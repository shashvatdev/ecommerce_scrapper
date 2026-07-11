"""
Simplified Live Compare API
POST /compare  →  { amazon: {...}, flipkart: {...} }
"""
import asyncio
import logging
import re
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scrapers.amazon import AmazonScraper
from scrapers.flipkart import FlipkartScraper
from cross_search import find_amazon_url, find_flipkart_url, build_search_query
from llm_matcher import find_best_match_via_llm
from cache import get_cached_result, save_to_cache

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting compare API...")
    yield


app = FastAPI(title="Price Compare API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

amazon_scraper   = AmazonScraper()
flipkart_scraper = FlipkartScraper()

SCRAPERS = {"amazon": amazon_scraper, "flipkart": flipkart_scraper}


# ── URL Detection ─────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    url = url.lower()
    if "amazon" in url:   return "amazon"
    if "flipkart" in url: return "flipkart"
    return "unknown"


def clean_url(url: str, platform: str) -> str:
    """Return canonical URL for scraping."""
    import re
    if platform == "amazon":
        m = re.search(r"amazon\.in/(?:[^/]+/)?dp/([A-Z0-9]{10})", url)
        if m:
            return f"https://www.amazon.in/dp/{m.group(1)}"
    if platform == "flipkart":
        m = re.search(r"(https://www\.flipkart\.com/[^/?]+/p/[^/?]+)", url)
        pid = re.search(r"pid=([A-Z0-9]+)", url)
        if m:
            return f"{m.group(1)}?pid={pid.group(1)}" if pid else m.group(1)
    return url


# ── Serialize Scraped Result ──────────────────────────────────────────────────

def serialize(scraped) -> dict:
    if scraped is None:
        return {"found": False}
    return {
        "found":        True,
        "title":        scraped.title or "",
        "price":        scraped.price,
        "mrp":          scraped.mrp,
        "discount":     scraped.discount,
        "rating":       scraped.rating,
        "review_count": scraped.review_count,
        "availability": scraped.availability or "Unknown",
        "image_url":    scraped.image_url,
        "product_url":  scraped.product_url,
        "seller":       scraped.seller,
        "specs":        scraped.specs or {},
        "reviews_snippet": scraped.reviews_snippet or [],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    url: str
    force_refresh: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/compare")
async def compare(req: CompareRequest):
    url = req.url.strip()
    platform = detect_platform(url)

    if platform == "unknown":
        raise HTTPException(400, "Only Amazon and Flipkart URLs are supported")
        
    # Check cache first
    if not req.force_refresh:
        cached_data = get_cached_result(url)
        if cached_data:
            cached_data["cached"] = True
            return cached_data

    canonical = clean_url(url, platform)
    other_platform = "flipkart" if platform == "amazon" else "amazon"

    logger.info(f"[Compare] Scraping {platform}: {canonical[:70]}")

    # Step 1: Scrape the provided URL
    try:
        source_result = await SCRAPERS[platform].scrape(canonical)
    except Exception as e:
        raise HTTPException(500, f"Failed to scrape {platform}: {str(e)}")

    # Step 2: Build search query from scraped title
    query = build_search_query(
        source_result.title or "",
        source_result.brand or "",
        source_result.model_number or "",
    )
    logger.info(f"[Compare] Searching {other_platform} for: '{query}'")

    # Step 3: Find + scrape other platform concurrently (up to 5 candidates)
    finder = find_flipkart_url if other_platform == "flipkart" else find_amazon_url
    candidate_urls = await finder(query)
    
    if not candidate_urls:
        logger.info(f"[Compare] {other_platform}: not found in search")
        other_result = None
        best_match_info = {}
    else:
        logger.info(f"[Compare] Found {len(candidate_urls)} candidates on {other_platform}")
        
        async def scrape_candidate(c_url):
            try:
                res = await SCRAPERS[other_platform].scrape(c_url)
                return res
            except Exception as e:
                logger.warning(f"[Compare] Error scraping candidate {c_url}: {e}")
                return None
                
        # Scrape all concurrently
        candidate_results = await asyncio.gather(*[scrape_candidate(u) for u in candidate_urls])
        
        # Use LLM to find the best match
        best_candidate, best_match_info = await find_best_match_via_llm(source_result, candidate_results)
        
        if best_candidate:
            logger.info(f"[Compare] LLM selected candidate '{best_candidate.title[:30]}...' with {best_match_info.get('confidence')}% confidence. Reason: {best_match_info.get('llm_reasoning')}")
            other_result = best_candidate
        else:
            logger.warning(f"[Compare] LLM rejected all candidates. Reason: {best_match_info.get('rejection_reason')}")
            other_result = None

    # Assign to correct keys
    results = {
        "matched": other_result is not None,
        "confidence": best_match_info.get("confidence", 0),
        "comparison": best_match_info,
        "query_platform": platform,
        "query":          query,
        "amazon":         serialize(source_result if platform == "amazon" else other_result),
        "flipkart":       serialize(source_result if platform == "flipkart" else other_result),
    }

    # Savings calculation
    ap = results["amazon"].get("price")
    fp = results["flipkart"].get("price")
    if ap and fp:
        results["cheaper_store"] = "amazon" if ap < fp else "flipkart"
        results["price_difference"] = abs(ap - fp)
    else:
        results["cheaper_store"] = None
        results["price_difference"] = None
        
    results["cached"] = False
    
    # Save to cache
    save_to_cache(url, results)

    return results
