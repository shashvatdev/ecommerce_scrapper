"""
JSON File Database — replaces SQLite/PostgreSQL for local MVP.
Thread-safe reads/writes with file locking.
Schema:
  data/canonical_products.json
  data/store_products.json
  data/price_history.json
  data/ai_summaries.json
  data/price_alerts.json
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))

_locks: dict[str, threading.Lock] = {}


def _lock_for(name: str) -> threading.Lock:
    if name not in _locks:
        _locks[name] = threading.Lock()
    return _locks[name]


def _path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{name}.json"


def _read(name: str) -> list[dict]:
    p = _path(name)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(name: str, data: list[dict]) -> None:
    with open(_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _next_id(rows: list[dict]) -> int:
    return max((r["id"] for r in rows), default=0) + 1


def now() -> str:
    return datetime.utcnow().isoformat()


# ── Canonical Products ────────────────────────────────────────────────────────

def get_all_canonicals() -> list[dict]:
    with _lock_for("canonical_products"):
        return _read("canonical_products")


def get_canonical(canonical_id: int) -> Optional[dict]:
    for row in get_all_canonicals():
        if row["id"] == canonical_id:
            return row
    return None


def find_canonical_by_model_number(model_number: str) -> Optional[dict]:
    if not model_number:
        return None
    mn = model_number.strip().upper()
    for row in get_all_canonicals():
        if row.get("model_number", "").upper() == mn:
            return row
    return None


def find_canonical_by_gtin(gtin: str) -> Optional[dict]:
    if not gtin:
        return None
    for row in get_all_canonicals():
        if row.get("gtin") == gtin:
            return row
    return None


def create_canonical(data: dict) -> dict:
    with _lock_for("canonical_products"):
        rows = _read("canonical_products")
        data["id"] = _next_id(rows)
        data.setdefault("created_at", now())
        data.setdefault("updated_at", now())
        rows.append(data)
        _write("canonical_products", rows)
        return data


def update_canonical(canonical_id: int, updates: dict) -> Optional[dict]:
    with _lock_for("canonical_products"):
        rows = _read("canonical_products")
        for row in rows:
            if row["id"] == canonical_id:
                row.update(updates)
                row["updated_at"] = now()
                _write("canonical_products", rows)
                return row
        return None


def search_canonicals(query: str) -> list[dict]:
    """Simple full-text search over brand + model_name."""
    q = query.lower()
    results = []
    for row in get_all_canonicals():
        text = f"{row.get('brand', '')} {row.get('model_name', '')}".lower()
        if all(word in text for word in q.split()):
            results.append(row)
    return results[:20]


# ── Store Products ────────────────────────────────────────────────────────────

def get_all_store_products() -> list[dict]:
    with _lock_for("store_products"):
        return _read("store_products")


def get_store_products_for_canonical(canonical_id: int) -> list[dict]:
    return [r for r in get_all_store_products() if r.get("canonical_id") == canonical_id]


def get_store_product(platform: str, platform_id: str) -> Optional[dict]:
    for row in get_all_store_products():
        if row["platform"] == platform and row["platform_id"] == platform_id:
            return row
    return None


def upsert_store_product(data: dict) -> dict:
    """Insert or update store product. Always appends price history."""
    with _lock_for("store_products"):
        rows = _read("store_products")
        for row in rows:
            if row["platform"] == data["platform"] and row["platform_id"] == data["platform_id"]:
                # Update existing
                old_price = row.get("price")
                row.update(data)
                row["last_scraped"] = now()
                _write("store_products", rows)
                # Record price if changed
                if data.get("price") and data["price"] != old_price:
                    _append_price_history(row["id"], data["price"])
                return row
        # Insert new
        data["id"] = _next_id(rows)
        data["last_scraped"] = now()
        rows.append(data)
        _write("store_products", rows)
        if data.get("price"):
            _append_price_history(data["id"], data["price"])
        return data


# ── Price History ─────────────────────────────────────────────────────────────

def _append_price_history(store_id: int, price: float) -> None:
    with _lock_for("price_history"):
        rows = _read("price_history")
        rows.append({
            "id": _next_id(rows),
            "store_id": store_id,
            "price": price,
            "recorded_at": now(),
        })
        _write("price_history", rows)


def get_price_history(store_id: int) -> list[dict]:
    with _lock_for("price_history"):
        rows = _read("price_history")
    return [r for r in rows if r["store_id"] == store_id]


def get_price_history_for_canonical(canonical_id: int) -> list[dict]:
    store_ids = {r["id"] for r in get_store_products_for_canonical(canonical_id)}
    with _lock_for("price_history"):
        rows = _read("price_history")
    return sorted(
        [r for r in rows if r["store_id"] in store_ids],
        key=lambda x: x["recorded_at"]
    )


# ── AI Summaries ──────────────────────────────────────────────────────────────

def get_ai_summary(canonical_id: int) -> Optional[dict]:
    with _lock_for("ai_summaries"):
        rows = _read("ai_summaries")
    for row in rows:
        if row["canonical_id"] == canonical_id:
            # Check if expired (7 days)
            if row.get("expires_at") and row["expires_at"] > now():
                return row
    return None


def save_ai_summary(canonical_id: int, data: dict) -> dict:
    from datetime import timedelta
    with _lock_for("ai_summaries"):
        rows = _read("ai_summaries")
        for row in rows:
            if row["canonical_id"] == canonical_id:
                row.update(data)
                row["generated_at"] = now()
                row["expires_at"] = (datetime.utcnow() + timedelta(days=7)).isoformat()
                _write("ai_summaries", rows)
                return row
        entry = {
            "id": _next_id(rows),
            "canonical_id": canonical_id,
            "generated_at": now(),
            "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            **data,
        }
        rows.append(entry)
        _write("ai_summaries", rows)
        return entry


# ── Price Alerts ──────────────────────────────────────────────────────────────

def get_all_alerts() -> list[dict]:
    with _lock_for("price_alerts"):
        return _read("price_alerts")


def create_alert(data: dict) -> dict:
    with _lock_for("price_alerts"):
        rows = _read("price_alerts")
        data["id"] = _next_id(rows)
        data["triggered"] = False
        data["created_at"] = now()
        rows.append(data)
        _write("price_alerts", rows)
        return data


def mark_alert_triggered(alert_id: int) -> None:
    with _lock_for("price_alerts"):
        rows = _read("price_alerts")
        for row in rows:
            if row["id"] == alert_id:
                row["triggered"] = True
                row["triggered_at"] = now()
        _write("price_alerts", rows)


def get_pending_alerts() -> list[dict]:
    return [r for r in get_all_alerts() if not r.get("triggered")]


# ── Scraper Queue (for crawler) ───────────────────────────────────────────────

def get_all_urls_to_crawl() -> list[dict]:
    """Return all store_products with platform + product_url for recrawling."""
    return [
        {"platform": r["platform"], "url": r["product_url"], "store_id": r["id"]}
        for r in get_all_store_products()
        if r.get("product_url")
    ]


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    canonicals = get_all_canonicals()
    stores = get_all_store_products()
    alerts = get_pending_alerts()

    prices = [r["price"] for r in stores if r.get("price")]
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0

    platform_counts: dict[str, int] = {}
    for r in stores:
        platform_counts[r["platform"]] = platform_counts.get(r["platform"], 0) + 1

    return {
        "total_products": len(canonicals),
        "total_listings": len(stores),
        "platform_counts": platform_counts,
        "average_price": avg_price,
        "pending_alerts": len(alerts),
    }
