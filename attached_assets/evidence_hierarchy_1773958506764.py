"""
AesthetiCite — Evidence Hierarchy Engine  (Canonical)
=====================================================
Single source of truth for evidence ranking across the entire stack.

Previously this logic was split across:
  - app/engine/improvements.py     (classify_chunk, DISPLAY_LABELS, evidence_rank_from_display)
  - app/engine/quality_fusion.py   (hybrid_rerank_sources, GUIDELINE_BOOST, etc.)
  - app/core/governance.py         (rerank_by_domain, _STUDY_TYPE_RANK)
  - app/api/oe_upgrade.py          (infer_tier, infer_study_type)

This module exposes:
  evidence_score(doc)              — The canonical ranking formula
  classify_document(doc)           — Tag any dict with evidence metadata
  rank_documents(docs)             — Sort a list by evidence score
  badge_for_type(evidence_type)    — 🟢/🔵/🟡/⚪ badge
  top_level_badge(docs)            — Best badge across a result set
  enrich_chunks_for_api(chunks)    — Prepare chunks for SSE meta payload
  enrich_document_for_ingest(doc)  — Tag a document before storing
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# TYPE TAXONOMY  (canonical — all other modules should import from here)
# ============================================================

#  evidence_type_raw → display label → numeric rank (lower = better)
EVIDENCE_TYPE_MAP: Dict[str, Tuple[str, int]] = {
    # Guidelines and regulatory
    "guideline":               ("Guideline",            1),
    "clinical_guideline":      ("Guideline",            1),
    "practice_guideline":      ("Guideline",            1),
    "position_statement":      ("Guideline",            1),
    "regulatory":              ("Guideline",            1),
    "labeling":                ("Guideline",            1),
    # Consensus
    "consensus":               ("Consensus Statement",  2),
    "consensus_statement":     ("Consensus Statement",  2),
    "expert_consensus":        ("Consensus Statement",  2),
    "delphi":                  ("Consensus Statement",  2),
    # High-quality primary evidence
    "meta_analysis":           ("Meta-Analysis",        3),
    "systematic_review":       ("Systematic Review",    3),
    "rct":                     ("RCT",                  4),
    "randomized_controlled":   ("RCT",                  4),
    "randomized":              ("RCT",                  4),
    # Secondary evidence
    "review":                  ("Review",               5),
    "narrative_review":        ("Review",               5),
    "scoping_review":          ("Review",               5),
    # Primary observational
    "cohort":                  ("Cohort Study",         6),
    "observational":           ("Cohort Study",         6),
    "cross_sectional":         ("Cohort Study",         6),
    # Case-level
    "case_series":             ("Case Series",          7),
    "case_report":             ("Case Report",          8),
    "case":                    ("Case Report",          8),
    # Expert / other
    "expert_opinion":          ("Expert Opinion",       9),
    "editorial":               ("Expert Opinion",       9),
    "letter":                  ("Expert Opinion",       9),
    "other":                   ("Other",               10),
    "unknown":                 ("Other",               10),
}

# Boost/penalty applied on top of similarity score during ranking
TYPE_SCORE_BOOST: Dict[str, float] = {
    "Guideline":            +0.30,
    "Consensus Statement":  +0.24,
    "Meta-Analysis":        +0.18,
    "Systematic Review":    +0.18,
    "RCT":                  +0.12,
    "Review":               +0.06,
    "Cohort Study":         -0.04,
    "Case Series":          -0.08,
    "Case Report":          -0.12,
    "Expert Opinion":       -0.16,
    "Other":                -0.20,
}

# Frontend badge config
BADGE_CONFIG: Dict[str, Dict[str, str]] = {
    "Guideline":            {"emoji": "🟢", "label": "Guideline-based",  "color": "emerald"},
    "Consensus Statement":  {"emoji": "🔵", "label": "Consensus",         "color": "blue"},
    "Meta-Analysis":        {"emoji": "🔵", "label": "Meta-Analysis",     "color": "blue"},
    "Systematic Review":    {"emoji": "🔵", "label": "Systematic Review", "color": "blue"},
    "RCT":                  {"emoji": "🟡", "label": "RCT",               "color": "amber"},
    "Review":               {"emoji": "🟡", "label": "Review",            "color": "amber"},
    "Cohort Study":         {"emoji": "⚪", "label": "Observational",     "color": "slate"},
    "Case Series":          {"emoji": "⚪", "label": "Case Series",       "color": "slate"},
    "Case Report":          {"emoji": "⚪", "label": "Case Report",       "color": "slate"},
    "Expert Opinion":       {"emoji": "⚪", "label": "Expert Opinion",    "color": "slate"},
    "Other":                {"emoji": "⚪", "label": "Limited",           "color": "slate"},
}

# Keyword patterns for auto-classification from title/abstract
_CLASSIFICATION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(guideline|guidelines|recommendation[s]?|position statement|clinical practice)\b", re.I), "guideline"),
    (re.compile(r"\b(consensus|delphi)\b", re.I), "consensus"),
    (re.compile(r"\b(meta.analysis|meta.analyses|pooled analysis)\b", re.I), "meta_analysis"),
    (re.compile(r"\b(systematic review|scoping review)\b", re.I), "systematic_review"),
    (re.compile(r"\b(randomized|randomised|RCT|controlled trial)\b", re.I), "rct"),
    (re.compile(r"\b(cohort|prospective|retrospective|observational)\b", re.I), "cohort"),
    (re.compile(r"\b(case series|case.series)\b", re.I), "case_series"),
    (re.compile(r"\b(case report|single case)\b", re.I), "case_report"),
    (re.compile(r"\b(review|overview)\b", re.I), "review"),
]

# Known high-tier source organisations
_GUIDELINE_ORGS = frozenset([
    "nice", "who", "fda", "ema", "mhra", "aad", "asds", "bafps", "raft",
    "isaps", "asaps", "british association of aesthetic plastic surgeons",
    "resuscitation council", "anaes", "rcgp", "rcp", "nhs",
])


# ============================================================
# CORE CLASSIFICATION
# ============================================================

def _normalise_type(raw: str) -> str:
    """Map any raw evidence_type string to a canonical key."""
    if not raw:
        return "unknown"
    r = raw.lower().strip().replace(" ", "_").replace("-", "_")
    if r in EVIDENCE_TYPE_MAP:
        return r
    # Fuzzy fallback
    for key in EVIDENCE_TYPE_MAP:
        if key in r or r in key:
            return key
    return "unknown"


def _infer_type_from_text(title: str, abstract: str, journal: str, org: str) -> str:
    """Heuristic classification from document text when no explicit type is set."""
    combined = f"{title} {abstract} {journal} {org}".lower()

    # Check known guideline organisations first — highest precision
    org_lower = (org or "").lower()
    if any(g in org_lower for g in _GUIDELINE_ORGS):
        return "guideline"

    for pattern, ev_type in _CLASSIFICATION_PATTERNS:
        if pattern.search(combined):
            return ev_type

    return "other"


def classify_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tag a document dict with canonical evidence metadata.
    Returns a NEW dict with added fields — does not mutate original.
    
    Input keys read: evidence_type, publication_type, document_type,
                     title, abstract, journal, organization
    Output keys added:
      evidence_type_canonical   — one of the keys in EVIDENCE_TYPE_MAP
      evidence_type_display     — human-readable label (e.g. "Guideline")
      evidence_rank             — int 1–10 (1 = best)
      evidence_badge            — dict {emoji, label, color}
      evidence_tier             — "primary" | "secondary" | "tertiary"
    """
    # Resolve raw type from whichever field is populated
    raw = (
        doc.get("evidence_type")
        or doc.get("publication_type")
        or doc.get("document_type")
        or doc.get("source_type")
        or ""
    )

    canonical = _normalise_type(raw)

    # If still unknown, infer from text
    if canonical in ("unknown", "other"):
        title    = doc.get("title", "")
        abstract = doc.get("text", "") or doc.get("abstract", "") or doc.get("chunk_text", "")
        journal  = doc.get("journal", "") or doc.get("organization_or_journal", "")
        org      = doc.get("organization", "") or doc.get("org", "")
        canonical = _infer_type_from_text(title, abstract, journal, org)

    display_label, rank = EVIDENCE_TYPE_MAP.get(canonical, ("Other", 10))
    badge = BADGE_CONFIG.get(display_label, BADGE_CONFIG["Other"])

    # Tier grouping
    if rank <= 2:
        tier = "primary_authoritative"
    elif rank <= 4:
        tier = "primary_empirical"
    elif rank <= 5:
        tier = "secondary"
    else:
        tier = "tertiary"

    result = dict(doc)
    result.update({
        "evidence_type_canonical": canonical,
        "evidence_type_display":   display_label,
        "evidence_rank":           rank,
        "evidence_badge":          badge,
        "evidence_tier":           tier,
    })
    return result


# ============================================================
# CANONICAL SCORING FORMULA
# ============================================================

def evidence_score(doc: Dict[str, Any]) -> float:
    """
    Canonical evidence ranking formula.

    score = similarity × 0.60 + type_weight × 0.30 + recency × 0.10

    Equivalent to the build plan formula but normalised properly:
    - type_weight is 1–5 (guideline=5) mapped from rank 1–10
    - recency uses exponential decay (half-life 6 years)
    - similarity falls back to relevance_score or 0.5 if missing

    This is the ONE function the entire stack should use for scoring.
    """
    # Ensure document is classified
    if "evidence_rank" not in doc:
        doc = classify_document(doc)

    similarity = float(
        doc.get("similarity")
        or doc.get("relevance_score")
        or doc.get("vector_score")
        or 0.5
    )
    # Clamp to [0, 1]
    similarity = max(0.0, min(1.0, similarity))

    # Map rank (1–10, lower=better) → weight (5–1, higher=better)
    rank = int(doc.get("evidence_rank") or 10)
    # Linear map: rank 1 → 5.0, rank 10 → 0.5
    type_weight = max(0.5, 5.5 - (rank * 0.5))

    # Recency: exponential decay, half-life 6 years
    year = doc.get("year")
    now_year = time.gmtime().tm_year
    if isinstance(year, int) and 1900 < year <= now_year:
        age = now_year - year
        recency = 2 ** -(age / 6.0)
    else:
        recency = 0.5

    score = similarity * 0.60 + type_weight * 0.30 + recency * 0.10

    # Store score for debugging / sorting
    doc["_evidence_score"] = round(score, 4)
    return score


# ============================================================
# RANKING
# ============================================================

def rank_documents(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort documents by canonical evidence score (highest first).
    Classifies any untagged documents in place.
    Removes internal _evidence_score key before returning.
    """
    classified = [classify_document(d) for d in docs]
    classified.sort(key=evidence_score, reverse=True)
    for d in classified:
        d.pop("_evidence_score", None)
    return classified


# ============================================================
# BADGE HELPERS
# ============================================================

def badge_for_type(evidence_type_display: str) -> Dict[str, str]:
    """Return badge config for a display label. Always returns a valid dict."""
    return BADGE_CONFIG.get(evidence_type_display, BADGE_CONFIG["Other"])


def top_level_badge(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Return the best badge across a result set plus a summary label.

    Examples:
      [Guideline, Review, Case]   → "🟢 Guideline-based"
      [RCT, Review, Cohort]       → "🟡 RCT-supported"
      [Case, Case, Other]         → "⚪ Limited evidence"
    """
    if not docs:
        return {
            "emoji": "⚪", "label": "Limited evidence", "color": "slate",
            "level": "Low", "best_type": "None",
        }

    classified = [classify_document(d) if "evidence_rank" not in d else d for d in docs]
    best = min(classified, key=lambda d: int(d.get("evidence_rank") or 10))
    best_display = best.get("evidence_type_display", "Other")
    badge = BADGE_CONFIG.get(best_display, BADGE_CONFIG["Other"])

    # Map to High/Moderate/Low for compatibility with existing frontend
    rank = int(best.get("evidence_rank") or 10)
    if rank <= 2:
        level = "High"
    elif rank <= 5:
        level = "Moderate"
    else:
        level = "Low"

    return {
        **badge,
        "level":     level,
        "best_type": best_display,
        "best_rank": rank,
    }


# ============================================================
# API PAYLOAD PREPARATION
# ============================================================

def enrich_chunks_for_api(
    chunks: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Prepare chunks for the SSE meta payload.
    Returns (ranked_chunks, top_badge_dict).

    Usage in ask_v2.py / oe_upgrade.py:
        ranked, badge = enrich_chunks_for_api(raw_chunks)
    """
    ranked = rank_documents(chunks)

    citations = []
    for i, ch in enumerate(ranked):
        b = ch.get("evidence_badge") or badge_for_type(ch.get("evidence_type_display", "Other"))
        citations.append({
            "id":                 i + 1,
            "label":              f"S{i + 1}",
            "title":              ch.get("title", "Unknown"),
            "source":             ch.get("journal") or ch.get("organization_or_journal") or ch.get("organization") or "Research Source",
            "year":               ch.get("year"),
            "url":                ch.get("url", ""),
            "doi":                ch.get("doi", ""),
            "authors":            ch.get("authors", ""),
            "source_id":          ch.get("source_id") or ch.get("id", ""),
            "evidence_type":      ch.get("evidence_type_display", "Other"),
            "evidence_type_raw":  ch.get("evidence_type_canonical", "unknown"),
            "evidence_rank":      ch.get("evidence_rank", 10),
            "evidence_tier":      ch.get("evidence_tier", "tertiary"),
            "evidence_badge":     b,
            # Legacy compat fields
            "evidence_grade":     "High" if ch.get("evidence_rank", 10) <= 2 else (
                                  "Moderate" if ch.get("evidence_rank", 10) <= 5 else "Low"),
            "source_tier":        ch.get("evidence_tier", "tertiary"),
        })

    top_badge = top_level_badge(ranked)

    return citations, top_badge


def enrich_document_for_ingest(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tag a document before storing to documents_meta or chunks table.
    Call this in the ingestion pipeline.
    
    Returns doc with evidence_type, evidence_rank, source_tier set.
    """
    tagged = classify_document(doc)
    return {
        **doc,
        "evidence_type":  tagged["evidence_type_canonical"],
        "evidence_rank":  tagged["evidence_rank"],
        "source_tier":    tagged["evidence_tier"],
        # Keep display label for search
        "evidence_type_display": tagged["evidence_type_display"],
    }


# ============================================================
# QUERY REWRITING  (boosts retrieval of high-tier evidence)
# ============================================================

_COMPLICATION_MARKERS = frozenset([
    "vascular", "occlusion", "ischaemia", "ischemia", "necrosis",
    "complication", "adverse", "anaphylaxis", "ptosis", "nodule",
    "infection", "biofilm", "hyaluronidase",
])

_TECHNIQUE_MARKERS = frozenset([
    "dose", "dosage", "volume", "dilution", "reconstitution",
    "injection plane", "technique", "cannula", "needle",
])


def rewrite_query_for_evidence(query: str) -> Dict[str, Any]:
    """
    Append evidence-type hints to a retrieval query so the vector search
    favours high-tier documents.

    Returns dict with:
      rewritten_query  — query string with appended hints
      intent           — "complication" | "guideline" | "technique" | "general"
      boost_types      — list of evidence types to boost in reranking
    """
    ql = query.lower()

    is_complication = any(m in ql for m in _COMPLICATION_MARKERS)
    is_guideline = any(m in ql for m in ("guideline", "consensus", "recommendation"))
    is_technique = any(m in ql for m in _TECHNIQUE_MARKERS)

    hints: List[str] = []
    boost_types: List[str] = []

    if is_complication or is_guideline:
        hints += ["guideline", "consensus", "recommendation", "protocol"]
        boost_types += ["Guideline", "Consensus Statement"]
    if is_complication:
        hints += ["management", "emergency", "algorithm"]
        boost_types += ["Systematic Review", "Meta-Analysis"]

    rewritten = query
    if hints:
        rewritten = f"{query} ({' OR '.join(hints[:4])})"

    intent = (
        "complication" if is_complication else
        "guideline"    if is_guideline else
        "technique"    if is_technique else
        "general"
    )

    return {
        "rewritten_query": rewritten,
        "intent": intent,
        "boost_types": boost_types,
    }


# ============================================================
# MIGRATION HELPER  (backfill documents_meta)
# ============================================================

BACKFILL_SQL = """
UPDATE documents_meta
SET
    evidence_type  = :evidence_type,
    evidence_rank  = :evidence_rank,
    source_tier    = :source_tier,
    updated_at     = now()
WHERE
    source_id = :source_id
    AND (evidence_type IS NULL OR evidence_type = '' OR evidence_rank IS NULL)
;
"""

INSERT_META_SQL = """
INSERT INTO documents_meta (source_id, title, year, journal, evidence_type, evidence_rank, source_tier)
VALUES (:source_id, :title, :year, :journal, :evidence_type, :evidence_rank, :source_tier)
ON CONFLICT (source_id) DO UPDATE SET
    evidence_type = EXCLUDED.evidence_type,
    evidence_rank = EXCLUDED.evidence_rank,
    source_tier   = EXCLUDED.source_tier,
    updated_at    = now()
WHERE documents_meta.evidence_type IS NULL OR documents_meta.evidence_type = ''
;
"""


def backfill_documents_meta(db_session, chunks: List[Dict[str, Any]]) -> int:
    """
    Backfill evidence_type/rank/tier into documents_meta for a batch of chunks.
    Returns number of rows updated.

    Call from a maintenance script or during answer generation.
    """
    from sqlalchemy import text
    updated = 0
    for ch in chunks:
        source_id = ch.get("source_id") or ch.get("id")
        if not source_id:
            continue
        tagged = classify_document(ch)
        try:
            db_session.execute(
                text(INSERT_META_SQL),
                {
                    "source_id":     source_id,
                    "title":         ch.get("title", ""),
                    "year":          ch.get("year"),
                    "journal":       ch.get("journal") or ch.get("organization_or_journal", ""),
                    "evidence_type": tagged["evidence_type_canonical"],
                    "evidence_rank": tagged["evidence_rank"],
                    "source_tier":   tagged["evidence_tier"],
                },
            )
            updated += 1
        except Exception:
            continue
    try:
        db_session.commit()
    except Exception:
        pass
    return updated
