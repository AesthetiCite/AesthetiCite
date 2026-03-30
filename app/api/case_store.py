"""
app/api/case_store.py
=====================
Postgres-backed case store.
Replaces the in-memory CASE_STORE list in complication_protocol_engine.py.

Cases survive server restarts. Dataset grows permanently.

SETUP (run once):
    from app.api.case_store import create_table
    import asyncio; asyncio.run(create_table())

Or add to main.py startup:
    from app.api.case_store import create_table_sync
    create_table_sync()

USAGE in complication_protocol_engine.py:
    Replace:
        CASE_STORE.append(case)
    With:
        from app.api.case_store import log_case, get_stats, list_cases

    Replace the /log-case endpoint body with:
        case_id = log_case(
            protocol_key=payload.protocol_key,
            clinic_id=payload.clinic_id,
            clinician_id=payload.clinician_id,
            region=payload.region,
            procedure=payload.procedure,
            product_type=payload.product_type,
            symptoms=payload.symptoms,
            outcome=payload.outcome,
        )
        return LogCaseResponse(status="ok", case_id=case_id)

    Replace the /stats endpoint body with:
        return DatasetStatsResponse(**get_stats())
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="case_store")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS complication_cases (
    case_id         TEXT PRIMARY KEY,
    logged_at_utc   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    clinic_id       TEXT,
    clinician_id    TEXT,
    protocol_key    TEXT NOT NULL,
    region          TEXT,
    procedure       TEXT,
    product_type    TEXT,
    symptoms        JSONB NOT NULL DEFAULT '[]',
    outcome         TEXT,
    query           TEXT,
    confidence      FLOAT
);
CREATE INDEX IF NOT EXISTS idx_cc_protocol  ON complication_cases(protocol_key);
CREATE INDEX IF NOT EXISTS idx_cc_clinic    ON complication_cases(clinic_id);
CREATE INDEX IF NOT EXISTS idx_cc_logged    ON complication_cases(logged_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_cc_procedure ON complication_cases(procedure);
CREATE INDEX IF NOT EXISTS idx_cc_region    ON complication_cases(region);
"""


# ─────────────────────────────────────────────────────────────────
# Connection helpers (per-call, no shared pool)
# ─────────────────────────────────────────────────────────────────

def _ssl_mode() -> str:
    """Use require only for cloud databases; skip SSL for local dev."""
    url = DATABASE_URL.lower()
    if "neon.tech" in url or "amazonaws.com" in url:
        return "require"
    return "prefer"


async def _connect() -> asyncpg.Connection:
    """Open a fresh asyncpg connection. Each async task gets its own connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return await asyncpg.connect(DATABASE_URL, ssl=_ssl_mode(), command_timeout=30)


def _run(coro) -> Any:
    """
    Run *coro* from a sync context.
    Always submits to a dedicated thread so asyncio.run() creates its own event
    loop — avoiding any clash with uvicorn's running loop.
    """
    try:
        future = _executor.submit(asyncio.run, coro)
        return future.result(timeout=15)
    except Exception as e:
        logger.error(f"[CaseStore] async run error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# Table creation
# ─────────────────────────────────────────────────────────────────

async def create_table() -> None:
    con = await _connect()
    try:
        await con.execute(CREATE_SQL)
    finally:
        await con.close()
    logger.info("[CaseStore] complication_cases table ready.")


def create_table_sync() -> None:
    """Call from main.py startup."""
    _run(create_table())


# ─────────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────────

async def _log_case_async(
    protocol_key: str,
    clinic_id: Optional[str],
    clinician_id: Optional[str],
    region: Optional[str],
    procedure: Optional[str],
    product_type: Optional[str],
    symptoms: List[str],
    outcome: Optional[str],
    query: Optional[str],
    confidence: Optional[float],
    case_id: str,
) -> None:
    con = await _connect()
    try:
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
    finally:
        await con.close()
    logger.info(f"[CaseStore] Saved case {case_id} ({protocol_key})")


def log_case(
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
    Fire-and-forget safe — errors are logged, not raised.
    """
    case_id = str(uuid.uuid4())
    _run(_log_case_async(
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
        case_id=case_id,
    ))
    return case_id


# ─────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────

async def _stats_async() -> Dict[str, Any]:
    con = await _connect()
    try:
        total        = await con.fetchval("SELECT COUNT(*) FROM complication_cases") or 0
        by_protocol  = await con.fetch("SELECT protocol_key, COUNT(*) c FROM complication_cases GROUP BY protocol_key")
        by_region    = await con.fetch("SELECT region, COUNT(*) c FROM complication_cases WHERE region IS NOT NULL GROUP BY region")
        by_procedure = await con.fetch("SELECT procedure, COUNT(*) c FROM complication_cases WHERE procedure IS NOT NULL GROUP BY procedure")
    finally:
        await con.close()
    return {
        "total_cases":  total,
        "by_protocol":  {r["protocol_key"]: r["c"] for r in by_protocol},
        "by_region":    {r["region"]: r["c"] for r in by_region},
        "by_procedure": {r["procedure"]: r["c"] for r in by_procedure},
    }


def get_stats() -> Dict[str, Any]:
    return _run(_stats_async()) or {
        "total_cases": 0, "by_protocol": {}, "by_region": {}, "by_procedure": {}
    }


# ─────────────────────────────────────────────────────────────────
# List / query
# ─────────────────────────────────────────────────────────────────

async def _list_async(
    clinic_id: Optional[str] = None,
    protocol_key: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses, params = [], []
    if clinic_id:
        params.append(clinic_id);     clauses.append(f"clinic_id = ${len(params)}")
    if protocol_key:
        params.append(protocol_key);  clauses.append(f"protocol_key = ${len(params)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    con = await _connect()
    try:
        rows = await con.fetch(
            f"SELECT * FROM complication_cases {where} ORDER BY logged_at_utc DESC LIMIT ${len(params)}",
            *params,
        )
    finally:
        await con.close()
    return [dict(r) for r in rows]


def list_cases(
    clinic_id: Optional[str] = None,
    protocol_key: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    return _run(_list_async(clinic_id, protocol_key, limit)) or []
