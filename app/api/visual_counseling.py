"""
Visual Counseling API — No-GPU edition.

Endpoints:
  POST /visual/upload       — store a patient photo
  POST /visual/preview      — return 2D overlay preview as PNG
  POST /ask/visual/stream   — SSE evidence-grounded long-term scenarios + complications
"""
from __future__ import annotations

import io
import json
import logging
import os
import secrets
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from PIL import Image, ImageDraw, ImageEnhance
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.lang import detect_lang, language_label, SUPPORTED_LANGS
from app.core.safety import safety_screen, sanitize_input
from app.core.governance import log_governance_event, rerank_by_domain, detect_intent, validate_citations, REFUSAL_ANSWER
from app.db.session import get_db
from app.rag.retriever import retrieve_db
from app.rag import async_retriever as _ar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["visual-counseling"])

COMPOSE_MODEL = os.getenv("COMPOSE_MODEL", "gpt-4o-mini")
CHUNK_CHAR_CAP = int(os.getenv("CHUNK_CHAR_CAP", "650"))
MAX_SOURCES_TO_LLM = int(os.getenv("MAX_SOURCES_TO_LLM", "10"))
COMPOSE_MAX_TOKENS = int(os.getenv("COMPOSE_MAX_TOKENS", "1100"))
COMPOSE_TEMPERATURE = float(os.getenv("COMPOSE_TEMPERATURE", "0.2"))
MEMORY_MAX_TURNS = int(os.getenv("MEMORY_MAX_TURNS", "6"))
MEMORY_MAX_CHARS = int(os.getenv("MEMORY_MAX_CHARS", "1800"))

_AI_PROXY_URL = settings.OPENAI_BASE_URL.rstrip("/") + "/chat/completions"

VISUALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS visuals (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'photo',
  image_bytes     BYTEA NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_visuals_user_created ON visuals(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visuals_conv_created ON visuals(conversation_id, created_at DESC);
"""


async def _ensure_visuals_table():
    if _ar._pool is None:
        return
    async with _ar._pool.acquire() as con:
        await con.execute(VISUALS_TABLE_SQL)


def _sse(event_type: str, data: Any) -> str:
    return f"data: {json.dumps({'type': event_type, **data} if isinstance(data, dict) else {'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"


def _img_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _make_2d_projection_preview(img: Image.Image, intensity: float) -> Image.Image:
    base = img.convert("RGBA")
    w, h = base.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    cx1 = int(w * 0.38)
    cx2 = int(w * 0.62)
    cy = int(h * 0.42)

    rx = int(w * (0.11 + 0.07 * intensity))
    ry = int(h * (0.09 + 0.06 * intensity))

    alpha = int(55 + 90 * intensity)

    for cx in (cx1, cx2):
        bbox = (cx - rx, cy - ry, cx + rx, cy + ry)
        d.ellipse(bbox, fill=(255, 255, 255, alpha), outline=(255, 255, 255, min(180, alpha + 40)))

    out = Image.alpha_composite(base, overlay)
    out = ImageEnhance.Contrast(out.convert("RGB")).enhance(1.03)
    return out


async def _save_visual(user_id: str, conversation_id: str, kind: str, image_bytes: bytes) -> str:
    vid = "v_" + secrets.token_hex(10)
    if _ar._pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")
    async with _ar._pool.acquire() as con:
        await con.execute(
            "INSERT INTO visuals(id, user_id, conversation_id, kind, image_bytes) VALUES($1,$2,$3,$4,$5)",
            vid, user_id, conversation_id, kind, image_bytes,
        )
    return vid


async def _load_visual(visual_id: str, user_id: str) -> Dict[str, Any]:
    if _ar._pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")
    async with _ar._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT id, kind, image_bytes, conversation_id FROM visuals WHERE id=$1 AND user_id=$2",
            visual_id, user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Visual not found")
    return dict(row)


async def _ensure_conversation(conversation_id: str, user_id: str = "") -> None:
    if _ar._pool is None:
        return
    async with _ar._pool.acquire() as con:
        await con.execute(
            "INSERT INTO conversations(id, user_id, title) VALUES($1, NULLIF($2,''), 'Visual Counseling') ON CONFLICT DO NOTHING",
            conversation_id, user_id,
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
            txt = txt[:700] + "..."
        parts.append(f"{role}: {txt}")
    ctx = "\n".join(parts)
    if len(ctx) > MEMORY_MAX_CHARS:
        ctx = ctx[-MEMORY_MAX_CHARS:]
    return ctx


def _get_headers() -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {settings.OPENAI_API_KEY}"}


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
        "Guideline/Consensus": 1, "Systematic Review": 2, "Randomized Trial": 3,
        "Observational Study": 4, "Case Report/Series": 5, "Narrative Review": 6,
        "Journal Article": 7, "Other": 8,
    }
    return order.get(evidence_type, 9)


def _build_citations_payload(chunks: list) -> list:
    citations = []
    for i, c in enumerate(chunks):
        title = c.get("title", "Unknown")
        year = c.get("year")
        source = c.get("organization_or_journal") or c.get("journal") or "Research Source"
        doc_type = c.get("document_type") or c.get("evidence_level") or ""
        et = _infer_evidence_type(doc_type, source)
        citations.append({
            "id": i + 1,
            "title": title,
            "source": source,
            "year": year or 2024,
            "authors": c.get("authors", "Author et al."),
            "url": c.get("url") or "",
            "document_type": doc_type,
            "evidence_type": et,
            "evidence_rank": _evidence_rank(et),
        })
    return citations


async def _llm_stream(prompt: str, system: str) -> AsyncGenerator[str, None]:
    import httpx
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


def _build_visual_counseling_prompt(question: str, conversation_context: str, chunks: list, lang: str) -> str:
    compact = []
    for c in chunks[:MAX_SOURCES_TO_LLM]:
        compact.append({
            "sid": c.get("sid") or f"S{len(compact)+1}",
            "t": (c.get("title") or "")[:160],
            "y": c.get("year"),
            "id": c.get("doi") or c.get("url"),
            "x": (c.get("text") or "")[:CHUNK_CHAR_CAP],
        })

    lang_name = language_label(lang)

    return f"""You are AesthetiCite (evidence-grounded clinical assistant for aesthetic medicine).

IMPORTANT CLINICAL GOVERNANCE RULES:
- This is patient counseling support. Do NOT promise outcomes.
- Do NOT predict exact appearance at 10 years. Provide scenario-based ranges and drivers of change.
- EVERY factual claim MUST include citations like [S1][S3]. No cite = no claim.
- If evidence is insufficient, say "Evidence insufficient" (in {lang_name}).
- Write the entire answer in {lang_name}.

Write exactly in this structure:

Evidence Strength Summary
- Overall confidence (0-10)
- Highest evidence level found
- Supporting sources used
- Evidence gaps

Counseling Summary (2-3 lines)

Expected Long-Term Trajectories (5-10 years) - scenario-based, not deterministic
- Scenario 1 (drivers + what may change) [S#]
- Scenario 2 ... [S#]

Complications & Revision Considerations
- Early complications (examples only if supported) [S#]
- Late complications (capsular contracture, rupture, reoperation/revision considerations) [S#]

Safety / Informed Consent Notes
- What must be explicitly discussed (if supported) [S#]

Limitations / Uncertainty

Suggested Follow-up Questions
- Q1
- Q2
- Q3

User question: {question}

Conversation context:
{conversation_context}

Sources (JSON):
{json.dumps(compact, ensure_ascii=False)}
""".strip()


@router.on_event("startup")
async def _visual_startup():
    try:
        await _ensure_visuals_table()
        logger.info("Visuals table ensured")
    except Exception as e:
        logger.warning(f"Could not create visuals table: {e}")


@router.post("/visual/upload")
async def visual_upload(
    conversation_id: str = Form(...),
    kind: str = Form("photo"),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    if _ar._pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    async with _ar._pool.acquire() as con:
        own = await con.fetchval(
            "SELECT 1 FROM conversations WHERE id=$1 AND user_id=$2",
            conversation_id, user["id"],
        )
        if not own:
            raise HTTPException(status_code=404, detail="Conversation not found")

    data = await file.read()
    if len(data) > 7_000_000:
        raise HTTPException(status_code=400, detail="Image too large (max 7MB)")

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    vid = await _save_visual(user["id"], conversation_id, kind, data)
    return {"ok": True, "visual_id": vid, "kind": kind}


class PreviewBody(BaseModel):
    visual_id: str
    intensity_0_1: float = 0.5


@router.post("/visual/preview")
async def visual_preview(body: PreviewBody, user: dict = Depends(get_current_user)):
    v = await _load_visual(body.visual_id, user["id"])
    intensity = max(0.0, min(1.0, body.intensity_0_1))

    img = Image.open(io.BytesIO(v["image_bytes"])).convert("RGB")
    max_w = 900
    if img.size[0] > max_w:
        ratio = max_w / img.size[0]
        img = img.resize((max_w, int(img.size[1] * ratio)))

    out = _make_2d_projection_preview(img, intensity)
    png = _img_to_png_bytes(out)

    return Response(content=png, media_type="image/png")


class AskVisualBody(BaseModel):
    q: str
    conversation_id: str
    visual_id: Optional[str] = None
    k: int = 14
    lang: Optional[str] = None


@router.post("/ask/visual/stream")
async def ask_visual_stream(body: AskVisualBody, request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    q = sanitize_input(body.q or "")
    if not q:
        return StreamingResponse(iter([_sse("error", {"message": "Empty query"})]), media_type="text/event-stream")

    safety = safety_screen(q)
    if not safety.allowed:
        async def refuse():
            yield _sse("error", {"message": safety.refusal_reason or "Request refused."})
        return StreamingResponse(refuse(), media_type="text/event-stream")

    cid = body.conversation_id.strip()
    if not cid:
        raise HTTPException(status_code=400, detail="conversation_id required")

    if _ar._pool is not None:
        async with _ar._pool.acquire() as con:
            own = await con.fetchval("SELECT 1 FROM conversations WHERE id=$1 AND user_id=$2", cid, user["id"])
            if not own:
                raise HTTPException(status_code=404, detail="Conversation not found")

    async def gen() -> AsyncGenerator[str, None]:
        import asyncio
        t0 = time.perf_counter()
        yield _sse("status", {"phase": "retrieval", "message": "Searching evidence..."})
        await _add_message(cid, "user", q)

        recent = await _fetch_recent_messages(cid, limit=MEMORY_MAX_TURNS)
        ctx = _compress_context(recent)

        lang = (body.lang or "").strip().lower() if body.lang else None
        if lang not in SUPPORTED_LANGS:
            lang = detect_lang(q)

        t_r0 = time.perf_counter()
        if _ar._pool is not None:
            chunks = await _ar.retrieve_db_async(question=q, domain="aesthetic_medicine", k=body.k)
        else:
            chunks = await asyncio.to_thread(retrieve_db, db=db, question=q, domain="aesthetic_medicine", k=body.k)
        t_r1 = time.perf_counter()

        intent = detect_intent(q)
        chunks = rerank_by_domain(chunks, intent)

        enriched = []
        for s in chunks:
            s2 = dict(s)
            et = _infer_evidence_type(s2.get("document_type"), s2.get("organization_or_journal") or s2.get("journal"))
            s2["evidence_type"] = et
            s2["evidence_rank"] = _evidence_rank(et)
            enriched.append(s2)

        enriched.sort(key=lambda s: (int(s.get("evidence_rank") or 9), -int(s.get("year") or 0)))

        citations_payload = _build_citations_payload(enriched)

        aci_score = None
        try:
            from app.engine.veridoc import compute_aci
            aci_sources = [{"source_type": c.get("document_type") or "other", "year": c.get("year"), "id": c.get("source_id") or c.get("id")} for c in enriched]
            aci_score = compute_aci(aci_sources)
        except Exception:  # nosec B110
            pass

        yield _sse("sources", {"count": len(enriched), "ms": int((t_r1 - t_r0) * 1000)})
        yield _sse("citations", {"citations": citations_payload, "aci_score": aci_score})

        if await request.is_disconnected():
            return

        if not enriched or len(enriched) < 2:
            yield _sse("error", {"message": "Insufficient evidence to provide counseling with citations."})
            return

        prompt = _build_visual_counseling_prompt(q, ctx, enriched, lang)
        yield _sse("status", {"phase": "answer", "message": "Generating grounded counseling note..."})
        yield _sse("replace", {"message": "Visual counseling response:"})

        t_c0 = time.perf_counter()
        buf: List[str] = []

        try:
            async for tok in _llm_stream(prompt, "Be concise. Follow citation rules exactly. No invented facts. This is visual counseling support."):
                buf.append(tok)
                yield _sse("content", tok)
                if await request.is_disconnected():
                    return
        except Exception as e:
            logger.error(f"Visual counseling LLM stream failed: {e}")
            yield _sse("error", {"message": "Answer generation failed."})
            return

        answer_text = "".join(buf).strip()

        citation_valid = validate_citations(answer_text)
        if not citation_valid:
            yield _sse("replace", {"message": "Citation validation:"})
            yield _sse("content", REFUSAL_ANSWER)
            answer_text = REFUSAL_ANSWER

        yield _sse("related", [])

        try:
            await _add_message(cid, "assistant", answer_text)
        except Exception as e:
            logger.warning(f"Failed to store visual counseling message: {e}")

        total_ms = int((time.perf_counter() - t0) * 1000)
        yield _sse("done", {"total_ms": total_ms, "conversation_id": cid})

        try:
            gov_source_ids = [c.get("source_id") or c.get("id") or f"S{i+1}" for i, c in enumerate(enriched)]
            gov_aci = aci_score.get("overall_confidence_0_10") if isinstance(aci_score, dict) else aci_score
            log_governance_event(
                question=f"[VISUAL] {q}",
                source_ids=gov_source_ids,
                aci_score=gov_aci,
                answer_text=answer_text,
                lang=lang,
                total_ms=total_ms,
                evidence_badge=None,
                citation_valid=citation_valid,
            )
        except Exception as e:
            logger.warning(f"Governance log error: {e}")

    return StreamingResponse(gen(), media_type="text/event-stream")
