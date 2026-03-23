"""
AesthetiCite — Guideline-first retrieval + query expansion + tier-aware reranking

Retrieves higher-quality evidence first (Guidelines / Consensus / Systematic reviews / Meta-analyses / RCTs),
expands complication queries so guidelines are found more reliably, ensures top sources shown are Tier A/B
before Tier C when available, and recomputes deterministic ACI AFTER fusion.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from cachetools import TTLCache

logger = logging.getLogger(__name__)

CACHE_TTL = 300
CACHE_MAX_SIZE = 500
_fusion_cache: TTLCache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL)
_cache_lock = threading.Lock()

_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}


QUALITY_PUB_TYPES = {
    "guideline",
    "consensus",
    "position statement",
    "systematic review",
    "meta-analysis",
    "meta analysis",
    "randomized controlled trial",
    "rct",
}

AUTHORITY_KEYWORDS = [
    "guideline", "consensus", "position statement",
    "recommendation", "delphi", "expert panel",
    "society guideline", "practice advisory",
]

EMERGENCY_HINTS = [
    "vascular occlusion", "occlusion", "ischemia", "ischaemia", "necrosis",
    "vision loss", "blindness", "embol", "intravascular", "arterial",
    "hyaluronidase", "filler complication", "adverse event", "complication",
]

EXPANSIONS = {
    "vascular occlusion": [
        "vascular compromise", "intravascular injection", "ischemic event",
        "ischemia", "arterial occlusion", "filler-induced ischemia",
        "hyaluronic acid filler complication", "dermal filler complication",
    ],
    "hyaluronidase": [
        "hyaluronidase protocol", "high-dose hyaluronidase", "hyaluronidase consensus",
        "hyaluronidase guideline", "hyaluronidase vascular compromise",
    ],
    "vision": [
        "ocular complication", "retinal artery occlusion", "visual loss filler",
        "ophthalmic emergency dermal filler",
    ],
}

EVIDENCE_TYPE_ORDER = [
    "Guideline", "Consensus", "SystematicReview", "MetaAnalysis", "RCT",
    "Cohort", "CaseControl", "CaseSeries", "NarrativeReview", "CaseReport", "Other"
]
EVIDENCE_TYPE_RANK = {t: i for i, t in enumerate(EVIDENCE_TYPE_ORDER)}

TIER_RANK = {"A": 0, "B": 1, "C": 2}


@dataclass
class Source:
    id: str
    title: str
    journal: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    publication_type: Optional[str] = None
    publication_types: Optional[List[str]] = None
    source_tier: Optional[str] = None
    evidence_rank: Optional[float] = None
    evidence_type: str = "Other"
    evidence_tier: str = "C"
    evidence_grade: str = "IV"
    source_id: Optional[str] = None
    organization_or_journal: Optional[str] = None
    chunk_text: Optional[str] = None
    page_or_section: Optional[str] = None
    pmid: Optional[str] = None
    doi_url: Optional[str] = None
    pubmed_url: Optional[str] = None
    authors: Optional[str] = None
    document_type: Optional[str] = None
    _raw: Optional[Dict[str, Any]] = None


@dataclass
class ACIResult:
    score_0_to_10: float
    badge: str
    components: Dict[str, float]
    rationale: str


def _norm_list(x: Optional[List[str]]) -> List[str]:
    return [s.strip().lower() for s in (x or []) if s and s.strip()]

def _norm_str(x: Optional[str]) -> str:
    return (x or "").strip().lower()

def classify_evidence_type(src: Source) -> str:
    pub = _norm_list(src.publication_types)
    one = _norm_str(src.publication_type)
    title = (src.title or "").lower()

    merged = set(pub)
    if one:
        merged.add(one)

    def has_any(sub: str) -> bool:
        return any(sub in p for p in merged)

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
    if has_any("randomized") or has_any("rct") or has_any("trial"):
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


def enrich_sources(raw_sources: List[Dict[str, Any]]) -> List[Source]:
    out: List[Source] = []
    for r in raw_sources:
        s = Source(
            id=str(r.get("id") or r.get("source_id") or r.get("doc_id") or ""),
            title=str(r.get("title") or r.get("paper_title") or ""),
            journal=r.get("journal") or r.get("organization_or_journal"),
            year=r.get("year"),
            url=r.get("url"),
            doi=r.get("doi"),
            publication_type=r.get("publication_type") or r.get("pub_type") or r.get("document_type"),
            publication_types=r.get("publication_types") or r.get("pub_types"),
            source_tier=r.get("source_tier"),
            evidence_rank=r.get("evidence_rank") or r.get("score"),
            source_id=r.get("source_id") or str(r.get("id") or ""),
            organization_or_journal=r.get("organization_or_journal") or r.get("journal"),
            chunk_text=r.get("chunk_text") or r.get("text") or r.get("content"),
            page_or_section=r.get("page_or_section"),
            pmid=r.get("pmid"),
            doi_url=r.get("doi_url"),
            pubmed_url=r.get("pubmed_url"),
            authors=r.get("authors"),
            document_type=r.get("document_type"),
            _raw=r,
        )
        s.evidence_type = classify_evidence_type(s)
        s.evidence_tier = map_to_tier(s.evidence_type) if not s.source_tier else str(s.source_tier).strip().upper()
        s.evidence_grade = map_to_grade(s.evidence_type)
        out.append(s)
    return [s for s in out if s.id and s.title]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def compute_aci(question: str, sources: List[Source], now_year: Optional[int] = None) -> ACIResult:
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

    recs: List[float] = []
    for s in sources:
        if not s.year:
            recs.append(0.4)
        else:
            age = max(0, now_year - int(s.year))
            rec = 1.0 / (1.0 + (age / 6.0))
            recs.append(_clamp(rec, 0.15, 1.0))
    recency = sum(recs) / n

    source_count = _clamp(1.0 - math.exp(-n / 7.0), 0.0, 1.0)

    guideline_presence = 1.0 if any(s.evidence_type in {"Guideline", "Consensus"} for s in sources) else 0.0

    q = (question or "").lower()
    missing_guideline_penalty = 0.0
    if any(k in q for k in EMERGENCY_HINTS) and guideline_presence < 0.5:
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

    score = round(raw * 10.0, 1)
    badge = "High" if score >= 8.0 else ("Moderate" if score >= 5.5 else "Low")

    rationale = (
        f"Computed from tier quality ({tier_quality:.2f}), diversity ({diversity:.2f}), "
        f"recency ({recency:.2f}), source count ({source_count:.2f}), guideline presence ({guideline_presence:.0f}), "
        f"authority boost ({authority_boost:.2f}, {authority_count} high-quality sources)."
    )
    if missing_guideline_penalty:
        rationale += " Mild penalty applied: emergency topic lacks guideline/consensus evidence."

    return ACIResult(
        score_0_to_10=score,
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


def expand_query(question: str) -> List[str]:
    q = (question or "").strip()
    ql = q.lower()
    expansions: List[str] = [q]

    if any(k in ql for k in EMERGENCY_HINTS):
        expansions.append(q + " guideline")
        expansions.append(q + " consensus")
        expansions.append(q + " position statement")
        expansions.append(q + " systematic review")
        expansions.append(q + " complications management")

    for key, adds in EXPANSIONS.items():
        if key in ql:
            for a in adds:
                expansions.append(f"{q} {a}")
                expansions.append(f"{a} guideline consensus")

    seen = set()
    dedup: List[str] = []
    for x in expansions:
        nx = " ".join(x.split())
        if nx.lower() not in seen:
            seen.add(nx.lower())
            dedup.append(nx)
    return dedup[:10]


def build_quality_filters() -> Dict[str, Any]:
    return {
        "publication_type_in": [
            "Guideline", "Consensus", "Position Statement",
            "Systematic Review", "Meta-analysis", "Randomized Controlled Trial"
        ]
    }


def _source_key(s: Source) -> str:
    if s.doi:
        return f"doi:{s.doi.lower()}"
    ty = (s.title or "").strip().lower()
    yr = str(s.year or "")
    if ty:
        return f"title:{ty}|year:{yr}"
    return f"id:{s.id}"


def rerank_sources(question: str, sources: List[Source]) -> List[Source]:
    ql = (question or "").lower()
    emergency = any(k in ql for k in EMERGENCY_HINTS)

    def score(s: Source) -> Tuple[int, int, int, float]:
        tier_r = TIER_RANK.get(s.evidence_tier, 2)
        type_r = EVIDENCE_TYPE_RANK.get(s.evidence_type, EVIDENCE_TYPE_RANK["Other"])
        year_r = -(int(s.year) if s.year else 0)
        retr = -(float(s.evidence_rank) if s.evidence_rank is not None else 0.0)

        if emergency and s.evidence_type in {"Guideline", "Consensus"}:
            type_r -= 2
            tier_r = 0

        return (tier_r, type_r, year_r, retr)

    return sorted(sources, key=score)


def _cache_key(question: str, k_final: int, k_quality: int, k_general: int) -> str:
    norm = re.sub(r"\s+", " ", (question or "").strip().lower())
    raw = f"{norm}|{k_final}|{k_quality}|{k_general}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _do_retrieve(
    question: str,
    retrieve_fn: Callable[[str, int, Optional[Dict[str, Any]]], List[Dict[str, Any]]],
    k_final: int,
    k_quality: int,
    k_general: int,
) -> Dict[str, Any]:
    expansions = expand_query(question)

    merged: Dict[str, Source] = {}

    def _add_results(results: List[Dict[str, Any]], overwrite: bool = False) -> None:
        for r in (results or []):
            enriched = enrich_sources([r])
            if enriched:
                key = _source_key(enriched[0])
                if overwrite or key not in merged:
                    merged[key] = enriched[0]

    authority_query = question.strip() + " guideline consensus position statement"
    try:
        _add_results(retrieve_fn(authority_query, k_quality, None), overwrite=True)
    except Exception:  # nosec B110
        pass

    q_filters = build_quality_filters()
    for q in expansions[:4]:
        try:
            _add_results(retrieve_fn(q, k_quality, q_filters))
        except Exception:
            _add_results(retrieve_fn(q, k_quality, None))

    for q in expansions[:3]:
        _add_results(retrieve_fn(q, k_general, None))

    fused = rerank_sources(question, list(merged.values()))[:k_final]

    # Enrich fused sources with canonical evidence metadata
    try:
        from app.engine.evidence_hierarchy import classify_document
        for s in fused:
            raw = asdict(s)
            tagged = classify_document(raw)
            if not s.evidence_type or s.evidence_type in ("Other", "unknown"):
                s.evidence_type = tagged.get("evidence_type_display", s.evidence_type)
    except Exception:
        pass

    aci = compute_aci(question, fused)

    return {
        "sources": fused,
        "sources_dicts": [asdict(s) for s in fused],
        "aci": aci,
        "aci_dict": asdict(aci),
        "meta": {
            "retrieval_mode": "authority_fusion_v2",
            "expansions_used": [authority_query] + expansions[:4],
            "retrieved_unique_sources": len(fused),
            "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    }


def retrieve_with_quality_fusion(
    question: str,
    retrieve_fn: Callable[[str, int, Optional[Dict[str, Any]]], List[Dict[str, Any]]],
    k_final: int = 40,
    k_quality: int = 25,
    k_general: int = 40,
) -> Dict[str, Any]:
    key = _cache_key(question, k_final, k_quality, k_general)

    with _cache_lock:
        cached = _fusion_cache.get(key)
        if cached is not None:
            _cache_stats["hits"] += 1
            logger.info(
                f"Quality fusion CACHE HIT (key={key[:8]}…, "
                f"sources={len(cached['sources'])}, "
                f"ACI={cached['aci'].score_0_to_10}, "
                f"hits={_cache_stats['hits']}, misses={_cache_stats['misses']})"
            )
            cached_copy = dict(cached)
            cached_copy["meta"] = dict(cached_copy.get("meta", {}))
            cached_copy["meta"]["cache_hit"] = True
            return cached_copy

    _cache_stats["misses"] += 1
    t0 = time.perf_counter()
    result = _do_retrieve(question, retrieve_fn, k_final, k_quality, k_general)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    result["meta"]["retrieval_ms"] = round(elapsed_ms, 1)
    result["meta"]["cache_hit"] = False
    result["meta"]["cache_key"] = key[:8]

    with _cache_lock:
        old_len = len(_fusion_cache)
        _fusion_cache[key] = result
        if len(_fusion_cache) <= old_len and old_len >= CACHE_MAX_SIZE:
            _cache_stats["evictions"] += 1

    logger.info(
        f"Quality fusion CACHE MISS (key={key[:8]}…, "
        f"sources={len(result['sources'])}, "
        f"ACI={result['aci'].score_0_to_10}, "
        f"retrieval={elapsed_ms:.0f}ms, "
        f"cache_size={len(_fusion_cache)}, "
        f"hits={_cache_stats['hits']}, misses={_cache_stats['misses']})"
    )
    return result


def get_fusion_cache_stats() -> Dict[str, Any]:
    with _cache_lock:
        total = _cache_stats["hits"] + _cache_stats["misses"]
        hit_rate = (_cache_stats["hits"] / total * 100) if total > 0 else 0.0
        return {
            "hits": _cache_stats["hits"],
            "misses": _cache_stats["misses"],
            "evictions": _cache_stats["evictions"],
            "hit_rate_pct": round(hit_rate, 1),
            "cache_size": len(_fusion_cache),
            "cache_max_size": CACHE_MAX_SIZE,
            "cache_ttl_seconds": CACHE_TTL,
        }


def clear_fusion_cache() -> Dict[str, Any]:
    with _cache_lock:
        size_before = len(_fusion_cache)
        _fusion_cache.clear()
        _cache_stats["hits"] = 0
        _cache_stats["misses"] = 0
        _cache_stats["evictions"] = 0
        return {"cleared": size_before, "status": "ok"}


def protocol_followups(question: str) -> List[str]:
    q = (question or "").lower()
    if "hyaluronidase" in q and ("occlusion" in q or "ischemi" in q):
        return [
            "What repeat dosing interval is recommended (e.g., every 30-60 minutes) and when should dosing be escalated?",
            "What clinical signs suggest worsening ischemia requiring urgent escalation or referral?",
            "What adjunctive measures are recommended alongside hyaluronidase and what is the evidence strength for each?",
            "If ocular symptoms occur, what immediate emergency steps and referral pathway are recommended?",
            "How do recommendations differ for impending versus established occlusion?"
        ]
    return [
        "What guideline or consensus statement provides the highest-quality recommendation on this topic?",
        "What contraindications and safety monitoring should be considered?",
        "Which patient factors change management and why?",
        "What evidence gaps remain and what studies would most strengthen recommendations?"
    ]


def source_to_citation_dict(s: Source, index: int) -> Dict[str, Any]:
    display_et = DISPLAY_LABELS.get(s.evidence_type, s.evidence_type)
    return {
        "id": index + 1,
        "title": s.title or "Unknown",
        "source": s.journal or s.organization_or_journal or "Research Source",
        "year": s.year or 2024,
        "authors": s.authors or "Author et al.",
        "url": s.url or s.doi_url or s.pubmed_url or "",
        "doi": s.doi or "",
        "document_type": s.document_type or "",
        "evidence_type": display_et,
        "evidence_type_raw": s.evidence_type,
        "evidence_tier": s.evidence_tier,
        "evidence_grade": s.evidence_grade,
        "evidence_rank": EVIDENCE_TYPE_RANK.get(s.evidence_type, 10),
        "source_tier": s.evidence_tier,
        "publication_type": s.publication_type or s.document_type or "",
        "source_id": s.source_id or s.id,
        "journal": s.journal or s.organization_or_journal or "",
    }
