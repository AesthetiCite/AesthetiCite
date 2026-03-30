from __future__ import annotations
import time
import uuid
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.schemas.ask import AskRequest, AskResponse
from app.core.config import settings
from app.core.safety import safety_screen
from app.core.limiter import limiter
from app.db.session import get_db
import logging as _logging
from app.rag.async_retriever import retrieve_db_async
from app.rag.retriever import retrieve_db as retrieve_db_sync
from app.rag.citations import to_citations
from app.rag.answer import build_answer
_logger = _logging.getLogger(__name__)
from app.rag.llm_answer import synthesize_answer
from app.rag.quality_guard import safe_finalize
from app.engine.speed_optimizer import get_hot_answer, set_hot_answer

router = APIRouter(prefix="", tags=["ask"])

def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[dict]:
    """Get current user if auth is required, otherwise return None."""
    if not settings.REQUIRE_AUTH_FOR_ASK:
        return None
    from app.core.auth import get_current_user
    from fastapi.security import HTTPBearer
    bearer = HTTPBearer(auto_error=False)
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")
    token = auth_header[7:]
    from app.core.auth import decode_token
    user_id = decode_token(token)
    row = db.execute(text("""
        SELECT id::text, email, is_active, role, created_at
        FROM users
        WHERE id = :id
    """), {"id": user_id}).mappings().first()
    if not row or not row["is_active"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return dict(row)

@router.post("/ask", response_model=AskResponse)
@limiter.limit(settings.RATE_LIMIT_ASK)
async def ask(payload: AskRequest, request: Request, db: Session = Depends(get_db)) -> AskResponse:
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    user = get_optional_user(request, db) if settings.REQUIRE_AUTH_FOR_ASK else None
    user_id = user["id"] if user else (request.client.host if request.client else None)

    safety = safety_screen(payload.question)
    if not safety.allowed:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        db.execute(text("""
          INSERT INTO queries (id, user_id, question, domain, mode, latency_ms, citations_count, refusal, refusal_reason)
          VALUES (:id, :user_id, :q, :domain, :mode, :lat, 0, true, :reason);
        """), {
            "id": request_id,
            "user_id": user_id,
            "q": payload.question,
            "domain": payload.domain,
            "mode": payload.mode,
            "lat": latency_ms,
            "reason": safety.refusal_reason or "Request refused by safety policy.",
        })
        db.commit()
        return AskResponse(
            answer="",
            citations=[],
            refusal=True,
            refusal_reason=safety.refusal_reason or "Request refused by safety policy.",
            request_id=request_id,
            latency_ms=latency_ms,
        )

    hot = get_hot_answer(payload.question)
    if hot:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return AskResponse(
            answer=hot.get("answer", ""),
            citations=hot.get("citations", []),
            refusal=False,
            request_id=request_id,
            latency_ms=latency_ms,
            evidence=hot.get("evidence", []),
        )

    try:
        retrieved = await retrieve_db_async(question=payload.question, domain=payload.domain, k=8)
    except Exception as _e:
        _logger.warning(f"Async retrieval failed ({_e}), falling back to sync retriever")
        retrieved = retrieve_db_sync(db=db, question=payload.question, domain=payload.domain, k=8)
    citations = to_citations(retrieved)

    max_src = min(len(retrieved), settings.MAX_SOURCES_IN_PROMPT)
    evidence_for_response = [
        {
            "id": f"S{i + 1}",
            "source_id": r.get("source_id", ""),
            "title": r.get("title") or "Unknown source",
            "year": r.get("year"),
            "organization_or_journal": r.get("organization_or_journal"),
            "page_or_section": r.get("page_or_section"),
            "evidence_level": r.get("evidence_level"),
            "snippet": (r.get("text") or "")[:240] or None,
        }
        for i, r in enumerate(retrieved[:max_src])
    ]

    if len(citations) < settings.MIN_CITATIONS_REQUIRED:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        db.execute(text("""
          INSERT INTO queries (id, user_id, question, domain, mode, latency_ms, citations_count, refusal, refusal_reason)
          VALUES (:id, :user_id, :q, :domain, :mode, :lat, 0, true, :reason);
        """), {
            "id": request_id,
            "user_id": user_id,
            "q": payload.question,
            "domain": payload.domain,
            "mode": payload.mode,
            "lat": latency_ms,
            "reason": "Insufficient evidence retrieved to answer with citations.",
        })
        db.commit()
        return AskResponse(
            answer="",
            citations=[],
            refusal=True,
            refusal_reason="Insufficient evidence retrieved to answer with citations.",
            request_id=request_id,
            latency_ms=latency_ms,
        )

    related_questions = []
    llm_refused = False
    try:
        loop = asyncio.get_event_loop()
        answer_llm = await loop.run_in_executor(
            None, synthesize_answer, payload.question, payload.domain, payload.mode, retrieved
        )
        answer = safe_finalize(answer_llm, sources=retrieved)
        if answer.startswith("REFUSAL:"):
            llm_refused = True
    except Exception as e:
        answer, related_questions = build_answer(
            question=payload.question,
            mode=payload.mode,
            domain=payload.domain,
            retrieved=retrieved,
            escalation_note=safety.escalation_note,
        )

    if llm_refused:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        db.execute(text("""
          INSERT INTO queries (id, user_id, question, domain, mode, latency_ms, citations_count, refusal, refusal_reason)
          VALUES (:id, :user_id, :q, :domain, :mode, :lat, 0, true, :reason);
        """), {
            "id": request_id,
            "user_id": user_id,
            "q": payload.question,
            "domain": payload.domain,
            "mode": payload.mode,
            "lat": latency_ms,
            "reason": "Insufficient evidence to provide a properly cited answer.",
        })
        db.commit()
        return AskResponse(
            answer="",
            citations=[],
            refusal=True,
            refusal_reason="Insufficient evidence to provide a properly cited answer.",
            request_id=request_id,
            latency_ms=latency_ms,
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    try:
        set_hot_answer(payload.question, {
            "answer": answer,
            "citations": [c.model_dump() for c in citations],
            "evidence": evidence_for_response,
        })
    except Exception:
        pass

    db.execute(text("""
      INSERT INTO queries (id, user_id, question, domain, mode, latency_ms, citations_count, refusal, refusal_reason)
      VALUES (:id, :user_id, :q, :domain, :mode, :lat, :cc, false, NULL);
    """), {
        "id": request_id,
        "user_id": user_id,
        "q": payload.question,
        "domain": payload.domain,
        "mode": payload.mode,
        "lat": latency_ms,
        "cc": len(citations),
    })
    db.execute(text("""
      INSERT INTO answers (query_id, answer_text, citations_json)
      VALUES (:qid, :ans, :cjson);
    """), {
        "qid": request_id,
        "ans": answer,
        "cjson": json.dumps([c.model_dump() for c in citations]),
    })
    db.commit()

    return AskResponse(
        answer=answer,
        citations=citations,
        related_questions=related_questions,
        refusal=False,
        request_id=request_id,
        latency_ms=latency_ms,
        evidence=evidence_for_response,
    )
