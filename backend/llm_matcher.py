import os
import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Initialize Groq Client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
# Use the versatile model since vision is decommissioned on Groq
MODEL_NAME = "llama-3.3-70b-versatile"

async def find_best_match_via_llm(source_product: Any, candidates: List[Any]) -> Tuple[Optional[Any], Dict[str, Any]]:
    """
    Uses the Groq LLM API to evaluate the candidates against the source product.
    Returns (best_candidate, match_info_dict).
    """
    if not client:
        logger.error("[LLM Matcher] GROQ_API_KEY is not set.")
        return None, {"rejection_reason": "LLM API Key missing"}
        
    if not source_product or not candidates:
        return None, {"rejection_reason": "Missing source or candidates"}

    # Filter out None candidates
    valid_candidates = [c for c in candidates if c is not None]
    if not valid_candidates:
        return None, {"rejection_reason": "No valid candidates to evaluate"}

    # Construct the Prompt
    sys_prompt = (
        "You are an expert e-commerce product matching AI. Your job is to find the EXACT same product "
        "across different platforms. You must ensure the core attributes match: "
        "Brand, Model, RAM, Storage (ROM), Color, and variant (e.g. Pro, Max, Plus). "
        "Do not penalize minor formatting differences (e.g., '128GB' vs '128 GB', or 'RAM' missing from title but present in specs). "
        "Different colors of the exact same phone/model can still be considered a match, but penalize the confidence slightly. "
        "If it is a mobile case or accessory, ensure it is for the exact same phone model. "
        "Respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        '  "best_match_index": <int> (the index of the matching candidate, or -1 if NONE match exactly),\n'
        '  "confidence": <int> (0 to 100),\n'
        '  "reason": "<string> (Explain why you picked it or why you rejected all)"\n'
        "}"
    )
    
    # Build text representation of source
    src_text = f"Source Product:\nTitle: {source_product.title}\nBrand: {source_product.brand}\nSpecs: {source_product.specs}"
    
    # Build text representation of candidates
    cands_text = "Target Candidates:\n"
    for i, c in enumerate(valid_candidates):
        cands_text += f"\n--- Candidate {i} ---\nTitle: {c.title}\nBrand: {c.brand}\nSpecs: {c.specs}\n"

    # Construct the message content payload
    content = [
        {"type": "text", "text": src_text},
        {"type": "text", "text": cands_text},
        {"type": "text", "text": "Evaluate the candidates against the source product. Base your decision on text attributes. Return JSON only."}
    ]
        
    # Optional: Add candidate images if we want it to visually compare them.
    # To save tokens/rate limits, we'll only send the first candidate's image if available.
    # Actually, sending all candidate images might exceed limits. We'll stick to source image + text for candidates, 
    # which is usually enough since candidate text is highly descriptive.
    
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "text": sys_prompt} if not hasattr(client.chat.completions, 'create') else {"role": "system", "content": sys_prompt},
                {"role": "user", "content": content}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=500
        )
        
        # Parse the JSON response
        result_text = response.choices[0].message.content
        logger.info(f"[LLM Matcher] Groq Response: {result_text}")
        
        result_json = json.loads(result_text)
        
        best_index = result_json.get("best_match_index", -1)
        confidence = result_json.get("confidence", 0)
        reason = result_json.get("reason", "No reason provided")
        
        if best_index != -1 and 0 <= best_index < len(valid_candidates) and confidence >= 70:
            match_info = {
                "confidence": confidence,
                "rejection_reason": None,
                "llm_reasoning": reason
            }
            return valid_candidates[best_index], match_info
        else:
            match_info = {
                "confidence": confidence,
                "rejection_reason": reason,
                "llm_reasoning": reason
            }
            return None, match_info
            
    except Exception as e:
        logger.error(f"[LLM Matcher] Error calling Groq API: {e}")
        return None, {"rejection_reason": f"LLM API Error: {str(e)}"}
