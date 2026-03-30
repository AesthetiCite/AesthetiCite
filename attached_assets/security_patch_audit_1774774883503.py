"""
security_patch_audit.py
========================
NEW FILE: app/core/audit.py

Drop this as a new file. It replaces safe_write_jsonl() from governance.py
with a durable Postgres-backed audit log.

The audit_log table is created on startup by the SQL in security_patch_main.py.

After creating this file:
  1. In app/core/governance.py, replace calls to safe_write_jsonl() with
     asyncio.create_task(write_audit_event(...)) — see instructions at bottom.
  2. Optionally call write_audit_event() from ask_stream.py and auth.py
     for full audit coverage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=4,
            ssl="require",
            command_timeout=10,
            max_inactive_connection_lifetime=300,
        )
    return _pool


async def write_audit_event(
    event_type: str,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    ip_address: Optional[str] = None,
    path: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Write a durable audit event to Postgres.

    Silently fails — audit logging must never crash the main request.

    Usage:
        # In any async endpoint:
        asyncio.create_task(write_audit_event(
            event_type="protocol_accessed",
            request_id=request_id,
            user_id=user["id"],
            email=user["email"],
            protocol_key=protocol_key,
        ))

        # In sync endpoints, schedule via background task:
        background_tasks.add_task(
            _sync_audit,
            event_type="case_logged",
            user_id=user_id,
        )
    """
    try:
        pool = await _get_pool()
        async with pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO audit_log
                    (event_type, request_id, user_id, email, ip_address, path, event_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                event_type,
                request_id,
                str(user_id) if user_id else None,
                email,
                ip_address,
                path,
                json.dumps(kwargs),
            )
    except Exception as e:
        # Never let audit logging crash the main request
        logger.warning(f"[Audit] Failed to write event '{event_type}': {e}")


def write_audit_sync(event_type: str, **kwargs: Any) -> None:
    """
    Sync wrapper — schedules audit write without blocking.
    Use in sync FastAPI endpoints via BackgroundTasks.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(write_audit_event(event_type, **kwargs))
        else:
            loop.run_until_complete(write_audit_event(event_type, **kwargs))
    except Exception as e:
        logger.warning(f"[Audit] Sync wrapper failed: {e}")


# ─────────────────────────────────────────────────────────────────
# Admin query helpers (used by super-admin dashboard)
# ─────────────────────────────────────────────────────────────────

async def get_recent_events(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 100,
) -> list:
    """Fetch recent audit events — for admin dashboard use only."""
    pool = await _get_pool()
    async with pool.acquire() as con:
        if event_type and user_id:
            rows = await con.fetch(
                """SELECT * FROM audit_log
                   WHERE event_type=$1 AND user_id=$2
                   ORDER BY logged_at DESC LIMIT $3""",
                event_type, user_id, limit,
            )
        elif event_type:
            rows = await con.fetch(
                """SELECT * FROM audit_log
                   WHERE event_type=$1
                   ORDER BY logged_at DESC LIMIT $2""",
                event_type, limit,
            )
        elif user_id:
            rows = await con.fetch(
                """SELECT * FROM audit_log
                   WHERE user_id=$1
                   ORDER BY logged_at DESC LIMIT $2""",
                user_id, limit,
            )
        else:
            rows = await con.fetch(
                "SELECT * FROM audit_log ORDER BY logged_at DESC LIMIT $1",
                limit,
            )
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────
# INTEGRATION INSTRUCTIONS
# ─────────────────────────────────────────────────────────────────
#
# 1. In app/core/governance.py:
#
#    Add import:
#        from app.core.audit import write_audit_sync
#
#    Find safe_write_jsonl() calls — they look like:
#        safe_write_jsonl(AUDIT_LOG_PATH, {...})
#
#    Replace each one with:
#        write_audit_sync(
#            event_type="query_answered",
#            request_id=request_id,
#            user_id=user_id,
#            question=question[:200],   # truncate long text
#            protocol_key=protocol_key,
#        )
#
#
# 2. In ask_stream.py (the main query endpoint), add after streaming:
#
#    asyncio.create_task(write_audit_event(
#        event_type    = "clinical_query",
#        request_id    = request_id,
#        user_id       = user_id,
#        email         = user_email,
#        ip_address    = request.client.host if request.client else None,
#        path          = "/ask/stream",
#        question_hash = hashlib.sha256(payload.question.encode()).hexdigest()[:16],
#        mode          = payload.mode,
#    ))
#
#
# 3. In complication_protocol_engine.py generate_protocol():
#
#    asyncio.create_task(write_audit_event(
#        event_type    = "protocol_accessed",
#        request_id    = request_id,
#        protocol_key  = protocol_key,
#        confidence    = confidence,
#    ))
#
#
# 4. In auth.py login endpoint:
#
#    asyncio.create_task(write_audit_event(
#        event_type = "user_login",
#        user_id    = str(row["id"]),
#        email      = row["email"],
#        ip_address = request.client.host if request.client else None,
#    ))
#
# These are the four highest-value audit events. Add others as needed.
