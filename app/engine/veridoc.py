"""
AesthetiCiteEngine — Evidence-grounded answering engine v2.

Implements:
  1) SPEED: Parallel multi-query retrieval, time-budgeted pipeline,
     aggressive caching (LRU+TTL), early exits, FAST mode (~15s target).
  2) DeepConsult reframing: Dedicated DEEPCONSULT mode with medico-legal/safety
     emphasis and PDF-ready structured output.
  3) Source-tier strategy: IFU/consensus/guideline weighting for aesthetic medicine,
     domain modifiers, defensibility > prestige.
  4) Aesthetic Confidence Index (ACI): Per-answer and per-claim confidence scoring
     based on evidence type, recency, and consensus across sources.
  5) Complication Protocol Layer: Automatic safety protocol injection for
     injectable-related queries (red flags, immediate actions).
  6) Aesthetic query classification: Injectable/device/regulatory routing with
     risk-level assessment for high-risk anatomical zones.

Usage:
  engine = AesthetiCiteEngine(retrieve_fn, llm_json_fn, llm_text_fn)
  out = engine.answer("question", mode="fast")
  out2 = engine.answer("question", mode="deepconsult")
"""

from __future__ import annotations

import math
import os
import re
import time
import json
import hashlib
import logging
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

_WORD = re.compile(r"\w+", re.UNICODE)
_NUMBER = re.compile(r"(?<![A-Za-z])(\d+(\.\d+)?)(?![A-Za-z])")

STRONG_TYPES = {"guideline", "consensus", "review", "rct", "ifu"}


# ---------------------------------------------------------------------------
# Aesthetic Confidence Index (ACI™)
# ---------------------------------------------------------------------------

ACI_EVIDENCE_WEIGHTS = {
    "guideline": 1.00,
    "consensus": 1.00,
    "meta-analysis": 0.95,
    "systematic-review": 0.90,
    "ifu": 0.92,
    "rct": 0.85,
    "labeling": 0.80,
    "cohort": 0.70,
    "case-control": 0.65,
    "observational": 0.65,
    "review": 0.55,
    "case-series": 0.45,
    "case_series": 0.45,
    "case-report": 0.35,
    "case_report": 0.35,
    "expert-opinion": 0.25,
    "expert": 0.25,
    "opinion": 0.25,
    "other": 0.40,
}


ACI_RECENCY_HALF_LIFE_YEARS = float(os.environ.get("ACI_RECENCY_HALF_LIFE_YEARS", "6"))


def _aci_recency_score(year: Optional[int], now_year: int = 2026) -> float:
    if not year or year < 1900 or year > now_year:
        return 0.5
    age = max(0, now_year - year)
    return 2 ** (-(age / max(0.1, ACI_RECENCY_HALF_LIFE_YEARS)))


def _aci_year_modifier(year: Optional[int], now_year: int = 2026) -> float:
    if not year:
        return 0.90
    age = max(0, now_year - year)
    if age <= 2:
        return 1.00
    if age <= 5:
        return 0.95
    if age <= 10:
        return 0.90
    return 0.85


def _aci_consensus_modifier(n_unique_sources: int) -> float:
    if n_unique_sources >= 4:
        return 1.00
    if n_unique_sources == 3:
        return 0.95
    if n_unique_sources == 2:
        return 0.90
    if n_unique_sources == 1:
        return 0.80
    return 0.60


def _infer_evidence_type_aci(doc_type: Optional[str], journal: Optional[str] = None) -> str:
    t = (doc_type or "").lower()
    if "guideline" in t or "consensus" in t or "recommendation" in t:
        return "Guideline/Consensus"
    if "systematic" in t or "meta" in t:
        return "Systematic Review"
    if "random" in t or "rct" in t or "trial" in t:
        return "Randomized Trial"
    if "cohort" in t or "case-control" in t or "observational" in t:
        return "Observational Study"
    if "case report" in t or "case series" in t:
        return "Case Report/Series"
    if "review" in t:
        return "Narrative Review"
    return "Other"


def _evidence_rank_aci(evidence_type: str) -> int:
    order = {
        "Guideline/Consensus": 1, "Systematic Review": 2,
        "Randomized Trial": 3, "Observational Study": 5,
        "Case Report/Series": 6, "Narrative Review": 7,
    }
    return order.get(evidence_type, 8)


def compute_aci(
    sources: List[Dict[str, Any]],
    risk_level: str = "low",
) -> Dict[str, Any]:
    """
    ACI v2: More realistic confidence scoring with evidence mix analysis,
    half-life recency decay, diminishing returns, and gap detection.
    Returns dict with overall_confidence_0_10, highest_level, gaps, mix.
    """
    import time as _time
    now_year = _time.gmtime().tm_year

    n = len(sources)
    if n == 0:
        return {
            "overall_confidence_0_10": 0.0,
            "highest_level": "N/A",
            "supporting_count": 0,
            "gaps": ["No sources retrieved"],
            "mix": {},
        }

    ranks = []
    types = []
    years = []
    for s in sources:
        st = s.get("source_type") or s.get("evidence_type") or "other"
        et = _infer_evidence_type_aci(st, s.get("journal") or s.get("organization_or_journal"))
        r = _evidence_rank_aci(et)
        y = s.get("year")
        types.append(et)
        ranks.append(r)
        years.append(y if isinstance(y, int) else None)

    mix: Dict[str, int] = {}
    for t_ in types:
        mix[t_] = mix.get(t_, 0) + 1

    best_idx = min(range(n), key=lambda i: ranks[i])
    highest = types[best_idx]

    hi = sum(1 for r in ranks if r <= 1)
    sr = sum(1 for r in ranks if r == 2)
    rct = sum(1 for r in ranks if r == 3)
    low = sum(1 for r in ranks if r >= 5)

    hi_frac = hi / n
    strong_frac = (hi + sr + rct) / n
    low_frac = low / n

    rec_scores = [_aci_recency_score(y, now_year) for y in years if y]
    rec = (sum(rec_scores) / len(rec_scores)) if rec_scores else 0.55

    support_score = min(1.0, (n ** 0.5) / (20 ** 0.5))

    base = 0.0
    base += 0.55 * strong_frac
    base += 0.20 * hi_frac
    base += 0.15 * rec
    base += 0.10 * support_score
    base -= 0.35 * max(0.0, low_frac - 0.35)

    risk_penalty = {"low": 0.0, "medium": 0.05, "high": 0.12}.get(risk_level, 0.05)
    base -= risk_penalty

    conf = max(0.0, min(1.0, base))
    conf_0_10 = round(conf * 10.0, 1)

    gaps = []
    if n < 5:
        gaps.append("Limited number of directly relevant sources retrieved")
    if strong_frac < 0.25:
        gaps.append("Low proportion of high-level evidence (guidelines/systematic reviews/RCTs)")
    if rec < 0.45:
        gaps.append("Evidence appears older on average (limited recent high-quality data)")
    if highest in ("Case Report/Series", "Narrative Review", "Other"):
        gaps.append("Highest evidence level found is low; interpret cautiously")

    return {
        "overall_confidence_0_10": conf_0_10,
        "highest_level": highest,
        "supporting_count": n,
        "gaps": gaps,
        "mix": mix,
    }


def compute_aci_from_references(
    refs: List[Dict[str, Any]],
    risk_level: str = "low",
) -> Dict[str, Any]:
    """Compute ACI v2 from reference metadata."""
    if not refs:
        return {
            "overall_confidence_0_10": 0.0,
            "highest_level": "N/A",
            "supporting_count": 0,
            "gaps": ["No sources retrieved"],
            "mix": {},
        }
    aci_sources = []
    for r in refs:
        aci_sources.append({
            "source_type": r.get("evidence_type") or r.get("source_type") or "other",
            "year": r.get("year"),
            "id": r.get("source") or r.get("id") or r.get("title", ""),
        })
    return compute_aci(aci_sources, risk_level=risk_level)


# ---------------------------------------------------------------------------
# Aesthetic Query Classification
# ---------------------------------------------------------------------------

INJECTABLE_TRIGGERS = [
    "filler", "hyaluronic", "ha filler", "juvederm", "restylane", "teosyal",
    "belotero", "radiesse", "sculptra", "pmma", "hyaluronidase",
    "vascular occlusion", "botox", "dysport", "xeomin", "bocouture",
    "botulinum", "glabella", "tear trough", "nasolabial", "cannula",
]

DEVICE_TRIGGERS = [
    "laser", "ipl", "radiofrequency", "hifu", "ultherapy", "morpheus",
    "fractional", "co2 laser", "erbium", "nd:yag", "picosecond",
    "microneedling", "energy device",
]

COMPLICATION_TRIGGERS = [
    "occlusion", "ischemia", "necrosis", "blindness", "vision loss", "granuloma",
    "tyndall", "infection", "burn", "hyperpigmentation", "ptosis", "complication",
]

REGULATORY_TRIGGERS = [
    "fda", "ce mark", "ce-mark", "approved", "off-label", "label", "indication",
]

HIGH_RISK_ZONES = [
    "glabella", "nose", "nasal", "tear trough", "forehead",
    "blindness", "vision loss", "retinal", "ophthalmic",
]


def classify_aesthetic_query(query: str) -> Dict[str, Any]:
    q = query.lower()
    injectable = any(t in q for t in INJECTABLE_TRIGGERS)
    device = any(t in q for t in DEVICE_TRIGGERS)
    high_risk = any(t in q for t in HIGH_RISK_ZONES)
    risk_level = "high" if high_risk else ("medium" if injectable else "low")
    matched_zones = [z for z in HIGH_RISK_ZONES if z in q]
    category = "injectable" if injectable else ("device" if device else "general")
    return {
        "is_injectable": injectable,
        "is_device": device,
        "risk_level": risk_level,
        "high_risk_zones": matched_zones,
        "category": category,
    }


def tag_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    t = ((chunk.get("title") or "") + " " + (chunk.get("text") or "")).lower()
    tags = set(chunk.get("aesthetic_tags") or [])

    if any(x in t for x in INJECTABLE_TRIGGERS):
        tags.add("injectables")
    if any(x in t for x in DEVICE_TRIGGERS):
        tags.add("devices")
    if any(x in t for x in COMPLICATION_TRIGGERS):
        tags.add("complications")
    if any(x in t for x in REGULATORY_TRIGGERS):
        tags.add("regulatory")

    chunk["aesthetic_tags"] = sorted(tags)
    return chunk


def apply_aesthetic_boosts(query_meta: Dict[str, Any], chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for c in chunks:
        tag_chunk(c)
        tags = set(c.get("aesthetic_tags") or [])
        boost = 1.0

        if query_meta.get("is_injectable") and "injectables" in tags:
            boost *= 1.25
        if query_meta.get("is_device") and "devices" in tags:
            boost *= 1.20
        if query_meta.get("is_injectable") and "complications" in tags:
            boost *= 1.20
        if "regulatory" in tags:
            boost *= 1.10

        et = (c.get("source_type") or c.get("evidence_type") or "other").lower()
        type_weight = ACI_EVIDENCE_WEIGHTS.get(et, ACI_EVIDENCE_WEIGHTS.get("other", 0.40))
        boost *= (0.9 + 0.2 * type_weight)

        c["aesthetic_boost"] = round(boost, 3)
    return chunks


def execute_inline_tools(query_meta: Dict[str, Any], question: str) -> List[Dict[str, Any]]:
    results = []
    if query_meta.get("is_injectable"):
        results.append({
            "tool": "hyaluronidase_helper",
            "output": {
                "purpose": "Structure the emergency workflow for HA-related vascular compromise.",
                "notes": [
                    "Follow your local protocol and training; dosing must be supported by your cited guideline(s).",
                    "Document time of onset and response.",
                    "Escalate urgently for any ocular symptoms.",
                ],
                "evidence_needed": "Consensus/guideline specifying hyaluronidase approach for HA filler vascular events.",
            },
        })
        if any(t in question.lower() for t in ["botox", "dysport", "xeomin", "bocouture", "botulinum", "dilution"]):
            results.append({
                "tool": "botox_dilution_helper",
                "input": {"vial_units": 100, "diluent_ml": 2.5},
                "output": {
                    "units_per_ml": 40.0,
                    "units_per_0_1ml": 4.0,
                    "note": "This is a math helper. Clinical dosing by region must be evidence-backed and product-specific.",
                },
            })
    if query_meta.get("is_device"):
        results.append({
            "tool": "fitzpatrick_laser_adjustment",
            "output": {
                "risk": "Higher Fitzpatrick types generally have higher PIH risk.",
                "mitigation": [
                    "Consider test spots and conservative starting parameters.",
                    "Emphasize photoprotection and careful post-procedure care.",
                    "Prefer approaches with lower epidermal injury when appropriate.",
                ],
                "note": "Parameter selection must follow device IFU and evidence; this tool provides a conservative checklist.",
            },
        })
    return results


# ---------------------------------------------------------------------------
# Complication Protocol Layer
# ---------------------------------------------------------------------------

def complication_protocol_layer(query: str) -> Optional[Dict[str, Any]]:
    q = query.lower()
    if not any(t in q for t in INJECTABLE_TRIGGERS):
        return None

    return {
        "title": "Complication Protocol Layer (Injectables)",
        "red_flags": [
            "Sudden severe pain, blanching, livedo/reticular discoloration",
            "Cool skin, delayed capillary refill",
            "Visual symptoms (blurred vision, scotoma), ptosis, ophthalmoplegia",
        ],
        "immediate_actions": [
            "Stop injection immediately; do not continue in the area.",
            "Assess perfusion and symptoms; document time of onset.",
            "Initiate your clinic's vascular occlusion protocol and escalate early if any ocular symptoms.",
        ],
        "note": "This section supports risk awareness and does not replace formal training, manufacturer IFUs, or local emergency protocols.",
    }


@dataclass
class ModeConfig:
    wall_time_budget_s: float
    max_queries: int
    per_query_k: int
    max_chunks_after_dedupe: int
    rerank_top_k: int
    min_directness: float
    max_claims: int
    citations_per_claim: int
    require_strong_for_actionable: bool
    label: str


FAST = ModeConfig(
    wall_time_budget_s=90.0,
    max_queries=3,
    per_query_k=14,
    max_chunks_after_dedupe=40,
    rerank_top_k=12,
    min_directness=0.16,
    max_claims=10,
    citations_per_claim=2,
    require_strong_for_actionable=True,
    label="FAST (clinical tool)",
)

DEEPCONSULT = ModeConfig(
    wall_time_budget_s=180.0,
    max_queries=8,
    per_query_k=28,
    max_chunks_after_dedupe=160,
    rerank_top_k=28,
    min_directness=0.12,
    max_claims=18,
    citations_per_claim=3,
    require_strong_for_actionable=True,
    label="DEEPCONSULT (slow & advanced, safety-grade)",
)


class TTLCache:
    def __init__(self, max_items: int = 2048, ttl_s: int = 3600):
        self.max_items = max_items
        self.ttl_s = ttl_s
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._order: List[str] = []

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            ts, val = item
            if now - ts > self.ttl_s:
                self._store.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
                return None
            if key in self._order:
                self._order.remove(key)
            self._order.append(key)
            return val

    def set(self, key: str, val: Any) -> None:
        now = time.time()
        with self._lock:
            if key in self._store:
                self._store[key] = (now, val)
                if key in self._order:
                    self._order.remove(key)
                self._order.append(key)
                return
            while len(self._order) >= self.max_items:
                old = self._order.pop(0)
                self._store.pop(old, None)
            self._store[key] = (now, val)
            self._order.append(key)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _fold_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _light_stem(tok: str) -> str:
    if not tok or not tok.isascii():
        return tok
    for suf in ("ments", "ment", "ations", "ation", "iques", "ique",
                "eurs", "eur", "ées", "ée", "es", "s"):
        if tok.endswith(suf) and len(tok) > len(suf) + 3:
            return tok[: -len(suf)]
    return tok


@lru_cache(maxsize=50_000)
def _tokens(s: str) -> frozenset:
    if not s:
        return frozenset()
    raw = _WORD.findall(_norm(s))
    toks = [w for w in raw if len(w) >= 2]
    folded_str = _fold_accents(" ".join(toks))
    ftoks = _WORD.findall(folded_str)
    out: list[str] = []
    for w in toks:
        out.append(w)
        out.append(_light_stem(w))
    for w in ftoks:
        out.append(w)
        out.append(_light_stem(w))
    return frozenset(w for w in out if w and len(w) >= 2)


def _support_score(claim: str, evidence: str) -> float:
    if not claim or not evidence:
        return 0.0
    cset = _tokens(claim)
    eset = _tokens(evidence)
    if not cset or not eset:
        return 0.0
    inter = len(cset & eset)
    if inter == 0:
        return 0.0
    claim_cov = inter / max(1, len(cset))
    jacc = inter / max(1, len(cset | eset))
    bonus = 0.0
    fc = _fold_accents(claim.lower())
    fe = _fold_accents(evidence.lower())
    cw = _WORD.findall(fc)
    if len(cw) >= 4:
        phrase = " ".join(cw[:3])
        if phrase and phrase in fe:
            bonus = 0.04
    return float(max(0.0, min(1.0, 0.72 * claim_cov + 0.28 * jacc + bonus)))


def _hash_chunk(c: Dict[str, Any]) -> str:
    key = (_norm(c.get("title", "")) + "||" + _norm(c.get("text", ""))[:600]).encode("utf-8")
    return hashlib.sha256(key).hexdigest()


def _dedupe(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for c in chunks:
        h = _hash_chunk(c)
        if h in seen:
            continue
        seen.add(h)
        out.append(c)
    return out


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _is_actionable(text: str) -> bool:
    t = _norm(text)
    markers = (
        "dose", "dosing", "mg", "units", "inject", "interval", "contraindication",
        "should", "must", "recommend", "avoid", "do not", "first-line", "treat",
        "screen", "monitor", "maximum", "minimum", "threshold", "protocol",
    )
    return any(m in t for m in markers)


def _has_numbers(text: str) -> bool:
    return bool(_NUMBER.search(text or ""))


def _evidence_coverage(question: str, chunks: List[Dict[str, Any]]) -> float:
    q = _tokens(question)
    if not q:
        return 0.0
    union = set()
    for c in chunks:
        union |= _tokens((c.get("title", "") + " " + c.get("text", ""))[:6000])
    return len(q & union) / max(1, len(q))


def _quality_weight(source_type: str, domain: str = "") -> float:
    st = _norm(source_type)
    dm = _norm(domain)

    if st in ("guideline", "consensus"):
        base = 1.00
    elif st == "ifu":
        base = 0.92
    elif st in ("labeling", "prescribing information"):
        base = 0.92
    elif st == "review":
        base = 0.85
    elif st == "rct":
        base = 0.80
    elif st in ("cohort", "case_control", "observational"):
        base = 0.62
    elif st == "case_series":
        base = 0.40
    elif st == "case_report":
        base = 0.30
    elif st in ("expert", "opinion"):
        base = 0.40
    else:
        base = 0.45

    if dm in ("society", "manufacturer", "journal"):
        base += 0.04
    if dm == "preprint":
        base -= 0.06

    return max(0.05, min(1.0, base))


def _directness_score(question: str, chunk_text: str) -> float:
    q = _tokens(question)
    c = _tokens(chunk_text)
    if not q or not c:
        return 0.0
    overlap = len(q & c) / max(1, len(q))

    text_l = _norm(chunk_text)
    boosts = 0.0
    for p in ("randomized", "guideline", "consensus", "instructions for use", "ifu",
              "contraindication", "adverse", "complication", "management", "dose", "units", "protocol"):
        if p in text_l:
            boosts += 0.01
    return min(1.0, overlap + boosts)


def _rerank(question: str, chunks: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    scored = []
    for c in chunks:
        text = (c.get("title", "") + " " + c.get("text", ""))[:8000]
        d = _directness_score(question, text)
        q = _quality_weight(c.get("source_type", "other"), c.get("domain", ""))
        score = 0.80 * d + 0.20 * q
        aesthetic_boost = c.get("aesthetic_boost", 1.0)
        score *= aesthetic_boost
        scored.append((score, d, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [c for _, __, c in scored[:top_k]]

    # Apply canonical evidence hierarchy on top of semantic ranking
    try:
        from app.engine.evidence_hierarchy import rank_documents
        ranked = rank_documents(ranked)
    except Exception:
        pass

    return ranked


def _veridoc_safety(question: str, protocol: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach canonical safety assessment to every VeriDoc result."""
    try:
        from app.engine.safety_layer import assess_safety
        existing_risk = protocol.get("risk_level") if protocol else None
        return assess_safety(question, existing_protocol_risk_level=existing_risk)
    except Exception:
        return {}


class AesthetiCiteEngine:
    def __init__(
        self,
        retrieve_fn: Callable[[str, int], List[Dict[str, Any]]],
        llm_json_fn: Callable[[str], Dict[str, Any]],
        llm_text_fn: Callable[[str], str],
        cache: Optional[TTLCache] = None,
        max_workers: int = 8,
    ):
        self.retrieve_fn = retrieve_fn
        self.llm_json_fn = llm_json_fn
        self.llm_text_fn = llm_text_fn
        self.cache = cache or TTLCache(max_items=4096, ttl_s=3600)
        self.pool = ThreadPoolExecutor(max_workers=max_workers)

    def answer(self, question: str, mode: str = "fast", user_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        user_ctx = user_ctx or {}
        mc = FAST if mode.lower() in ("fast", "standard") else DEEPCONSULT
        start = time.time()

        cache_key = f"ans::{mode}::{hashlib.sha256((_norm(question) + json.dumps(user_ctx, sort_keys=True)).encode()).hexdigest()}"
        cached = self.cache.get(cache_key)
        if cached:
            cached = dict(cached)
            cached["meta"] = dict(cached.get("meta", {}))
            cached["meta"]["cache_hit"] = True
            return cached

        try:
            return self._answer_inner(question, mode, user_ctx, mc, start, cache_key)
        except Exception as exc:
            elapsed = int((time.time() - start) * 1000)
            return {
                "status": "error",
                "clinical_answer": f"I was unable to complete the evidence search due to a processing timeout. Please try again or rephrase your question.",
                "references": [],
                "grounded_claims": [],
                "intent_pack": {"intent": "other", "entities": [], "patient_factors": [], "outcome_focus": []},
                "evidence_strength": "Insufficient",
                "meta": {
                    "engine": "veridoc_v2",
                    "mode": mode,
                    "latency_ms": elapsed,
                    "cache_hit": False,
                    "error": str(exc)[:200],
                },
            }

    @staticmethod
    def _intent_from_meta(query_meta: Dict[str, Any]) -> Dict[str, Any]:
        cat = query_meta.get("category", "general")
        intent_map = {
            "injectable": "procedure",
            "device": "device",
            "general": "other",
        }
        intent = intent_map.get(cat, "other")
        entities = query_meta.get("high_risk_zones", [])
        return {
            "intent": intent,
            "entities": entities,
            "patient_factors": [],
            "outcome_focus": ["complication management"] if query_meta.get("risk_level") == "high" else [],
        }

    def _answer_inner(self, question: str, mode: str, user_ctx: Dict[str, Any], mc: ModeConfig, start: float, cache_key: str) -> Dict[str, Any]:
        query_meta = classify_aesthetic_query(question)

        t0 = time.time()
        if mc is FAST:
            intent_pack = self._intent_from_meta(query_meta)
        else:
            intent_pack = self._understand(question, user_ctx, deadline=start + mc.wall_time_budget_s)
        logger.info(f"[VeriDoc] understand: {time.time()-t0:.2f}s (mode={mc.label})")

        subqueries = self._build_subqueries(question, intent_pack, mc)[: mc.max_queries]

        t1 = time.time()
        chunks = self._retrieve_parallel(subqueries, mc, deadline=start + mc.wall_time_budget_s)
        logger.info(f"[VeriDoc] retrieve: {time.time()-t1:.2f}s ({len(chunks)} chunks from {len(subqueries)} queries)")

        chunks = _dedupe(chunks)[: mc.max_chunks_after_dedupe]

        chunks = apply_aesthetic_boosts(query_meta, chunks)

        ranked = _rerank(question, chunks, top_k=min(mc.rerank_top_k, len(chunks)))
        ranked = [c for c in ranked if _directness_score(question, (c.get("title", "") + " " + c.get("text", ""))[:8000]) >= mc.min_directness]

        coverage = _evidence_coverage(question, ranked)

        protocol = complication_protocol_layer(question)

        inline_tools = execute_inline_tools(query_meta, question)

        time_left = (start + mc.wall_time_budget_s) - time.time()
        if (mode.lower() in ("fast", "standard")) and time_left < 3.0:
            out = self._best_effort(question, intent_pack, ranked, coverage, mc, start, query_meta=query_meta, protocol=protocol, inline_tools=inline_tools)
            self.cache.set(cache_key, out)
            return out

        t2 = time.time()
        claim_plan = self._plan_claims(question, intent_pack, ranked, mc, deadline=start + mc.wall_time_budget_s)
        logger.info(f"[VeriDoc] plan_claims: {time.time()-t2:.2f}s ({len(claim_plan.get('claims',[]))} claims)")

        t3 = time.time()
        claims = self._ground_claims(question, claim_plan, ranked, mc, deadline=start + mc.wall_time_budget_s)
        logger.info(f"[VeriDoc] ground_claims: {time.time()-t3:.2f}s (batched={mc is FAST})")

        supported = [c for c in claims if c["status"] == "SUPPORTED"]
        supported_ratio = len(supported) / max(1, len(claims))

        if coverage < 0.22 or (supported_ratio < 0.35 and coverage < 0.6):
            out = self._insufficient(question, intent_pack, ranked, coverage, supported_ratio, mc, start, query_meta=query_meta, inline_tools=inline_tools)
            self.cache.set(cache_key, out)
            return out

        conflicts = self._detect_conflicts(supported)
        t4 = time.time()
        out = self._compose(question, intent_pack, supported, claims, conflicts, ranked, mc, start, query_meta=query_meta, protocol=protocol, inline_tools=inline_tools)
        logger.info(f"[VeriDoc] compose: {time.time()-t4:.2f}s | total: {time.time()-start:.2f}s")

        self.cache.set(cache_key, out)
        return out

    def _understand(self, question: str, user_ctx: Dict[str, Any], deadline: float) -> Dict[str, Any]:
        if time.time() > deadline - 0.5:
            return {"intent": "other", "entities": [], "patient_factors": [], "outcome_focus": []}

        prompt = f"""You are AesthetiCite, an evidence assistant specialized in aesthetic medicine.
Extract intent + key entities.

Return JSON:
- intent: one of ["treatment","procedure","device","safety","contraindication","dosing","guideline","complication","other"]
- entities: key terms (products, procedures, devices, conditions, complications)
- patient_factors: if present (pregnancy, anticoagulants, autoimmune, skin type, etc)
- outcome_focus: (efficacy, duration, adverse events, complication management, etc)

Question: {question}
User context: {user_ctx}"""
        try:
            out = self.llm_json_fn(prompt)
        except Exception:
            out = {}
        return {
            "intent": out.get("intent", "other") or "other",
            "entities": out.get("entities", []) or [],
            "patient_factors": out.get("patient_factors", []) or [],
            "outcome_focus": out.get("outcome_focus", []) or [],
        }

    def _build_subqueries(self, question: str, intent_pack: Dict[str, Any], mc: ModeConfig) -> List[str]:
        intent = intent_pack.get("intent", "other")
        entities = intent_pack.get("entities", [])
        pf = intent_pack.get("patient_factors", [])
        of = intent_pack.get("outcome_focus", [])

        base = [question.strip()]

        if intent in ("complication", "safety", "contraindication"):
            base.append(f"{question} complication management adverse events guideline")
        elif intent in ("device", "procedure", "treatment"):
            base.append(f"{question} protocol technique adverse events guideline")
        elif intent == "dosing":
            base.append(f"{question} dose units interval guideline")
        else:
            base.append(f"{question} review guideline consensus")

        extra = f"{question} cosmetic aesthetic dermatology"
        if entities:
            extra = f"{' '.join(entities)} {intent} cosmetic aesthetic"
        if pf:
            extra += f" {' '.join(pf)}"
        if of:
            extra += f" {' '.join(of)}"
        base.append(extra)

        if mc is not FAST:
            if intent in ("complication", "safety", "contraindication"):
                base.append(f"{question} guideline consensus statement")
            elif intent in ("device", "procedure", "treatment"):
                base.append(f"{question} adverse events contraindications")
                base.append(f"{question} guideline consensus statement")
            if pf:
                base.append(f"{question} {' '.join(pf)} safety")
            if of:
                base.append(f"{question} {' '.join(of)}")

        seen = set()
        out = []
        for q in base:
            nq = _norm(q)
            if nq in seen:
                continue
            seen.add(nq)
            out.append(q)
        return out

    def _retrieve_parallel(self, queries: List[str], mc: ModeConfig, deadline: float) -> List[Dict[str, Any]]:
        futures = []
        out: List[Dict[str, Any]] = []

        for q in queries:
            qkey = f"ret::{hashlib.sha256(_norm(q).encode()).hexdigest()}::{mc.per_query_k}"
            cached = self.cache.get(qkey)
            if cached is not None:
                out.extend(cached)
                continue
            futures.append(self.pool.submit(self._safe_retrieve, q, mc.per_query_k, qkey))

        timeout = max(0.1, deadline - time.time())
        try:
            for fut in as_completed(futures, timeout=timeout):
                try:
                    res = fut.result()
                    if res:
                        out.extend(res)
                except Exception:  # nosec B112
                    continue
                if time.time() > deadline - 1.0:
                    break
        except TimeoutError:
            for fut in futures:
                if fut.done():
                    try:
                        res = fut.result()
                        if res:
                            out.extend(res)
                    except Exception:  # nosec B110
                        pass

        return out

    def _safe_retrieve(self, q: str, k: int, cache_key: str) -> List[Dict[str, Any]]:
        try:
            res = self.retrieve_fn(q, k)
            if isinstance(res, list):
                self.cache.set(cache_key, res)
                logger.debug(f"[VeriDoc] _safe_retrieve: {len(res)} results for '{q[:60]}'")
                return res
        except Exception as e:
            import traceback
            logger.warning(f"[VeriDoc] _safe_retrieve error for '{q[:60]}': {type(e).__name__}: {e}\n{traceback.format_exc()}")
            return []
        return []

    def _plan_claims(self, question: str, intent_pack: Dict[str, Any], ranked: List[Dict[str, Any]], mc: ModeConfig, deadline: float) -> Dict[str, Any]:
        if time.time() > deadline - 1.0:
            return {"claims": [question]}

        source_summaries = [{
            "id": c.get("id"),
            "title": _clip(c.get("title", ""), 140),
            "year": c.get("year"),
            "source_type": c.get("source_type", "other"),
            "domain": c.get("domain", ""),
            "snippet": _clip(c.get("text", ""), 240),
        } for c in ranked[: mc.rerank_top_k]]

        deep_bias = ""
        if mc is DEEPCONSULT:
            deep_bias = """
DEEPCONSULT GOAL:
- prioritize complication management, contraindications, risk mitigation, and defensible guidance
- if evidence is weak, say so and show what is missing
"""

        prompt = f"""You are building an evidence-grounded plan for aesthetic medicine answers.

RULES:
- Atomic, checkable claims only.
- No invented numbers.
- Prefer safety/complications where relevant.
- Max {mc.max_claims} claims.

{deep_bias}

Return JSON: {{ "claims": ["..."] }}

Question: {question}
Intent pack: {intent_pack}

Evidence snippets:
{source_summaries}"""
        try:
            out = self.llm_json_fn(prompt)
        except Exception:
            out = {}
        claims = out.get("claims", []) if isinstance(out, dict) else []
        claims = [c.strip() for c in claims if isinstance(c, str) and c.strip()]
        return {"claims": claims[: mc.max_claims]}

    def _select_support(self, claim: str, ranked: List[Dict[str, Any]], mc: ModeConfig) -> List[Dict[str, Any]]:
        scored = []
        for c in ranked:
            text = (c.get("title", "") + " " + c.get("text", ""))[:8000]
            text_score = _support_score(claim, text)
            quality = _quality_weight(c.get("source_type", "other"), c.get("domain", ""))
            score = 0.68 * text_score + 0.32 * quality
            if score > 0.10:
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored][: mc.citations_per_claim]

    def _ground_claims_batched(self, question: str, claim_plan: Dict[str, Any], ranked: List[Dict[str, Any]], mc: ModeConfig, deadline: float) -> List[Dict[str, Any]]:
        claims = claim_plan.get("claims", [])
        if not claims:
            return []

        claim_support_map: List[Tuple[str, List[Dict[str, Any]]]] = []
        pre_gated: List[Dict[str, Any]] = []

        for claim in claims:
            support = self._select_support(claim, ranked, mc)
            if not support:
                pre_gated.append({"text": claim, "status": "UNSUPPORTED", "citations": [], "notes": "No supporting sources retrieved."})
                continue

            if mc.require_strong_for_actionable and _is_actionable(claim):
                has_strong = any(_norm(s.get("source_type", "")) in STRONG_TYPES for s in support)
                if (not has_strong) and len(support) < 2:
                    pre_gated.append({
                        "text": claim,
                        "status": "WEAK_SUPPORT",
                        "citations": [s.get("id") for s in support if s.get("id")],
                        "notes": "Actionable claim but evidence strength insufficient.",
                    })
                    continue

            claim_support_map.append((claim, support))

        if not claim_support_map:
            return pre_gated

        batch_lines = []
        for idx, (claim, support) in enumerate(claim_support_map, 1):
            excerpts = "; ".join([_clip(s.get("text", ""), 600) for s in support])
            batch_lines.append(f"CLAIM_{idx}: {claim}\nEXCERPTS_{idx}: {excerpts}")

        prompt = f"""You are an evidence-grounded medical writer for aesthetic medicine.

TASK:
For each claim below, rewrite it so it is faithful ONLY to its excerpts.

HARD RULES:
- Do NOT add facts not in excerpts.
- If excerpts do NOT justify a claim, output UNSUPPORTED for that claim.
- If you include numbers, they MUST appear in the excerpts.
- Keep each rewrite concise (1 sentence).

OUTPUT FORMAT (one line per claim, no JSON):
CLAIM_1: <rewritten text or UNSUPPORTED>
CLAIM_2: <rewritten text or UNSUPPORTED>
...

{chr(10).join(batch_lines)}"""

        try:
            response = self.llm_text_fn(prompt).strip()
        except Exception:
            return pre_gated + [{"text": c, "status": "UNSUPPORTED", "citations": [], "notes": "LLM error."} for c, _ in claim_support_map]

        lines = [l.strip() for l in response.split("\n") if l.strip()]
        rewritten_map: Dict[int, str] = {}
        for line in lines:
            m = re.match(r"CLAIM_(\d+):\s*(.+)", line, re.IGNORECASE)
            if m:
                rewritten_map[int(m.group(1))] = m.group(2).strip()

        out = list(pre_gated)
        for idx, (claim, support) in enumerate(claim_support_map, 1):
            rewritten = rewritten_map.get(idx, "")

            if not rewritten or rewritten.upper().startswith("UNSUPPORTED"):
                out.append({"text": claim, "status": "UNSUPPORTED", "citations": [], "notes": "Not justified by excerpts."})
                continue

            if _has_numbers(rewritten):
                nums = {m_num[0] for m_num in _NUMBER.findall(rewritten)}
                sup_text = " ".join([s.get("text", "") for s in support]).lower()
                if not all(n in sup_text for n in nums):
                    out.append({"text": claim, "status": "UNSUPPORTED", "citations": [], "notes": "Rejected: unsourced numeric content."})
                    continue

            out.append({
                "text": rewritten,
                "status": "SUPPORTED",
                "citations": [s.get("id") for s in support if s.get("id")],
                "notes": "",
            })

        return out

    def _ground_claims(self, question: str, claim_plan: Dict[str, Any], ranked: List[Dict[str, Any]], mc: ModeConfig, deadline: float) -> List[Dict[str, Any]]:
        if mc is FAST:
            return self._ground_claims_batched(question, claim_plan, ranked, mc, deadline)

        out = []
        for claim in claim_plan.get("claims", []):
            if time.time() > deadline - 1.0:
                break

            support = self._select_support(claim, ranked, mc)
            if not support:
                out.append({"text": claim, "status": "UNSUPPORTED", "citations": [], "notes": "No supporting sources retrieved."})
                continue

            if mc.require_strong_for_actionable and _is_actionable(claim):
                has_strong = any(_norm(s.get("source_type", "")) in STRONG_TYPES for s in support)
                if (not has_strong) and len(support) < 2:
                    out.append({
                        "text": claim,
                        "status": "WEAK_SUPPORT",
                        "citations": [s.get("id") for s in support if s.get("id")],
                        "notes": "Actionable claim but evidence strength insufficient.",
                    })
                    continue

            support_pack = [{
                "id": s.get("id"),
                "title": _clip(s.get("title", ""), 160),
                "year": s.get("year"),
                "source_type": s.get("source_type", "other"),
                "domain": s.get("domain", ""),
                "excerpt": _clip(s.get("text", ""), 950),
                "url": s.get("url"),
            } for s in support]

            deep_bias = """
DEEPCONSULT RULE:
- If the excerpt is low-quality or indirect, downgrade the claim to "Evidence is limited" wording.
- Emphasize complication management / risk mitigation when relevant.
"""

            prompt = f"""You are an evidence-grounded medical writer for aesthetic medicine.

TASK:
Rewrite the claim so it is faithful ONLY to the supporting excerpts.

HARD RULES:
- Do NOT add facts not present in excerpts.
- If excerpts do NOT justify the claim, output: UNSUPPORTED
- If you include numbers, they MUST appear in excerpts.
- Keep it concise (1 sentence).

{deep_bias}

Original claim: {claim}

Supporting excerpts:
{support_pack}

Output: single line, no JSON."""
            rewritten = self.llm_text_fn(prompt).strip()

            if rewritten.upper().startswith("UNSUPPORTED"):
                out.append({"text": claim, "status": "UNSUPPORTED", "citations": [], "notes": "Not justified by excerpts."})
                continue

            if _has_numbers(rewritten):
                nums = {m[0] for m in _NUMBER.findall(rewritten)}
                sup_text = " ".join([s.get("text", "") for s in support]).lower()
                if not all(n in sup_text for n in nums):
                    out.append({"text": claim, "status": "UNSUPPORTED", "citations": [], "notes": "Rejected: unsourced numeric content."})
                    continue

            out.append({
                "text": rewritten,
                "status": "SUPPORTED",
                "citations": [s.get("id") for s in support if s.get("id")],
                "notes": "",
            })

        return out

    def _detect_conflicts(self, supported: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        conflicts = []
        for i in range(len(supported)):
            for j in range(i + 1, len(supported)):
                a = _norm(supported[i]["text"])
                b = _norm(supported[j]["text"])
                shared = _tokens(a) & _tokens(b)
                if len(shared) < 3:
                    continue
                na = (" not " in f" {a} " or " no " in f" {a} " or "avoid" in a)
                nb = (" not " in f" {b} " or " no " in f" {b} " or "avoid" in b)
                if na != nb:
                    conflicts.append({
                        "a": supported[i]["text"],
                        "b": supported[j]["text"],
                        "shared_terms": sorted(list(shared))[:8],
                        "note": "Potential polarity conflict.",
                    })
        return conflicts[:6]

    def _compose(
        self,
        question: str,
        intent_pack: Dict[str, Any],
        supported: List[Dict[str, Any]],
        all_claims: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
        mc: ModeConfig,
        start: float,
        query_meta: Optional[Dict[str, Any]] = None,
        protocol: Optional[Dict[str, Any]] = None,
        inline_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        query_meta = query_meta or {}
        ref_map = {}
        for c in ranked:
            cid = c.get("id")
            if not cid or cid in ref_map:
                continue
            ref_map[cid] = {
                "id": cid,
                "title": c.get("title"),
                "year": c.get("year"),
                "source_type": c.get("source_type", "other"),
                "domain": c.get("domain", ""),
                "url": c.get("url"),
            }

        used_ids = set()
        for c in supported:
            used_ids |= set(c.get("citations", []))
        used_sources = [r for r in ranked if r.get("id") in used_ids]
        best_q = max((_quality_weight(s.get("source_type", "other"), s.get("domain", "")) for s in used_sources), default=0.0)
        grade = "Low"
        why = "Limited supported claims and/or lower-quality evidence."
        if best_q >= 0.90 and len(supported) >= 5:
            grade, why = "High", "Multiple supported claims anchored in guideline/consensus/IFU/review-level sources."
        elif best_q >= 0.62 and len(supported) >= 3:
            grade, why = "Moderate", "Several supported claims with at least moderate-quality evidence."

        aci_score = compute_aci(used_sources, risk_level=query_meta.get("risk_level", "low"))
        if aci_score.get("overall_confidence_0_10", 0) == 0.0 and ref_map:
            aci_score = compute_aci_from_references(list(ref_map.values()), risk_level=query_meta.get("risk_level", "low"))

        deep_instructions = ""
        if mc is DEEPCONSULT:
            deep_instructions = """
DEEPCONSULT OUTPUT:
- Include a "Safety-grade synthesis" tone.
- Include a small "Medicolegal notes" section ONLY if supported claims mention risks/contraindications/complications.
- Include a "What would change the recommendation" section (e.g., missing data, patient factors).
"""

        protocol_instructions = ""
        if protocol:
            protocol_instructions = f"""
COMPLICATION PROTOCOL (include in answer if relevant):
Red flags: {', '.join(protocol['red_flags'])}
Immediate actions: {', '.join(protocol['immediate_actions'])}
Note: {protocol['note']}
"""

        time_left = (start + mc.wall_time_budget_s) - time.time()
        claims_for_prompt = supported
        if mc is FAST and time_left < 8.0 and len(supported) > 4:
            claims_for_prompt = supported[:4]

        prompt = f"""You are AesthetiCite, a specialist evidence assistant for aesthetic medicine.

Write the answer using ONLY the supported claims below.

FORMAT:
1) Clinical Summary (3-6 sentences)
2) What the evidence says (bullets; each bullet ends with citations like [id1, id2])
3) Evidence strength (High/Moderate/Low + 1-2 sentences)
4) Safety / Contraindications (ONLY if supported claims mention safety)
5) If conflicts exist: add 1 short bullet under "What the evidence says" mentioning the disagreement.

{deep_instructions}
{protocol_instructions}

Question: {question}
Intent pack: {intent_pack}

Supported claims:
{[{"text": c["text"], "citations": c["citations"]} for c in claims_for_prompt]}

Conflicts:
{conflicts}"""
        answer_text = self.llm_text_fn(prompt).strip()

        return {
            "mode": mc.label,
            "question": question,
            "intent": intent_pack.get("intent", "other"),
            "intent_pack": intent_pack,
            "clinical_answer": answer_text,
            "evidence_strength": {"grade": grade, "why": why},
            "aci_score": aci_score,
            "query_meta": query_meta,
            "complication_protocol": protocol,
            "safety": _veridoc_safety(question, protocol),
            "supported_claims": supported,
            "excluded_claims": [c for c in all_claims if c["status"] != "SUPPORTED"],
            "conflicts": conflicts,
            "references": list(ref_map.values()),
            "ranked_chunks": ranked,
            "meta": {
                "latency_s": round(time.time() - start, 2),
                "cache_hit": False,
                "coverage": round(_evidence_coverage(question, ranked), 2),
                "ranked_sources": len(ranked),
                "aci_score": aci_score,
            },
            "inline_tools": inline_tools or [],
            "actions": [
                {"type": "suggested_mode", "label": "Run DeepConsult (slow & advanced)", "mode": "deepconsult"}
            ] if mc is FAST else [],
        }

    def _best_effort(self, question: str, intent_pack: Dict[str, Any], ranked: List[Dict[str, Any]], coverage: float, mc: ModeConfig, start: float, query_meta: Optional[Dict[str, Any]] = None, protocol: Optional[Dict[str, Any]] = None, inline_tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        query_meta = query_meta or {}
        refs = []
        for c in ranked[:10]:
            refs.append({
                "id": c.get("id"),
                "title": c.get("title"),
                "year": c.get("year"),
                "source_type": c.get("source_type", "other"),
                "domain": c.get("domain", ""),
                "url": c.get("url"),
            })
        aci_score = compute_aci_from_references(refs, risk_level=query_meta.get("risk_level", "low"))
        return {
            "mode": mc.label,
            "question": question,
            "intent": intent_pack.get("intent", "other"),
            "intent_pack": intent_pack,
            "clinical_answer": (
                "Best-effort FAST answer: I'm short on time budget to fully ground multiple claims. "
                "Here are the most relevant sources retrieved; re-run in DeepConsult for a safety-grade synthesis."
            ),
            "evidence_strength": {"grade": "Insufficient", "why": f"Time-budget cutoff. Coverage={coverage:.2f}"},
            "aci_score": aci_score,
            "query_meta": query_meta,
            "complication_protocol": protocol,
            "safety": _veridoc_safety(question, protocol),
            "supported_claims": [],
            "excluded_claims": [],
            "conflicts": [],
            "references": refs,
            "ranked_chunks": ranked,
            "inline_tools": inline_tools or [],
            "meta": {"latency_s": round(time.time() - start, 2), "cache_hit": False, "coverage": round(coverage, 2), "ranked_sources": len(ranked), "aci_score": aci_score},
            "actions": [{"type": "suggested_mode", "label": "Run DeepConsult (slow & advanced)", "mode": "deepconsult"}],
        }

    def _insufficient(self, question: str, intent_pack: Dict[str, Any], ranked: List[Dict[str, Any]], coverage: float, supported_ratio: float, mc: ModeConfig, start: float, query_meta: Optional[Dict[str, Any]] = None, inline_tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        query_meta = query_meta or {}
        entities = intent_pack.get("entities", [])
        intent = intent_pack.get("intent", "other")

        next_terms = [
            f"{' '.join(entities)} {intent} guideline consensus" if entities else f"{question} guideline consensus",
            f"{' '.join(entities)} IFU instructions for use" if entities else f"{question} instructions for use IFU",
            f"{' '.join(entities)} complications management" if entities else f"{question} complications management",
            f"{question} cosmetic aesthetic dermatology plastic surgery",
        ]

        refs = []
        for c in ranked[:10]:
            refs.append({
                "id": c.get("id"),
                "title": c.get("title"),
                "year": c.get("year"),
                "source_type": c.get("source_type", "other"),
                "domain": c.get("domain", ""),
                "url": c.get("url"),
            })

        aci_score = compute_aci_from_references(refs, risk_level=query_meta.get("risk_level", "low"))
        return {
            "mode": mc.label,
            "question": question,
            "intent": intent,
            "intent_pack": intent_pack,
            "clinical_answer": (
                "I couldn't find enough direct, high-confidence evidence in the retrieved sources to answer safely.\n\n"
                f"Signals: coverage={coverage:.2f}, supported_claims_ratio={supported_ratio:.2f}\n\n"
                "Try refining the query (examples):\n- " + "\n- ".join(next_terms)
            ),
            "evidence_strength": {"grade": "Insufficient", "why": f"coverage={coverage:.2f}, supported_ratio={supported_ratio:.2f}"},
            "aci_score": aci_score,
            "query_meta": query_meta,
            "complication_protocol": None,
            "supported_claims": [],
            "excluded_claims": [],
            "conflicts": [],
            "references": refs,
            "ranked_chunks": ranked,
            "inline_tools": inline_tools or [],
            "next_search_terms": next_terms,
            "meta": {"latency_s": round(time.time() - start, 2), "cache_hit": False, "coverage": round(coverage, 2), "ranked_sources": len(ranked), "aci_score": aci_score},
            "actions": [{"type": "suggested_mode", "label": "Run DeepConsult (slow & advanced)", "mode": "deepconsult"}] if mc is FAST else [],
        }
