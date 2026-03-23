"""
AesthetiCite — Control-Plane Upgrade Pack
==========================================
Implements three upgrades:

1) Per-category tuning of retrieval (wide_k/final_k + thresholds) for:
   - dosing, anatomy, complications, injectables, energy devices, comparison, general

2) PI-only fallback retrieval for high-stakes queries when initial evidence is weak

3) OpenEvidence-style selective refusal when high-stakes + missing PI/guideline support
"""

from __future__ import annotations

import os
import re
import json
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Callable

from cachetools import TTLCache

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "172800"))
ans_cache: TTLCache = TTLCache(maxsize=50_000, ttl=CACHE_TTL)


def _h(kind: str, obj: dict) -> str:
    raw = kind + ":" + json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def llm_text(system: str, user: str, temperature: float = 0.2) -> str:
    from app.openai_wiring import llm_text as _llm_text
    return _llm_text(system, user, temperature=temperature)


def llm_json(system: str, user: str, temperature: float = 0.0) -> dict:
    txt = llm_text(system, user, temperature=temperature).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        txt = m.group(0)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {txt[:200]}")
        return {}


QUALITY_WEIGHT = {
    "pi": 1.00,
    "guideline": 0.95,
    "meta_analysis": 0.85,
    "rct": 0.80,
    "case_series": 0.55,
    "review": 0.50,
    "textbook": 0.45,
    "other": 0.35,
}


def source_type(c: dict) -> str:
    return (c.get("source_type") or "other").lower().strip()


def quality_score(c: dict) -> float:
    return QUALITY_WEIGHT.get(source_type(c), 0.35)


def uniq_sources(chunks: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


Category = str

CATEGORY_RULES: List[Tuple[Category, List[str]]] = [
    ("comparison", [" vs ", "versus", "compare", "difference between"]),
    ("dosing", ["dose", "dosing", "units", "iu", "mg", "mcg", "ml", "mL", "maximum dose", "max dose"]),
    ("complications", ["complication", "occlusion", "necrosis", "vision", "blind", "ptosis", "asymmetry", "infection", "granuloma", "delayed nodule"]),
    ("anatomy", ["anatomy", "artery", "vascular", "plane", "landmark", "corrugator", "procerus", "supratrochlear", "angular artery"]),
    ("energy_devices", ["laser", "ipl", "rf", "radiofrequency", "ultrasound", "hifu", "device", "microneedling"]),
    ("injectables", ["botox", "dysport", "xeomin", "toxin", "filler", "hyaluronic", "restylane", "juvederm", "sculptra", "radiesse", "hyaluronidase"]),
]


def detect_category(query: str) -> Category:
    q = (query or "").lower()
    for cat, kws in CATEGORY_RULES:
        if any(k in q for k in kws):
            return cat
    return "general"


def is_high_stakes(query: str, category: Category) -> bool:
    q = (query or "").lower()
    if category in ("dosing", "complications", "anatomy"):
        return True
    for t in ["vascular occlusion", "blind", "vision loss", "necrosis", "anaphyl", "toxicity"]:
        if t in q:
            return True
    return False


@dataclass
class CategoryConfig:
    wide_k: int
    final_k: int
    max_chunks_per_source: int
    min_unique_sources: int
    min_unique_sources_high_stakes: int
    require_pi_or_guideline_high_stakes: bool
    prefer_pi_guideline: bool
    allow_refusal: bool


CATEGORY_CONFIG: Dict[Category, CategoryConfig] = {
    "dosing": CategoryConfig(
        wide_k=80, final_k=22, max_chunks_per_source=2,
        min_unique_sources=3, min_unique_sources_high_stakes=4,
        require_pi_or_guideline_high_stakes=True, prefer_pi_guideline=True, allow_refusal=True
    ),
    "anatomy": CategoryConfig(
        wide_k=70, final_k=20, max_chunks_per_source=2,
        min_unique_sources=3, min_unique_sources_high_stakes=4,
        require_pi_or_guideline_high_stakes=False, prefer_pi_guideline=True, allow_refusal=True
    ),
    "complications": CategoryConfig(
        wide_k=80, final_k=24, max_chunks_per_source=2,
        min_unique_sources=3, min_unique_sources_high_stakes=4,
        require_pi_or_guideline_high_stakes=True, prefer_pi_guideline=True, allow_refusal=True
    ),
    "injectables": CategoryConfig(
        wide_k=60, final_k=18, max_chunks_per_source=2,
        min_unique_sources=2, min_unique_sources_high_stakes=3,
        require_pi_or_guideline_high_stakes=True, prefer_pi_guideline=True, allow_refusal=True
    ),
    "energy_devices": CategoryConfig(
        wide_k=60, final_k=18, max_chunks_per_source=2,
        min_unique_sources=2, min_unique_sources_high_stakes=3,
        require_pi_or_guideline_high_stakes=False, prefer_pi_guideline=True, allow_refusal=True
    ),
    "comparison": CategoryConfig(
        wide_k=90, final_k=26, max_chunks_per_source=2,
        min_unique_sources=3, min_unique_sources_high_stakes=4,
        require_pi_or_guideline_high_stakes=False, prefer_pi_guideline=True, allow_refusal=False
    ),
    "general": CategoryConfig(
        wide_k=50, final_k=16, max_chunks_per_source=2,
        min_unique_sources=2, min_unique_sources_high_stakes=3,
        require_pi_or_guideline_high_stakes=False, prefer_pi_guideline=False, allow_refusal=False
    ),
}


def rerank_chunks(query: str, chunks: List[dict], prefer_pi_guideline: bool) -> List[dict]:
    q_terms = set(re.findall(r"[a-z0-9]+", (query or "").lower()))
    scored = []
    for c in chunks:
        txt = (c.get("text") or "").lower()
        overlap = sum(1 for t in q_terms if t in txt)
        st = source_type(c)
        score = overlap * 1.0 + quality_score(c) * 5.0
        if prefer_pi_guideline and st in ("pi", "guideline"):
            score += 8.0
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


def diversify(chunks: List[dict], final_k: int, max_chunks_per_source: int) -> List[dict]:
    out = []
    per: Dict[str, int] = {}
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id") or "unknown"
        n = per.get(key, 0)
        if n >= max_chunks_per_source:
            continue
        per[key] = n + 1
        out.append(c)
        if len(out) >= final_k:
            break
    return out


BRAND_HINTS = [
    "botox", "dysport", "xeomin",
    "juvederm", "restylane", "sculptra", "radiesse", "belotero",
    "hyaluronidase"
]


def build_pi_fallback_filters(filters: Optional[dict], query: str) -> dict:
    f = dict(filters or {})
    f["source_type_in"] = ["pi", "guideline"]
    f["prefer_source_types"] = ["pi", "guideline"]
    f["boost_source_types"] = {"pi": 3.0, "guideline": 2.0}
    ql = query.lower()
    hints = [b for b in BRAND_HINTS if b in ql]
    if hints:
        f["must_terms"] = list(set((f.get("must_terms") or []) + hints))
    return f


def gate_decision(query: str, category: Category, cfg: CategoryConfig, chunks: List[dict]) -> Tuple[bool, str]:
    u = uniq_sources(chunks)
    hs = is_high_stakes(query, category)

    if hs:
        if len(u) < cfg.min_unique_sources_high_stakes:
            return False, "too_few_unique_sources_high_stakes"
        if cfg.require_pi_or_guideline_high_stakes:
            pg = sum(1 for c in u if source_type(c) in ("pi", "guideline"))
            if pg < 1:
                return False, "missing_pi_or_guideline_high_stakes"
        return True, ""
    else:
        if len(u) < cfg.min_unique_sources:
            return False, "too_few_sources"
        return True, ""


def refusal_answer(reason: str) -> str:
    return (
        "Clinical Summary:\n"
        "Insufficient high-quality evidence was retrieved to provide a reliable, specific answer.\n\n"
        "Practical Steps:\n"
        "- Use product prescribing information and/or clinical guidelines for the exact product and indication.\n"
        "- If this is a high-risk scenario, follow emergency and escalation protocols.\n\n"
        "Complications & Red Flags:\n"
        "If severe pain, blanching, neurologic or visual symptoms occur, treat as urgent and escalate.\n\n"
        "Evidence Notes:\n"
        f"Refusal reason: {reason}."
    )


def format_citations(chunks: List[dict], max_items: int = 8) -> List[dict]:
    out = []
    for c in uniq_sources(chunks)[:max_items]:
        out.append({
            "title": c.get("title"),
            "year": c.get("year"),
            "source_type": c.get("source_type"),
            "doi": c.get("doi"),
            "url": c.get("url"),
        })
    return out


_NUM = re.compile(r"\b(\d+(\.\d+)?)\b")


def extract_numbers(text: str) -> List[str]:
    return [m.group(1) for m in _NUM.finditer(text or "")]


def numeric_supported(answer: str, chunks: List[dict]) -> Tuple[bool, List[str]]:
    nums = list(dict.fromkeys(extract_numbers(answer)))[:12]
    if not nums:
        return True, []
    ev = "\n".join((c.get("text") or "") for c in chunks).lower()
    missing = [n for n in nums if n.lower() not in ev]
    return len(missing) == 0, missing


def answer_with_control_plane(
    query: str,
    filters: Optional[dict],
    retrieve_chunks: Callable[[str, Optional[dict], Optional[int]], List[dict]],
    compact: bool = True,
    enable_cache: bool = True,
) -> Dict[str, Any]:
    """
    Main answer function with per-category tuning, PI fallback, and selective refusal.
    """
    cat = detect_category(query)
    cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["general"])
    hs = is_high_stakes(query, cat)

    cache_key = _h("cpqa", {"q": query, "f": filters or {}, "cat": cat, "compact": compact})
    if enable_cache:
        cached = ans_cache.get(cache_key)
        if cached is not None:
            return {**cached, "meta": {**cached.get("meta", {}), "cached": True}}

    wide = retrieve_chunks(query, filters, cfg.wide_k) or []
    wide = wide[:cfg.wide_k]

    ranked = rerank_chunks(query, wide, prefer_pi_guideline=cfg.prefer_pi_guideline)
    top = diversify(ranked, final_k=cfg.final_k, max_chunks_per_source=cfg.max_chunks_per_source)

    ok, reason = gate_decision(query, cat, cfg, top)

    used_fallback = False
    if (not ok) and hs:
        fb_filters = build_pi_fallback_filters(filters, query)
        wide_fb = retrieve_chunks(query, fb_filters, cfg.wide_k) or []
        ranked_fb = rerank_chunks(query, wide_fb, prefer_pi_guideline=True)
        top_fb = diversify(ranked_fb, final_k=max(cfg.final_k, 18), max_chunks_per_source=cfg.max_chunks_per_source)

        ok2, reason2 = gate_decision(query, cat, cfg, top_fb)
        if ok2:
            used_fallback = True
            top = top_fb
            ok, reason = ok2, ""
        else:
            top = top_fb if len(uniq_sources(top_fb)) >= len(uniq_sources(top)) else top
            ok, reason = ok2, reason2

    if not ok:
        if cfg.allow_refusal or hs:
            out = {
                "answer": refusal_answer(reason),
                "refused": True,
                "citations": format_citations(top),
                "meta": {
                    "category": cat,
                    "high_stakes": hs,
                    "reason": reason,
                    "used_pi_fallback": used_fallback,
                    "wide_k": cfg.wide_k,
                    "final_k": len(top),
                    "cached": False
                }
            }
            if enable_cache:
                ans_cache[cache_key] = out
            return out

    citations = format_citations(top, max_items=8)
    cite_lines = "\n".join(
        [f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}] {c.get('doi') or c.get('url') or ''}".strip()
         for c in citations]
    )

    system = (
        "You are AesthetiCite, clinician-facing decision support for aesthetic medicine.\n"
        "Return STRICT JSON only.\n"
        "Schema:\n"
        "{\n"
        "  \"answer_sections\": {\n"
        "    \"Clinical Summary\": string,\n"
        "    \"Practical Steps\": string,\n"
        "    \"Complications & Red Flags\": string,\n"
        "    \"What can go wrong next?\": string,\n"
        "    \"Evidence Notes\": string\n"
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Be conservative.\n"
        "- Prefer PI/guidelines.\n"
        "- If unsure, say 'insufficient evidence' and avoid precise dosing.\n"
    )
    user = (
        f"Category: {cat}\n"
        f"High-stakes: {hs}\n"
        f"Question: {query}\n\n"
        f"Sources:\n{cite_lines}\n"
    )
    data = llm_json(system, user, temperature=0.2)
    sec = data.get("answer_sections") or {}

    answer_text = (
        "Clinical Summary:\n" + (sec.get("Clinical Summary") or "").strip() + "\n\n"
        "Practical Steps:\n" + (sec.get("Practical Steps") or "").strip() + "\n\n"
        "Complications & Red Flags:\n" + (sec.get("Complications & Red Flags") or "").strip() + "\n\n"
        "What can go wrong next?\n" + (sec.get("What can go wrong next?") or "").strip() + "\n\n"
        "Evidence Notes:\n" + (sec.get("Evidence Notes") or "").strip()
    ).strip()

    if compact:
        answer_text = re.sub(r"\n{3,}", "\n\n", answer_text).strip()
        if len(answer_text) > 1900:
            answer_text = answer_text[:1900].rsplit(" ", 1)[0] + "…"

    ok_nums, missing = numeric_supported(answer_text, top)
    downgraded = False
    if hs and (not ok_nums) and missing:
        downgraded = True
        answer_text = answer_text + (
            "\n\nEvidence Check:\n"
            "Some numeric details could not be directly verified in the retrieved sources. "
            "For dosing, follow the product PI and local protocol."
        )

    out = {
        "answer": answer_text,
        "refused": False,
        "citations": citations,
        "meta": {
            "category": cat,
            "high_stakes": hs,
            "used_pi_fallback": used_fallback,
            "downgraded_for_unverified_numbers": downgraded,
            "missing_numbers": missing if downgraded else [],
            "wide_k": cfg.wide_k,
            "final_k": len(top),
            "cached": False,
            "model": OPENAI_MODEL
        }
    }
    if enable_cache:
        ans_cache[cache_key] = out
    return out
