"""
AesthetiCite — app/api/operational.py
=======================================
Operational module.
Provides the router and apply_operational_patches imported by main.py,
plus a pdf_storage helper, live evidence retriever patching,
ingest status, evidence test, and full health endpoints.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, APIRouter, Request as _Request, Header as _Header
from pydantic import BaseModel as _BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operational"])


# ─── PDF storage helper ───────────────────────────────────────────────────────

class _LocalPDFStorage:
    """Serves PDFs from the local exports directory via /exports/<filename>."""

    def save(self, local_path: str, filename: str) -> str:
        return f"/exports/{filename}"

    def get_url(self, filename: str) -> str:
        return f"/exports/{filename}"


pdf_storage = _LocalPDFStorage()


# ─── Live evidence retriever ──────────────────────────────────────────────────

def _safe_db_scalar(sql: str, params=None, default=None):
    try:
        import psycopg2
        url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        if not url:
            return default
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default


def _safe_db_query(sql: str, params=None):
    try:
        import psycopg2
        url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        if not url:
            return []
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


class _LiveEvidenceRetriever:
    """
    Queries PostgreSQL for relevant evidence chunks using full-text search.
    Falls back to an empty list if the knowledge base is empty.
    """

    def retrieve(self, request: Any, matched_rule: Dict[str, Any]) -> List[Any]:
        try:
            from app.api.preprocedure_safety_engine import EvidenceItem
        except ImportError:
            return []

        query_terms = " ".join(filter(None, [
            getattr(request, "procedure", ""),
            getattr(request, "region", ""),
            getattr(request, "product_type", ""),
        ])).strip()

        if not query_terms:
            return []

        rows = _safe_db_query(
            """
            SELECT d.title, c.text, d.source_id, d.domain, d.document_type
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.tsv @@ plainto_tsquery('english', %s)
            ORDER BY ts_rank(c.tsv, plainto_tsquery('english', %s)) DESC
            LIMIT 5
            """,
            (query_terms, query_terms),
        )

        if not rows:
            first_term = query_terms.split()[0] if query_terms else "filler"
            rows = _safe_db_query(
                """
                SELECT d.title, c.text, d.source_id, d.domain, d.document_type
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.text ILIKE %s
                LIMIT 5
                """,
                (f"%{first_term}%",),
            )

        items = []
        for i, row in enumerate(rows[:5]):
            title, text, source_id, domain, doc_type = row
            items.append(EvidenceItem(
                source_id=f"LIVE-{i+1}",
                title=(title or "Untitled")[:120],
                note=(text or "")[:250],
                citation_text=(text or "")[:200],
                source_type=doc_type or "peer_reviewed",
                relevance_score=round(0.95 - i * 0.05, 2),
            ))

        return items


# ─── Sentry initialiser ───────────────────────────────────────────────────────

def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1)
        logger.info("[operational] Sentry initialised")
    except ImportError:
        logger.warning("[operational] sentry_sdk not installed — Sentry disabled")
    except Exception as exc:
        logger.warning(f"[operational] Sentry init failed: {exc}")


# ─── Safety engine patching ───────────────────────────────────────────────────

def patch_safety_engines() -> None:
    """Replace DummyEvidenceRetriever with LiveEvidenceRetriever in safety engines."""
    patched = []

    try:
        from app.api import preprocedure_safety_engine as pse
        if "Dummy" in type(pse.evidence_retriever).__name__:
            pse.evidence_retriever = _LiveEvidenceRetriever()
            patched.append("preprocedure_safety_engine")
    except Exception as exc:
        logger.warning(f"[operational] Could not patch preprocedure_safety_engine: {exc}")

    try:
        from app.api import preprocedure_safety_engine_v2 as pse2
        if hasattr(pse2, "evidence_retriever") and "Dummy" in type(pse2.evidence_retriever).__name__:
            pse2.evidence_retriever = _LiveEvidenceRetriever()
            patched.append("preprocedure_safety_engine_v2")
    except Exception as exc:
        logger.warning(f"[operational] Could not patch preprocedure_safety_engine_v2: {exc}")

    if patched:
        os.environ["AESTHETICITE_PGVECTOR_ENABLED"] = "1"
        logger.info(f"[operational] Live retriever patched into: {', '.join(patched)}")
    else:
        logger.info("[operational] Safety engines already patched or unavailable")


# ─── Operational patches (called at startup) ──────────────────────────────────

def apply_operational_patches(app: FastAPI) -> None:
    """Apply runtime patches to the FastAPI app on startup."""
    patch_safety_engines()
    logger.info("[operational] Operational patches applied")


# ─── Health endpoint ──────────────────────────────────────────────────────────

@router.get("/health/full")
def full_health() -> dict:
    db_ok = _safe_db_scalar("SELECT 1") == 1
    doc_count = _safe_db_scalar("SELECT COUNT(*) FROM documents", default=0) or 0
    chunk_count = _safe_db_scalar("SELECT COUNT(*) FROM chunks", default=0) or 0
    pgvector_ok = bool(_safe_db_scalar(
        "SELECT 1 FROM pg_extension WHERE extname='vector'"
    ))

    try:
        from app.api import preprocedure_safety_engine as pse
        retriever_live = "Dummy" not in type(pse.evidence_retriever).__name__
    except Exception:
        retriever_live = False

    checks = {
        "database": db_ok,
        "pgvector": pgvector_ok,
        "knowledge_base": doc_count > 0,
        "evidence_retriever": retriever_live,
        "pdf_storage": os.path.isdir(os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")),
    }

    all_ok = all(checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "operational": all_ok,
        "pdf_storage": "local",
        "checks": checks,
        "summary": {
            "documents": doc_count,
            "chunks": chunk_count,
            "retriever_live": retriever_live,
        },
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ─── Ingestion status ─────────────────────────────────────────────────────────

@router.get("/ingest/status")
def ingest_status() -> dict:
    doc_count = _safe_db_scalar("SELECT COUNT(*) FROM documents", default=0) or 0
    chunk_count = _safe_db_scalar("SELECT COUNT(*) FROM chunks", default=0) or 0
    embedded_count = _safe_db_scalar(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL", default=0
    ) or 0

    rows = _safe_db_query(
        "SELECT created_at FROM documents ORDER BY created_at DESC LIMIT 1"
    )
    last_ingest = rows[0][0].isoformat() if rows and rows[0][0] else None

    ingest_status_label = "idle"
    if doc_count > 0:
        ingest_status_label = "complete"

    return {
        "state": {
            "status": ingest_status_label,
            "papers_inserted": doc_count,
            "chunks_created": chunk_count,
            "chunks_embedded": embedded_count,
            "last_ingest_at": last_ingest,
            "embedding_coverage": (
                round(embedded_count / chunk_count * 100, 1) if chunk_count > 0 else 0
            ),
        },
        "ready": doc_count > 100 and embedded_count > 0,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ─── Fast corpus count (pg_class estimate, no table scan) ─────────────────────

@router.get("/corpus/count")
def corpus_count_fast() -> dict:
    """Returns a near-instant row estimate from pg_class statistics."""
    try:
        import psycopg2
        url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("No DATABASE_URL")
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(
            "SELECT reltuples::bigint FROM pg_class WHERE relname = 'documents'"
        )
        row = cur.fetchone()
        doc_estimate = int(row[0]) if row and row[0] and row[0] > 0 else 0
        cur.execute(
            "SELECT reltuples::bigint FROM pg_class WHERE relname = 'chunks'"
        )
        row2 = cur.fetchone()
        chunk_estimate = int(row2[0]) if row2 and row2[0] and row2[0] > 0 else 0
        conn.close()
        return {
            "papers_inserted": doc_estimate,
            "chunks_created": chunk_estimate,
            "estimate": True,
            "ready": doc_estimate > 100,
        }
    except Exception as exc:
        logger.warning("corpus_count_fast failed: %s", exc)
        return {"papers_inserted": 0, "chunks_created": 0, "estimate": True, "ready": False}


# ─── Evidence retrieval test ──────────────────────────────────────────────────

@router.get("/evidence/test")
def evidence_test(
    procedure: str = "lip filler",
    region: str = "lip",
    product_type: str = "hyaluronic acid filler",
) -> dict:
    t0 = time.time()

    try:
        from app.api import preprocedure_safety_engine as pse

        class _FakeRequest:
            pass

        req = _FakeRequest()
        req.procedure = procedure
        req.region = region
        req.product_type = product_type

        retriever = pse.evidence_retriever
        using_live = "Dummy" not in type(retriever).__name__
        items = retriever.retrieve(req, {})
    except Exception as exc:
        return {
            "using_live_retrieval": False,
            "results_count": 0,
            "results": [],
            "error": str(exc)[:200],
            "elapsed_ms": round((time.time() - t0) * 1000),
        }

    elapsed = round((time.time() - t0) * 1000)
    return {
        "using_live_retrieval": using_live,
        "results_count": len(items),
        "results": [
            {
                "source_id": getattr(i, "source_id", ""),
                "title": getattr(i, "title", ""),
                "relevance_score": getattr(i, "relevance_score", 0),
            }
            for i in items[:5]
        ],
        "query": {"procedure": procedure, "region": region, "product_type": product_type},
        "elapsed_ms": elapsed,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ─── Auth: forgot password / verify email ────────────────────────────────────

class _ForgotPasswordPayload(_BaseModel):
    email: str


class _VerifyEmailPayload(_BaseModel):
    token: str


@router.post("/auth/forgot-password")
async def forgot_password(payload: _ForgotPasswordPayload) -> dict:
    import secrets, hashlib

    email = payload.email.strip().lower()
    if not email or "@" not in email:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Valid email required")

    user_id = _safe_db_scalar(
        "SELECT id FROM users WHERE LOWER(email) = %s", (email,)
    )
    if not user_id:
        return {"status": "ok", "message": "If that email exists, a reset link has been sent."}

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    try:
        import psycopg2
        url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO auth_tokens (user_id, token_hash, token_type, expires_at)
            VALUES (%s, %s, 'password_reset',
                    NOW() + INTERVAL '1 hour')
            ON CONFLICT DO NOTHING
            """,
            (user_id, token_hash),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"[operational] forgot-password DB error: {exc}")
        return {"status": "ok", "message": "If that email exists, a reset link has been sent."}

    base_url = os.environ.get("APP_BASE_URL", "").rstrip("/")
    reset_link = f"{base_url}/reset-password?token={raw_token}" if base_url else None

    if reset_link:
        smtp_host = os.environ.get("SMTP_HOST", "")
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        if smtp_host and smtp_user and smtp_pass:
            try:
                import smtplib
                from email.mime.text import MIMEText
                msg = MIMEText(
                    f"Click to reset your password:\n\n{reset_link}\n\n"
                    f"This link expires in 1 hour.",
                    "plain",
                )
                msg["Subject"] = "AesthetiCite — Password Reset"
                msg["From"] = smtp_user
                msg["To"] = email
                with smtplib.SMTP_SSL(smtp_host, 465) as smtp:
                    smtp.login(smtp_user, smtp_pass)
                    smtp.send_message(msg)
                logger.info("[operational] Password reset email sent")
            except Exception as exc:
                logger.warning(f"[operational] Email send failed: {exc}")

    return {"status": "ok", "message": "If that email exists, a reset link has been sent."}


@router.post("/auth/verify-email")
async def verify_email(payload: _VerifyEmailPayload) -> dict:
    import hashlib
    from fastapi import HTTPException

    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token required")

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    try:
        import psycopg2
        url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, expires_at, used_at
            FROM auth_tokens
            WHERE token_hash = %s AND token_type = 'email_verify'
            """,
            (token_hash,),
        )
        row = cur.fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=400, detail="Invalid or expired token")

        user_id, expires_at, used_at = row
        if used_at:
            conn.close()
            raise HTTPException(status_code=400, detail="Token already used")

        if expires_at and expires_at < datetime.now(timezone.utc):
            conn.close()
            raise HTTPException(status_code=400, detail="Token expired")

        cur.execute(
            "UPDATE auth_tokens SET used_at = NOW() WHERE token_hash = %s", (token_hash,)
        )
        try:
            cur.execute(
                "UPDATE users SET email_verified = TRUE WHERE id = %s", (user_id,)
            )
        except Exception:  # nosec B110
            pass

        conn.commit()
        conn.close()
        return {"status": "ok", "message": "Email verified successfully."}

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[operational] verify-email error: {exc}")
        raise HTTPException(status_code=400, detail="Invalid or expired token")


# ─── Dashboard query logging ──────────────────────────────────────────────────

class _QueryLogPayload(_BaseModel):
    query_text: str
    answer_type: str = "evidence_search"
    aci_score: Optional[float] = None
    response_time_ms: Optional[float] = None
    evidence_level: Optional[str] = None
    domain: Optional[str] = "aesthetic_medicine"


@router.post("/dashboard/log-query")
async def log_query(
    payload: _QueryLogPayload,
    authorization: Optional[str] = _Header(default=None),
) -> dict:
    """
    Thin wrapper that proxies query-log writes to growth_engine's /api/growth/query-logs.
    clinic_id and clinician_id are derived from the JWT token on the Python side.
    """
    import httpx
    import json as _json

    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None

    if authorization and authorization.startswith("Bearer "):
        try:
            import base64
            parts = authorization[7:].split(".")
            if len(parts) == 3:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                claims = _json.loads(base64.urlsafe_b64decode(padded))
                clinician_id = str(claims.get("sub", ""))
                clinic_id = claims.get("clinic_id")
        except Exception:  # nosec B110
            pass

    body = {
        "clinic_id": clinic_id,
        "clinician_id": clinician_id,
        "query_text": payload.query_text,
        "answer_type": payload.answer_type,
        "aci_score": payload.aci_score,
        "response_time_ms": payload.response_time_ms,
        "evidence_level": payload.evidence_level,
        "domain": payload.domain,
    }

    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=3.0) as client:
            r = await client.post("/api/growth/query-logs", json=body)
            return r.json()
    except Exception as exc:
        logger.warning(f"[operational] log-query failed: {exc}")
        return {"status": "deferred"}
