"""
app/api/session_tracker.py
==========================
Session tracking for the super-admin support@aestheticite.com.

Tracks:
  - Login events (session start)
  - Heartbeats (active presence, every 60s from frontend)
  - Logout / token expiry (session end)
  - Per-session duration and query count
  - Per-user aggregated stats

Tables created on startup:
  user_sessions         — one row per session
  session_heartbeats    — one row per 60s heartbeat

Admin endpoints (require role=admin AND email=support@aestheticite.com):
  POST /admin/sessions/start              — called on login
  POST /admin/sessions/heartbeat          — called every 60s
  POST /admin/sessions/end                — called on logout
  GET  /admin/sessions/user/{email}       — full session history for a user
  GET  /admin/sessions/user/{email}/stats — aggregated stats

INTEGRATION:
  1. In main.py, add:
       from app.api.session_tracker import router as session_tracker_router
       app.include_router(session_tracker_router)

  2. In server/routes.ts, add:
       app.post("/api/admin/sessions/start",           (req,res) => proxyToFastAPI(req,res,"/admin/sessions/start"));
       app.post("/api/admin/sessions/heartbeat",        (req,res) => proxyToFastAPI(req,res,"/admin/sessions/heartbeat"));
       app.post("/api/admin/sessions/end",              (req,res) => proxyToFastAPI(req,res,"/admin/sessions/end"));
       app.get ("/api/admin/sessions/user/:email",      (req,res) => proxyToFastAPI(req,res,`/admin/sessions/user/${req.params.email}`));
       app.get ("/api/admin/sessions/user/:email/stats",(req,res) => proxyToFastAPI(req,res,`/admin/sessions/user/${req.params.email}/stats`));

  3. In app/api/auth.py login endpoint, add after token creation:
       from app.api.session_tracker import record_session_start
       record_session_start(user_id=str(row["id"]), email=row["email"], session_token=token)

  4. Add the frontend SessionTracker component to ask.tsx (see session-tracker-hook.ts).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user, require_admin_user

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SUPER_ADMIN_EMAIL = "support@aestheticite.com"

router = APIRouter(prefix="/admin/sessions", tags=["Session Tracker"])

_pool: Optional[asyncpg.Pool] = None
_executor = ThreadPoolExecutor(max_workers=2)


# ─────────────────────────────────────────────────────────────────
# Pool
# ─────────────────────────────────────────────────────────────────

async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = _executor.submit(asyncio.run, coro)
            return future.result(timeout=10)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"[SessionTracker] async run error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# Migration — called from startup
# ─────────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id          TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    email               TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat_at   TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    duration_seconds    INTEGER,
    query_count         INTEGER NOT NULL DEFAULT 0,
    ip_address          TEXT,
    user_agent          TEXT,
    end_reason          TEXT   -- 'logout' | 'expired' | 'heartbeat_timeout'
);
CREATE INDEX IF NOT EXISTS idx_us_email     ON user_sessions(email);
CREATE INDEX IF NOT EXISTS idx_us_user_id   ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_us_started   ON user_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_us_active    ON user_sessions(ended_at) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS session_heartbeats (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES user_sessions(session_id) ON DELETE CASCADE,
    beat_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    page_path       TEXT,
    query_count_inc INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sh_session   ON session_heartbeats(session_id);
CREATE INDEX IF NOT EXISTS idx_sh_beat_at   ON session_heartbeats(beat_at DESC);
"""


async def create_tables_async() -> None:
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(CREATE_TABLES_SQL)
    logger.info("[SessionTracker] Tables ready.")


def create_tables_sync() -> None:
    """Call from main.py @app.on_event('startup')"""
    _run(create_tables_async())


# ─────────────────────────────────────────────────────────────────
# Auth guard — super admin only
# ─────────────────────────────────────────────────────────────────

def require_super_admin(user=Depends(require_admin_user)):
    if user.get("email") != SUPER_ADMIN_EMAIL:
        raise HTTPException(
            status_code=403,
            detail=f"This endpoint is restricted to {SUPER_ADMIN_EMAIL}",
        )
    return user


# ─────────────────────────────────────────────────────────────────
# Internal helpers (called from auth.py login endpoint)
# ─────────────────────────────────────────────────────────────────

async def _start_session_async(
    user_id: str,
    email: str,
    session_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    pool = await _get_pool()
    async with pool.acquire() as con:
        # Close any orphaned open sessions for this user first
        await con.execute(
            """
            UPDATE user_sessions
            SET ended_at = NOW(),
                end_reason = 'new_login',
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INT
            WHERE email = $1 AND ended_at IS NULL
            """,
            email,
        )
        await con.execute(
            """
            INSERT INTO user_sessions
                (session_id, user_id, email, ip_address, user_agent)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (session_id) DO NOTHING
            """,
            session_id, user_id, email, ip_address, user_agent,
        )
    logger.info(f"[SessionTracker] Session started: {email} ({session_id[:8]}...)")


def record_session_start(
    user_id: str,
    email: str,
    session_token: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """
    Call this from the login endpoint after issuing a JWT.
    Uses a hash of the token as the session_id (no raw token stored).
    Returns the session_id.
    """
    session_id = hashlib.sha256(session_token.encode()).hexdigest()[:32]
    _run(_start_session_async(user_id, email, session_id, ip_address, user_agent))
    return session_id


# ─────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────

class HeartbeatPayload(BaseModel):
    page_path: Optional[str] = None
    query_count_inc: int = 0


class EndSessionPayload(BaseModel):
    end_reason: str = "logout"


# ─────────────────────────────────────────────────────────────────
# Endpoints called by the frontend (authenticated user, not admin)
# ─────────────────────────────────────────────────────────────────

@router.post("/start")
async def session_start(
    request_data: Dict[str, Any] = {},
    user=Depends(get_current_user),
):
    """
    Called on page load / login to open a session.
    Frontend sends this once after authentication.
    """
    from fastapi import Request
    session_id = hashlib.sha256(
        f"{user['id']}{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:32]

    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """
            UPDATE user_sessions
            SET ended_at = NOW(), end_reason = 'new_login',
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INT
            WHERE email = $1 AND ended_at IS NULL
            """,
            user["email"],
        )
        await con.execute(
            """
            INSERT INTO user_sessions (session_id, user_id, email)
            VALUES ($1, $2, $3)
            ON CONFLICT (session_id) DO NOTHING
            """,
            session_id, str(user["id"]), user["email"],
        )
    return {"session_id": session_id, "ok": True}


@router.post("/heartbeat")
async def heartbeat(
    payload: HeartbeatPayload,
    user=Depends(get_current_user),
):
    """
    Called every 60 seconds by the frontend while the page is open.
    Updates last_heartbeat_at and increments query count.
    """
    pool = await _get_pool()
    async with pool.acquire() as con:
        # Find the open session for this user
        row = await con.fetchrow(
            "SELECT session_id FROM user_sessions WHERE email=$1 AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            user["email"],
        )
        if not row:
            # No open session — create one silently
            session_id = hashlib.sha256(
                f"{user['id']}{datetime.now(timezone.utc).isoformat()}".encode()
            ).hexdigest()[:32]
            await con.execute(
                "INSERT INTO user_sessions (session_id, user_id, email) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                session_id, str(user["id"]), user["email"],
            )
        else:
            session_id = row["session_id"]

        await con.execute(
            """
            UPDATE user_sessions
            SET last_heartbeat_at = NOW(),
                query_count = query_count + $2
            WHERE session_id = $1
            """,
            session_id, payload.query_count_inc,
        )
        await con.execute(
            """
            INSERT INTO session_heartbeats (session_id, page_path, query_count_inc)
            VALUES ($1, $2, $3)
            """,
            session_id, payload.page_path, payload.query_count_inc,
        )
    return {"ok": True}


@router.post("/end")
async def session_end(
    payload: EndSessionPayload,
    user=Depends(get_current_user),
):
    """Called on logout or tab close."""
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """
            UPDATE user_sessions
            SET ended_at = NOW(),
                end_reason = $2,
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INT
            WHERE email = $1 AND ended_at IS NULL
            """,
            user["email"], payload.end_reason,
        )
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# Admin endpoints — super admin only
# ─────────────────────────────────────────────────────────────────

@router.get("/user/{email}")
async def get_user_sessions(
    email: str,
    limit: int = 50,
    _=Depends(require_super_admin),
):
    """
    Full session history for a specific user.
    Accessible only to support@aestheticite.com.
    """
    pool = await _get_pool()
    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT
                session_id,
                email,
                started_at,
                last_heartbeat_at,
                ended_at,
                duration_seconds,
                query_count,
                end_reason,
                CASE
                    WHEN ended_at IS NULL
                         AND last_heartbeat_at > NOW() - INTERVAL '5 minutes'
                    THEN TRUE
                    ELSE FALSE
                END AS is_active
            FROM user_sessions
            WHERE email = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            email, limit,
        )

    sessions = []
    for r in rows:
        d = dict(r)
        # Compute effective duration for active sessions
        if d["is_active"] and d["duration_seconds"] is None:
            started = d["started_at"]
            if started:
                d["duration_seconds"] = int(
                    (datetime.now(timezone.utc) - started).total_seconds()
                )
        # Format timestamps to ISO strings
        for key in ("started_at", "last_heartbeat_at", "ended_at"):
            if d[key]:
                d[key] = d[key].isoformat()
        sessions.append(d)

    return {"email": email, "sessions": sessions, "total": len(sessions)}


@router.get("/user/{email}/stats")
async def get_user_stats(
    email: str,
    _=Depends(require_super_admin),
):
    """
    Aggregated stats for a specific user.
    Returns connection frequency, average session length, total time, etc.
    """
    pool = await _get_pool()
    async with pool.acquire() as con:
        agg = await con.fetchrow(
            """
            SELECT
                COUNT(*)                                            AS total_sessions,
                COUNT(*) FILTER (WHERE ended_at IS NULL
                    AND last_heartbeat_at > NOW() - INTERVAL '5 minutes')
                                                                   AS active_now,
                ROUND(AVG(duration_seconds) FILTER (WHERE duration_seconds IS NOT NULL))
                                                                   AS avg_duration_seconds,
                MAX(duration_seconds)                              AS longest_session_seconds,
                MIN(duration_seconds) FILTER (WHERE duration_seconds > 0)
                                                                   AS shortest_session_seconds,
                SUM(duration_seconds)                              AS total_time_seconds,
                SUM(query_count)                                   AS total_queries,
                MAX(started_at)                                    AS last_login,
                MIN(started_at)                                    AS first_login,
                COUNT(DISTINCT started_at::DATE)                   AS active_days
            FROM user_sessions
            WHERE email = $1
            """,
            email,
        )

        # Sessions by day (last 30 days)
        by_day = await con.fetch(
            """
            SELECT
                started_at::DATE        AS date,
                COUNT(*)                AS sessions,
                SUM(duration_seconds)   AS total_seconds,
                SUM(query_count)        AS queries
            FROM user_sessions
            WHERE email = $1
              AND started_at > NOW() - INTERVAL '30 days'
            GROUP BY started_at::DATE
            ORDER BY started_at::DATE DESC
            """,
            email,
        )

        # Hourly distribution (what time of day does this user connect?)
        by_hour = await con.fetch(
            """
            SELECT
                EXTRACT(HOUR FROM started_at)::INT AS hour,
                COUNT(*)                            AS sessions
            FROM user_sessions
            WHERE email = $1
            GROUP BY hour
            ORDER BY hour
            """,
            email,
        )

    def fmt(ts):
        return ts.isoformat() if ts else None

    agg_d = dict(agg)
    return {
        "email": email,
        "summary": {
            "total_sessions":          int(agg_d["total_sessions"] or 0),
            "active_now":              int(agg_d["active_now"] or 0),
            "avg_duration_seconds":    int(agg_d["avg_duration_seconds"] or 0),
            "avg_duration_formatted":  _fmt_duration(int(agg_d["avg_duration_seconds"] or 0)),
            "longest_session_seconds": int(agg_d["longest_session_seconds"] or 0),
            "longest_formatted":       _fmt_duration(int(agg_d["longest_session_seconds"] or 0)),
            "total_time_seconds":      int(agg_d["total_time_seconds"] or 0),
            "total_time_formatted":    _fmt_duration(int(agg_d["total_time_seconds"] or 0)),
            "total_queries":           int(agg_d["total_queries"] or 0),
            "last_login":              fmt(agg_d["last_login"]),
            "first_login":             fmt(agg_d["first_login"]),
            "active_days":             int(agg_d["active_days"] or 0),
        },
        "by_day":  [
            {
                "date":          str(r["date"]),
                "sessions":      int(r["sessions"]),
                "total_seconds": int(r["total_seconds"] or 0),
                "formatted":     _fmt_duration(int(r["total_seconds"] or 0)),
                "queries":       int(r["queries"] or 0),
            }
            for r in by_day
        ],
        "by_hour": [
            {"hour": int(r["hour"]), "sessions": int(r["sessions"])}
            for r in by_hour
        ],
    }


def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"
