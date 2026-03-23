"""
Evidence Badge System for Confidence UI.
Provides evidence strength scoring and visual badges for search results.
"""
from __future__ import annotations
from typing import List, Dict, Any

EVIDENCE_WEIGHTS = {
    "pi": 1.00,
    "prescribing_information": 1.00,
    "guideline": 0.95,
    "guidelines": 0.95,
    "rct": 0.80,
    "randomized_controlled_trial": 0.80,
    "meta_analysis": 0.85,
    "systematic_review": 0.75,
    "review": 0.55,
    "cohort": 0.50,
    "case_series": 0.45,
    "textbook": 0.45,
    "case_report": 0.40,
    "expert_opinion": 0.35,
    "other": 0.35,
}

BADGE_THRESHOLDS = {
    "high": 0.85,
    "moderate": 0.65,
    "low": 0.0
}


def get_source_weight(source_type: str) -> float:
    """Get evidence weight for a source type."""
    if not source_type:
        return 0.30
    normalized = source_type.lower().strip().replace(" ", "_").replace("-", "_")
    return EVIDENCE_WEIGHTS.get(normalized, 0.30)


def compute_evidence_badge(chunks: List[dict]) -> Dict[str, Any]:
    """
    Compute evidence strength score and badge for a set of chunks.
    
    Returns:
        {
            "score": 0.0-1.0,
            "badge": "High" | "Moderate" | "Low",
            "badge_color": "green" | "yellow" | "red",
            "types": {"rct": 2, "review": 3, ...},
            "why": "explanation string",
            "unique_sources": 5
        }
    """
    if not chunks:
        return {
            "score": 0.10,
            "badge": "Low",
            "badge_color": "red",
            "types": {},
            "why": "No retrievable sources",
            "unique_sources": 0
        }
    
    seen_keys = set()
    strongest = 0.0
    total_weight = 0.0
    type_counts: Dict[str, int] = {}
    
    for chunk in chunks:
        key = (
            chunk.get("doi") or
            chunk.get("url") or 
            chunk.get("title") or 
            chunk.get("id") or
            chunk.get("chunk_id")
        )
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        
        source_type = (chunk.get("source_type") or chunk.get("study_type") or "other").lower().strip()
        weight = get_source_weight(source_type)
        strongest = max(strongest, weight)
        total_weight += weight
        
        normalized_type = source_type.replace("_", " ").title()
        type_counts[normalized_type] = type_counts.get(normalized_type, 0) + 1
    
    n_unique = max(1, len(seen_keys))
    avg_weight = total_weight / n_unique
    
    breadth_bonus = min(1.0, n_unique / 6.0) * 0.05
    score = min(0.99, 0.55 * strongest + 0.45 * avg_weight + breadth_bonus)
    score = max(0.10, score)
    
    if score >= BADGE_THRESHOLDS["high"]:
        badge = "High"
        badge_color = "green"
    elif score >= BADGE_THRESHOLDS["moderate"]:
        badge = "Moderate"
        badge_color = "yellow"
    else:
        badge = "Low"
        badge_color = "red"
    
    why_parts = []
    if type_counts.get("Pi") or type_counts.get("Prescribing Information"):
        why_parts.append("Prescribing information available")
    if type_counts.get("Guideline") or type_counts.get("Guidelines"):
        why_parts.append("Clinical guidelines available")
    if type_counts.get("Rct") or type_counts.get("Randomized Controlled Trial"):
        why_parts.append("RCT evidence present")
    if type_counts.get("Meta Analysis") or type_counts.get("Systematic Review"):
        why_parts.append("Systematic evidence available")
    if not why_parts:
        if n_unique >= 3:
            why_parts.append(f"Based on {n_unique} sources")
        else:
            why_parts.append("Limited primary evidence")
    
    return {
        "score": round(score, 2),
        "badge": badge,
        "badge_color": badge_color,
        "types": type_counts,
        "why": "; ".join(why_parts),
        "unique_sources": n_unique
    }


def get_evidence_tier(score: float) -> str:
    """Convert numeric score to A/B/C tier."""
    if score >= 0.80:
        return "A"
    elif score >= 0.60:
        return "B"
    else:
        return "C"


def get_evidence_level(source_type: str) -> str:
    """
    Map source type to evidence level (I-IV).
    
    Level I: Systematic reviews, meta-analyses, RCTs
    Level II: Cohort studies, guidelines
    Level III: Case-control, case series
    Level IV: Case reports, expert opinion
    """
    st = (source_type or "").lower().strip().replace(" ", "_").replace("-", "_")
    
    level_i = {"systematic_review", "meta_analysis", "rct", "randomized_controlled_trial"}
    level_ii = {"cohort", "guideline", "guidelines", "prospective_study", "pi", "prescribing_information"}
    level_iii = {"case_control", "case_series", "retrospective_study"}
    level_iv = {"case_report", "expert_opinion", "textbook", "review", "other"}
    
    if st in level_i:
        return "I"
    elif st in level_ii:
        return "II"
    elif st in level_iii:
        return "III"
    else:
        return "IV"
