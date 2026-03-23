"""
Single-call streaming endpoint — OpenEvidence-feel pipeline.

1) Deterministic skeleton (<1ms, no LLM) for instant perceived speed
2) ONE async httpx streaming call (no separate plan phase)
3) Citation enforcement baked into the prompt itself
4) Heartbeat while proxy warms up
5) TTL caches for retrieval + full answers
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.safety import safety_screen, sanitize_input
from app.core.lang import detect_lang, language_label, SUPPORTED_LANGS
from app.core.query_translator import get_retrieval_query, needs_translation
from app.core.governance import log_governance_event, rerank_by_domain, detect_intent, validate_citations, REFUSAL_ANSWER
from app.db.session import get_db
from app.rag.retriever import retrieve_db
from app.rag import async_retriever as _ar
from app.engine.improvements import classify_chunk, DISPLAY_LABELS, protocol_followups
from app.engine.improvements import compute_aci as compute_aci_deterministic
from app.engine.improvements import Source as ImpSource
from app.engine.evidence_hierarchy import enrich_chunks_for_api, rewrite_query_for_evidence
from app.engine.safety_layer import enrich_meta_payload as _enrich_safety, safety_block_for_prompt as _safety_prompt
from app.engine.protocol_gap_fix import (
    build_enhanced_answer_context,
    enforce_protocol_completeness,
    generate_answer_with_gap_fix,
)
from app.api.protocol_bridge import get_bridge as _get_protocol_bridge
from app.engine.quality_fusion import (
    retrieve_with_quality_fusion,
    source_to_citation_dict,
    protocol_followups as qf_protocol_followups,
    Source as QFSource,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["ask-v2"])


class _TTLCache:
    def __init__(self, max_items: int = 2000, ttl_seconds: int = 3600):
        self._max = max_items
        self._ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        exp, val = item
        if exp < time.time():
            self._store.pop(key, None)
            return None
        return val

    def put(self, key: str, value: Any) -> None:
        if len(self._store) >= self._max:
            oldest = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest, None)
        self._store[key] = (time.time() + self._ttl, value)


_retrieval_cache = _TTLCache(max_items=3000, ttl_seconds=3600)
_answer_cache = _TTLCache(max_items=1500, ttl_seconds=900)


def _cache_key(q: str, extra: str = "") -> str:
    return hashlib.sha256((q.strip().lower() + "|" + extra).encode()).hexdigest()


def _sse(event_type: str, data: Any) -> str:
    return f"data: {json.dumps({'type': event_type, **data} if isinstance(data, dict) else {'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"


async def _ensure_conversation(conversation_id: str, user_id: str = "", title: str = "") -> None:
    if _ar._pool is None:
        return
    async with _ar._pool.acquire() as con:
        await con.execute(
            "INSERT INTO conversations(id, user_id, title) VALUES($1, NULLIF($2,''), NULLIF($3,'')) ON CONFLICT DO NOTHING",
            conversation_id, user_id, title,
        )


async def _add_message(conversation_id: str, role: str, content: str) -> None:
    if _ar._pool is None:
        return
    async with _ar._pool.acquire() as con:
        await con.execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES($1,$2,$3)",
            conversation_id, role, content,
        )


async def _fetch_recent_messages(conversation_id: str, limit: int = 6) -> List[Dict[str, Any]]:
    if _ar._pool is None:
        return []
    async with _ar._pool.acquire() as con:
        rows = await con.fetch(
            "SELECT role, content FROM messages WHERE conversation_id=$1 ORDER BY created_at DESC LIMIT $2",
            conversation_id, limit,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _compress_context(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for m in messages[-MEMORY_MAX_TURNS:]:
        role = "User" if m["role"] == "user" else "Assistant"
        txt = m["content"].strip()
        if len(txt) > 700:
            txt = txt[:700] + "…"
        parts.append(f"{role}: {txt}")
    ctx = "\n".join(parts)
    if len(ctx) > MEMORY_MAX_CHARS:
        ctx = ctx[-MEMORY_MAX_CHARS:]
    return ctx


COMPOSE_MODEL = os.getenv("COMPOSE_MODEL", "gpt-4o-mini")
CHUNK_CHAR_CAP = int(os.getenv("CHUNK_CHAR_CAP", "650"))
MAX_SOURCES_TO_LLM = int(os.getenv("MAX_SOURCES_TO_LLM", "10"))

COMPOSE_MAX_TOKENS = int(os.getenv("COMPOSE_MAX_TOKENS", "1100"))
COMPOSE_TEMPERATURE = float(os.getenv("COMPOSE_TEMPERATURE", "0.2"))
HEARTBEAT_SECONDS = float(os.getenv("HEARTBEAT_SECONDS", "0.8"))

MEMORY_MAX_TURNS = int(os.getenv("MEMORY_MAX_TURNS", "6"))
MEMORY_MAX_CHARS = int(os.getenv("MEMORY_MAX_CHARS", "1800"))

_AI_PROXY_URL = settings.OPENAI_BASE_URL.rstrip("/") + "/chat/completions"
_AI_HEADERS = {"Content-Type": "application/json"}


def _get_headers() -> dict:
    return {**_AI_HEADERS, "Authorization": f"Bearer {settings.OPENAI_API_KEY}"}


SYSTEM_COMPOSE = "Be concise. Follow citation rules exactly. No invented facts."


async def _llm_stream(prompt: str, system: str) -> AsyncGenerator[str, None]:
    payload = {
        "model": COMPOSE_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": COMPOSE_TEMPERATURE,
        "max_tokens": COMPOSE_MAX_TOKENS,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=None) as client:  # nosec B113
        async with client.stream("POST", _AI_PROXY_URL, json=payload, headers=_get_headers()) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                    tok = obj["choices"][0].get("delta", {}).get("content")
                    if tok:
                        yield tok
                except Exception:  # nosec B112
                    continue


def _build_single_call_prompt(question: str, chunks: list, conversation_context: str = "", lang: str = "en", protocol_block: str = "") -> str:
    compact = []
    for i, c in enumerate(chunks[:MAX_SOURCES_TO_LLM]):
        compact.append({
            "sid": f"S{i+1}",
            "t": (c.get("title") or "")[:160],
            "y": c.get("year"),
            "id": c.get("doi") or c.get("url") or c.get("source_id"),
            "x": (c.get("text") or "")[:CHUNK_CHAR_CAP],
        })

    ctx_block = ""
    if conversation_context:
        ctx_block = f"\nConversation context (most recent turns):\n{conversation_context}\n"

    lang_name = language_label(lang)
    lang_instruction = f"6) CRITICAL: You MUST write the ENTIRE answer in {lang_name}. Every section—Clinical Summary, Key Evidence-Based Points, Safety Considerations, Limitations, and Follow-up Questions—must be in {lang_name}. Only source IDs like [S1] and medical abbreviations remain in their original form. Do not write any section in English." if lang != "en" else ""

    return f"""You are AesthetiCite (evidence-grounded clinical assistant for aesthetic medicine).
{ctx_block}
Hard rules:
1) EVERY factual claim MUST include inline citation using EXACTLY [S1], [S2], [S3] format (with the letter S). Never use [1], [2] or any other format.
2) You may cite MULTIPLE sources per claim if relevant.
3) If insufficient evidence: say "Evidence insufficient".
4) Prefer high-quality sources when multiple exist.
5) You may reuse source IDs multiple times across the answer.
{lang_instruction}
{protocol_block}

Write in this exact structure:

Clinical Summary (2\u20133 lines)

Key Evidence-Based Points
- Bullet (end with citations like [S1][S3])
- Bullet

Safety Considerations (if applicable)

Limitations / Uncertainty

Suggested Follow-up Questions
- Contextual follow-up question 1
- Contextual follow-up question 2
- Contextual follow-up question 3

Question: {question}

Sources (JSON):
{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}""".strip()


def _infer_evidence_type(document_type: Optional[str], journal_or_org: Optional[str]) -> str:
    t = (document_type or "").lower()
    j = (journal_or_org or "").lower()
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
    if any(x in j for x in ["nejm", "jama", "lancet", "bmj"]):
        return "Journal Article"
    return "Other"


def _evidence_rank(evidence_type: str) -> int:
    order = {
        "Guideline/Consensus": 1,
        "Systematic Review": 2,
        "Randomized Trial": 3,
        "Observational Study": 4,
        "Case Report/Series": 5,
        "Narrative Review": 6,
        "Journal Article": 7,
        "Other": 8,
    }
    return order.get(evidence_type, 9)


_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _normalize_doi(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip().replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "").strip()
    m = _DOI_RE.search(s)
    return m.group(0) if m else None


def _best_url(chunk: dict) -> str:
    url = (chunk.get("url") or "").strip()
    if url and url.startswith("http"):
        return url
    doi = _normalize_doi(chunk.get("doi") or chunk.get("url"))
    if doi:
        return f"https://doi.org/{doi}"
    source_id = (chunk.get("source_id") or "").strip()
    if source_id.upper().startswith("PMC"):
        pmc_num = source_id.upper().replace("PMC", "")
        if pmc_num.isdigit():
            return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{source_id.upper()}/"
    pmid_raw = source_id.upper().replace("PMID_", "").replace("PMID", "")
    if pmid_raw.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid_raw}/"
    pmid_field = (chunk.get("pmid") or "").strip()
    if pmid_field and pmid_field.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid_field}/"
    return ""


def _build_citations_payload(chunks: list) -> list:
    citations = []
    for i, c in enumerate(chunks):
        title = c.get("title", "Unknown")
        year = c.get("year")
        source = c.get("organization_or_journal") or c.get("journal") or "Research Source"
        url = _best_url(c)
        doc_type = c.get("document_type") or c.get("evidence_level") or ""
        doi = _normalize_doi(c.get("doi") or c.get("url"))

        enriched = classify_chunk(c)
        display_et = DISPLAY_LABELS.get(enriched.evidence_type, enriched.evidence_type)
        citations.append({
            "id": i + 1,
            "title": title,
            "source": source,
            "year": year or 2024,
            "authors": c.get("authors", "Author et al."),
            "url": url,
            "doi": doi or "",
            "document_type": doc_type,
            "evidence_type": display_et,
            "evidence_type_raw": enriched.evidence_type,
            "evidence_tier": enriched.evidence_tier,
            "evidence_grade": enriched.evidence_grade,
            "evidence_rank": _evidence_rank(display_et),
            "source_tier": enriched.evidence_tier,
            "publication_type": c.get("publication_type") or c.get("document_type") or "",
            "source_id": c.get("source_id", ""),
            "journal": c.get("journal") or c.get("organization_or_journal") or "",
        })
    return citations


def _compute_badge(citations: list) -> dict:
    if not citations:
        return {"score": 0.1, "badge": "Low", "badge_color": "red", "types": {}, "why": "No sources", "unique_sources": 0}

    type_weights = {
        "guideline": 0.95, "consensus": 0.95, "meta-analysis": 0.95,
        "systematic-review": 0.92, "rct": 0.88, "review": 0.75,
        "cohort": 0.72, "case-series": 0.60, "journal_article": 0.80,
    }

    types: Dict[str, int] = {}
    total_w = 0.0
    strongest = 0.0
    for c in citations:
        dt = (c.get("document_type") or "other").lower().replace(" ", "-")
        w = type_weights.get(dt, 0.65)
        total_w += w
        strongest = max(strongest, w)
        src = c.get("source", "Other")
        types[src] = types.get(src, 0) + 1

    avg = total_w / max(len(citations), 1)
    breadth = min(1.0, len(citations) / 6.0) * 0.05
    score = min(0.99, max(0.10, 0.55 * strongest + 0.45 * avg + breadth))

    if score >= 0.85:
        badge, color = "High", "green"
    elif score >= 0.65:
        badge, color = "Moderate", "yellow"
    else:
        badge, color = "Low", "red"

    why_parts = []
    for t in types:
        why_parts.append(t)

    return {
        "score": round(score, 2),
        "badge": badge,
        "badge_color": color,
        "types": types,
        "why": "; ".join(why_parts[:3]) if why_parts else f"{len(citations)} sources",
        "unique_sources": len(citations),
    }


def _build_authority_header(chunks: list, badge: dict, aci_result=None) -> str:
    if not chunks:
        return ""

    total = len(chunks)
    typed_sources: List[tuple] = []
    years = []
    for c in chunks:
        enriched = classify_chunk(c)
        display_et = DISPLAY_LABELS.get(enriched.evidence_type, enriched.evidence_type)
        typed_sources.append((_evidence_rank(display_et), display_et))
        yr = c.get("year")
        if yr:
            years.append(int(yr))

    typed_sources.sort(key=lambda x: x[0])
    top_types: List[str] = []
    for _, et in typed_sources:
        if et not in top_types:
            top_types.append(et)
        if len(top_types) >= 3:
            break

    highest = top_types[0] if top_types else "N/A"
    if aci_result is not None:
        conf_str = f"{aci_result.score_0_to_10}/10"
    else:
        confidence = badge.get("score", 0.5)
        conf_str = f"{round(confidence * 10, 1)}/10"

    gaps: List[str] = []
    has_high = any(r <= 3 for r, _ in typed_sources)
    if not has_high:
        gaps.append("No RCTs, guidelines, or systematic reviews found")
    if years:
        recent = [y for y in years if y >= 2020]
        if len(recent) < total * 0.3:
            gaps.append("Limited recent evidence (post-2020)")
    if total < 5:
        gaps.append("Few supporting sources")

    gaps_text = ""
    if gaps:
        gaps_text = f"\n- Evidence gaps: {'; '.join(gaps)}"

    header = (
        "**Evidence Strength Summary**\n"
        f"- Overall confidence: {conf_str}\n"
        f"- Highest evidence level: {highest}\n"
        f"- Supporting sources: {total}\n"
        f"- Evidence mix: {', '.join(top_types) if top_types else 'N/A'}"
        f"{gaps_text}\n\n"
        "**Safety considerations (aesthetic practice):**\n"
        "- Prioritize vascular risk mitigation where relevant; have an occlusion response protocol.\n"
        "- Favor conservative dosing/volumes and reassess; document informed consent and contraindications.\n\n"
        "What is well-supported vs. uncertain will be stated explicitly below.\n\n"
        "---\n\n"
    )
    return header


def _build_evidence_footer(chunks: list) -> str:
    well_supported: List[str] = []
    limited: List[str] = []

    for c in chunks[:MAX_SOURCES_TO_LLM]:
        enriched = classify_chunk(c)
        display_et = DISPLAY_LABELS.get(enriched.evidence_type, enriched.evidence_type)
        rank = _evidence_rank(display_et)
        title = (c.get("title") or "Untitled")[:80]
        tier_label = f"Tier {enriched.evidence_tier}"
        if rank <= 3:
            well_supported.append(f"{title} ({display_et}, {tier_label})")
        elif rank <= 5:
            limited.append(f"{title} ({display_et}, {tier_label})")

    lines = ["\n\n---\n"]
    if well_supported:
        lines.append("**Well-supported by:**")
        for s in well_supported[:4]:
            lines.append(f"- {s}")
    if limited:
        lines.append("\n**Where evidence is more limited:**")
        for s in limited[:3]:
            lines.append(f"- {s}")
    if not well_supported and not limited:
        lines.append("**Evidence base:** Primarily narrative reviews and case-level evidence.")

    return "\n".join(lines) + "\n"


def _skeleton_from_sources(q: str, citations: list) -> str:
    top = citations[:5]
    cites = " ".join([f"[S{c['id']}]" for c in top])
    return (
        "Clinical summary (loading grounded answer\u2026)\n"
        "- Evidence retrieved; generating a grounded answer with inline citations.\n"
        "- Claims will only be stated when supported by the provided sources.\n\n"
        f"Top sources: {cites}\n\n"
    )


def _extract_followups(full_text: str, question: str, intent: str = "general") -> List[str]:
    ql = (question or "").lower()
    is_complication = intent in ("complication", "complications") or any(
        k in ql for k in ["occlusion", "ischemia", "hyaluronidase", "necrosis", "complication", "vascular"]
    )
    if is_complication:
        return qf_protocol_followups(question)[:4]

    lines = full_text.split("\n")
    in_followup = False
    extracted: List[str] = []
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if "follow-up" in lower or "follow up" in lower or "suggested follow" in lower:
            in_followup = True
            continue
        if in_followup:
            if stripped.startswith("- ") or stripped.startswith("* "):
                candidate = stripped.lstrip("-* ").strip()
                candidate = re.sub(r'\[S\d+\]', '', candidate).strip()
                if len(candidate) > 10 and candidate.endswith("?"):
                    extracted.append(candidate)
            elif stripped.startswith("**") or stripped.startswith("---"):
                in_followup = False
        if len(extracted) >= 4:
            break

    if len(extracted) < 2:
        protocol = qf_protocol_followups(question)
        for fb in protocol:
            if fb not in extracted:
                extracted.append(fb)
            if len(extracted) >= 4:
                break

    return extracted[:4]


K_DEFAULT = int(os.getenv("K_DEFAULT", "40"))


class AskV2Body(BaseModel):
    question: str
    domain: str = "aesthetic_medicine"
    mode: str = "standard"
    k: int = K_DEFAULT
    conversation_id: str = ""
    lang: Optional[str] = None


@router.post("/v2/stream")
async def ask_v2_stream(body: AskV2Body, request: Request, db: Session = Depends(get_db)):
    q = sanitize_input(body.question)
    if not q:
        return StreamingResponse(
            iter([_sse("error", {"message": "Empty query"})]),
            media_type="text/event-stream",
        )

    safety = safety_screen(q)
    if not safety.allowed:
        async def refuse():
            yield _sse("error", {"message": safety.refusal_reason or "Request refused."})
        return StreamingResponse(refuse(), media_type="text/event-stream")

    conversation_id = body.conversation_id.strip() or ""

    async def generate() -> AsyncGenerator[str, None]:
        t0 = time.perf_counter()
        timing: Dict[str, Any] = {}

        yield _sse("status", {"phase": "started", "message": "Searching evidence..."})

        conv_context = ""
        if conversation_id:
            try:
                await _ensure_conversation(conversation_id)
                await _add_message(conversation_id, "user", q)
                recent = await _fetch_recent_messages(conversation_id, limit=MEMORY_MAX_TURNS)
                conv_context = _compress_context(recent)
            except Exception as e:
                logger.warning(f"Conversation memory error: {e}")

        # ── Speed optimizer: hot complication cache ───────────────────────────
        from app.engine.speed_optimizer import (
            get_hot_answer, set_hot_answer, is_hot_complication,
            limit_context, record_latency,
        )
        hot = get_hot_answer(q)
        if hot:
            yield _sse("citations", hot.get("citations", []))
            answer = hot.get("answer", "")
            for i in range(0, len(answer), 150):
                yield _sse("content", answer[i:i+150])
            yield _sse("done", {"cached": True, "cache_source": hot.get("cache_source")})
            return

        ans_key = _cache_key(q, f"k={body.k}")
        cached = _answer_cache.get(ans_key)
        if cached:
            yield _sse("citations", cached.get("citations", []))
            yield _sse("evidence_badge", cached.get("badge", {}))
            if cached.get("meta"):
                yield _sse("meta", cached["meta"])
            for chunk in cached.get("tokens", []):
                yield _sse("content", chunk)
            yield _sse("related", cached.get("related", []))
            yield _sse("done", {"cached": True, "total_ms": int((time.perf_counter() - t0) * 1000)})
            return

        explicit_lang_early = (body.lang or "").strip().lower() if body.lang else None
        detected_lang = explicit_lang_early if explicit_lang_early in SUPPORTED_LANGS else detect_lang(q)
        retrieval_query, original_native_query = get_retrieval_query(q, detected_lang)
        translation_strategy = needs_translation(detected_lang)
        if original_native_query:
            logger.info(f"Multilingual retrieval: lang={detected_lang}, strategy={translation_strategy}, translated='{retrieval_query[:80]}'")

        t1 = time.perf_counter()
        rkey = _cache_key(retrieval_query, f"retrieval:{translation_strategy}:{detected_lang}:k={body.k}")
        chunks = _retrieval_cache.get(rkey)
        if chunks is None:
            if _ar._pool is not None:
                chunks = await _ar.retrieve_hardened_async(
                    question=retrieval_query, domain=body.domain, k=body.k
                )
            else:
                chunks = await asyncio.to_thread(
                    retrieve_db, db=db, question=retrieval_query, domain=body.domain, k=body.k
                )
            if translation_strategy == "dual" and original_native_query:
                native_key = _cache_key(q, f"retrieval_native:k={body.k}")
                native_chunks = _retrieval_cache.get(native_key)
                if native_chunks is None:
                    if _ar._pool is not None:
                        native_chunks = await _ar.retrieve_hardened_async(
                            question=q, domain=body.domain, k=body.k
                        )
                    else:
                        native_chunks = await asyncio.to_thread(
                            retrieve_db, db=db, question=q, domain=body.domain, k=body.k
                        )
                    _retrieval_cache.put(native_key, native_chunks)
                seen_ids = {c.get("id") or c.get("doc_id") or c.get("title", "") for c in chunks}
                for nc in (native_chunks or []):
                    nc_id = nc.get("id") or nc.get("doc_id") or nc.get("title", "")
                    if nc_id not in seen_ids:
                        chunks.append(nc)
                        seen_ids.add(nc_id)
                logger.info(f"Dual retrieval merged: {len(chunks)} total chunks (translated + native)")
            _retrieval_cache.put(rkey, chunks)
        timing["retrieval_ms"] = int((time.perf_counter() - t1) * 1000)

        intent = detect_intent(q)
        chunks = rerank_by_domain(chunks, intent)

        if not chunks or len(chunks) < 2:
            yield _sse("error", {"message": "Insufficient evidence to answer with citations."})
            return

        t2 = time.perf_counter()

        def _sync_retrieve_adapter(query: str, k: int, filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
            try:
                return retrieve_db(db=db, question=query, domain=body.domain, k=k)
            except Exception as e:
                logger.warning(f"Quality fusion retrieval error: {e}")
                return []

        # Rewrite query to boost high-tier evidence retrieval
        _qf_rewrite = rewrite_query_for_evidence(q)
        qf_retrieval_query = _qf_rewrite["rewritten_query"] if _qf_rewrite["boost_types"] else retrieval_query
        protocol_prompt_block = ""
        _eh_badge: dict = {}

        try:
            qf_bundle = await asyncio.to_thread(
                retrieve_with_quality_fusion,
                qf_retrieval_query,
                _sync_retrieve_adapter,
                k_final=40,
                k_quality=25,
                k_general=40,
            )
            qf_sources: List[QFSource] = qf_bundle["sources"]
            qf_aci = qf_bundle["aci"]

            if qf_sources and len(qf_sources) >= 2:
                chunks_for_prompt = []
                for s in qf_sources:
                    raw = s._raw if s._raw else {}
                    raw.update({
                        "title": s.title, "year": s.year, "journal": s.journal,
                        "source_id": s.source_id, "evidence_type": s.evidence_type,
                        "evidence_tier": s.evidence_tier, "publication_type": s.publication_type,
                        "chunk_text": s.chunk_text or raw.get("chunk_text", ""),
                    })
                    chunks_for_prompt.append(raw)
                citations_payload, _eh_badge = enrich_chunks_for_api(chunks_for_prompt)
                gap_ctx = build_enhanced_answer_context(q, chunks_for_prompt)
                chunks = gap_ctx["reranked_chunks"]
                protocol_prompt_block = gap_ctx["protocol_prompt_block"]
                if gap_ctx["coverage_gaps"]:
                    logger.info(f"Protocol coverage gaps: {gap_ctx['coverage_gaps']}")
                logger.info(
                    f"Quality fusion: {len(qf_sources)} sources, "
                    f"tiers={sum(1 for s in qf_sources if s.evidence_tier == 'A')}A/"
                    f"{sum(1 for s in qf_sources if s.evidence_tier == 'B')}B/"
                    f"{sum(1 for s in qf_sources if s.evidence_tier == 'C')}C, "
                    f"ACI={qf_aci.score_0_to_10}"
                )
            else:
                gap_ctx = build_enhanced_answer_context(q, chunks)
                chunks = gap_ctx["reranked_chunks"]
                protocol_prompt_block = gap_ctx["protocol_prompt_block"]
                citations_payload, _eh_badge = enrich_chunks_for_api(chunks)
                qf_aci = None
        except Exception as e:
            logger.warning(f"Quality fusion failed, falling back: {e}")
            gap_ctx = build_enhanced_answer_context(q, chunks)
            chunks = gap_ctx["reranked_chunks"]
            protocol_prompt_block = gap_ctx["protocol_prompt_block"]
            citations_payload, _eh_badge = enrich_chunks_for_api(chunks)
            qf_aci = None

        badge_payload = {
            "level":     _eh_badge.get("level", "Low"),
            "label":     f"{_eh_badge.get('emoji', '⚪')} {_eh_badge.get('label', 'Limited')}",
            "color":     _eh_badge.get("color", "slate"),
            "best_type": _eh_badge.get("best_type", "Other"),
            "emoji":     _eh_badge.get("emoji", "⚪"),
        }
        yield _sse("citations", citations_payload)
        yield _sse("evidence_badge", badge_payload)
        timing["citations_ms"] = int((time.perf_counter() - t2) * 1000)

        # ── Protocol bridge: emit structured protocol card if query triggers one ──
        try:
            _protocol_card = _get_protocol_bridge().evaluate(
                query=q,
                context_hints={
                    "symptoms": [
                        kw for kw in ["blanching", "mottling", "visual", "ptosis",
                                      "nodule", "infection", "wheeze", "urticaria"]
                        if kw in q.lower()
                    ],
                    "free_text": q,
                },
            )
            if _protocol_card:
                yield _sse("protocol_card", _protocol_card)
                logger.info(
                    f"Protocol bridge: emitted card for "
                    f"key={_protocol_card.get('_triggered_by')} "
                    f"protocol={_protocol_card.get('matched_protocol_key')}"
                )
        except Exception as _bridge_err:
            logger.warning(f"Protocol bridge error (non-fatal): {_bridge_err}")
        # ── end protocol bridge ──

        if await request.is_disconnected():
            return

        meta_payload: Dict[str, Any] = {}
        aci_result = None
        if qf_aci is not None:
            aci_result = qf_aci
            meta_payload["aci_score"] = qf_aci.score_0_to_10
            meta_payload["aci_badge"] = qf_aci.badge
            meta_payload["aci_components"] = qf_aci.components
            meta_payload["aci_rationale"] = qf_aci.rationale
        else:
            try:
                enriched_sources = [classify_chunk(c) for c in chunks]
                aci_result = compute_aci_deterministic(topic=q, sources=enriched_sources)
                meta_payload["aci_score"] = aci_result.score_0_to_10
                meta_payload["aci_badge"] = aci_result.badge
                meta_payload["aci_components"] = aci_result.components
                meta_payload["aci_rationale"] = aci_result.rationale
            except Exception as e:
                logger.warning(f"Deterministic ACI failed: {e}")
        meta_payload = _enrich_safety(
            meta_payload, q,
            region=getattr(body, "region", None),
            procedure=getattr(body, "procedure", None),
        )
        yield _sse("meta", meta_payload)

        skeleton = _skeleton_from_sources(q, citations_payload)
        yield _sse("preview", skeleton)

        explicit_lang = (body.lang or "").strip().lower() if body.lang else None
        lang = explicit_lang if explicit_lang in SUPPORTED_LANGS else detect_lang(q)
        # Context limiter — reduce prompt tokens for complication queries
        chunks = limit_context(chunks, q)

        prompt = _build_single_call_prompt(q, chunks, conversation_context=conv_context, lang=lang, protocol_block=protocol_prompt_block)
        prompt += f"\n\n{_safety_prompt(q)}"
        system = SYSTEM_COMPOSE

        yield _sse("replace", {"message": "Verified answer:"})

        authority_header = _build_authority_header(chunks, badge_payload, aci_result=aci_result)
        if authority_header:
            yield _sse("content", authority_header)

        yield _sse("status", {"phase": "answer", "message": "Generating grounded answer..."})

        t_compose = time.perf_counter()
        streamed_tokens: List[str] = [authority_header] if authority_header else []
        t_first_token: Optional[float] = None

        try:
            async for tok in _llm_stream(prompt, system):
                if t_first_token is None:
                    t_first_token = time.perf_counter()
                streamed_tokens.append(tok)
                yield _sse("content", tok)
                if await request.is_disconnected():
                    return
        except Exception as e:
            logger.error(f"Compose stream failed: {e}")
            yield _sse("error", {"message": "Answer generation failed."})
            return

        t_end = time.perf_counter()
        timing["compose_first_token_ms"] = int((t_first_token - t_compose) * 1000) if t_first_token else 0
        timing["compose_total_ms"] = int((t_end - t_compose) * 1000)

        footer = _build_evidence_footer(chunks)
        if footer:
            streamed_tokens.append(footer)
            yield _sse("content", footer)

        full_answer = "".join(streamed_tokens)

        full_answer = enforce_protocol_completeness(full_answer, q)
        original_joined = "".join(streamed_tokens)
        if full_answer != original_joined:
            protocol_addendum = full_answer[len(original_joined):]
            if protocol_addendum.strip():
                streamed_tokens.append(protocol_addendum)
                yield _sse("content", protocol_addendum)

        citation_valid = validate_citations(full_answer)
        if not citation_valid:
            logger.warning(f"Citation validation failed for query: {q[:60]}. Replacing with refusal.")
            yield _sse("replace", {"message": "Citation validation:"})
            yield _sse("content", REFUSAL_ANSWER)
            full_answer = REFUSAL_ANSWER

        related = _extract_followups(full_answer, q, intent=intent)
        if intent not in ("complication", "complications"):
            proto_followups = protocol_followups(q)
            seen = set(related)
            for pf in proto_followups:
                if pf not in seen and len(related) < 6:
                    related.append(pf)
                    seen.add(pf)
        yield _sse("related", related)

        if conversation_id:
            try:
                await _add_message(conversation_id, "assistant", full_answer)
            except Exception as e:
                logger.warning(f"Failed to store assistant message: {e}")

        total_ms = int((time.perf_counter() - t0) * 1000)
        timing["total_ms"] = total_ms

        # Promote to hot cache if this is a known complication query
        is_hot, _ = is_hot_complication(q)
        if is_hot and full_answer and len(full_answer) > 100:
            set_hot_answer(q, {"answer": full_answer, "citations": citations_payload})

        record_latency("ask_v2", total_ms)
        timing["model"] = COMPOSE_MODEL
        timing["conversation_id"] = conversation_id or None
        timing["caps"] = {
            "compose_max_tokens": COMPOSE_MAX_TOKENS,
            "compose_temp": COMPOSE_TEMPERATURE,
            "chunk_char_cap": CHUNK_CHAR_CAP,
            "max_sources_to_llm": MAX_SOURCES_TO_LLM,
            "memory_max_turns": MEMORY_MAX_TURNS,
            "memory_max_chars": MEMORY_MAX_CHARS,
        }
        yield _sse("done", {"total_ms": total_ms, "timing_ms": timing, "conversation_id": conversation_id or None})
        logger.info(f"Stream timing: {timing}")

        if citation_valid:
            _answer_cache.put(ans_key, {
                "tokens": streamed_tokens,
                "citations": citations_payload,
                "badge": badge_payload,
                "related": related,
                "meta": meta_payload if meta_payload else None,
            })

        try:
            gov_source_ids = [c.get("source_id") or c.get("id") or f"S{i+1}" for i, c in enumerate(chunks)]
            gov_aci = aci_result.score_0_to_10 if aci_result else None
            gov_badge_label = badge_payload.get("badge") if badge_payload else None
            log_governance_event(
                question=q,
                source_ids=gov_source_ids,
                aci_score=gov_aci,
                answer_text=full_answer,
                lang=lang,
                total_ms=total_ms,
                evidence_badge=gov_badge_label,
                citation_valid=citation_valid,
            )
        except Exception as e:
            logger.warning(f"Governance logging error: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v2/conversations/new")
async def new_conversation(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:  # nosec B110
        pass
    user_id = body.get("user_id", "")
    title = body.get("title", "")
    cid = f"c_{int(time.time()*1000)}_{os.urandom(3).hex()}"
    try:
        await _ensure_conversation(cid, user_id=user_id, title=title)
    except Exception as e:
        logger.error(f"Failed to create conversation: {e}")
    return {"conversation_id": cid}


@router.get("/v2/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    try:
        await _ensure_conversation(conversation_id)
        msgs = await _fetch_recent_messages(conversation_id, limit=50)
        return {"conversation_id": conversation_id, "messages": msgs}
    except Exception as e:
        logger.error(f"Failed to fetch messages: {e}")
        return {"conversation_id": conversation_id, "messages": []}


@router.get("/v2/conversations/user/{user_id}")
async def list_user_conversations(user_id: str):
    if _ar._pool is None:
        return {"conversations": []}
    try:
        async with _ar._pool.acquire() as con:
            rows = await con.fetch(
                """SELECT c.id, c.title, c.created_at,
                          (SELECT content FROM messages WHERE conversation_id=c.id AND role='user' ORDER BY created_at ASC LIMIT 1) as first_query
                   FROM conversations c
                   WHERE c.user_id=$1
                   ORDER BY c.created_at DESC LIMIT 50""",
                user_id,
            )
        convs = []
        for r in rows:
            convs.append({
                "id": r["id"],
                "title": r["title"] or r["first_query"] or "Untitled",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
        return {"conversations": convs}
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        return {"conversations": []}


@router.delete("/v2/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    if _ar._pool is None:
        return {"ok": False}
    body = {}
    try:
        body = await request.json()
    except Exception:  # nosec B110
        pass
    user_id = body.get("user_id", "")
    try:
        async with _ar._pool.acquire() as con:
            if user_id:
                result = await con.execute(
                    "DELETE FROM conversations WHERE id=$1 AND user_id=$2",
                    conversation_id, user_id,
                )
            else:
                result = await con.execute(
                    "DELETE FROM conversations WHERE id=$1",
                    conversation_id,
                )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        return {"ok": False}
