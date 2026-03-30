"""
Fix 1 — Postgres persistence for case store
============================================
Replaces the in-memory CASE_STORE list in complication_protocol_engine.py
with direct Postgres persistence using the existing asyncpg pool.

INTEGRATION:
1. Run the migration SQL below once against your Postgres instance.
2. Replace the in-memory store and log functions in complication_protocol_engine.py
   with the functions from this file.
3. Import and call init_cases_table() on app startup (add to main.py startup).

Migration SQL (run once):
    CREATE TABLE IF NOT EXISTS complication_cases (
        case_id TEXT PRIMARY KEY,
        logged_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        clinic_id TEXT,
        clinician_id TEXT,
        protocol_key TEXT NOT NULL,
        region TEXT,
        procedure TEXT,
        product_type TEXT,
        symptoms JSONB NOT NULL DEFAULT '[]',
        outcome TEXT,
        query TEXT,
        confidence FLOAT
    );
    CREATE INDEX IF NOT EXISTS idx_cases_protocol ON complication_cases(protocol_key);
    CREATE INDEX IF NOT EXISTS idx_cases_clinic ON complication_cases(clinic_id);
    CREATE INDEX IF NOT EXISTS idx_cases_logged ON complication_cases(logged_at_utc DESC);
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ─────────────────────────────────────────────────────────────────
# Connection pool (reuse existing pool if available)
# ─────────────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=8,
            ssl="require",
            command_timeout=30,
            max_inactive_connection_lifetime=300,
        )
    return _pool


async def init_cases_table() -> None:
    """Run once on startup — creates the table if it does not exist."""
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute("""
            CREATE TABLE IF NOT EXISTS complication_cases (
                case_id       TEXT PRIMARY KEY,
                logged_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                clinic_id     TEXT,
                clinician_id  TEXT,
                protocol_key  TEXT NOT NULL,
                region        TEXT,
                procedure     TEXT,
                product_type  TEXT,
                symptoms      JSONB NOT NULL DEFAULT '[]',
                outcome       TEXT,
                query         TEXT,
                confidence    FLOAT
            );
            CREATE INDEX IF NOT EXISTS idx_cases_protocol
                ON complication_cases(protocol_key);
            CREATE INDEX IF NOT EXISTS idx_cases_clinic
                ON complication_cases(clinic_id);
            CREATE INDEX IF NOT EXISTS idx_cases_logged
                ON complication_cases(logged_at_utc DESC);
        """)
    logger.info("[CaseStore] complication_cases table ready.")


# ─────────────────────────────────────────────────────────────────
# Sync wrapper for use in synchronous FastAPI endpoints
# ─────────────────────────────────────────────────────────────────

import asyncio


def _run(coro):
    """Run an async function from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"[CaseStore] async run error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# Core persistence functions
# Replace the CASE_STORE.append() and _log_protocol_request() calls
# in complication_protocol_engine.py with these.
# ─────────────────────────────────────────────────────────────────

async def _persist_case_async(
    case_id: str,
    protocol_key: str,
    clinic_id: Optional[str],
    clinician_id: Optional[str],
    region: Optional[str],
    procedure: Optional[str],
    product_type: Optional[str],
    symptoms: List[str],
    outcome: Optional[str],
    query: Optional[str] = None,
    confidence: Optional[float] = None,
) -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO complication_cases
                    (case_id, clinic_id, clinician_id, protocol_key, region,
                     procedure, product_type, symptoms, outcome, query, confidence)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (case_id) DO NOTHING
                """,
                case_id,
                clinic_id,
                clinician_id,
                protocol_key,
                region,
                procedure,
                product_type,
                json.dumps(symptoms),
                outcome,
                query,
                confidence,
            )
        logger.info(f"[CaseStore] Persisted case {case_id} for protocol {protocol_key}")
        return True
    except Exception as e:
        logger.error(f"[CaseStore] Failed to persist case: {e}")
        return False


def log_case_to_postgres(
    protocol_key: str,
    clinic_id: Optional[str] = None,
    clinician_id: Optional[str] = None,
    region: Optional[str] = None,
    procedure: Optional[str] = None,
    product_type: Optional[str] = None,
    symptoms: Optional[List[str]] = None,
    outcome: Optional[str] = None,
    query: Optional[str] = None,
    confidence: Optional[float] = None,
) -> str:
    """
    Persist a case to Postgres. Returns the case_id.
    Drop-in replacement for CASE_STORE.append().

    In complication_protocol_engine.py, replace:
        CASE_STORE.append(case)
    with:
        log_case_to_postgres(protocol_key=..., ...)
    """
    case_id = str(uuid.uuid4())
    _run(_persist_case_async(
        case_id=case_id,
        protocol_key=protocol_key,
        clinic_id=clinic_id,
        clinician_id=clinician_id,
        region=region,
        procedure=procedure,
        product_type=product_type,
        symptoms=symptoms or [],
        outcome=outcome,
        query=query,
        confidence=confidence,
    ))
    return case_id


# ─────────────────────────────────────────────────────────────────
# Stats queries (replace in-memory Counter logic)
# ─────────────────────────────────────────────────────────────────

async def _get_stats_async() -> Dict[str, Any]:
    try:
        pool = await get_pool()
        async with pool.acquire() as con:
            total = await con.fetchval("SELECT COUNT(*) FROM complication_cases")
            by_protocol = await con.fetch(
                "SELECT protocol_key, COUNT(*) as cnt FROM complication_cases GROUP BY protocol_key"
            )
            by_region = await con.fetch(
                "SELECT region, COUNT(*) as cnt FROM complication_cases WHERE region IS NOT NULL GROUP BY region"
            )
            by_procedure = await con.fetch(
                "SELECT procedure, COUNT(*) as cnt FROM complication_cases WHERE procedure IS NOT NULL GROUP BY procedure"
            )
        return {
            "total_cases": total or 0,
            "by_protocol":  {r["protocol_key"]: r["cnt"] for r in by_protocol},
            "by_region":    {r["region"]: r["cnt"] for r in by_region},
            "by_procedure": {r["procedure"]: r["cnt"] for r in by_procedure},
        }
    except Exception as e:
        logger.error(f"[CaseStore] Stats query failed: {e}")
        return {"total_cases": 0, "by_protocol": {}, "by_region": {}, "by_procedure": {}}


def get_dataset_stats() -> Dict[str, Any]:
    """Replace the in-memory Counter stats in the /stats endpoint."""
    return _run(_get_stats_async()) or {"total_cases": 0, "by_protocol": {}, "by_region": {}, "by_procedure": {}}


async def _list_cases_async(
    clinic_id: Optional[str] = None,
    protocol_key: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    try:
        pool = await get_pool()
        clauses = []
        params = []
        if clinic_id:
            params.append(clinic_id)
            clauses.append(f"clinic_id = ${len(params)}")
        if protocol_key:
            params.append(protocol_key)
            clauses.append(f"protocol_key = ${len(params)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        async with pool.acquire() as con:
            rows = await con.fetch(
                f"SELECT * FROM complication_cases {where} ORDER BY logged_at_utc DESC LIMIT ${len(params)}",
                *params,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[CaseStore] List cases failed: {e}")
        return []


def list_cases(
    clinic_id: Optional[str] = None,
    protocol_key: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    return _run(_list_cases_async(clinic_id, protocol_key, limit)) or []
