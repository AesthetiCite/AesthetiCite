"""
app/core/audit.py
==================
Durable Postgres-backed audit log for AesthetiCite.

Replaces safe_write_jsonl() with persistent audit events that survive deploys.
The audit_log table is created on startup by the SQL in DOC_META_MIGRATION_SQL (main.py).
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
        logger.warning(f"[Audit] Failed to write event '{event_type}': {e}")


def write_audit_sync(event_type: str, **kwargs: Any) -> None:
    """
    Sync wrapper — schedules audit write without blocking.
    Safe to call from sync FastAPI endpoints.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(write_audit_event(event_type, **kwargs))
        else:
            loop.run_until_complete(write_audit_event(event_type, **kwargs))
    except Exception as e:
        logger.warning(f"[Audit] Sync wrapper failed: {e}")


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
                "SELECT * FROM audit_log WHERE event_type=$1 AND user_id=$2 ORDER BY logged_at DESC LIMIT $3",
                event_type, user_id, limit,
            )
        elif event_type:
            rows = await con.fetch(
                "SELECT * FROM audit_log WHERE event_type=$1 ORDER BY logged_at DESC LIMIT $2",
                event_type, limit,
            )
        elif user_id:
            rows = await con.fetch(
                "SELECT * FROM audit_log WHERE user_id=$1 ORDER BY logged_at DESC LIMIT $2",
                user_id, limit,
            )
        else:
            rows = await con.fetch(
                "SELECT * FROM audit_log ORDER BY logged_at DESC LIMIT $1",
                limit,
            )
    return [dict(r) for r in rows]
