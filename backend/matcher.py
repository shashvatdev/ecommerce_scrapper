import re
import logging
from rapidfuzz import fuzz
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

def normalize_title(title: str) -> str:
    """Normalize the title for comparison."""
    if not title:
        return ""
    
    # Remove marketing fluff and common words
    stopwords = [
        "best seller", "limited offer", "new launch", "assured",
        "free delivery", "bank offer", "no cost emi", "amazon choice",
        "flipkart assured", "official", "latest", "smartphone", "mobile phone",
        "mobile", "phone", "smart", "with", "and", "or", "in", "the", "a", "an",
        "online at best price", "online at best price in india"
    ]
    
    t = title.lower()
    for word in stopwords:
        t = re.sub(rf"\b{word}\b", "", t)
        
    # Standardize GB/TB
    t = re.sub(r"(\d+)\s*gb", r"\1gb", t)
    t = re.sub(r"(\d+)\s*tb", r"\1tb", t)
    
    # Remove punctuation except alphanumeric and spaces
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    
    # Remove duplicate spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t

def extract_attributes(title: str, specs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract RAM, Storage, and Color from normalized title and specs."""
    attrs = {
        "ram": None,
        "storage": None,
        "color": None
    }
    
    norm_title = normalize_title(title)
    
    # Try to extract from specs first
    for k, v in specs.items():
        k_lower = k.lower()
        v_lower = str(v).lower()
        if "ram" in k_lower:
            m = re.search(r"(\d+)\s*gb", v_lower)
            if m: attrs["ram"] = m.group(1) + "gb"
        elif "storage" in k_lower or "internal" in k_lower or "rom" in k_lower:
            m = re.search(r"(\d+)\s*(gb|tb)", v_lower)
            if m: attrs["storage"] = m.group(1) + m.group(2)
        elif "color" in k_lower:
            attrs["color"] = v_lower.split()[0] # Take first word of color
            
    # Fallback to extracting from normalized title
    if not attrs["ram"]:
        # Look for patterns like "8gb ram" or just "8gb" if another is storage
        m = re.findall(r"(\d+)gb", norm_title)
        if len(m) >= 2:
            # Usually smaller is RAM, larger is storage (e.g., 8gb 128gb)
            nums = sorted([int(x) for x in m])
            attrs["ram"] = f"{nums[0]}gb"
            if not attrs["storage"]:
                attrs["storage"] = f"{nums[1]}gb"
        elif len(m) == 1:
            # Hard to tell if it's RAM or storage without context, but often phones advertise storage
            val = int(m[0])
            if val <= 16:
                attrs["ram"] = f"{val}gb"
            else:
                attrs["storage"] = f"{val}gb"
                
    if not attrs["storage"]:
        m = re.search(r"(\d+)tb", norm_title)
        if m:
            attrs["storage"] = m.group(1) + "tb"
            
    # Simple color extraction fallback (very basic list)
    if not attrs["color"]:
        colors = ["black", "white", "blue", "red", "green", "yellow", "purple", "gray", "grey", "silver", "gold", "pink", "cyan", "magenta", "emerald"]
        for c in colors:
            if c in norm_title.split():
                attrs["color"] = c
                break
                
    return attrs

def calculate_match_score(source_product: Any, target_product: Any) -> Tuple[int, Dict[str, Any]]:
    """
    Calculate a match score between two scraped products.
    Returns (final_score, comparison_details).
    """
    if not source_product or not target_product:
        return 0, {}
        
    source_title = source_product.title or ""
    target_title = target_product.title or ""
    
    if not source_title or not target_title:
        return 0, {}

    norm_src = normalize_title(source_title)
    norm_tgt = normalize_title(target_title)
    
    src_attrs = extract_attributes(source_title, source_product.specs or {})
    tgt_attrs = extract_attributes(target_title, target_product.specs or {})
    
    score = 0
    comparison = {
        "brand": False,
        "model": False,
        "storage": False,
        "ram": False,
        "color": False,
        "title_similarity": 0,
        "rejection_reason": None
    }
    
    # 1. Brand Match (+30)
    # Simple check if first word of source title is in target title
    src_words = norm_src.split()
    tgt_words = norm_tgt.split()
    
    if src_words and tgt_words and (src_words[0] in tgt_words[:4] or (len(src_words) > 1 and src_words[0] + src_words[1] in norm_tgt)):
        score += 30
        comparison["brand"] = True
        
    # 2. Model Match (+30)
    # We'll use title similarity for model match if we don't have explicit models
    if len(src_words) > 1:
        # Check if the second word (usually model family like "Galaxy", "iPhone", "Nord") is present
        if src_words[1] in tgt_words:
            score += 30
            comparison["model"] = True
    elif len(src_words) == 1:
        if src_words[0] in tgt_words:
            score += 30
            comparison["model"] = True
            
    # 3. Storage Match (+15)
    if src_attrs["storage"]:
        if tgt_attrs["storage"] == src_attrs["storage"]:
            score += 15
            comparison["storage"] = True
        else:
            comparison["rejection_reason"] = f"Storage mismatch: {src_attrs['storage']} vs {tgt_attrs['storage']}"
            return 0, comparison # Hard reject
    else:
        # Not applicable (e.g., accessories)
        score += 15 
        
    # 4. RAM Match (+10)
    if src_attrs["ram"]:
        if tgt_attrs["ram"] == src_attrs["ram"]:
            score += 10
            comparison["ram"] = True
        else:
            comparison["rejection_reason"] = f"RAM mismatch: {src_attrs['ram']} vs {tgt_attrs['ram']}"
            return 0, comparison # Hard reject
    else:
        # Not applicable
        score += 10
        
    # 5. Color Match (+5)
    if src_attrs["color"] and tgt_attrs["color"]:
        if src_attrs["color"] == tgt_attrs["color"]:
            score += 5
            comparison["color"] = True
        else:
            # Soft penalty for different color, don't reject
            score -= 2
    else:
        score += 5
            
    # 6. Title Similarity (+10 scaled)
    title_sim = fuzz.token_set_ratio(norm_src, norm_tgt)
    comparison["title_similarity"] = round(title_sim)
    
    # Scale title similarity to 10 points
    sim_score = (title_sim / 100.0) * 10
    score += sim_score
    
    # Check for hard rejections (Generation/Variant mismatch like "Plus" vs non-"Plus")
    variants = ["plus", "pro", "max", "ultra", "lite", "fe"]
    for v in variants:
        v_in_src = v in src_words
        v_in_tgt = v in tgt_words
        if v_in_src != v_in_tgt:
            comparison["rejection_reason"] = f"Variant mismatch detected (e.g., {v})"
            return 0, comparison
            
    return round(score), comparison
