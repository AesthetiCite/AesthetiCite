"""
Evidence classification, tier mapping, deterministic ACI engine,
and protocol-specific follow-ups.

Replaces LLM-hallucinated ACI with a deterministic, weighted-signal score.
Provides robust evidence type classification using publication_types metadata
and title-based regex fallback.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math
import re

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Source:
    id: str
    title: str
    journal: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    publication_types: Optional[List[str]] = None
    abstract: Optional[str] = None
    evidence_type: str = "Other"
    evidence_tier: str = "C"
    evidence_grade: str = "III"


@dataclass
class ACIResult:
    score_0_to_10: float
    badge: str
    components: Dict[str, float]
    rationale: str


_GUIDELINE_HINTS = [
    r"\bguideline(s)?\b", r"\bconsensus\b", r"\bposition statement\b",
    r"\brecommendation(s)?\b", r"\bexpert panel\b", r"\bdelphi\b",
    r"\bpractice advisory\b", r"\bsociety guideline\b",
]
_SYSTEMATIC_HINTS = [r"\bsystematic review\b", r"\bmeta[- ]analysis\b", r"\bPRISMA\b"]
_RCT_HINTS = [r"\brandomi[sz]ed\b", r"\btrial\b", r"\bdouble[- ]blind\b", r"\bplacebo\b"]
_OBSERVATIONAL_HINTS = [r"\bcohort\b", r"\bcase[- ]control\b", r"\bcross[- ]sectional\b"]
_CASESERIES_HINTS = [r"\bcase series\b", r"\bcase[- ]series\b"]
_CASEREPORT_HINTS = [r"\bcase report\b"]
_REVIEW_HINTS = [r"\bnarrative review\b", r"\breview\b"]

EMERGENCY_HINTS = [
    "vascular occlusion", "occlusion", "ischemia", "ischaemia", "necrosis",
    "vision loss", "blindness", "embol", "intravascular", "arterial",
    "hyaluronidase", "filler complication", "adverse event", "complication",
]


def _norm_pubtypes(pubtypes: Optional[List[str]]) -> List[str]:
    if not pubtypes:
        return []
    return [p.strip().lower() for p in pubtypes if p and p.strip()]


def classify_evidence_type(src: Source) -> str:
    pub = _norm_pubtypes(src.publication_types)
    title = (src.title or "").lower()

    def has_any(sub: str) -> bool:
        return any(sub in p for p in pub)

    if has_any("guideline") or has_any("society guideline") or has_any("practice advisory"):
        return "Guideline"
    if has_any("consensus") or has_any("position statement") or has_any("delphi") or has_any("expert panel"):
        return "Consensus"
    if has_any("recommendation") and (has_any("society") or has_any("academy") or has_any("college")):
        return "Consensus"
    if has_any("systematic"):
        return "SystematicReview"
    if has_any("meta-analysis") or has_any("meta analysis"):
        return "MetaAnalysis"
    if has_any("randomized controlled trial") or has_any("rct") or has_any("trial"):
        return "RCT"
    if has_any("cohort"):
        return "Cohort"
    if has_any("case-control") or has_any("case control"):
        return "CaseControl"
    if has_any("case series"):
        return "CaseSeries"
    if has_any("case report"):
        return "CaseReport"
    if has_any("review"):
        return "NarrativeReview"

    if re.search(r"\bguideline(s)?\b|\bpractice advisory\b", title):
        return "Guideline"
    if re.search(r"\bconsensus\b|\bposition statement\b|\bdelphi\b|\bexpert panel\b", title):
        return "Consensus"
    if re.search(r"\brecommendation(s)?\b", title) and re.search(r"\bsociety\b|\bacademy\b|\bcollege\b", title):
        return "Consensus"
    if re.search(r"\bsystematic review\b", title):
        return "SystematicReview"
    if re.search(r"\bmeta[- ]analysis\b", title):
        return "MetaAnalysis"
    if re.search(r"\brandomi[sz]ed\b|\bdouble[- ]blind\b|\bplacebo\b|\btrial\b", title):
        return "RCT"
    if re.search(r"\bcohort\b", title):
        return "Cohort"
    if re.search(r"\bcase[- ]control\b", title):
        return "CaseControl"
    if re.search(r"\bcase series\b|\bcase[- ]series\b", title):
        return "CaseSeries"
    if re.search(r"\bcase report\b", title):
        return "CaseReport"
    if re.search(r"\breview\b", title):
        return "NarrativeReview"

    return "Other"


DISPLAY_LABELS = {
    "Guideline": "Guideline/Consensus",
    "Consensus": "Guideline/Consensus",
    "SystematicReview": "Systematic Review",
    "MetaAnalysis": "Systematic Review",
    "RCT": "Randomized Trial",
    "Cohort": "Observational Study",
    "CaseControl": "Observational Study",
    "CaseSeries": "Case Report/Series",
    "CaseReport": "Case Report/Series",
    "NarrativeReview": "Narrative Review",
    "Other": "Other",
}


def map_to_tier(evidence_type: str) -> str:
    if evidence_type in {"Guideline", "Consensus", "SystematicReview", "MetaAnalysis", "RCT"}:
        return "A"
    if evidence_type in {"Cohort", "CaseControl"}:
        return "B"
    return "C"


def map_to_grade(evidence_type: str) -> str:
    if evidence_type in {"Guideline", "Consensus"}:
        return "I"
    if evidence_type in {"SystematicReview", "MetaAnalysis", "RCT"}:
        return "II"
    if evidence_type in {"Cohort", "CaseControl", "CaseSeries"}:
        return "III"
    return "IV"


def enrich_sources(sources: List[Source]) -> List[Source]:
    for s in sources:
        s.evidence_type = classify_evidence_type(s)
        s.evidence_tier = map_to_tier(s.evidence_type)
        s.evidence_grade = map_to_grade(s.evidence_type)
    return sources


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_aci(topic: str, sources: List[Source], now_year: Optional[int] = None) -> ACIResult:
    if now_year is None:
        now_year = datetime.utcnow().year

    n = len(sources)
    if n == 0:
        return ACIResult(
            score_0_to_10=0.0,
            badge="Low",
            components={"tier_quality": 0.0, "evidence_diversity": 0.0, "recency": 0.0, "source_count": 0.0, "guideline_presence": 0.0},
            rationale="No supporting sources retrieved."
        )

    tier_map = {"A": 1.0, "B": 0.6, "C": 0.3}
    tier_quality = sum(tier_map.get(s.evidence_tier, 0.3) for s in sources) / n

    types = {s.evidence_type for s in sources}
    diversity = _clamp(len(types) / 6.0, 0.0, 1.0)

    recency_scores: List[float] = []
    for s in sources:
        if not s.year:
            recency_scores.append(0.4)
        else:
            age = max(0, now_year - s.year)
            rec = 1.0 / (1.0 + (age / 6.0))
            recency_scores.append(_clamp(rec, 0.15, 1.0))
    recency = sum(recency_scores) / n

    source_count = 1.0 - math.exp(-n / 7.0)
    source_count = _clamp(source_count, 0.0, 1.0)

    guideline_presence = 1.0 if any(s.evidence_type in {"Guideline", "Consensus"} for s in sources) else 0.0

    topic_lower = (topic or "").lower()
    missing_guideline_penalty = 0.0
    if any(k in topic_lower for k in EMERGENCY_HINTS) and guideline_presence < 0.5:
        missing_guideline_penalty = 0.08

    authority_boost = 0.0
    authority_count = sum(1 for s in sources if s.evidence_type in {"Guideline", "Consensus", "SystematicReview", "MetaAnalysis", "RCT"})
    if authority_count > 0:
        authority_boost = _clamp(authority_count / 5.0, 0.0, 1.0) * 0.15

    raw = (
        0.42 * tier_quality +
        0.18 * diversity +
        0.22 * recency +
        0.08 * source_count +
        0.10 * guideline_presence
    ) + authority_boost
    raw = _clamp(raw - missing_guideline_penalty, 0.0, 1.0)

    score_0_to_10 = round(raw * 10.0, 1)

    if score_0_to_10 >= 8.0:
        badge = "High"
    elif score_0_to_10 >= 5.5:
        badge = "Moderate"
    else:
        badge = "Low"

    rationale = (
        f"Computed from tier quality ({tier_quality:.2f}), diversity ({diversity:.2f}), "
        f"recency ({recency:.2f}), source count ({source_count:.2f}), guideline presence ({guideline_presence:.0f}), "
        f"authority boost ({authority_boost:.2f}, {authority_count} high-quality sources)."
    )
    if missing_guideline_penalty > 0:
        rationale += " Mild penalty applied due to missing guideline/consensus evidence for an emergency protocol topic."

    return ACIResult(
        score_0_to_10=score_0_to_10,
        badge=badge,
        components={
            "tier_quality": round(tier_quality, 2),
            "evidence_diversity": round(diversity, 2),
            "recency": round(recency, 2),
            "source_count": round(source_count, 2),
            "guideline_presence": guideline_presence,
            "authority_boost": round(authority_boost, 2),
        },
        rationale=rationale
    )


def protocol_followups(topic: str) -> List[str]:
    t = (topic or "").lower()
    if any(k in t for k in ["vascular occlusion", "occlusion", "ischemia", "hyaluronidase"]):
        return [
            "What repeat dosing interval is recommended (e.g., every 30-60 minutes) and when should dosing be escalated?",
            "What are the key clinical signs that indicate worsening ischemia requiring urgent escalation or referral?",
            "What adjunctive measures are recommended alongside hyaluronidase (e.g., massage, warming, antiplatelet considerations)?",
            "When ocular symptoms occur, what immediate emergency steps are recommended and which specialist referral pathway should be activated?",
            "How do recommended approaches differ for impending versus established occlusion?",
        ]
    return [
        "What is the highest-quality guideline or consensus statement on this topic and what does it recommend?",
        "What are the main contraindications and safety monitoring requirements?",
        "What factors change management (severity, comorbidities, timing) and how?",
        "What evidence gaps remain and what research would most strengthen recommendations?",
    ]


def classify_chunk(chunk: Dict[str, Any]) -> Source:
    title = chunk.get("title") or ""
    pub_types_raw = chunk.get("publication_types") or chunk.get("document_type") or ""

    if isinstance(pub_types_raw, str):
        pub_types: List[str] = [pub_types_raw] if pub_types_raw else []
    elif isinstance(pub_types_raw, list):
        pub_types = [str(p) for p in pub_types_raw if p]
    else:
        pub_types = []

    src = Source(
        id=chunk.get("source_id") or chunk.get("id") or "",
        title=title,
        journal=chunk.get("organization_or_journal") or chunk.get("journal") or None,
        year=chunk.get("year"),
        doi=chunk.get("doi") or None,
        url=chunk.get("url") or None,
        publication_types=pub_types,
    )
    src.evidence_type = classify_evidence_type(src)
    src.evidence_tier = map_to_tier(src.evidence_type)
    src.evidence_grade = map_to_grade(src.evidence_type)
    return src


def enrich_and_score(topic: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    sources = [classify_chunk(c) for c in chunks]
    aci = compute_aci(topic=topic, sources=sources)

    def _rank_key(s: Source) -> Tuple[int, int]:
        tier_order = {"A": 0, "B": 1, "C": 2}
        year = s.year or 0
        return (tier_order.get(s.evidence_tier, 2), -year)

    sources_sorted = sorted(sources, key=_rank_key)

    return {
        "sources": [asdict(s) for s in sources_sorted],
        "aci": asdict(aci),
        "followups": protocol_followups(topic),
        "meta": {
            "topic": topic,
            "retrieved_source_count": len(sources_sorted),
            "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    }


EVIDENCE_RANK_ORDER = {
    "Guideline/Consensus": 1,
    "Systematic Review": 2,
    "Randomized Trial": 3,
    "Observational Study": 4,
    "Case Report/Series": 5,
    "Narrative Review": 6,
    "Journal Article": 7,
    "Other": 8,
}


def evidence_rank_from_display(display_label: str) -> int:
    return EVIDENCE_RANK_ORDER.get(display_label, 9)


PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")


async def pubmed_summary(pmid: str) -> Dict[str, Any]:
    params: Dict[str, str] = {"db": "pubmed", "id": pmid, "retmode": "json"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(PUBMED_SUMMARY_URL, params=params)
        r.raise_for_status()
        data = r.json() or {}
        result = data.get("result", {})
        return result.get(str(pmid), {}) if result else {}


def infer_pubtype_from_pubmed_summary(s: Dict[str, Any]) -> Optional[str]:
    for k in ("pubtype", "pubtypes", "publicationtype", "publicationtypes"):
        v = s.get(k)
        if isinstance(v, list) and v:
            return "; ".join([str(x) for x in v if x])
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def upsert_doc_meta(
    db_session,
    source_id: str,
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    url: Optional[str] = None,
    title: Optional[str] = None,
    journal: Optional[str] = None,
    year: Optional[int] = None,
    publication_type: Optional[str] = None,
    organization: Optional[str] = None,
) -> None:
    from sqlalchemy import text as sa_text
    db_session.execute(
        sa_text("""
            INSERT INTO documents_meta(source_id, doi, pmid, url, title, journal, year, publication_type, organization, updated_at)
            VALUES(:sid, :doi, :pmid, :url, :title, :journal, :year, :pt, :org, now())
            ON CONFLICT(source_id) DO UPDATE SET
              doi=COALESCE(EXCLUDED.doi, documents_meta.doi),
              pmid=COALESCE(EXCLUDED.pmid, documents_meta.pmid),
              url=COALESCE(EXCLUDED.url, documents_meta.url),
              title=COALESCE(EXCLUDED.title, documents_meta.title),
              journal=COALESCE(EXCLUDED.journal, documents_meta.journal),
              year=COALESCE(EXCLUDED.year, documents_meta.year),
              publication_type=COALESCE(EXCLUDED.publication_type, documents_meta.publication_type),
              organization=COALESCE(EXCLUDED.organization, documents_meta.organization),
              updated_at=now()
        """),
        {"sid": source_id, "doi": doi, "pmid": pmid, "url": url,
         "title": title, "journal": journal, "year": year, "pt": publication_type, "org": organization}
    )
    db_session.commit()


def fetch_doc_meta(db_session, source_id: str) -> Optional[Dict[str, Any]]:
    from sqlalchemy import text as sa_text
    row = db_session.execute(
        sa_text("""
            SELECT source_id, doi, pmid, url, title, journal, year, publication_type, organization
            FROM documents_meta WHERE source_id=:sid
        """),
        {"sid": source_id}
    ).mappings().first()
    return dict(row) if row else None


def enrich_source_from_meta(source: Dict[str, Any], db_session) -> Dict[str, Any]:
    s2 = dict(source)
    sid = s2.get("source_id")
    if not sid:
        return s2

    meta = fetch_doc_meta(db_session, sid)
    if meta:
        for field in ("doi", "pmid", "url", "title", "journal", "year"):
            if not s2.get(field) and meta.get(field):
                s2[field] = meta[field]
        if meta.get("publication_type"):
            s2["publication_type"] = meta["publication_type"]
        if meta.get("organization"):
            s2["organization_or_journal"] = s2.get("organization_or_journal") or meta["organization"]

    enriched = classify_chunk(s2)
    display_et = DISPLAY_LABELS.get(enriched.evidence_type, enriched.evidence_type)
    s2["evidence_type"] = display_et
    s2["evidence_type_raw"] = enriched.evidence_type
    s2["evidence_tier"] = enriched.evidence_tier
    s2["evidence_grade"] = enriched.evidence_grade
    s2["evidence_rank"] = evidence_rank_from_display(display_et)
    return s2


def compute_aci_from_enriched(topic: str, enriched_sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    sources = []
    for s in enriched_sources:
        src = Source(
            id=s.get("source_id") or s.get("id") or "",
            title=s.get("title") or "",
            journal=s.get("organization_or_journal") or s.get("journal"),
            year=s.get("year") if isinstance(s.get("year"), int) else None,
            evidence_type=s.get("evidence_type_raw") or "Other",
            evidence_tier=s.get("evidence_tier") or "C",
            evidence_grade=s.get("evidence_grade") or "IV",
        )
        sources.append(src)

    aci = compute_aci(topic=topic, sources=sources)
    return asdict(aci)


def build_followup_hint(intent: str) -> str:
    if intent in ("complications", "complication"):
        return (
            "Follow-up questions should be protocol-specific "
            "(e.g., reassessment timing, repeat dosing interval, red-flag symptoms, urgent referral criteria).\n"
        )
    if intent in ("technique_or_dosing", "dosing"):
        return (
            "Follow-up questions should clarify dosing protocol details "
            "(e.g., repeat dosing interval, dosing per area, reassessment criteria).\n"
        )
    return ""


# ── Evidence hierarchy shim — import from canonical module ──────────────────
try:
    from app.engine.evidence_hierarchy import (
        classify_document  as classify_chunk,          # noqa: F811, F401
        EVIDENCE_TYPE_MAP  as _TYPE_MAP,
        badge_for_type     as _badge_for_type,
        enrich_chunks_for_api,                         # noqa: F401
    )
    DISPLAY_LABELS = {k: v[0] for k, v in _TYPE_MAP.items()}

    def evidence_rank_from_display(display: str) -> int:
        for canonical, (label, rank) in _TYPE_MAP.items():
            if label == display:
                return rank
        return 10
except ImportError:
    pass
