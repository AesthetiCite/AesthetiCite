"""
AesthetiCite Super-Admin Dashboard API
Access restricted to support@aestheticite.com only.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

SUPER_ADMIN_EMAIL = "support@aestheticite.com"


def require_super_admin(user=Depends(get_current_user)):
    if user.get("email") != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Super-admin access required")
    return user


# ─── Overview ────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(
    db: Session = Depends(get_db),
    _user=Depends(require_super_admin),
) -> dict[str, Any]:
    try:
        total_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        total_queries = db.execute(text("SELECT COUNT(*) FROM queries")).scalar() or 0
        total_answers = db.execute(text("SELECT COUNT(*) FROM answers")).scalar() or 0

        try:
            total_case_logs = db.execute(text(
                "SELECT COUNT(*) FROM network_case_logs"
            )).scalar() or 0
        except Exception:
            total_case_logs = 0

        try:
            total_safety_reports = db.execute(text(
                "SELECT COUNT(*) FROM safety_reports"
            )).scalar() or 0
        except Exception:
            total_safety_reports = 0

        active_24h = db.execute(text("""
            SELECT COUNT(DISTINCT uid) FROM (
                SELECT user_id::text AS uid FROM queries
                WHERE created_at > NOW() - INTERVAL '24 hours'
                UNION
                SELECT user_id::text AS uid FROM analytics_events
                WHERE created_at > NOW() - INTERVAL '24 hours' AND user_id IS NOT NULL
            ) t
        """)).scalar() or 0

        active_7d = db.execute(text("""
            SELECT COUNT(DISTINCT uid) FROM (
                SELECT user_id::text AS uid FROM queries
                WHERE created_at > NOW() - INTERVAL '7 days'
                UNION
                SELECT user_id::text AS uid FROM analytics_events
                WHERE created_at > NOW() - INTERVAL '7 days' AND user_id IS NOT NULL
            ) t
        """)).scalar() or 0

        avg_resp = db.execute(text(
            "SELECT ROUND(AVG(latency_ms)::numeric, 0) FROM queries WHERE latency_ms IS NOT NULL"
        )).scalar()

        avg_q_per_user = round(total_queries / total_users, 2) if total_users else 0.0

        top_complications_rows = db.execute(text("""
            SELECT complication_type AS name, COUNT(*) AS count
            FROM network_case_logs
            WHERE complication_type IS NOT NULL AND complication_type <> ''
            GROUP BY complication_type
            ORDER BY count DESC
            LIMIT 10
        """)).mappings().all()
        top_complications = [dict(r) for r in top_complications_rows]

        top_protocols_rows = db.execute(text("""
            SELECT title AS name, COUNT(*) AS count
            FROM saved_protocols
            WHERE title IS NOT NULL
            GROUP BY title
            ORDER BY count DESC
            LIMIT 10
        """)).mappings().all()
        top_protocols = [dict(r) for r in top_protocols_rows]

        recent_rows = db.execute(text("""
            SELECT * FROM (
                SELECT
                    'query' AS type,
                    q.question AS label,
                    u.email,
                    q.created_at,
                    NULL::text AS metadata
                FROM queries q
                LEFT JOIN users u ON u.id::text = q.user_id::text
                ORDER BY q.created_at DESC
                LIMIT 8
            ) a
            UNION ALL
            SELECT * FROM (
                SELECT
                    'signup' AS type,
                    'New user: ' || COALESCE(full_name, email) AS label,
                    email,
                    created_at,
                    NULL::text AS metadata
                FROM users
                ORDER BY created_at DESC
                LIMIT 6
            ) b
            UNION ALL
            SELECT * FROM (
                SELECT
                    'case_log' AS type,
                    COALESCE(complication_type, 'Unknown complication') AS label,
                    NULL AS email,
                    created_at,
                    procedure AS metadata
                FROM network_case_logs
                ORDER BY created_at DESC
                LIMIT 6
            ) c
            ORDER BY created_at DESC
            LIMIT 20
        """)).mappings().all()

        recent_activity = [
            {
                "type": r["type"],
                "label": r["label"],
                "email": r["email"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "metadata": r["metadata"],
            }
            for r in recent_rows
        ]

        return {
            "totalUsers": int(total_users),
            "activeUsers24h": int(active_24h),
            "activeUsers7d": int(active_7d),
            "totalQueries": int(total_queries),
            "totalAnswers": int(total_answers),
            "totalCaseLogs": int(total_case_logs),
            "totalSafetyReports": int(total_safety_reports),
            "avgQueriesPerUser": avg_q_per_user,
            "avgResponseTimeMs": int(avg_resp) if avg_resp else None,
            "topComplications": top_complications,
            "topProtocols": top_protocols,
            "recentActivity": recent_activity,
        }
    except Exception as e:
        logger.error("admin_dashboard overview error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Users ───────────────────────────────────────────────────────────────────

@router.get("/users")
def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(require_super_admin),
) -> dict[str, Any]:
    try:
        offset = (page - 1) * page_size
        total = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0

        rows = db.execute(text("""
            SELECT
                u.id::text,
                u.email,
                u.full_name AS name,
                u.role,
                u.created_at,
                CASE WHEN u.email = :admin_email THEN 'admin' ELSE u.role END AS display_role,
                COALESCE(q.query_count, 0) AS query_count,
                COALESCE(a.answer_count, 0) AS answer_count,
                COALESCE(c.case_log_count, 0) AS case_log_count,
                GREATEST(
                    q.last_query,
                    ae.last_event
                ) AS last_seen_at
            FROM users u
            LEFT JOIN (
                SELECT user_id::text AS uid, COUNT(*) AS query_count, MAX(created_at) AS last_query
                FROM queries GROUP BY user_id
            ) q ON q.uid = u.id::text
            LEFT JOIN (
                SELECT query_id, COUNT(*) AS answer_count FROM answers GROUP BY query_id
            ) a ON FALSE
            LEFT JOIN (
                SELECT created_by::text AS uid, COUNT(*) AS case_log_count
                FROM network_case_logs GROUP BY created_by
            ) c ON c.uid = u.id::text
            LEFT JOIN (
                SELECT user_id::text AS uid, MAX(created_at) AS last_event
                FROM analytics_events WHERE user_id IS NOT NULL GROUP BY user_id
            ) ae ON ae.uid = u.id::text
            ORDER BY u.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"admin_email": SUPER_ADMIN_EMAIL, "limit": page_size, "offset": offset}).mappings().all()

        users = [
            {
                "id": r["id"],
                "email": r["email"],
                "name": r["name"],
                "role": r["display_role"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
                "lastSeenAt": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
                "queryCount": int(r["query_count"]),
                "answerCount": int(r["answer_count"]),
                "caseLogCount": int(r["case_log_count"]),
            }
            for r in rows
        ]

        return {"users": users, "total": int(total), "page": page, "pageSize": page_size}
    except Exception as e:
        logger.error("admin_dashboard users error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Analytics ───────────────────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics(
    db: Session = Depends(get_db),
    _user=Depends(require_super_admin),
) -> dict[str, Any]:
    try:
        daily_queries = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                COUNT(*) AS count
            FROM queries
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY day
        """)).mappings().all()

        daily_users = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                COUNT(DISTINCT user_id) AS count
            FROM queries
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY day
        """)).mappings().all()

        complication_dist = db.execute(text("""
            SELECT complication_type AS name, COUNT(*) AS count
            FROM network_case_logs
            WHERE complication_type IS NOT NULL AND complication_type <> ''
            GROUP BY complication_type
            ORDER BY count DESC
            LIMIT 12
        """)).mappings().all()

        protocol_dist = db.execute(text("""
            SELECT title AS name, COUNT(*) AS count
            FROM saved_protocols
            WHERE title IS NOT NULL AND is_archived = false
            GROUP BY title
            ORDER BY count DESC
            LIMIT 10
        """)).mappings().all()

        domain_dist = db.execute(text("""
            SELECT COALESCE(domain, 'unknown') AS name, COUNT(*) AS count
            FROM queries
            WHERE domain IS NOT NULL
            GROUP BY domain
            ORDER BY count DESC
            LIMIT 10
        """)).mappings().all()

        avg_resp_rows = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                ROUND(AVG(latency_ms)::numeric, 0) AS avg_ms
            FROM queries
            WHERE created_at >= NOW() - INTERVAL '30 days'
              AND latency_ms IS NOT NULL
            GROUP BY DATE(created_at)
            ORDER BY day
        """)).mappings().all()

        return {
            "dailyQueriesLast30d": [
                {"day": str(r["day"]), "count": int(r["count"])} for r in daily_queries
            ],
            "dailyActiveUsersLast30d": [
                {"day": str(r["day"]), "count": int(r["count"])} for r in daily_users
            ],
            "complicationDistribution": [
                {"name": r["name"], "count": int(r["count"])} for r in complication_dist
            ],
            "protocolDistribution": [
                {"name": r["name"], "count": int(r["count"])} for r in protocol_dist
            ],
            "queryLanguageDistribution": [
                {"name": r["name"], "count": int(r["count"])} for r in domain_dist
            ],
            "avgResponseTimeLast30d": [
                {"day": str(r["day"]), "avgMs": int(r["avg_ms"])} for r in avg_resp_rows
            ],
        }
    except Exception as e:
        logger.error("admin_dashboard analytics error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Recent Logins ───────────────────────────────────────────────────────────

@router.get("/recent-logins")
def get_recent_logins(
    db: Session = Depends(get_db),
    _user=Depends(require_super_admin),
) -> dict[str, Any]:
    try:
        rows = db.execute(text("""
            SELECT
                u.email,
                GREATEST(
                    MAX(q.created_at),
                    MAX(ae.created_at)
                ) AS last_activity_at,
                CASE
                    WHEN MAX(q.created_at) > COALESCE(MAX(ae.created_at), '1970-01-01') THEN 'query'
                    WHEN MAX(ae.created_at) IS NOT NULL THEN 'event'
                    ELSE 'signup'
                END AS source
            FROM users u
            LEFT JOIN queries q ON q.user_id::text = u.id::text
            LEFT JOIN analytics_events ae ON ae.user_id = u.id
            GROUP BY u.id, u.email
            HAVING GREATEST(MAX(q.created_at), MAX(ae.created_at)) IS NOT NULL
            ORDER BY last_activity_at DESC
            LIMIT 30
        """)).mappings().all()

        return {
            "recentLogins": [
                {
                    "email": r["email"],
                    "lastActivityAt": r["last_activity_at"].isoformat() if r["last_activity_at"] else None,
                    "source": r["source"],
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("admin_dashboard recent-logins error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
def get_health(
    db: Session = Depends(get_db),
    _user=Depends(require_super_admin),
) -> dict[str, Any]:
    try:
        db_ok = True
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            db_ok = False

        total_docs = db.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0
        active_docs = db.execute(text("SELECT COUNT(*) FROM documents WHERE status='active'")).scalar() or 0
        total_chunks = db.execute(text("SELECT COUNT(*) FROM chunks")).scalar() or 0
        chunked_docs = db.execute(text("SELECT COUNT(DISTINCT document_id) FROM chunks")).scalar() or 0
        docs_without_chunks = db.execute(text("""
            SELECT COUNT(*) FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE c.id IS NULL AND d.status = 'active'
        """)).scalar() or 0

        latest_query_at = db.execute(text("SELECT MAX(created_at) FROM queries")).scalar()
        latest_case_log_at = db.execute(text("SELECT MAX(created_at) FROM network_case_logs")).scalar()

        return {
            "dbConnected": db_ok,
            "totalDocuments": int(total_docs),
            "activeDocuments": int(active_docs),
            "totalChunks": int(total_chunks),
            "chunkedDocuments": int(chunked_docs),
            "documentsWithoutChunks": int(docs_without_chunks),
            "latestQueryAt": latest_query_at.isoformat() if latest_query_at else None,
            "latestCaseLogAt": latest_case_log_at.isoformat() if latest_case_log_at else None,
        }
    except Exception as e:
        logger.error("admin_dashboard health error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
