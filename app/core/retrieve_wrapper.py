"""
Thin wrapper around retrieve_db for improve_pack compatibility.
Ensures wide-K behavior even if k=None.
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.rag.retriever import retrieve_db


def retrieve_chunks(
    db: Session,
    query: str,
    filters: Optional[dict] = None,
    k: Optional[int] = None
) -> List[Dict]:
    """
    Wrapper around retrieve_db to ensure:
    - wide retrieval when k is provided
    - backward compatibility when k is None
    - consistent output format for improve_pack
    
    Args:
        db: SQLAlchemy session
        query: The search query string
        filters: Optional dict with filtering options (e.g., {"domain": "aesthetic_medicine"})
        k: Number of chunks to retrieve
    
    Returns:
        List of chunk dicts with standardized fields for improve_pack
    """
    domain = (filters or {}).get("domain", "aesthetic_medicine")
    
    results = retrieve_db(db=db, question=query, domain=domain, k=k or 60)
    
    def map_source_type(doc_type: str) -> str:
        """Map document_type to source_type for improve_pack quality weighting."""
        dt = (doc_type or "").lower().strip()
        if dt in ("prescribing_information", "pi", "label", "package_insert"):
            return "pi"
        elif dt in ("guideline", "clinical_guideline", "consensus", "ifu"):
            return "guideline"
        elif dt in ("meta_analysis", "meta-analysis", "systematic_review"):
            return "meta_analysis"
        elif dt in ("rct", "randomized_controlled_trial"):
            return "rct"
        elif dt in ("case_series", "case_report"):
            return "case_series"
        elif dt in ("review", "journal_article", "pubmed_pmc"):
            return "review"
        elif dt == "textbook":
            return "textbook"
        return "other"
    
    return [
        {
            "id": r.get("source_id"),
            "title": r.get("title"),
            "year": r.get("year"),
            "source_type": map_source_type(r.get("document_type", "")),
            "text": r.get("text", ""),
            "doi": r.get("doi"),
            "url": r.get("url"),
            "page_or_section": r.get("page_or_section"),
            "evidence_level": r.get("evidence_level"),
            "organization": r.get("organization_or_journal"),
        }
        for r in results
    ]


def make_retrieve_fn(db: Session):
    """
    Factory function to create a retrieve_chunks callable bound to a db session.
    Use this with improve_pack.improved_answer().
    
    Example:
        retrieve_fn = make_retrieve_fn(db)
        result = improved_answer(
            query="...",
            filters={"domain": "aesthetic_medicine"},
            retrieve_chunks=retrieve_fn,
        )
    """
    def retrieve_fn(query: str, filters: Optional[dict], k: Optional[int] = None) -> List[Dict]:
        return retrieve_chunks(db=db, query=query, filters=filters, k=k)
    return retrieve_fn
