"""
AesthetiCite — "Top 10 Improvements" single code patch
======================================================
Implements 10 upgrades for "better-than-OpenEvidence" in aesthetic medicine:
1) Procedure-aware context extraction
2) Complication-centric answer template
3) "What can go wrong next?" engine
4) Claim-level evidence tagging
5) Evidence freshness scoring
6) Hallucination kill-switch
7) Emergency Mode endpoint
8) Treatment comparison tool
9) Injection-zone risk map tool
10) Predictive precompute + multi-layer caching
"""

from __future__ import annotations

import os
import re
import io
import json
import time
import hashlib
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from cachetools import TTLCache

from app.pilot.client import log_event
from app.pilot.deps import get_case_id

from app.openai_wiring import llm_text, embed

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))

router = APIRouter(prefix="", tags=["top10"])


def llm_json(system: str, user: str, temperature: float = 0.0) -> dict:
    txt = llm_text(system, user, temperature=temperature).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        txt = m.group(0)
    try:
        return json.loads(txt)
    except Exception:
        txt2 = txt.replace("\n", " ").strip()
        m2 = re.search(r"\{.*\}", txt2, re.S)
        if m2:
            return json.loads(m2.group(0))
        raise


def retrieve_chunks(query: str, filters: Optional[dict] = None) -> List[dict]:
    """
    Full hybrid retrieval: HNSW (fast) + DB (BM25 + vector + trigram).
    Prioritizes PI/guidelines, returns chunk format expected by Top 10 patch.
    """
    from app.rag.retriever import retrieve_hnsw
    from app.rag.hnsw_store import hnsw_store
    from app.db.session import SessionLocal
    
    results = []
    seen_keys = set()
    
    hnsw_results = retrieve_hnsw(query, k=12)
    for i, r in enumerate(hnsw_results):
        key = (r.get("title", ""), r.get("text", "")[:100])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append({
            "id": f"{r.get('title', '')}#{i}",
            "text": r.get("text", ""),
            "title": r.get("title", ""),
            "source_type": r.get("source_type", "other"),
            "year": r.get("year"),
            "doi": r.get("url", ""),
            "url": r.get("url", ""),
            "_score": r.get("_score", 0.5),
        })
    
    if len(results) < 8:
        try:
            from app.rag.retriever import retrieve_db
            domain = (filters or {}).get("domain")
            with SessionLocal() as db:
                db_results = retrieve_db(db=db, question=query, domain=domain, k=12)
                for r in db_results:
                    key = (r.get("title", ""), r.get("text", "")[:100])
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    
                    doc_type = (r.get("document_type") or "").lower()
                    if doc_type in ("prescribing_information", "pi"):
                        source_type = "pi"
                    elif doc_type in ("guideline", "consensus", "ifu"):
                        source_type = "guideline"
                    elif doc_type == "rct":
                        source_type = "rct"
                    elif doc_type == "review":
                        source_type = "review"
                    else:
                        source_type = "other"
                    
                    results.append({
                        "id": r.get("source_id", f"db#{len(results)}"),
                        "text": r.get("text", ""),
                        "title": r.get("title", ""),
                        "source_type": source_type,
                        "year": r.get("year"),
                        "doi": "",
                        "url": "",
                        "_score": r.get("_score", 0.3),
                    })
        except Exception as e:  # nosec B110
            pass
    
    pi_guideline = [r for r in results if r.get("source_type") in ("pi", "guideline")]
    other = [r for r in results if r.get("source_type") not in ("pi", "guideline")]
    
    pi_guideline.sort(key=lambda x: x.get("_score", 0), reverse=True)
    other.sort(key=lambda x: x.get("_score", 0), reverse=True)
    
    final = pi_guideline + other
    return final[:12]


CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "172800"))
embed_cache = TTLCache(maxsize=50_000, ttl=CACHE_TTL)
answer_cache = TTLCache(maxsize=25_000, ttl=CACHE_TTL)
tool_cache = TTLCache(maxsize=25_000, ttl=CACHE_TTL)


def _h(kind: str, obj: dict) -> str:
    raw = kind + ":" + json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def embed_cached(text: str) -> List[float]:
    k = _h("emb", {"t": text[:4000]})
    v = embed_cache.get(k)
    if v is not None:
        return v
    v = embed(text[:8000])
    embed_cache[k] = v
    return v


WEIGHTS = {"pi": 1.00, "guideline": 0.95, "rct": 0.80, "review": 0.55, "textbook": 0.45, "other": 0.35}
CURRENT_YEAR = datetime.utcnow().year


def extract_citations(chunks: List[dict], max_items: int = 8) -> List[dict]:
    seen = set()
    out = []
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "title": c.get("title"),
            "year": c.get("year"),
            "doi": c.get("doi"),
            "url": c.get("url"),
            "source_type": c.get("source_type"),
        })
        if len(out) >= max_items:
            break
    return out


def evidence_freshness_score(chunks: List[dict]) -> dict:
    if not chunks:
        return {"score": 0.10, "badge": "Low", "freshness": "unknown", "why": "No retrievable sources"}

    seen = set()
    best_q = 0.0
    total_q = 0.0
    years = []
    type_counts: Dict[str, int] = {}
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        st = (c.get("source_type") or "other").lower().strip()
        w = WEIGHTS.get(st, 0.30)
        best_q = max(best_q, w)
        total_q += w
        type_counts[st] = type_counts.get(st, 0) + 1
        y = c.get("year")
        if isinstance(y, int) and 1900 < y <= CURRENT_YEAR:
            years.append(y)

    n = max(1, len(seen))
    avg_q = total_q / n

    if years:
        years_sorted = sorted(years)
        med = years_sorted[len(years_sorted)//2]
        age = max(0, CURRENT_YEAR - med)
        freshness_mult = max(0.55, 1.0 - 0.03 * age)
        freshness_label = f"median source year {med} (~{age}y old)"
    else:
        freshness_mult = 0.75
        freshness_label = "unknown (years not provided)"

    base = min(0.99, 0.55 * best_q + 0.45 * avg_q + 0.05 * min(1.0, n / 6.0))
    score = max(0.10, min(0.99, base * freshness_mult))

    if score >= 0.85:
        badge = "High"
    elif score >= 0.65:
        badge = "Moderate"
    else:
        badge = "Low"

    why = []
    if type_counts.get("pi"):
        why.append("Prescribing information present")
    if type_counts.get("guideline"):
        why.append("Guidelines present")
    if not why:
        why.append("Mostly secondary literature")
    why.append(freshness_label)

    return {"score": round(score, 2), "badge": badge, "types": type_counts, "freshness": freshness_label, "why": "; ".join(why)}


def parse_context(query: str) -> dict:
    key = _h("ctx", {"q": query})
    cached = tool_cache.get(key)
    if cached is not None:
        return cached

    system = (
        "Extract structured clinical context from a query about aesthetic medicine.\n"
        "Return STRICT JSON with fields:\n"
        "procedure (string|null), area (string|null), product (string|null), intent (one of: dosing, protocol, comparison, complication, consent, general),\n"
        "patient_constraints (array of strings), urgency (one of: routine, urgent, emergency),\n"
        "high_stakes (boolean)\n"
        "Rules: If unknown, use null or empty list."
    )
    user = f"Query: {query}"
    try:
        data = llm_json(system, user, temperature=0.0)
    except Exception:
        data = {}

    data.setdefault("procedure", None)
    data.setdefault("area", None)
    data.setdefault("product", None)
    data.setdefault("intent", "general")
    data.setdefault("patient_constraints", [])
    data.setdefault("urgency", "routine")
    data.setdefault("high_stakes", False)

    tool_cache[key] = data
    return data


HIGH_STAKES_INTENTS = {"dosing", "protocol", "complication"}


def should_kill_switch(ctx: dict, evidence: dict) -> bool:
    if ctx.get("high_stakes") or ctx.get("intent") in HIGH_STAKES_INTENTS or ctx.get("urgency") in ("urgent", "emergency"):
        return evidence.get("badge") == "Low" and evidence.get("score", 0.0) < 0.60
    return False


def build_answer(query: str, ctx: dict, chunks: List[dict], evidence: dict, compact: bool) -> str:
    citations = extract_citations(chunks, max_items=8)
    cite_lines = "\n".join([f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}] {c.get('doi') or c.get('url') or ''}".strip()
                            for c in citations])

    kill = should_kill_switch(ctx, evidence)
    if kill:
        return (
            "Clinical Summary:\n"
            "Insufficient high-quality evidence was retrieved to provide specific dosing/protocol-level guidance for this request.\n\n"
            "Practical Steps:\n"
            "* Use local institutional protocol / prescribing information for the exact product and indication.\n"
            "* If this involves an acute complication or patient harm risk, escalate to senior clinician support and follow emergency pathways.\n\n"
            "Safety / Red Flags:\n"
            "If severe pain, skin color change, neurologic symptoms, visual symptoms, or rapid swelling occur, treat as urgent and follow emergency management protocols.\n"
        )

    system = (
        "You are AesthetiCite, clinician-facing decision support for aesthetic medicine.\n"
        "Write conservatively and be procedure-aware.\n"
        "MANDATORY sections (in this order):\n"
        "1) Clinical Summary (3-6 lines)\n"
        "2) Practical Steps (bullets)\n"
        "3) Complications & Red Flags (bullets; include escalation threshold)\n"
        "4) What can go wrong next? (3-6 bullets)\n"
        "5) Evidence Notes (brief; mention if PI/guidelines vs consensus)\n"
        "Rules:\n"
        "- Prefer PI/guidelines.\n"
        "- If a detail is not supported, say 'insufficient evidence' rather than guessing.\n"
        "- Avoid marketing tone.\n"
        "- This is not a substitute for clinical judgement.\n"
    )

    user = (
        f"Query: {query}\n\n"
        f"Context JSON:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"Evidence badge: {evidence.get('badge')} (score={evidence.get('score')}, freshness={evidence.get('freshness')})\n\n"
        f"Sources:\n{cite_lines}\n"
    )

    text = llm_text(system, user, temperature=0.2).strip()
    if compact:
        text = compact_text(text, 1900)
    return text


def compact_text(s: str, max_chars: int) -> str:
    s = re.sub(r"\n{3,}", "\n\n", (s or "")).strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rsplit(" ", 1)[0] + "..."


def claim_level_tagging(answer_text: str, chunks: List[dict]) -> dict:
    key = _h("claims", {"a": answer_text[:2400], "n": len(chunks)})
    cached = tool_cache.get(key)
    if cached is not None:
        return cached

    st = {}
    for c in chunks:
        t = (c.get("source_type") or "other").lower().strip()
        st[t] = st.get(t, 0) + 1

    system = (
        "Extract up to 8 key clinical claims from the answer and label each with evidence_strength.\n"
        "Return STRICT JSON:\n"
        '{ "claims": [ {"claim":"...", "evidence_strength":"High|Moderate|Low|Consensus", "why":"..."} ] }\n'
        "Rules:\n"
        "- High: PI or guideline directly supports.\n"
        "- Moderate: RCT supports or multiple high-quality sources indirectly support.\n"
        "- Low: secondary or limited support.\n"
        "- Consensus: expert practice without strong trials.\n"
        "- If uncertain, choose lower strength.\n"
    )
    user = (
        f"Answer:\n{answer_text}\n\n"
        f"Available source-type counts: {json.dumps(st)}\n"
    )
    try:
        data = llm_json(system, user, temperature=0.0)
    except Exception:
        data = {"claims": []}
    tool_cache[key] = data
    return data


EMERGENCY_KEYWORDS = ["vascular occlusion", "vision loss", "blindness", "necrosis", "anaphylaxis", "compartment", "airway", "stroke"]


def emergency_payload(query: str, ctx: dict, chunks: List[dict], compact: bool) -> dict:
    evidence = evidence_freshness_score(chunks)
    citations = extract_citations(chunks, max_items=6)

    system = (
        "You are AesthetiCite Emergency Mode for aesthetic complications.\n"
        "Return a step-by-step checklist with short lines suitable for a phone screen.\n"
        "Return in plain text with sections:\n"
        "IMMEDIATE ACTIONS\n"
        "DO NOT DO\n"
        "ESCALATE WHEN\n"
        "DOCUMENTATION\n"
        "Rules:\n"
        "- Be conservative.\n"
        "- If a detail is not supported, state 'follow local protocol / PI'.\n"
        "- Avoid exact dosing if not supported by PI/guidelines in sources.\n"
    )

    cite_lines = "\n".join([f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}]".strip()
                            for c in citations])

    user = (
        f"Emergency query: {query}\n"
        f"Context JSON: {json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"Sources:\n{cite_lines}\n"
    )
    text = llm_text(system, user, temperature=0.1).strip()
    if compact:
        text = compact_text(text, 2200)

    timers = []
    if any(k in query.lower() for k in ["vascular occlusion", "vision", "blind"]):
        timers = [
            {"label": "Reassess symptoms", "minutes": 5},
            {"label": "Consider escalation threshold check", "minutes": 10},
        ]
    return {"mode": "emergency", "checklist": text, "timers": timers, "evidence": evidence, "citations": citations}


class CompareRequest(BaseModel):
    treatments: List[str] = Field(..., min_length=2, max_length=4)
    context: Optional[str] = None
    compact: bool = True


def compare_tool(req: CompareRequest) -> dict:
    key = _h("compare", req.model_dump())
    cached = answer_cache.get(key)
    if cached is not None:
        return {**cached, "meta": {"cached": True}}

    q = (
        f"Compare {', '.join(req.treatments)} in aesthetic practice.\n"
        "Include: typical indications, onset, duration, diffusion/spread, storage/handling, dosing equivalence if supported, contraindications, adverse events,\n"
        "practical selection notes, and any medicolegal/documentation considerations."
    )
    if req.context:
        q += f" Context: {req.context}"

    chunks = retrieve_chunks(q, filters={"domain": "aesthetics"})
    evidence = evidence_freshness_score(chunks)
    citations = extract_citations(chunks, max_items=8)

    system = (
        "Return STRICT JSON for a side-by-side comparison.\n"
        "Schema:\n"
        '{"table": {"columns": ["Feature", ...treatments], "rows": [["Feature", "...", "..."], ...]},'
        '"summary": "short paragraph",'
        '"selection_tips": ["..."],'
        '"limitations": ["... (insufficient evidence where applicable)"]'
        "}\n"
        "Rules: never invent equivalence; if unsure, say 'insufficient evidence'. Prefer PI/guidelines.\n"
    )
    user = f"Treatments: {req.treatments}\nContext: {req.context or ''}\nEvidence badge: {evidence}\nCitations:\n" + "\n".join(
        [f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}]".strip() for c in citations]
    )
    try:
        data = llm_json(system, user, temperature=0.0)
    except Exception:
        data = {"table": {}, "summary": "Unable to generate comparison", "selection_tips": [], "limitations": []}

    payload = {"comparison": data, "evidence": evidence, "citations": citations, "meta": {"cached": False}}
    answer_cache[key] = payload
    return payload


RISK_MAP = {
    "high_risk_zones": [
        {"zone": "Glabella / nasal root", "risk": "vascular compromise; severe ischemic complications", "note": "Use careful technique; avoid blind bolus."},
        {"zone": "Nose (dorsum / tip)", "risk": "vascular compromise; skin necrosis risk", "note": "High-risk territory; consider minimal volumes and cautious planes."},
        {"zone": "Nasolabial fold (superior)", "risk": "vascular branches; embolic risk", "note": "Prioritize anatomical knowledge; aspirate practice varies-follow local protocol."},
        {"zone": "Periorbital / tear trough", "risk": "vascular + vision-threatening events", "note": "Treat as high-stakes; have emergency plan."},
        {"zone": "Temple", "risk": "vascular injury; deep anatomy complexity", "note": "High expertise zone."},
    ],
    "principles": [
        "High-risk areas demand strict technique, conservative volumes, and readiness to manage complications.",
        "Use product-specific PI and institutional protocols; avoid unsupported dosing/technique claims.",
        "For suspected acute complication (severe pain, blanching, livedo, visual symptoms), treat as emergency."
    ],
    "disclaimer": "Educational guidance only; follow product PI, local protocols, and qualified clinical judgement."
}


class HandoutRequest(BaseModel):
    topic: str
    language: str = "en"
    style: str = "patient_handout"
    compact: bool = True


def handout_tool(req: HandoutRequest) -> dict:
    key = _h("handout", req.model_dump())
    cached = answer_cache.get(key)
    if cached is not None:
        return {**cached, "meta": {"cached": True}}

    q = f"Patient education: {req.topic}"
    chunks = retrieve_chunks(q, filters={"domain": "aesthetics"})
    evidence = evidence_freshness_score(chunks)
    citations = extract_citations(chunks, max_items=6)

    system = (
        "Write a patient-facing document.\n"
        f"Language: {req.language}\n"
        f"Style: {req.style}\n"
        "Include: what it is, benefits, common side effects, rare serious risks, aftercare, when to call.\n"
        "Avoid jargon and marketing.\n"
        "If evidence is weak, keep conservative.\n"
    )
    user = f"Topic: {req.topic}\nEvidence badge: {evidence}\nCitations:\n" + "\n".join(
        [f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}]".strip() for c in citations]
    )
    text = llm_text(system, user, temperature=0.2).strip()
    if req.compact:
        text = compact_text(text, 2200)

    payload = {"handout": text, "style": req.style, "evidence": evidence, "citations": citations, "meta": {"cached": False}}
    answer_cache[key] = payload
    return payload


class DocNoteRequest(BaseModel):
    procedure: str
    area: str
    product: Optional[str] = None
    indications: Optional[str] = None
    consent_obtained: bool = True
    complications: Optional[str] = None
    compact: bool = True


def doc_note_tool(req: DocNoteRequest) -> dict:
    key = _h("docnote", req.model_dump())
    cached = answer_cache.get(key)
    if cached is not None:
        return {**cached, "meta": {"cached": True}}

    system = (
        "Generate a clinic documentation note template for aesthetic medicine.\n"
        "Return plain text with:\n"
        "CHIEF CONCERN / INDICATION\n"
        "COUNSELING & CONSENT\n"
        "PROCEDURE DETAILS\n"
        "POST-PROCEDURE INSTRUCTIONS\n"
        "COMPLICATIONS / FOLLOW-UP\n"
        "Tone: neutral, factual, medico-legal friendly. Do not invent specifics.\n"
    )
    user = json.dumps(req.model_dump(), ensure_ascii=False)
    text = llm_text(system, user, temperature=0.2).strip()
    if req.compact:
        text = compact_text(text, 2400)

    payload = {"note": text, "meta": {"cached": False}}
    answer_cache[key] = payload
    return payload


HOT_TOPICS_DEFAULT = [
    "Hyaluronic acid vascular occlusion management",
    "Botulinum toxin dosing glabella practical protocol",
    "Tear trough filler complication management",
    "Local anesthetic maximum safe dosing in office procedures",
    "Post-filler delayed nodule evaluation and management"
]


class PrecomputeRequest(BaseModel):
    topics: List[str] = Field(default_factory=list)


_precompute_lock = threading.Lock()


def precompute_hot(topics: List[str]) -> dict:
    topics = topics or HOT_TOPICS_DEFAULT
    done = []
    failed = []
    with _precompute_lock:
        for t in topics:
            try:
                ctx = parse_context(t)
                chunks = retrieve_chunks(t, filters={"domain": "aesthetics"})
                ev = evidence_freshness_score(chunks)
                ans = build_answer(t, ctx, chunks, ev, compact=True)
                claims = claim_level_tagging(ans, chunks)
                payload = {
                    "answer": ans,
                    "context": ctx,
                    "evidence": ev,
                    "claims": claims.get("claims", []),
                    "citations": extract_citations(chunks),
                    "meta": {"precomputed": True}
                }
                answer_cache[_h("qa", {"q": t, "compact": True})] = payload
                done.append(t)
            except Exception as e:
                failed.append({"topic": t, "error": str(e)})
    return {"ok": True, "done": done, "failed": failed}


class QARequest(BaseModel):
    query: str
    filters: Optional[dict] = None
    compact: bool = True
    include_claim_tags: bool = True
    include_progressive_disclosure: bool = True
    force_emergency: bool = False


def is_emergency(query: str, ctx: dict) -> bool:
    q = query.lower()
    if ctx.get("urgency") == "emergency":
        return True
    return any(k in q for k in EMERGENCY_KEYWORDS)


def fast_qa_one_call(query: str, filters: Optional[dict], compact: bool = True) -> dict:
    """
    FAST QA: single LLM call for context + answer + claim tags.
    Replaces 3 separate LLM calls (parse_context, build_answer, claim_level_tagging)
    with ONE call returning structured JSON.
    """
    cache_key = _h("fastqa", {"q": query, "f": filters or {}, "compact": compact})
    cached = answer_cache.get(cache_key)
    if cached is not None:
        return {**cached, "meta": {**cached.get("meta", {}), "cached": True}}

    chunks = retrieve_chunks(query, filters=filters or {"domain": "aesthetics"})
    citations = extract_citations(chunks, max_items=8)
    evidence = evidence_freshness_score(chunks)

    ql = query.lower()
    inferred_high_stakes = any(k in ql for k in ["dose", "dosing", "units", "occlusion", "blind", "necrosis", "anaphyl", "emergency"])
    inferred_intent = "dosing" if "dose" in ql or "units" in ql else ("comparison" if "vs" in ql else "general")
    ctx_stub = {"intent": inferred_intent, "urgency": "emergency" if "emergency" in ql else "routine", "high_stakes": inferred_high_stakes}

    if should_kill_switch(ctx_stub, evidence):
        payload = {
            "answer": (
                "Clinical Summary:\n"
                "Insufficient high-quality evidence was retrieved to provide specific dosing/protocol-level guidance for this high-stakes request.\n\n"
                "Practical Steps:\n"
                "- Use the product prescribing information and your institutional protocol for the exact indication.\n"
                "- If this is an acute complication or patient harm risk, escalate and follow emergency pathways.\n\n"
                "Complications & Red Flags:\n"
                "If severe pain, skin color change, neurologic symptoms, or visual symptoms occur, treat as urgent and follow emergency management protocols.\n\n"
                "What can go wrong next?\n"
                "- Delayed recognition of evolving complication\n"
                "- Inadequate escalation / referral timing\n"
                "- Incomplete documentation\n\n"
                "Evidence Notes:\n"
                "Low evidence / insufficient retrievable primary sources for safe specificity."
            ),
            "sections": {},
            "context": ctx_stub,
            "evidence": evidence,
            "claim_tags": [],
            "citations": citations,
            "meta": {"cached": False, "mode": "killswitch"}
        }
        answer_cache[cache_key] = payload
        return payload

    cite_lines = "\n".join(
        [f"- {c.get('title','')} ({c.get('year','')}) [{c.get('source_type','')}] {c.get('doi') or c.get('url') or ''}".strip()
         for c in citations]
    )

    system = (
        "You are AesthetiCite, clinician-facing decision support for aesthetic medicine.\n"
        "Return STRICT JSON only. No markdown.\n\n"
        "You MUST output this exact schema:\n"
        "{\n"
        "  \"context\": {\n"
        "    \"procedure\": string|null,\n"
        "    \"area\": string|null,\n"
        "    \"product\": string|null,\n"
        "    \"intent\": \"dosing\"|\"protocol\"|\"comparison\"|\"complication\"|\"consent\"|\"general\",\n"
        "    \"patient_constraints\": string[],\n"
        "    \"urgency\": \"routine\"|\"urgent\"|\"emergency\",\n"
        "    \"high_stakes\": boolean\n"
        "  },\n"
        "  \"answer_sections\": {\n"
        "    \"Clinical Summary\": string,\n"
        "    \"Practical Steps\": string,\n"
        "    \"Complications & Red Flags\": string,\n"
        "    \"What can go wrong next?\": string,\n"
        "    \"Evidence Notes\": string\n"
        "  },\n"
        "  \"claim_tags\": [\n"
        "    {\"claim\": string, \"evidence_strength\": \"High\"|\"Moderate\"|\"Low\"|\"Consensus\", \"why\": string}\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Be conservative. Prefer PI/guidelines.\n"
        "- If unsure, say 'insufficient evidence' (do NOT guess).\n"
        "- Keep claim_tags to 5-6 items unless truly necessary.\n"
    )

    user = (
        f"Query: {query}\n\n"
        f"Evidence badge: {evidence.get('badge')} (score={evidence.get('score')}, freshness={evidence.get('freshness')})\n\n"
        f"Sources:\n{cite_lines}\n"
    )

    data = llm_json(system, user, temperature=0.2)

    sections = data.get("answer_sections") or {}
    answer_text = (
        "Clinical Summary:\n" + (sections.get("Clinical Summary") or "").strip() + "\n\n"
        "Practical Steps:\n" + (sections.get("Practical Steps") or "").strip() + "\n\n"
        "Complications & Red Flags:\n" + (sections.get("Complications & Red Flags") or "").strip() + "\n\n"
        "What can go wrong next?\n" + (sections.get("What can go wrong next?") or "").strip() + "\n\n"
        "Evidence Notes:\n" + (sections.get("Evidence Notes") or "").strip()
    ).strip()

    if compact:
        answer_text = compact_text(answer_text, 1900)

    payload = {
        "answer": answer_text,
        "sections": sections,
        "context": data.get("context") or {},
        "evidence": evidence,
        "claim_tags": (data.get("claim_tags") or [])[:8],
        "citations": citations,
        "meta": {"cached": False, "mode": "single_call", "model": OPENAI_MODEL}
    }
    answer_cache[cache_key] = payload
    return payload


def qa(req: QARequest) -> dict:
    """
    Main QA function using control plane with per-category tuning,
    PI fallback, and OpenEvidence-style selective refusal.
    """
    from app.core.control_plane import answer_with_control_plane
    from app.core.retrieve_wrapper import make_retrieve_fn
    from app.db.session import SessionLocal
    
    filters = req.filters or {"domain": "aesthetic_medicine"}
    
    if req.force_emergency or any(k in req.query.lower() for k in EMERGENCY_KEYWORDS):
        filters = dict(filters)
        filters["bias"] = "complications"
    
    with SessionLocal() as db:
        retrieve_fn = make_retrieve_fn(db)
        return answer_with_control_plane(
            query=req.query,
            filters=filters,
            retrieve_chunks=retrieve_fn,
            compact=req.compact,
            enable_cache=True
        )


def split_sections(text: str) -> dict:
    headings = ["Clinical Summary", "Practical Steps", "Complications & Red Flags", "What can go wrong next?", "Evidence Notes"]
    out = {}
    current = None
    buf = []
    for line in text.splitlines():
        line_stripped = line.strip().rstrip(":")
        if line_stripped in headings:
            if current:
                out[current] = "\n".join(buf).strip()
            current = line_stripped
            buf = []
        else:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    if not out:
        out["Answer"] = text.strip()
    return out


@router.get("/health/top10")
def health():
    return {"ok": True, "app": "AesthetiCite Top 10", "time": datetime.utcnow().isoformat() + "Z"}


@router.post("/qa")
def qa_endpoint(req: QARequest, request: Request, background: BackgroundTasks):
    try:
        result = qa(req)
        case_id = get_case_id(request)
        if case_id:
            background.add_task(
                log_event,
                case_id=case_id,
                event_type="aestheticite_opened",
                payload={
                    "endpoint": "/qa",
                    "query": (req.question or "")[:280],
                    "procedure": req.procedure,
                    "mode": "qa"
                }
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA error: {e}")


@router.post("/emergency")
def emergency_endpoint(req: QARequest, request: Request, background: BackgroundTasks):
    try:
        req.force_emergency = True
        result = qa(req)
        case_id = get_case_id(request)
        if case_id:
            background.add_task(
                log_event,
                case_id=case_id,
                event_type="emergency_mode_opened",
                payload={
                    "endpoint": "/emergency",
                    "query": (req.question or "")[:280],
                    "procedure": req.procedure,
                    "mode": "emergency"
                }
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emergency error: {e}")


@router.post("/compare")
def compare_endpoint(req: CompareRequest):
    try:
        return compare_tool(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compare error: {e}")


@router.get("/risk-map")
def risk_map():
    return {"ok": True, "risk_map": RISK_MAP}


@router.post("/handout")
def handout_endpoint(req: HandoutRequest):
    try:
        return handout_tool(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Handout error: {e}")


@router.post("/doc-note")
def doc_note_endpoint(req: DocNoteRequest):
    try:
        return doc_note_tool(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Doc note error: {e}")


@router.post("/precompute/hot")
def precompute_endpoint(req: PrecomputeRequest):
    try:
        return precompute_hot(req.topics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Precompute error: {e}")


class DeepConsultRequest(BaseModel):
    """Request for PhD-level multi-study analysis."""
    question: str
    filters: Optional[dict] = None
    max_sources: int = Field(default=40, ge=10, le=100)
    min_meta_analyses: int = Field(default=1, ge=0, le=5)
    min_rcts: int = Field(default=3, ge=0, le=10)
    include_disagreement: bool = Field(default=True)


class QARequestWithRouting(BaseModel):
    """QA request with optional auto-routing to DeepConsult."""
    query: str
    filters: Optional[dict] = None
    auto_route: bool = Field(default=True, description="Auto-route to DeepConsult for complex queries")
    force_deep: bool = Field(default=False, description="Force DeepConsult even if router says no")
    compact: bool = Field(default=True)


@router.post("/deepconsult")
def deepconsult_endpoint(req: DeepConsultRequest, request: Request, background: BackgroundTasks):
    """
    PhD-level multi-study analysis endpoint.
    
    Use ONLY for complex questions requiring:
    - Multi-paper synthesis
    - Evidence comparison
    - Systematic review-style reasoning
    
    NOT for routine clinical questions (use /qa instead).
    """
    from app.core.deepconsult import run_deepconsult
    from app.core.retrieve_wrapper import make_retrieve_fn
    from app.db.session import SessionLocal
    
    try:
        with SessionLocal() as db:
            retrieve_fn = make_retrieve_fn(db)
            result = run_deepconsult(
                question=req.question,
                retrieve_chunks=retrieve_fn,
                filters=req.filters or {"domain": "aesthetic_medicine"},
                max_sources=req.max_sources,
                min_meta_analyses=req.min_meta_analyses,
                min_rcts=req.min_rcts,
                include_disagreement=req.include_disagreement,
            )
        
        case_id = get_case_id(request)
        background.add_task(log_event, case_id, "deepconsult", {
            "question": req.question[:200],
            "refused": result.get("refused", False),
            "sources_used": result.get("meta", {}).get("sources_used", 0),
            "conflict_found": result.get("disagreement", {}).get("conflict_found", False),
        })
        
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DeepConsult error: {e}")




@router.post("/qa/smart")
def qa_smart_endpoint(req: QARequestWithRouting, request: Request, background: BackgroundTasks):
    """
    Smart QA endpoint with automatic routing to DeepConsult.
    
    If auto_route=True and query is detected as complex multi-study analysis,
    automatically routes to DeepConsult for PhD-level synthesis.
    
    Otherwise returns fast clinical answer from /qa.
    """
    from app.core.deepconsult import run_deepconsult, classify_need_deepconsult
    from app.core.control_plane import answer_with_control_plane
    from app.core.retrieve_wrapper import make_retrieve_fn
    from app.db.session import SessionLocal
    
    filters = req.filters or {"domain": "aesthetic_medicine"}
    
    try:
        with SessionLocal() as db:
            retrieve_fn = make_retrieve_fn(db)
            
            sample = retrieve_fn(req.query, filters, 20)
            use_deep, router_meta = classify_need_deepconsult(req.query, sample)
            
            if req.force_deep:
                use_deep = True
                router_meta["forced"] = True
            
            if req.auto_route and use_deep:
                result = run_deepconsult(
                    question=req.query,
                    retrieve_chunks=retrieve_fn,
                    filters=filters,
                    max_sources=40,
                    include_disagreement=True,
                )
                result["meta"] = result.get("meta", {})
                result["meta"]["auto_routed"] = True
                result["meta"]["router"] = router_meta
                
                case_id = get_case_id(request)
                background.add_task(log_event, case_id, "qa_smart_deep", {
                    "query": req.query[:200],
                    "routed_to": "deepconsult",
                    "router_score": router_meta.get("router_score", 0),
                })
                
                return {"ok": True, **result}
            
            result = answer_with_control_plane(
                query=req.query,
                filters=filters,
                retrieve_chunks=retrieve_fn,
                compact=req.compact,
                enable_cache=True,
            )
            result["meta"] = result.get("meta", {})
            result["meta"]["auto_routed"] = False
            result["meta"]["router"] = router_meta
            
            case_id = get_case_id(request)
            background.add_task(log_event, case_id, "qa_smart_fast", {
                "query": req.query[:200],
                "routed_to": "qa",
                "router_score": router_meta.get("router_score", 0),
            })
            
            return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Smart QA error: {e}")
