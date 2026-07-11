"""
AI Engine — Groq-powered product summaries.
Uses llama-3.3-70b-versatile for rich Pros/Cons/Verdict generation.

Flow:
  1. Collect review snippets (from scraped store products)
  2. Cluster/deduplicate before sending to LLM (saves tokens)
  3. Call Groq API
  4. Parse structured response
  5. Cache result in JSON DB (7-day TTL)
"""

import os
import json
import logging
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

import json_db

load_dotenv()

logger = logging.getLogger(__name__)

# ── Groq Client ───────────────────────────────────────────────────────────────
_client: Optional[Groq] = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set in .env")
        _client = Groq(api_key=api_key)
    return _client

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


# ── Review Deduplication ──────────────────────────────────────────────────────

def _deduplicate_reviews(reviews: list[str], max_reviews: int = 20) -> list[str]:
    """Keep unique, non-empty reviews. Truncate each to 200 chars."""
    seen = set()
    unique = []
    for r in reviews:
        r = r.strip()
        if not r or len(r) < 20:
            continue
        key = r[:80].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r[:200])
        if len(unique) >= max_reviews:
            break
    return unique


# ── Prompt Builder ────────────────────────────────────────────────────────────

def _build_prompt(product_title: str, brand: str, category: str, reviews: list[str], store_prices: list[dict]) -> str:
    price_lines = "\n".join(
        f"  - {s['platform'].title()}: ₹{s['price']:,.0f}" if s.get("price") else f"  - {s['platform'].title()}: Price not available"
        for s in store_prices
    )
    review_block = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(reviews)) if reviews else "  No reviews available."

    return f"""You are a product review expert. Analyze the following product and generate a structured buying guide.

Product: {product_title}
Brand: {brand or 'Unknown'}
Category: {category or 'Electronics'}

Current Prices:
{price_lines}

Customer Review Snippets:
{review_block}

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{{
  "pros": ["pro 1", "pro 2", "pro 3", "pro 4", "pro 5"],
  "cons": ["con 1", "con 2", "con 3"],
  "verdict": "One paragraph buying verdict (2-3 sentences max). Be direct and opinionated.",
  "best_for": ["use case 1", "use case 2"],
  "avoid_if": ["reason 1", "reason 2"],
  "ai_score": 7.5,
  "value_rating": "Good Value",
  "summary_one_line": "Single sentence that captures the essence of this product."
}}

Rules:
- ai_score is 1.0 to 10.0 based on overall quality/value
- value_rating is one of: "Exceptional Value", "Good Value", "Fair Value", "Overpriced"
- Be honest, balanced, and specific — not generic
- Base pros/cons on actual reviews when available, otherwise on product category knowledge
"""


# ── Main AI Summary Function ──────────────────────────────────────────────────

async def generate_ai_summary(canonical_id: int) -> dict:
    """
    Generate AI summary for a canonical product.
    Returns cached version if available and not expired.
    """
    # Check cache first
    cached = json_db.get_ai_summary(canonical_id)
    if cached:
        logger.info(f"[AI] Cache hit for canonical #{canonical_id}")
        return cached

    canon = json_db.get_canonical(canonical_id)
    if not canon:
        raise ValueError(f"Canonical product #{canonical_id} not found")

    # Gather store data
    stores = json_db.get_store_products_for_canonical(canonical_id)
    reviews = []
    for store in stores:
        reviews.extend(store.get("reviews_snippet", []))

    unique_reviews = _deduplicate_reviews(reviews)
    store_prices = [s for s in stores if s.get("price")]

    logger.info(
        f"[AI] Generating summary for '{canon['model_name']}' "
        f"({len(unique_reviews)} reviews, {len(store_prices)} stores)"
    )

    prompt = _build_prompt(
        product_title=canon.get("model_name", ""),
        brand=canon.get("brand", ""),
        category=canon.get("category", ""),
        reviews=unique_reviews,
        store_prices=store_prices,
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a concise, expert product analyst. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        # Validate required fields
        summary = {
            "pros":             parsed.get("pros", [])[:6],
            "cons":             parsed.get("cons", [])[:4],
            "verdict":          parsed.get("verdict", ""),
            "best_for":         parsed.get("best_for", []),
            "avoid_if":         parsed.get("avoid_if", []),
            "ai_score":         float(parsed.get("ai_score", 0.0)),
            "value_rating":     parsed.get("value_rating", ""),
            "summary_one_line": parsed.get("summary_one_line", ""),
        }

        saved = json_db.save_ai_summary(canonical_id, summary)
        logger.info(f"[AI] Summary generated and cached for canonical #{canonical_id}")
        return saved

    except json.JSONDecodeError as e:
        logger.error(f"[AI] Failed to parse Groq response: {e}")
        raise
    except Exception as e:
        logger.error(f"[AI] Groq API error: {e}")
        raise


async def generate_search_summary(query: str, results: list[dict]) -> str:
    """Quick one-line summary for search results page."""
    if not results:
        return f"No products found for '{query}'."

    try:
        client = _get_client()
        names = [r.get("model_name", "") for r in results[:5]]
        prompt = f"User searched for '{query}'. Top results: {', '.join(names)}. Write ONE sentence (max 15 words) helping them pick."

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Use faster model for quick summaries
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=60,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"[AI] Quick summary failed: {e}")
        return f"Found {len(results)} products matching '{query}'."
