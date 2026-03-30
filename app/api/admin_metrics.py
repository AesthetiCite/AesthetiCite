"""
AesthetiCite Admin Metrics API

Provides comprehensive metrics dashboard data for admin users.
Protected by ADMIN_API_KEY header authentication.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import text
from app.db import get_db


router = APIRouter(prefix="/admin/metrics", tags=["admin-metrics"])


class TimeWindow(BaseModel):
    fromISO: str
    toISO: str


class ConnectionMetrics(BaseModel):
    active_last_5m: int = 0
    active_last_60m: int = 0
    unique_ip_last_24h: int = 0
    unique_users_last_24h: int = 0


class UsageMetrics(BaseModel):
    queries_last_24h: int = 0
    queries_last_7d: int = 0
    tool_calls_last_24h: int = 0
    refusals_last_24h: int = 0
    refusal_rate_last_24h: float = 0.0
    errors_last_24h: int = 0
    error_rate_last_24h: float = 0.0


class PerformanceMetrics(BaseModel):
    latency_ms_p50_last_24h: float = 0.0
    latency_ms_p95_last_24h: float = 0.0
    retrieval_ms_p50_last_24h: float = 0.0
    retrieval_ms_p95_last_24h: float = 0.0
    llm_ms_p50_last_24h: float = 0.0
    llm_ms_p95_last_24h: float = 0.0


class CostMetrics(BaseModel):
    llm_usd_last_24h: float = 0.0
    llm_usd_last_7d: float = 0.0


class QueryCount(BaseModel):
    query: str
    count: int


class ReasonCount(BaseModel):
    reason: str
    count: int


class ToolCount(BaseModel):
    tool: str
    count: int


class ContentMetrics(BaseModel):
    top_queries_last_24h: List[QueryCount] = []
    top_refusal_reasons_last_7d: List[ReasonCount] = []
    top_tools_last_7d: List[ToolCount] = []


class SafetyMetrics(BaseModel):
    citation_mismatch_last_24h: int = 0
    citation_mismatch_rate_last_24h: float = 0.0
    dosing_requests_last_24h: int = 0
    interaction_checks_last_24h: int = 0


class AdminMetricsResponse(BaseModel):
    window: TimeWindow
    connections: ConnectionMetrics
    usage: UsageMetrics
    performance: PerformanceMetrics
    cost: CostMetrics
    content: ContentMetrics
    safety: SafetyMetrics


def verify_admin_key(
    x_admin_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db=Depends(get_db),
):
    """Verify admin access — accepts either the ADMIN_API_KEY header or a valid JWT with admin/super_admin role."""
    # ── Path 1: API key (legacy) ─────────────────────────────────
    expected_key = os.getenv("ADMIN_API_KEY")
    if x_admin_api_key and expected_key and x_admin_api_key == expected_key:
        return True

    # ── Path 2: JWT Bearer token with admin/super_admin role ─────
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            from app.core.auth import decode_token
            user_id = decode_token(token)
            row = db.execute(
                text("SELECT role FROM users WHERE id = :id AND is_active = true"),
                {"id": user_id},
            ).mappings().first()
            if row and row["role"] in ("admin", "super_admin"):
                return True
        except Exception:
            pass

    raise HTTPException(
        status_code=403,
        detail="Access denied — admin role or valid API key required.",
    )


@router.get("", response_model=AdminMetricsResponse)
def get_admin_metrics(
    db=Depends(get_db),
    _auth=Depends(verify_admin_key)
):
    """Get comprehensive admin metrics dashboard data."""
    now = datetime.utcnow()
    h24_ago = now - timedelta(hours=24)
    d7_ago = now - timedelta(days=7)
    m5_ago = now - timedelta(minutes=5)
    m60_ago = now - timedelta(minutes=60)
    
    # Initialize metrics
    connections = ConnectionMetrics()
    usage = UsageMetrics()
    performance = PerformanceMetrics()
    cost = CostMetrics()
    content = ContentMetrics()
    safety = SafetyMetrics()
    
    try:
        # Query counts
        q24h = db.execute(
            text("SELECT COUNT(*) FROM queries WHERE created_at >= :since"),
            {"since": h24_ago}
        ).scalar() or 0
        
        q7d = db.execute(
            text("SELECT COUNT(*) FROM queries WHERE created_at >= :since"),
            {"since": d7_ago}
        ).scalar() or 0
        
        usage.queries_last_24h = q24h
        usage.queries_last_7d = q7d
        
        # Unique users (24h)
        unique_users = db.execute(
            text("SELECT COUNT(DISTINCT user_id) FROM queries WHERE created_at >= :since AND user_id IS NOT NULL"),
            {"since": h24_ago}
        ).scalar() or 0
        connections.unique_users_last_24h = unique_users
        
        # Top queries (24h)
        top_queries_result = db.execute(
            text("""
                SELECT query_text, COUNT(*) as cnt 
                FROM queries 
                WHERE created_at >= :since 
                GROUP BY query_text 
                ORDER BY cnt DESC 
                LIMIT 10
            """),
            {"since": h24_ago}
        ).fetchall()
        content.top_queries_last_24h = [
            QueryCount(query=row[0][:100], count=row[1]) 
            for row in top_queries_result
        ]
        
        # Answers/refusals (24h)
        answers_24h = db.execute(
            text("SELECT COUNT(*) FROM answers WHERE created_at >= :since"),
            {"since": h24_ago}
        ).scalar() or 0
        
        refusals_24h = db.execute(
            text("SELECT COUNT(*) FROM answers WHERE created_at >= :since AND status = 'refuse'"),
            {"since": h24_ago}
        ).scalar() or 0
        
        usage.refusals_last_24h = refusals_24h
        usage.refusal_rate_last_24h = refusals_24h / max(answers_24h, 1)
        
        errors_24h = db.execute(
            text("SELECT COUNT(*) FROM answers WHERE created_at >= :since AND status = 'error'"),
            {"since": h24_ago}
        ).scalar() or 0
        
        usage.errors_last_24h = errors_24h
        usage.error_rate_last_24h = errors_24h / max(answers_24h, 1)
        
    except Exception as e:  # nosec B110
        # Tables might not exist yet, return defaults
        pass
    
    return AdminMetricsResponse(
        window=TimeWindow(
            fromISO=h24_ago.isoformat() + "Z",
            toISO=now.isoformat() + "Z"
        ),
        connections=connections,
        usage=usage,
        performance=performance,
        cost=cost,
        content=content,
        safety=safety
    )


@router.get("/summary")
def get_metrics_summary(
    db=Depends(get_db),
    _auth=Depends(verify_admin_key)
):
    """Get a quick summary of key metrics."""
    now = datetime.utcnow()
    h24_ago = now - timedelta(hours=24)
    
    try:
        queries_24h = db.execute(
            text("SELECT COUNT(*) FROM queries WHERE created_at >= :since"),
            {"since": h24_ago}
        ).scalar() or 0
        
        users_24h = db.execute(
            text("SELECT COUNT(DISTINCT user_id) FROM queries WHERE created_at >= :since AND user_id IS NOT NULL"),
            {"since": h24_ago}
        ).scalar() or 0
        
        total_docs = db.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0
        total_chunks = db.execute(text("SELECT COUNT(*) FROM chunks")).scalar() or 0
        
        return {
            "queries_24h": queries_24h,
            "users_24h": users_24h,
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "timestamp": now.isoformat() + "Z"
        }
    except Exception as e:
        return {
            "queries_24h": 0,
            "users_24h": 0,
            "total_documents": 0,
            "total_chunks": 0,
            "timestamp": now.isoformat() + "Z",
            "error": str(e)
        }
