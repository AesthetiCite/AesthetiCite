from __future__ import annotations
import time
import uuid
import json
from typing import Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.schemas.ask import AskRequest, AskResponse
from app.core.config import settings
from app.core.safety import safety_screen
from app.core.limiter import limiter
from app.db.session import get_db
from app.rag.retriever import retrieve_db
from app.rag.citations import to_citations
from app.rag.answer import build_answer
from app.rag.llm_answer import synthesize_answer
from app.rag.quality_guard import safe_finalize

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
def ask(payload: AskRequest, request: Request, db: Session = Depends(get_db)) -> AskResponse:
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

    retrieved = retrieve_db(db=db, question=payload.question, domain=payload.domain, k=8)
    citations = to_citations(retrieved)

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

    # High-quality LLM synthesis (OpenEvidence-like), with strict citation enforcement
    related_questions = []
    llm_refused = False
    try:
        answer_llm = synthesize_answer(payload.question, payload.domain, payload.mode, retrieved)
        answer = safe_finalize(answer_llm, sources=retrieved)
        if answer.startswith("REFUSAL:"):
            llm_refused = True
    except Exception as e:
        # LLM failed (network/timeout/config) - fallback to template
        answer, related_questions = build_answer(
            question=payload.question,
            mode=payload.mode,
            domain=payload.domain,
            retrieved=retrieved,
            escalation_note=safety.escalation_note,
        )
    
    # If LLM explicitly refused due to insufficient evidence, return refusal
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
    )
