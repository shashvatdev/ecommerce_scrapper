import json
import os
import time
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
CACHE_FILE = DATA_DIR / "search_cache.json"
CACHE_TTL = 12 * 3600  # 12 hours in seconds

_cache_lock = threading.Lock()

def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CACHE_FILE.exists():
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def normalize_url(url: str) -> str:
    """Normalize URL to create a consistent cache key (stripping tracking params)."""
    try:
        parsed = urlparse(url)
        # Reconstruct URL without query params to avoid tracking variations
        # Note: Flipkart uses ?pid= which is required. Amazon uses /dp/ASIN.
        # So we should be careful. We'll strip query params for Amazon, but keep for Flipkart.
        if "amazon" in parsed.netloc:
            # Amazon URLs usually look like /dp/ASIN
            # Let's just use the path
            return f"{parsed.netloc}{parsed.path}"
        elif "flipkart" in parsed.netloc:
            # Flipkart needs the query params, or at least pid=
            # We'll just lowercase the whole URL and strip tracking like otracker
            clean_url = url.split("&otracker")[0].split("&affid")[0]
            return clean_url.lower()
        else:
            return url.lower()
    except Exception:
        return url.lower()

def get_cached_result(url: str) -> Optional[Dict[str, Any]]:
    """Retrieve a cached comparison result if it exists and is not expired."""
    _ensure_dir()
    cache_key = normalize_url(url)
    
    with _cache_lock:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                
            entry = cache_data.get(cache_key)
            if entry:
                timestamp = entry.get("timestamp", 0)
                if time.time() - timestamp < CACHE_TTL:
                    logger.info(f"[Cache] HIT for key: {cache_key}")
                    return entry.get("data")
                else:
                    logger.info(f"[Cache] EXPIRED for key: {cache_key}")
                    # Clean up expired entry
                    del cache_data[cache_key]
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
            else:
                logger.info(f"[Cache] MISS for key: {cache_key}")
                
        except Exception as e:
            logger.error(f"[Cache] Error reading cache: {e}")
            
    return None

def save_to_cache(url: str, data: Dict[str, Any]):
    """Save a comparison result to the cache."""
    _ensure_dir()
    cache_key = normalize_url(url)
    
    with _cache_lock:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                
            cache_data[cache_key] = {
                "timestamp": time.time(),
                "data": data
            }
            
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"[Cache] SAVED for key: {cache_key}")
        except Exception as e:
            logger.error(f"[Cache] Error writing to cache: {e}")
