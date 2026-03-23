import re
from typing import List, Dict, Tuple, Optional


def is_refusal(text: str) -> bool:
    """Check if LLM output is a refusal."""
    return (text or "").strip().lower().startswith("refusal:")


def has_citations(text: str) -> bool:
    """Check if text has at least one [S1]-style citation."""
    return bool(re.search(r"\[S\d+\]", text or ""))


def count_citations(text: str) -> int:
    """Count unique citations in text."""
    matches = re.findall(r"\[S(\d+)\]", text or "")
    return len(set(matches))


def extract_numbers(text: str) -> List[str]:
    """Extract numeric values (doses, percentages, durations) from text."""
    patterns = [
        r"\d+\.?\d*\s*(?:mg|mcg|µg|g|kg|ml|mL|L|cc|units?|IU)",
        r"\d+\.?\d*\s*%",
        r"\d+\.?\d*\s*(?:hours?|hrs?|minutes?|mins?|days?|weeks?|months?|years?)",
        r"\d+\.?\d*\s*(?:mm|cm|m)",
    ]
    numbers = []
    for pattern in patterns:
        numbers.extend(re.findall(pattern, text, re.IGNORECASE))
    return numbers


def normalize_number(text: str) -> str:
    """Normalize a number for comparison (remove spaces, standardize units)."""
    t = text.lower().strip()
    t = re.sub(r"\s+", "", t)
    t = t.replace(",", "")
    t = t.replace("µg", "mcg")
    return t


def verify_numbers_in_sources(answer: str, sources: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Verify that numbers in the answer can be found in sources.
    Returns (all_verified, list_of_unverified_numbers).
    
    Uses lenient matching - normalizes numbers and checks if the numeric value exists.
    """
    answer_numbers = extract_numbers(answer)
    if not answer_numbers:
        return True, []
    
    source_text = " ".join(
        (s.get("text", "") + " " + s.get("title", "")) 
        for s in sources
    )
    source_normalized = normalize_number(source_text)
    source_text_lower = source_text.lower()
    
    unverified = []
    for num in answer_numbers:
        num_normalized = normalize_number(num)
        num_value = re.sub(r"[^\d.]", "", num)
        
        found = (
            num_normalized in source_normalized or
            num_value in source_text_lower or
            num.strip().lower() in source_text_lower
        )
        
        if not found:
            unverified.append(num)
    
    return len(unverified) == 0, unverified


def check_citation_coverage(answer: str, min_citations: int = 2) -> bool:
    """Check if answer has sufficient citation coverage."""
    return count_citations(answer) >= min_citations


def detect_hedging_without_citation(text: str) -> List[str]:
    """Detect phrases that suggest uncertainty but lack citations."""
    hedging_phrases = [
        r"(?:studies\s+(?:show|suggest|indicate))",
        r"(?:research\s+(?:shows|suggests|indicates))",
        r"(?:evidence\s+(?:shows|suggests|indicates))",
        r"(?:it\s+is\s+(?:known|believed|thought))",
        r"(?:typically|generally|usually|often|commonly)",
        r"(?:may\s+be|might\s+be|could\s+be)",
    ]
    
    uncited_hedges = []
    for phrase_pattern in hedging_phrases:
        for match in re.finditer(phrase_pattern, text, re.IGNORECASE):
            start = match.start()
            end = min(match.end() + 50, len(text))
            context = text[start:end]
            if not re.search(r"\[S\d+\]", context):
                uncited_hedges.append(match.group())
    
    return uncited_hedges


def safe_finalize(llm_text: str, sources: Optional[List[Dict]] = None) -> str:
    """
    Finalize LLM output with comprehensive safety and anti-hallucination checks.
    
    Checks:
    1. Explicit refusal detection
    2. Citation presence
    3. Numeric verification against sources (if sources provided) - lenient mode
    
    Note: sources parameter is optional for backward compatibility.
    Numeric verification only triggers refusal for egregious cases (>4 unverified numbers).
    """
    t = (llm_text or "").strip()
    
    if is_refusal(t):
        return "REFUSAL: insufficient evidence."
    
    if not has_citations(t):
        return "REFUSAL: insufficient evidence."
    
    if sources and len(sources) > 0:
        numbers_ok, unverified = verify_numbers_in_sources(t, sources)
        if not numbers_ok and len(unverified) > 4:
            return "REFUSAL: multiple numeric claims could not be verified against sources."
    
    return t


def validate_answer_quality(
    answer: str, 
    sources: List[Dict],
    min_citations: int = 2
) -> Dict:
    """
    Comprehensive answer quality validation.
    Returns a dict with validation results and warnings.
    """
    result = {
        "valid": True,
        "warnings": [],
        "citation_count": count_citations(answer),
        "numbers_verified": True,
        "unverified_numbers": [],
    }
    
    if not has_citations(answer):
        result["valid"] = False
        result["warnings"].append("No citations found in answer")
        return result
    
    if result["citation_count"] < min_citations:
        result["warnings"].append(f"Only {result['citation_count']} citations, recommend {min_citations}+")
    
    numbers_ok, unverified = verify_numbers_in_sources(answer, sources)
    result["numbers_verified"] = numbers_ok
    result["unverified_numbers"] = unverified
    if unverified:
        result["warnings"].append(f"Unverified numbers: {', '.join(unverified[:3])}")
    
    uncited_hedges = detect_hedging_without_citation(answer)
    if uncited_hedges:
        result["warnings"].append(f"Uncited hedging phrases: {', '.join(uncited_hedges[:2])}")
    
    return result
