"""
Price Drop Alerts — check and notify when product price hits target.
Simple in-app system (no external email for now).
Triggered after every crawler refresh.
"""

import logging
from typing import Optional

import json_db

logger = logging.getLogger(__name__)


# ── Alert Checker ─────────────────────────────────────────────────────────────

async def check_alerts_for_canonical(canonical_id: int):
    """Run after a price update — check if any alerts should trigger."""
    pending = json_db.get_pending_alerts()
    canon_alerts = [a for a in pending if a["canonical_id"] == canonical_id]

    if not canon_alerts:
        return

    stores = json_db.get_store_products_for_canonical(canonical_id)
    canon = json_db.get_canonical(canonical_id)

    for alert in canon_alerts:
        target = alert.get("target_price")
        platform_filter = alert.get("platform")  # None = any platform

        # Find matching store with price below target
        for store in stores:
            if platform_filter and store["platform"] != platform_filter:
                continue
            current_price = store.get("price")
            if current_price and target and current_price <= target:
                _trigger_alert(alert, store, canon)
                break


def _trigger_alert(alert: dict, store: dict, canon: dict):
    """Mark alert as triggered and log the notification."""
    product_name = canon.get("model_name", "Unknown Product") if canon else "Unknown Product"
    platform = store.get("platform", "").title()
    price = store.get("price", 0)
    target = alert.get("target_price", 0)

    logger.info(
        f"🔔 PRICE ALERT TRIGGERED!\n"
        f"   Product: {product_name}\n"
        f"   Platform: {platform}\n"
        f"   Current Price: ₹{price:,.0f}\n"
        f"   Target Price: ₹{target:,.0f}\n"
        f"   Email: {alert.get('email', 'N/A')}\n"
        f"   URL: {store.get('product_url', '')}"
    )

    # Save to triggered alerts list in DB
    json_db.mark_alert_triggered(alert["id"])

    # Store triggered notification in a notifications list
    _save_notification({
        "alert_id": alert["id"],
        "canonical_id": alert["canonical_id"],
        "product_name": product_name,
        "platform": store.get("platform"),
        "current_price": price,
        "target_price": target,
        "product_url": store.get("product_url"),
        "email": alert.get("email"),
    })


def _save_notification(data: dict):
    """Append to notifications.json for the frontend to display."""
    import json_db as db
    # Reuse the generic append pattern
    from pathlib import Path
    import json
    from json_db import DATA_DIR, _lock_for, _read, _write, _next_id, now

    with _lock_for("notifications"):
        rows = _read("notifications")
        data["id"] = _next_id(rows)
        data["created_at"] = now()
        data["seen"] = False
        rows.append(data)
        _write("notifications", rows)


# ── Alert API Helpers ─────────────────────────────────────────────────────────

def create_price_alert(canonical_id: int, target_price: float,
                       email: str, platform: Optional[str] = None) -> dict:
    """Create a new price alert. Returns the created alert."""
    canon = json_db.get_canonical(canonical_id)
    if not canon:
        raise ValueError(f"Canonical product #{canonical_id} not found")

    alert = json_db.create_alert({
        "canonical_id": canonical_id,
        "target_price": target_price,
        "email": email,
        "platform": platform,  # None = any platform
    })

    logger.info(
        f"[Alerts] Created alert: '{canon['model_name']}' @ ₹{target_price:,.0f} "
        f"→ {email} (platform: {platform or 'any'})"
    )
    return alert


def get_notifications(limit: int = 20) -> list[dict]:
    """Get recent price drop notifications."""
    from json_db import _read
    rows = _read("notifications")
    return sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]


def mark_notification_seen(notification_id: int):
    from json_db import _lock_for, _read, _write
    with _lock_for("notifications"):
        rows = _read("notifications")
        for row in rows:
            if row["id"] == notification_id:
                row["seen"] = True
        _write("notifications", rows)
