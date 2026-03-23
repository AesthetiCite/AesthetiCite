"""
AesthetiCite — Improvement Pack
===============================
Wide retrieval + rerank + source diversity (PI/guideline first)
High-stakes evidence gating + refusals (stop guessing)
Numeric verification (dosing/units/ml/mg) against evidence text
Single-call option (context+answer+claims) to reduce latency
Benchmark harness with semantic scoring + numeric checks + refusal credit
"""

from __future__ import annotations

import os
import re
import json
import time
import math
import hashlib
import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple, Callable

from cachetools import TTLCache

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

_client = None

def get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL") or "https://api.openai.com/v1"
        )
    return _client


def llm_text(system: str, user: str, temperature: float = 0.2) -> str:
    client = get_openai_client()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


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


def embed_text(text: str) -> List[float]:
    from app.rag.embedder import embed_text as local_embed
    return local_embed(text[:8000])


def cosine(a: List[float], b: List[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "172800"))
emb_cache: TTLCache = TTLCache(maxsize=100_000, ttl=CACHE_TTL)
ans_cache: TTLCache = TTLCache(maxsize=40_000, ttl=CACHE_TTL)


def _h(kind: str, obj: dict) -> str:
    raw = kind + ":" + json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def embed_cached(text: str) -> List[float]:
    key = _h("emb", {"t": text[:4000]})
    v = emb_cache.get(key)
    if v is not None:
        return v
    v = embed_text(text[:8000])
    emb_cache[key] = v
    return v


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

HIGH_STAKES_TRIGGERS = [
    "dose", "dosing", "units", "mg", "mcg", "g", "ml", "mL", "maximum", "max",
    "vascular occlusion", "blindness", "vision loss", "necrosis", "anaphyl", "lidocaine",
    "hyaluronidase", "epinephrine", "toxicity"
]


def is_high_stakes(query: str) -> bool:
    q = query.lower()
    return any(t in q for t in HIGH_STAKES_TRIGGERS)


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


def source_type(c: dict) -> str:
    return (c.get("source_type") or "other").lower().strip()


def quality_score(c: dict) -> float:
    return QUALITY_WEIGHT.get(source_type(c), 0.35)


@dataclass
class RetrievalConfig:
    wide_k: int = 60
    final_k: int = 18
    require_pi_or_guideline_for_high_stakes: bool = True
    min_unique_sources_high_stakes: int = 3
    min_unique_sources_normal: int = 2
    max_chunks_per_source: int = 2
    boost_pi_guideline: float = 6.0
    boost_quality: float = 5.0
    boost_keyword_overlap: float = 1.0


def rerank_chunks(query: str, chunks: List[dict], cfg: RetrievalConfig) -> List[dict]:
    q_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored = []
    for c in chunks:
        txt = (c.get("text") or "").lower()
        overlap = sum(1 for t in q_terms if t in txt)
        st = source_type(c)
        base = overlap * cfg.boost_keyword_overlap + quality_score(c) * cfg.boost_quality
        if st in ("pi", "guideline"):
            base += cfg.boost_pi_guideline
        scored.append((base, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


def diversify_by_source(chunks: List[dict], cfg: RetrievalConfig) -> List[dict]:
    out = []
    per_source: Dict[str, int] = {}
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id") or "unknown"
        n = per_source.get(key, 0)
        if n >= cfg.max_chunks_per_source:
            continue
        per_source[key] = n + 1
        out.append(c)
        if len(out) >= cfg.final_k:
            break
    return out


def evidence_gate(query: str, chunks: List[dict], cfg: RetrievalConfig) -> Tuple[bool, str]:
    u = uniq_sources(chunks)
    if is_high_stakes(query):
        if len(u) < cfg.min_unique_sources_high_stakes:
            return False, "too_few_unique_sources_for_high_stakes"
        if cfg.require_pi_or_guideline_for_high_stakes:
            pg = sum(1 for c in u if source_type(c) in ("pi", "guideline"))
            if pg < 1:
                return False, "no_pi_or_guideline_for_high_stakes"
        return True, ""
    else:
        if len(u) < cfg.min_unique_sources_normal:
            return False, "too_few_sources"
        return True, ""


_NUM_RE = re.compile(r"\b(\d+(\.\d+)?)\b")


def extract_numeric_facts(text: str) -> List[str]:
    return [m.group(1) for m in _NUM_RE.finditer(text or "")]


def numeric_support_check(answer: str, evidence_texts: List[str]) -> Dict[str, Any]:
    nums = extract_numeric_facts(answer)
    nums = list(dict.fromkeys(nums))
    if not nums:
        return {"has_numbers": False, "numbers": [], "unsupported": [], "supported": []}

    supported = []
    unsupported = []
    ev_join = "\n".join(evidence_texts).lower()

    for n in nums[:12]:
        if n.lower() in ev_join:
            supported.append(n)
        else:
            unsupported.append(n)

    return {
        "has_numbers": True,
        "numbers": nums[:12],
        "supported": supported,
        "unsupported": unsupported,
        "all_supported": len(unsupported) == 0
    }


@dataclass
class AnswerConfig:
    compact: bool = True
    single_call_json: bool = True
    max_claim_tags: int = 6


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


def compact_text(s: str, max_chars: int = 1900) -> str:
    s = re.sub(r"\n{3,}", "\n\n", (s or "")).strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rsplit(" ", 1)[0] + "…"


def build_answer_single_call(query: str, chunks: List[dict], ans_cfg: AnswerConfig) -> Dict[str, Any]:
    citations = format_citations(chunks)
    cite_lines = "\n".join(
        [f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}] {c.get('doi') or c.get('url') or ''}".strip()
         for c in citations]
    )

    system = (
        "You are AesthetiCite, clinician-facing decision support for aesthetic medicine.\n"
        "Return STRICT JSON only.\n"
        "Schema:\n"
        "{\n"
        "  \"context\": {\"procedure\":string|null,\"area\":string|null,\"product\":string|null,"
        "              \"intent\":\"dosing\"|\"protocol\"|\"comparison\"|\"complication\"|\"consent\"|\"general\","
        "              \"urgency\":\"routine\"|\"urgent\"|\"emergency\",\"high_stakes\":boolean},\n"
        "  \"answer_sections\": {\n"
        "     \"Clinical Summary\": string,\n"
        "     \"Practical Steps\": string,\n"
        "     \"Complications & Red Flags\": string,\n"
        "     \"What can go wrong next?\": string,\n"
        "     \"Evidence Notes\": string\n"
        "  },\n"
        "  \"claim_tags\": [{\"claim\":string,\"evidence_strength\":\"High\"|\"Moderate\"|\"Low\"|\"Consensus\",\"why\":string}]\n"
        "}\n"
        "Rules:\n"
        "- Prefer PI/guidelines.\n"
        "- If unsure, say 'insufficient evidence' and do NOT guess.\n"
        f"- claim_tags: max {ans_cfg.max_claim_tags}.\n"
    )

    user = f"Question: {query}\n\nSources:\n{cite_lines}\n"
    data = llm_json(system, user, temperature=0.2)

    sec = data.get("answer_sections") or {}
    answer_text = (
        "Clinical Summary:\n" + (sec.get("Clinical Summary") or "").strip() + "\n\n"
        "Practical Steps:\n" + (sec.get("Practical Steps") or "").strip() + "\n\n"
        "Complications & Red Flags:\n" + (sec.get("Complications & Red Flags") or "").strip() + "\n\n"
        "What can go wrong next?\n" + (sec.get("What can go wrong next?") or "").strip() + "\n\n"
        "Evidence Notes:\n" + (sec.get("Evidence Notes") or "").strip()
    ).strip()

    if ans_cfg.compact:
        answer_text = compact_text(answer_text, 1900)

    return {
        "answer": answer_text,
        "sections": sec,
        "context": data.get("context") or {},
        "claim_tags": (data.get("claim_tags") or [])[:ans_cfg.max_claim_tags],
        "citations": citations,
        "meta": {"mode": "single_call"}
    }


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


def improved_answer(
    query: str,
    filters: Optional[dict],
    retrieve_chunks: Callable[[str, Optional[dict], Optional[int]], List[dict]],
    retrieval_cfg: RetrievalConfig = RetrievalConfig(),
    answer_cfg: AnswerConfig = AnswerConfig(),
    enable_cache: bool = True,
) -> Dict[str, Any]:
    """Main function to call from /qa and /emergency."""

    cache_key = _h("qa2", {"q": query, "f": filters or {}, "rcfg": asdict(retrieval_cfg), "acfg": asdict(answer_cfg)})
    if enable_cache:
        cached = ans_cache.get(cache_key)
        if cached is not None:
            return {**cached, "meta": {**cached.get("meta", {}), "cached": True}}

    try:
        wide = retrieve_chunks(query, filters, retrieval_cfg.wide_k)
    except TypeError:
        wide = retrieve_chunks(query, filters)
        wide = wide[:retrieval_cfg.wide_k]

    reranked = rerank_chunks(query, wide, retrieval_cfg)
    top = diversify_by_source(reranked, retrieval_cfg)

    ok, reason = evidence_gate(query, top, retrieval_cfg)
    if not ok:
        out = {
            "answer": refusal_answer(reason),
            "refused": True,
            "citations": format_citations(top),
            "meta": {"refused": True, "reason": reason, "wide_k": len(wide), "final_k": len(top), "cached": False},
        }
        if enable_cache:
            ans_cache[cache_key] = out
        return out

    out = build_answer_single_call(query, top, answer_cfg)

    evidence_texts = [(c.get("text") or "")[:6000] for c in top]
    num_check = numeric_support_check(out["answer"], evidence_texts)
    out["meta"]["numeric_check"] = num_check

    if is_high_stakes(query) and num_check["has_numbers"] and not num_check["all_supported"]:
        out["answer"] = out["answer"].strip() + (
            "\n\nEvidence Check:\n"
            "Some numeric details could not be directly verified in the retrieved sources. "
            "For dosing, follow the product prescribing information and local protocol."
        )
        out["meta"]["downgraded_for_unverified_numbers"] = True
    else:
        out["meta"]["downgraded_for_unverified_numbers"] = False

    out["refused"] = False
    out["meta"].update({"wide_k": len(wide), "final_k": len(top), "cached": False})

    if enable_cache:
        ans_cache[cache_key] = out
    return out


@dataclass
class BenchmarkQuestion:
    id: str
    category: str
    question: str
    gold_answer: str
    gold_numbers: List[str]
    allow_refusal: bool = True


@dataclass
class BenchmarkResult:
    id: str
    category: str
    refused: bool
    latency_ms: int
    semantic_score: float
    numeric_score: float
    final_score: float
    notes: str


def semantic_similarity(a: str, b: str) -> float:
    va = embed_cached(a[:4000])
    vb = embed_cached(b[:4000])
    return max(0.0, min(1.0, (cosine(va, vb) + 1.0) / 2.0))


def numeric_score(pred_answer: str, gold_numbers: List[str]) -> float:
    if not gold_numbers:
        return 1.0
    pred_nums = set(extract_numeric_facts(pred_answer))
    gold = set(gold_numbers)
    if not gold:
        return 1.0
    hit = len(pred_nums.intersection(gold))
    return hit / max(1, len(gold))


def run_benchmark(
    questions: List[BenchmarkQuestion],
    retrieve_chunks: Callable[[str, Optional[dict], Optional[int]], List[dict]],
    filters: Optional[dict] = None,
    retrieval_cfg: RetrievalConfig = RetrievalConfig(),
    answer_cfg: AnswerConfig = AnswerConfig(),
) -> Dict[str, Any]:
    """Hybrid scoring: final_score = 0.70*semantic + 0.30*numeric"""
    results: List[BenchmarkResult] = []
    t0 = time.time()
    
    for q in questions:
        start = time.time()
        out = improved_answer(
            query=q.question,
            filters=filters,
            retrieve_chunks=retrieve_chunks,
            retrieval_cfg=retrieval_cfg,
            answer_cfg=answer_cfg,
            enable_cache=False,
        )
        latency_ms = int((time.time() - start) * 1000)
        refused = bool(out.get("refused"))
        pred = out.get("answer", "")

        sem = semantic_similarity(pred, q.gold_answer)
        num = numeric_score(pred, q.gold_numbers)

        if refused and q.allow_refusal:
            final = max(sem, 0.75)
            notes = "refusal_credit"
        elif refused and not q.allow_refusal:
            final = 0.0
            notes = "refused_not_allowed"
        else:
            final = 0.70 * sem + 0.30 * num
            notes = ""

        results.append(BenchmarkResult(
            id=q.id,
            category=q.category,
            refused=refused,
            latency_ms=latency_ms,
            semantic_score=round(sem, 3),
            numeric_score=round(num, 3),
            final_score=round(final, 3),
            notes=notes
        ))

    elapsed_ms = int((time.time() - t0) * 1000)
    avg = sum(r.final_score for r in results) / max(1, len(results))

    by_cat: Dict[str, List[BenchmarkResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    cat_scores = {c: round(sum(x.final_score for x in xs)/len(xs), 3) for c, xs in by_cat.items()}
    refused_n = sum(1 for r in results if r.refused)

    return {
        "overall_score": round(avg, 3),
        "grade": grade_from_score(avg),
        "total": len(results),
        "refused": refused_n,
        "avg_latency_ms": int(sum(r.latency_ms for r in results)/max(1, len(results))),
        "elapsed_ms": elapsed_ms,
        "category_scores": cat_scores,
        "results": [asdict(r) for r in results],
    }


def grade_from_score(s: float) -> str:
    if s >= 0.90: return "A"
    if s >= 0.80: return "B"
    if s >= 0.70: return "C"
    if s >= 0.60: return "D"
    return "F"
