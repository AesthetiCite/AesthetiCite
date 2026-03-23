"""
Governance pipeline for AesthetiCite.

- Domain-weighted retrieval reranking
- Intent-aware complication boost
- Strict citation validation
- Citation density computation
- Audit logging with gap analysis
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_IN_MEMORY = 2000

DOMAIN_PRIORITY = {
    "aesthetic_core": 1.0,
    "aesthetic_medicine": 1.0,
    "plastic_surgery": 0.85,
    "dermatology": 0.65,
    "general_medicine": 0.45,
}

CITATION_RE = re.compile(r"\[S\d+\]")


@dataclass
class GovernanceEvent:
    timestamp: float
    question_hash: str
    question_preview: str
    source_ids: List[str]
    source_count: int
    aci_score: Optional[float]
    citation_density: float
    citation_valid: bool
    lang: str
    intent: str
    total_ms: int
    evidence_badge: Optional[str] = None
    gaps: List[str] = field(default_factory=list)


_log_buffer: deque[GovernanceEvent] = deque(maxlen=MAX_IN_MEMORY)


def detect_intent(q: str) -> str:
    ql = q.lower()
    if any(k in ql for k in [
        "occlusion", "vascular", "necrosis", "blindness", "embol",
        "ischemia", "complication", "adverse event", "adverse",
        "granuloma", "infection", "hematoma", "edema", "swelling",
        "nodule", "migration", "asymmetry", "ptosis", "bruising",
        "skin necrosis", "filler migration", "tyndall", "biofilm",
        "hypersensitivity", "allergic", "anaphyla", "tissue death",
        "stroke", "vision loss", "skin discoloration",
        "nécrose", "ischémie", "cécité", "hématome", "infection",
        "complicación", "necrosis", "hematoma", "hinchazón",
        "komplikation", "nekrose", "hämatom",
        "مضاعفات", "نخر", "انسداد",
        "合并症", "坏死", "并发症",
        "合併症", "壊死",
        "осложнение", "некроз",
    ]):
        return "complication"
    if any(k in ql for k in [
        "dose", "dosing", "units", "dilution", "reconstitution",
        "max dose", "maximum dose", "concentration", "volume",
        "injection technique", "injection site", "how many units",
        "posologie", "dilución", "dosis", "dosierung",
        "جرعة", "剂量", "用量",
        "дозировка", "доза",
    ]):
        return "dosing"
    if any(k in ql for k in [
        "compare", "versus", "vs ", "comparison", "difference between",
        "better than", "which is better", "pros and cons",
        "comparaison", "comparación", "vergleich",
        "مقارنة", "比较", "比較", "сравнение",
    ]):
        return "comparison"
    if any(k in ql for k in [
        "mechanism", "how does", "pharmacokinetics", "pharmacodynamics",
        "half-life", "onset", "duration of action", "mode of action",
        "mécanisme", "mecanismo", "mechanismus",
        "آلية", "机制", "機序", "механизм",
    ]):
        return "mechanism"
    return "general"


def rerank_by_domain(chunks: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
    now_year = time.gmtime().tm_year

    def _score(c: Dict[str, Any]) -> float:
        domain = (c.get("domain") or "general_medicine").lower().replace(" ", "_")
        domain_w = DOMAIN_PRIORITY.get(domain, 0.5)

        doc_type = (c.get("document_type") or "").lower()
        if "guideline" in doc_type or "consensus" in doc_type:
            ev_rank = 1
        elif "systematic" in doc_type or "meta" in doc_type:
            ev_rank = 2
        elif "random" in doc_type or "rct" in doc_type or "trial" in doc_type:
            ev_rank = 3
        elif "cohort" in doc_type or "observational" in doc_type:
            ev_rank = 5
        elif "case" in doc_type:
            ev_rank = 7
        else:
            ev_rank = 6

        evidence_bonus = (10 - ev_rank) / 10
        year = c.get("year") or 2000
        recency_bonus = max(0, (year - 2000)) / 50
        complication_boost = 0.2 if intent == "complication" and ev_rank <= 2 else 0

        return domain_w + evidence_bonus + recency_bonus + complication_boost

    return sorted(chunks, key=_score, reverse=True)


def validate_citations(answer_text: str) -> bool:
    if not CITATION_RE.search(answer_text):
        return False

    _CLAIM_HEADERS = (
        "Key Evidence-Based Points",
        "Evidence-Based Answer",
        "Clinical Summary",
    )
    _STOP_HEADERS = (
        "Safety Considerations",
        "Limitations",
        "Suggested Follow-up",
        "Red Flags",
        "Evidence Level",
        "Evidence Strength",
    )

    in_claim = False
    claim_bullets: list[str] = []
    claim_prose: list[str] = []
    for line in answer_text.split("\n"):
        stripped = line.strip()
        if any(h in stripped for h in _CLAIM_HEADERS):
            in_claim = True
            continue
        if any(h in stripped for h in _STOP_HEADERS):
            in_claim = False
            continue
        if in_claim:
            if re.match(r"^[-*]\s+", stripped):
                claim_bullets.append(stripped)
            elif len(stripped) > 30 and not stripped.startswith("#") and not stripped.startswith("**"):
                claim_prose.append(stripped)

    claim_lines = claim_bullets or claim_prose
    if not claim_lines:
        total_citations = len(CITATION_RE.findall(answer_text))
        return total_citations >= 2

    cited = sum(1 for b in claim_lines if CITATION_RE.search(b))
    return cited >= max(1, len(claim_lines) * 0.5)


REFUSAL_ANSWER = (
    "**Clinical Summary**\n"
    "Evidence insufficient based on retrieved sources.\n\n"
    "**Limitations / Uncertainty**\n"
    "Retrieved evidence does not adequately support a grounded response "
    "with inline citations. Please refine your question or consult primary sources.\n"
)


def compute_citation_density(answer_text: str) -> float:
    lines = [l.strip() for l in answer_text.split("\n") if l.strip()]
    claim_lines = [
        l for l in lines
        if l.startswith("-") or l.startswith("*") or (len(l) > 30 and not l.startswith("#") and not l.startswith("**"))
    ]
    if not claim_lines:
        return 0.0
    cited = sum(1 for l in claim_lines if CITATION_RE.search(l))
    return round(cited / len(claim_lines), 3)


def log_governance_event(
    question: str,
    source_ids: List[str],
    aci_score: Optional[float],
    answer_text: str,
    lang: str,
    total_ms: int,
    evidence_badge: Optional[str] = None,
    citation_valid: bool = True,
) -> GovernanceEvent:
    density = compute_citation_density(answer_text)
    intent = detect_intent(question)
    q_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
    preview = question[:80] + ("..." if len(question) > 80 else "")

    gaps: List[str] = []
    if density < 0.5:
        gaps.append("Low citation density (<50%)")
    if len(source_ids) < 3:
        gaps.append("Limited supporting sources")
    if aci_score is not None and aci_score < 4.0:
        gaps.append("Low confidence score")
    if not citation_valid:
        gaps.append("Citation validation failed — answer replaced with refusal")

    event = GovernanceEvent(
        timestamp=time.time(),
        question_hash=q_hash,
        question_preview=preview,
        source_ids=source_ids,
        source_count=len(source_ids),
        aci_score=aci_score,
        citation_density=density,
        citation_valid=citation_valid,
        lang=lang,
        intent=intent,
        total_ms=total_ms,
        evidence_badge=evidence_badge,
        gaps=gaps,
    )

    _log_buffer.append(event)
    logger.info(
        f"Governance: hash={q_hash} aci={aci_score} density={density:.2f} "
        f"valid={citation_valid} sources={len(source_ids)} lang={lang} intent={intent} ms={total_ms}"
    )
    return event


def get_governance_logs(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    items = list(_log_buffer)
    items.reverse()
    page = items[offset:offset + min(limit, 500)]
    return [asdict(e) for e in page]


def get_governance_summary() -> Dict[str, Any]:
    items = list(_log_buffer)
    if not items:
        return {"total_queries": 0}

    aci_scores = [e.aci_score for e in items if e.aci_score is not None]
    densities = [e.citation_density for e in items]
    intents: Dict[str, int] = {}
    langs: Dict[str, int] = {}
    low_density_count = sum(1 for d in densities if d < 0.5)
    citation_fail_count = sum(1 for e in items if not e.citation_valid)

    for e in items:
        intents[e.intent] = intents.get(e.intent, 0) + 1
        langs[e.lang] = langs.get(e.lang, 0) + 1

    return {
        "total_queries": len(items),
        "avg_aci": round(sum(aci_scores) / len(aci_scores), 2) if aci_scores else None,
        "avg_citation_density": round(sum(densities) / len(densities), 3) if densities else None,
        "low_density_pct": round(low_density_count / len(items) * 100, 1),
        "citation_fail_pct": round(citation_fail_count / len(items) * 100, 1),
        "intent_distribution": intents,
        "lang_distribution": langs,
    }
