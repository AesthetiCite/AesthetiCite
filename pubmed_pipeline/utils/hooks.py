"""
Performance Hooks for PubMed Pipeline
======================================
Implements the hooks from corpus.yaml:
- source_type classification
- quality_rank assignment  
- freshness_years computation
"""

from datetime import datetime
import re
from typing import Dict, Any, List


CURRENT_YEAR = datetime.utcnow().year

# ---- Hook configuration (mirrors corpus.yaml exactly) ----

SOURCE_TYPE_RULES = [
    # Order matters: first match wins
    {
        "if_publication_type_any": ["Practice Guideline", "Guideline"],
        "then": "guideline",
    },
    {
        "if_title_or_abstract_regex": r"(consensus|recommendation|position statement|guideline)",
        "then": "guideline",
    },
    {
        "if_publication_type_any": ["Randomized Controlled Trial"],
        "then": "rct",
    },
    {
        "if_publication_type_any": ["Systematic Review", "Meta-Analysis"],
        "then": "meta_analysis",
    },
    {
        "if_publication_type_any": ["Review"],
        "then": "review",
    },
    {
        "if_publication_type_any": ["Case Reports"],
        "then": "case_series",
    },
]

QUALITY_RANK = {
    "pi": 100,              # kept for unified schema
    "guideline": 95,
    "meta_analysis": 85,
    "rct": 80,
    "case_series": 55,
    "review": 50,
    "other": 35,
}


# ---- Core hook function ----

def apply_pubmed_hooks(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies:
      - source_type classification
      - quality_rank assignment
      - freshness_years computation

    Expected input fields (best effort):
      record = {
        "title": str,
        "abstract": str,
        "publication_types": List[str],
        "year": int | None
      }

    Returns the same dict with added fields:
      - source_type
      - quality_rank
      - freshness_years
    """

    title = (record.get("title") or "").lower()
    abstract = (record.get("abstract") or "").lower()
    pub_types: List[str] = record.get("publication_types") or []

    source_type = "other"

    # ---- source_type classifier ----
    for rule in SOURCE_TYPE_RULES:
        # Match publication types
        if "if_publication_type_any" in rule:
            if any(pt in pub_types for pt in rule["if_publication_type_any"]):
                source_type = rule["then"]
                break

        # Match regex on title or abstract
        if "if_title_or_abstract_regex" in rule:
            pattern = rule["if_title_or_abstract_regex"]
            if re.search(pattern, title) or re.search(pattern, abstract):
                source_type = rule["then"]
                break

    # ---- quality rank ----
    quality_rank = QUALITY_RANK.get(source_type, QUALITY_RANK["other"])

    # ---- freshness ----
    year = record.get("year")
    if isinstance(year, int) and 1900 <= year <= CURRENT_YEAR:
        freshness_years = max(0, CURRENT_YEAR - year)
    else:
        freshness_years = None

    # ---- attach results ----
    record["source_type"] = source_type
    record["quality_rank"] = quality_rank
    record["freshness_years"] = freshness_years

    return record


def classify_source_type(pub_types: List[str], title: str, abstract: str = "") -> str:
    """
    Classify source type from publication metadata.
    Returns: guideline, rct, meta_analysis, review, case_series, or other
    """
    title_lower = title.lower()
    abstract_lower = abstract.lower()
    
    for rule in SOURCE_TYPE_RULES:
        if "if_publication_type_any" in rule:
            if any(pt in pub_types for pt in rule["if_publication_type_any"]):
                return rule["then"]
        
        if "if_title_or_abstract_regex" in rule:
            pattern = rule["if_title_or_abstract_regex"]
            if re.search(pattern, title_lower) or re.search(pattern, abstract_lower):
                return rule["then"]
    
    return "other"


def get_quality_rank(source_type: str) -> int:
    """Get quality rank for a source type."""
    return QUALITY_RANK.get(source_type, QUALITY_RANK["other"])


def compute_freshness_years(year: int) -> int:
    """Compute freshness in years from publication year."""
    if isinstance(year, int) and 1900 <= year <= CURRENT_YEAR:
        return max(0, CURRENT_YEAR - year)
    return None
