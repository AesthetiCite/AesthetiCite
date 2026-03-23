from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.admin_auth import require_admin
from app.db.session import get_db

router = APIRouter(prefix="/admin/analytics", tags=["analytics"])

@router.get("/overview")
def overview(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """
    High-level metrics buyers ask for first.
    """
    q = db.execute(text("SELECT COUNT(*) FROM queries;")).scalar_one()
    u = db.execute(text("SELECT COUNT(*) FROM users WHERE role='clinician';")).scalar_one()
    d = db.execute(text("SELECT COUNT(*) FROM documents WHERE status='active';")).scalar_one()
    r = db.execute(text("SELECT COUNT(*) FROM queries WHERE refusal=true;")).scalar_one()

    refusal_rate = round((r / q) * 100, 2) if q else 0.0

    return {
        "total_queries": q,
        "active_clinicians": u,
        "active_documents": d,
        "refusal_rate_percent": refusal_rate,
    }

@router.get("/usage")
def usage(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Usage per clinician (last 30 days).
    """
    rows = db.execute(text("""
      SELECT
        user_id,
        COUNT(*) AS queries_last_30d
      FROM queries
      WHERE created_at >= now() - interval '30 days'
        AND refusal = false
      GROUP BY user_id
      ORDER BY queries_last_30d DESC;
    """)).mappings().all()

    return {"usage_last_30d": list(rows)}

@router.get("/retention")
def retention(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Weekly retention proxy: clinicians active ≥2 different weeks in last 8 weeks.
    """
    rows = db.execute(text("""
      WITH weekly AS (
        SELECT
          user_id,
          date_trunc('week', created_at) AS wk
        FROM queries
        WHERE created_at >= now() - interval '8 weeks'
          AND refusal = false
        GROUP BY user_id, wk
      )
      SELECT
        user_id,
        COUNT(DISTINCT wk) AS active_weeks
      FROM weekly
      GROUP BY user_id
      HAVING COUNT(DISTINCT wk) >= 2
      ORDER BY active_weeks DESC;
    """)).mappings().all()

    retained = len(rows)
    total = db.execute(text("SELECT COUNT(DISTINCT user_id) FROM queries;")).scalar_one()

    retention_rate = round((retained / total) * 100, 2) if total else 0.0

    return {
        "retained_users": retained,
        "total_users_with_activity": total,
        "retention_rate_percent": retention_rate,
        "detail": list(rows),
    }

@router.get("/export")
def export(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Buyer-ready CSV-style export (JSON arrays, easy to convert).
    """
    queries = db.execute(text("""
      SELECT
        q.id,
        q.user_id,
        q.domain,
        q.mode,
        q.latency_ms,
        q.citations_count,
        q.refusal,
        q.created_at
      FROM queries q
      ORDER BY q.created_at DESC
      LIMIT 5000;
    """)).mappings().all()

    answers = db.execute(text("""
      SELECT
        a.query_id,
        LEFT(a.answer_text, 500) AS answer_preview
      FROM answers a
      LIMIT 5000;
    """)).mappings().all()

    return {
        "queries": list(queries),
        "answers_preview": list(answers),
    }
