"""
Async retrieval using asyncpg connection pool + prepared statements.

Eliminates per-request connect/TLS overhead and parse/plan overhead.
Drop-in replacement for retrieve_db() in async contexts.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import asyncpg

from app.core.config import settings
from app.rag.embedder import embed_text
from app.rag.cache import embed_text_cached
from app.rag.retriever import (
    is_numerical_query,
    extract_drug_names,
    numerical_relevance_bonus,
    _doc_type_bonus,
    _recency_bonus,
    _preferred_doc_types,
    _truncate_text,
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")

SQL_UNIFIED_ALL = r"""
WITH
v AS (
  -- No JOIN here so the planner can use the IVFFlat index for ORDER BY + LIMIT.
  -- Inactive-doc filtering is deferred to the final SELECT.
  SELECT c.id,
         (c.embedding <=> CAST($2 AS vector(384))) AS vdist
  FROM chunks c
  WHERE c.embedding IS NOT NULL
  ORDER BY c.embedding <=> CAST($2 AS vector(384))
  LIMIT 60
),
f AS (
  SELECT c.id,
         ts_rank_cd(c.tsv, websearch_to_tsquery('english', $1)) AS fts
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.status = 'active'
    AND c.tsv @@ websearch_to_tsquery('english', $1)
  ORDER BY fts DESC
  LIMIT 80
),
u AS (
  SELECT id,
         min(vdist) AS vdist,
         max(fts)   AS fts
  FROM (
    SELECT id, vdist, NULL::float AS fts FROM v
    UNION ALL
    SELECT id, NULL::float, fts FROM f
  ) s
  GROUP BY id
),
ranked AS (
  SELECT *
  FROM u
  ORDER BY
    COALESCE(vdist, 1e9) ASC,
    COALESCE(fts, 0) DESC
  LIMIT $3
)
SELECT
  d.source_id, d.title, d.year, d.organization_or_journal,
  d.document_type, d.domain, c.page_or_section,
  COALESCE(c.evidence_level, d.document_type) AS evidence_level,
  c.text, r.vdist, r.fts AS krank,
  COALESCE(d.url, '') AS url
FROM ranked r
JOIN chunks c ON c.id = r.id
JOIN documents d ON d.id = c.document_id
WHERE d.status = 'active'
ORDER BY COALESCE(r.vdist, 1e9) ASC, COALESCE(r.fts, 0) DESC;
"""

SQL_UNIFIED_DOMAIN = r"""
WITH
v AS (
  -- No JOIN here so the planner can use the IVFFlat index.
  -- Domain and active-doc filtering is deferred to the final SELECT.
  SELECT c.id,
         (c.embedding <=> CAST($2 AS vector(384))) AS vdist
  FROM chunks c
  WHERE c.embedding IS NOT NULL
  ORDER BY c.embedding <=> CAST($2 AS vector(384))
  LIMIT 100
),
f AS (
  SELECT c.id,
         ts_rank_cd(c.tsv, websearch_to_tsquery('english', $1)) AS fts
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.status = 'active'
    AND d.domain = $4
    AND c.tsv @@ websearch_to_tsquery('english', $1)
  ORDER BY fts DESC
  LIMIT 80
),
u AS (
  SELECT id,
         min(vdist) AS vdist,
         max(fts)   AS fts
  FROM (
    SELECT id, vdist, NULL::float AS fts FROM v
    UNION ALL
    SELECT id, NULL::float, fts FROM f
  ) s
  GROUP BY id
),
ranked AS (
  SELECT *
  FROM u
  ORDER BY
    COALESCE(vdist, 1e9) ASC,
    COALESCE(fts, 0) DESC
  LIMIT $3
)
SELECT
  d.source_id, d.title, d.year, d.organization_or_journal,
  d.document_type, d.domain, c.page_or_section,
  COALESCE(c.evidence_level, d.document_type) AS evidence_level,
  c.text, r.vdist, r.fts AS krank,
  COALESCE(d.url, '') AS url
FROM ranked r
JOIN chunks c ON c.id = r.id
JOIN documents d ON d.id = c.document_id
WHERE d.status = 'active'
  AND d.domain = $4
ORDER BY COALESCE(r.vdist, 1e9) ASC, COALESCE(r.fts, 0) DESC;
"""

SQL_DRUG_TITLE = r"""
SELECT
  d.source_id, d.title, d.year, d.organization_or_journal,
  d.document_type, d.domain, c.page_or_section,
  COALESCE(c.evidence_level, d.document_type) AS evidence_level,
  c.text, NULL::float AS vdist, NULL::float AS krank,
  COALESCE(d.url, '') AS url
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE d.status = 'active'
  AND d.document_type = 'prescribing_information'
  AND lower(d.title) LIKE $1
LIMIT $2;
"""

_pool: Optional[asyncpg.Pool] = None
_stmts: Dict[int, Dict[str, asyncpg.prepared_stmt.PreparedStatement]] = {}


async def _init_connection(con: asyncpg.Connection):
    """Called once per new connection in the pool — prepare + cache statements."""
    try:
        await con.execute("SET statement_timeout = '120s'")
        await con.execute("SET ivfflat.probes = 5")
        cid = id(con)
        _stmts[cid] = {
            "all": await con.prepare(SQL_UNIFIED_ALL),
            "domain": await con.prepare(SQL_UNIFIED_DOMAIN),
            "drug": await con.prepare(SQL_DRUG_TITLE),
        }
    except Exception as e:
        # Non-fatal: log and continue. Pool will still work; prepared stmts fall back to plain queries.
        logger.warning(f"[async_retriever] _init_connection partial failure (non-fatal): {e}")


def _sanitize_asyncpg_dsn(dsn: str) -> tuple[str, bool]:
    """
    Asyncpg does not accept ?sslmode=require in the URL the same way psycopg does.
    Strip sslmode from the query string and return (clean_dsn, ssl_required).
    """
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
    try:
        p = urlparse(dsn)
        qs = parse_qs(p.query, keep_blank_values=True)
        sslmode = qs.pop("sslmode", ["prefer"])[0]
        ssl_required = sslmode in ("require", "verify-ca", "verify-full")
        new_query = urlencode({k: v[0] for k, v in qs.items()})
        clean = urlunparse(p._replace(query=new_query))
        return clean, ssl_required
    except Exception:
        return dsn, True  # leave URL as-is, assume SSL needed


async def init_retrieval_pool():
    global _pool
    if _pool is not None:
        return
    dsn = DATABASE_URL
    if not dsn:
        logger.error("DATABASE_URL not set, async retrieval pool not initialized")
        return

    clean_dsn, ssl_required = _sanitize_asyncpg_dsn(dsn)
    ssl_param: Any = "require" if ssl_required else False

    async def _create():
        return await asyncpg.create_pool(
            dsn=clean_dsn,
            ssl=ssl_param,
            min_size=1,
            max_size=20,
            max_inactive_connection_lifetime=300,
            command_timeout=30,
            timeout=10,
            init=_init_connection,
        )

    try:
        _pool = await asyncio.wait_for(_create(), timeout=20)
        logger.info("asyncpg retrieval pool initialized (min=1, max=20)")
    except Exception as e:
        logger.error(f"Failed to initialize asyncpg pool: {e}")
        _pool = None


def _get_stmt(con: asyncpg.Connection, key: str):
    """Get cached prepared statement for this connection, or None."""
    return _stmts.get(id(con), {}).get(key)


async def close_retrieval_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
    _stmts.clear()


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "source_id": r["source_id"],
        "title": r["title"],
        "year": r["year"],
        "organization_or_journal": r["organization_or_journal"],
        "document_type": r["document_type"],
        "domain": r["domain"],
        "page_or_section": r["page_or_section"],
        "evidence_level": r["evidence_level"],
        "text": r["text"],
        "vdist": float(r["vdist"]) if r["vdist"] is not None else None,
        "krank": float(r["krank"]) if r["krank"] is not None else None,
        "url": r["url"] if "url" in r.keys() else "",
    }


async def retrieve_db_async(
    question: str,
    domain: Optional[str] = None,
    k: int = 0,
    ef_search: int = 40,
) -> List[Dict]:
    """
    Async retrieval via asyncpg pool + prepared statements.
    Returns scored + ranked chunks ready for LLM consumption.
    """
    if _pool is None:
        raise RuntimeError("Async retrieval pool not initialized. Call init_retrieval_pool() on startup.")

    k_final = k if k else settings.RERANK_TOP_N
    numerical_query = is_numerical_query(question)
    if numerical_query:
        logger.info(f"Numerical query detected: {question[:80]}...")

    t0 = time.perf_counter()
    # Run embedding in a thread — embed_text is synchronous CPU/IO work and
    # must not block the uvicorn event loop (would starve concurrent requests).
    qvec = await asyncio.to_thread(embed_text_cached, question, embed_text)
    qvec_str = "[" + ",".join(str(v) for v in qvec) + "]"
    t_embed = time.perf_counter() - t0

    candidate_k = max(k_final * 2, 30)

    t1 = time.perf_counter()
    drug_title_rows = []
    async with _pool.acquire() as con:
        t_acq = time.perf_counter() - t1

        await con.execute(f"SET LOCAL ivfflat.probes = {min(int(ef_search // 8), 5)};")

        t_q0 = time.perf_counter()
        if domain:
            stmt = _get_stmt(con, "domain") or await con.prepare(SQL_UNIFIED_DOMAIN)
            rows = await stmt.fetch(question, qvec_str, int(candidate_k), domain)
        else:
            stmt = _get_stmt(con, "all") or await con.prepare(SQL_UNIFIED_ALL)
            rows = await stmt.fetch(question, qvec_str, int(candidate_k))
        t_fetch = time.perf_counter() - t_q0

        if numerical_query:
            try:
                drug_names = extract_drug_names(question)
                drug_stmt = _get_stmt(con, "drug") or await con.prepare(SQL_DRUG_TITLE)
                for drug in list(drug_names)[:3]:
                    if len(drug) >= 4:
                        drug_pattern = f"%{drug}%"
                        dr = await drug_stmt.fetch(drug_pattern, 10)
                        drug_title_rows.extend(dr)
                        if dr:
                            logger.info(f"Drug-title search found {len(dr)} PI chunks")
            except Exception as e:
                logger.warning(f"Drug-title search failed: {e}")

    t_sql = time.perf_counter() - t1

    logger.info(
        f"Async retrieval: {len(rows)} candidates in {t_sql*1000:.1f}ms "
        f"(embed {t_embed*1000:.1f}ms, acquire {t_acq*1000:.1f}ms, fetch {t_fetch*1000:.1f}ms)"
    )

    merged: Dict[tuple, Dict] = {}

    def _get(r, field, default=None):
        try:
            return r[field]
        except (KeyError, IndexError):
            return default

    def add_row(r, kind: str):
        src_id = _get(r, "source_id", "")
        section = _get(r, "page_or_section", "")
        key = (src_id, section)
        if key not in merged:
            merged[key] = {
                "source_id": src_id,
                "title": _get(r, "title"),
                "year": _get(r, "year"),
                "organization_or_journal": _get(r, "organization_or_journal"),
                "page_or_section": section,
                "evidence_level": _get(r, "evidence_level"),
                "document_type": _get(r, "document_type"),
                "domain": _get(r, "domain"),
                "text": _truncate_text(_get(r, "text") or ""),
                "vdist": None,
                "krank": None,
                "num_match": False,
                "url": _get(r, "url", ""),
            }
        vdist = _get(r, "vdist")
        krank = _get(r, "krank")
        if vdist is not None:
            merged[key]["vdist"] = float(vdist)
        if krank is not None and krank:
            merged[key]["krank"] = float(krank)
        if kind == "drug":
            merged[key]["drug_match"] = True

    for r in rows:
        add_row(r, "unified")
    for r in drug_title_rows:
        add_row(r, "drug")

    candidates = list(merged.values())
    max_krank = max((c["krank"] or 0.0 for c in candidates), default=1.0) or 1.0

    for c in candidates:
        v_sim = 0.0
        if c["vdist"] is not None:
            v_sim = max(0.0, 1.0 - (c["vdist"] / 2.0))

        k_sim = 0.0
        if c["krank"] is not None and c["krank"] > 0:
            k_sim = min(1.0, c["krank"] / max_krank)

        bonus = _doc_type_bonus(c.get("document_type")) + _recency_bonus(c.get("year"))

        num_bonus = 0.0
        if numerical_query:
            chunk_text = c.get("text", "")
            chunk_title = c.get("title", "")
            if c.get("drug_match"):
                num_bonus += 0.40
            num_bonus += numerical_relevance_bonus(chunk_text, question, chunk_title)
            doc_type = (c.get("document_type") or "").lower()
            if doc_type == "prescribing_information":
                num_bonus += 0.20

        c["_score"] = (0.55 * v_sim) + (0.45 * k_sim) + bonus + num_bonus
        c["_num_bonus"] = num_bonus

    pref = _preferred_doc_types()
    preferred = [c for c in candidates if (c.get("document_type") or "").lower() in pref]
    if len(preferred) >= 8:
        candidates = preferred

    candidates.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
    return candidates[:k_final]


async def retrieve_hardened_async(
    question: str,
    domain: Optional[str] = None,
    k: int = 0,
    ef_search: int = 40,
) -> List[Dict]:
    """
    Hardened async retrieval using the scoring SQL from retrieval_hardening.py.
    Returns chunks in the same format as retrieve_db_async() — drop-in replacement.
    Falls back to retrieve_db_async() if the pool is unavailable.
    """
    from app.rag.retrieval_hardening import HardenedRetrieverAsync

    if _pool is None:
        logger.warning("Hardened async retrieval: pool not available, falling back to retrieve_db_async")
        return await retrieve_db_async(question=question, domain=domain, k=k, ef_search=ef_search)

    k_final = k if k else settings.RERANK_TOP_N

    try:
        retriever = HardenedRetrieverAsync()
        result = await retriever.search(
            user_query=question,
            pool=_pool,
            k=k_final,
            ef_search=ef_search,
        )
        chunks = result.get("chunks", [])
        logger.info(
            f"Hardened retrieval: {len(chunks)} chunks in {result.get('retrieval_ms', 0):.1f}ms"
        )
        return chunks
    except Exception as e:
        logger.warning(f"Hardened retrieval failed ({e}), falling back to retrieve_db_async")
        return await retrieve_db_async(question=question, domain=domain, k=k, ef_search=ef_search)
