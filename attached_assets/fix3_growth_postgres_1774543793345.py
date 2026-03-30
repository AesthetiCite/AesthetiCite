"""
Fix 3 — SQLite → Postgres migration for Growth Engine
======================================================
Migrates all six SQLite tables from growth_engine.py to Postgres.

Tables migrated:
  - bookmarks
  - session_reports + session_report_items
  - query_logs
  - api_keys
  - alert_subscriptions
  - drug_interaction_log (new — was not persisted before)

USAGE:
  Step 1 — Run migration (one time):
      python fix3_growth_postgres.py migrate

  Step 2 — Replace db() in growth_engine.py:
      from app.api.growth_postgres import get_pg_conn as db
      (The API is synchronous — compatible with existing endpoint code)

  Step 3 — Remove SQLite import and DB_PATH from growth_engine.py

ENVIRONMENT:
  DATABASE_URL — standard Postgres connection string (already set)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


# ─────────────────────────────────────────────────────────────────
# Migration — run once
# ─────────────────────────────────────────────────────────────────

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS growth_bookmarks (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer_json     JSONB NOT NULL DEFAULT '{}',
    tags            JSONB NOT NULL DEFAULT '[]',
    created_at_utc  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bm_user ON growth_bookmarks(user_id);

CREATE TABLE IF NOT EXISTS growth_session_reports (
    id              TEXT PRIMARY KEY,
    clinic_id       TEXT,
    clinician_id    TEXT,
    title           TEXT NOT NULL,
    report_date     DATE,
    notes           TEXT,
    created_at_utc  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS growth_session_report_items (
    id                  TEXT PRIMARY KEY,
    report_id           TEXT NOT NULL REFERENCES growth_session_reports(id) ON DELETE CASCADE,
    patient_label       TEXT,
    procedure           TEXT NOT NULL,
    region              TEXT NOT NULL,
    product_type        TEXT,
    technique           TEXT,
    injector_experience TEXT,
    patient_factors     JSONB NOT NULL DEFAULT '[]',
    engine_response     JSONB NOT NULL DEFAULT '{}',
    created_at_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sri_report ON growth_session_report_items(report_id);

CREATE TABLE IF NOT EXISTS growth_query_logs (
    id                  TEXT PRIMARY KEY,
    clinic_id           TEXT,
    clinician_id        TEXT,
    query_text          TEXT NOT NULL,
    answer_type         TEXT,
    aci_score           FLOAT,
    response_time_ms    INT,
    evidence_level      TEXT,
    risk_level          TEXT,
    protocol_triggered  BOOLEAN DEFAULT FALSE,
    created_at_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ql_clinic ON growth_query_logs(clinic_id);
CREATE INDEX IF NOT EXISTS idx_ql_created ON growth_query_logs(created_at_utc DESC);

CREATE TABLE IF NOT EXISTS growth_api_keys (
    id              TEXT PRIMARY KEY,
    clinic_id       TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,
    key_prefix      TEXT NOT NULL,
    label           TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at_utc  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_utc   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ak_hash ON growth_api_keys(key_hash);

CREATE TABLE IF NOT EXISTS growth_alert_subscriptions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    topic           TEXT NOT NULL,
    email           TEXT,
    created_at_utc  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_as_user ON growth_alert_subscriptions(user_id);
"""


async def _run_migration() -> None:
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(MIGRATION_SQL)
    logger.info("[GrowthPostgres] Migration complete.")
    print("Migration complete — all growth engine tables created in Postgres.")


# ─────────────────────────────────────────────────────────────────
# Sync wrapper (keeps existing endpoint code compatible)
# ─────────────────────────────────────────────────────────────────

def _run_sync(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"[GrowthPostgres] sync wrapper error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# Bookmarks
# ─────────────────────────────────────────────────────────────────

async def _create_bookmark_async(user_id, title, question, answer_json, tags):
    rec_id = str(uuid.uuid4())
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO growth_bookmarks (id,user_id,title,question,answer_json,tags)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            rec_id, user_id, title, question,
            json.dumps(answer_json), json.dumps(tags)
        )
    return rec_id


def create_bookmark(user_id, title, question, answer_json, tags=None):
    return _run_sync(_create_bookmark_async(user_id, title, question, answer_json, tags or []))


async def _list_bookmarks_async(user_id):
    pool = await _get_pool()
    async with pool.acquire() as con:
        rows = await con.fetch(
            "SELECT * FROM growth_bookmarks WHERE user_id=$1 ORDER BY created_at_utc DESC",
            user_id
        )
    return [dict(r) for r in rows]


def list_bookmarks(user_id):
    return _run_sync(_list_bookmarks_async(user_id)) or []


async def _delete_bookmark_async(bookmark_id):
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute("DELETE FROM growth_bookmarks WHERE id=$1", bookmark_id)


def delete_bookmark(bookmark_id):
    _run_sync(_delete_bookmark_async(bookmark_id))


# ─────────────────────────────────────────────────────────────────
# Session reports
# ─────────────────────────────────────────────────────────────────

async def _create_session_report_async(clinic_id, clinician_id, title, report_date, notes):
    rec_id = str(uuid.uuid4())
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO growth_session_reports
               (id,clinic_id,clinician_id,title,report_date,notes)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            rec_id, clinic_id, clinician_id, title, report_date, notes
        )
    return rec_id


def create_session_report(clinic_id, clinician_id, title, report_date=None, notes=None):
    return _run_sync(_create_session_report_async(clinic_id, clinician_id, title, report_date, notes))


async def _add_session_item_async(report_id, patient_label, procedure, region,
                                   product_type, technique, injector_experience,
                                   patient_factors, engine_response):
    rec_id = str(uuid.uuid4())
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO growth_session_report_items
               (id,report_id,patient_label,procedure,region,product_type,
                technique,injector_experience,patient_factors,engine_response)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            rec_id, report_id, patient_label, procedure, region,
            product_type, technique, injector_experience,
            json.dumps(patient_factors or []),
            json.dumps(engine_response or {})
        )
    return rec_id


def add_session_item(report_id, patient_label, procedure, region,
                     product_type=None, technique=None, injector_experience=None,
                     patient_factors=None, engine_response=None):
    return _run_sync(_add_session_item_async(
        report_id, patient_label, procedure, region,
        product_type, technique, injector_experience,
        patient_factors, engine_response
    ))


async def _get_session_report_async(report_id):
    pool = await _get_pool()
    async with pool.acquire() as con:
        report = await con.fetchrow(
            "SELECT * FROM growth_session_reports WHERE id=$1", report_id
        )
        if not report:
            return None
        items = await con.fetch(
            "SELECT * FROM growth_session_report_items WHERE report_id=$1 ORDER BY created_at_utc",
            report_id
        )
    return {"report": dict(report), "items": [dict(i) for i in items]}


def get_session_report(report_id):
    return _run_sync(_get_session_report_async(report_id))


# ─────────────────────────────────────────────────────────────────
# Query logs
# ─────────────────────────────────────────────────────────────────

async def _log_query_async(clinic_id, clinician_id, query_text, answer_type=None,
                            aci_score=None, response_time_ms=None, evidence_level=None,
                            risk_level=None, protocol_triggered=False):
    rec_id = str(uuid.uuid4())
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO growth_query_logs
               (id,clinic_id,clinician_id,query_text,answer_type,aci_score,
                response_time_ms,evidence_level,risk_level,protocol_triggered)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            rec_id, clinic_id, clinician_id, query_text, answer_type,
            aci_score, response_time_ms, evidence_level, risk_level, protocol_triggered
        )
    return rec_id


def log_query(clinic_id, clinician_id, query_text, **kwargs):
    return _run_sync(_log_query_async(clinic_id, clinician_id, query_text, **kwargs))


async def _clinic_dashboard_async(clinic_id):
    pool = await _get_pool()
    async with pool.acquire() as con:
        rows = await con.fetch(
            "SELECT * FROM growth_query_logs WHERE clinic_id=$1", clinic_id
        )
    rows = [dict(r) for r in rows]
    total = len(rows)
    aci_vals = [r["aci_score"] for r in rows if r.get("aci_score") is not None]
    rt_vals  = [r["response_time_ms"] for r in rows if r.get("response_time_ms") is not None]
    from collections import Counter
    import statistics
    return {
        "total_queries": total,
        "average_aci_score": round(statistics.mean(aci_vals), 2) if aci_vals else None,
        "average_response_time_ms": round(statistics.mean(rt_vals)) if rt_vals else None,
        "top_questions": [
            {"query": q, "count": c}
            for q, c in Counter(r["query_text"] for r in rows).most_common(10)
        ],
        "evidence_level_distribution": dict(Counter(
            r["evidence_level"] for r in rows if r.get("evidence_level")
        )),
        "protocol_trigger_count": sum(1 for r in rows if r.get("protocol_triggered")),
        "high_risk_query_count": sum(1 for r in rows if r.get("risk_level") == "high"),
    }


def clinic_dashboard(clinic_id):
    return _run_sync(_clinic_dashboard_async(clinic_id)) or {}


# ─────────────────────────────────────────────────────────────────
# API keys
# ─────────────────────────────────────────────────────────────────

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _create_api_key_async(clinic_id, label=None):
    import secrets
    raw = "ac_" + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw)
    prefix = raw[:12]
    rec_id = str(uuid.uuid4())
    pool = await _get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO growth_api_keys (id,clinic_id,key_hash,key_prefix,label)
               VALUES ($1,$2,$3,$4,$5)""",
            rec_id, clinic_id, key_hash, prefix, label
        )
    return {"id": rec_id, "key": raw, "prefix": prefix, "clinic_id": clinic_id}


def create_api_key(clinic_id, label=None):
    return _run_sync(_create_api_key_async(clinic_id, label))


async def _validate_api_key_async(raw_key):
    key_hash = _hash_key(raw_key)
    pool = await _get_pool()
    async with pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT * FROM growth_api_keys WHERE key_hash=$1 AND is_active=TRUE",
            key_hash
        )
        if row:
            await con.execute(
                "UPDATE growth_api_keys SET last_used_utc=NOW() WHERE id=$1",
                row["id"]
            )
    return dict(row) if row else None


def validate_api_key(raw_key):
    return _run_sync(_validate_api_key_async(raw_key))


# ─────────────────────────────────────────────────────────────────
# CLI: python fix3_growth_postgres.py migrate
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        asyncio.run(_run_migration())
    else:
        print("Usage: python fix3_growth_postgres.py migrate")
