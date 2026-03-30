"""
Fix 6 — HNSW Vector Index for pgvector
=======================================
Wires the HNSW index in pgvector to replace the keyword fallback
in the HNSWRetriever class in growth_engine.py.

pgvector has supported HNSW natively since v0.5.0.
This is one of the highest-impact answer quality improvements
available — more relevant chunks = better evidence grounding
= higher ACI scores on every query.

INTEGRATION:
1. Run the SQL migration below (one time).
2. Replace the HNSWRetriever class in growth_engine.py with
   the HNSWVectorRetriever class from this file.
3. Update the retrieve_fn passed to AesthetiCiteEngine.

ENVIRONMENT:
  DATABASE_URL — Postgres connection string with pgvector enabled
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ─────────────────────────────────────────────────────────────────
# Step 1: Migration SQL — run once
# ─────────────────────────────────────────────────────────────────

MIGRATION_SQL = """
-- Ensure pgvector extension is enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- HNSW index on the chunks table (846K rows)
-- Uses cosine similarity — matches the query operator <=> used at inference
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw2
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Set ef_search for query-time accuracy/speed tradeoff
-- Higher = more accurate, slower. 40 is a good production default.
SET hnsw.ef_search = 40;
"""

# ─────────────────────────────────────────────────────────────────
# Step 2: Query parameters
# Tune these to balance recall vs latency.
# ─────────────────────────────────────────────────────────────────

HNSW_CONFIG = {
    "ef_search": 40,           # candidates examined at query time (40 = good balance)
    "top_k": 14,               # chunks returned per query
    "similarity_threshold": 0.35,  # minimum cosine similarity (0 = no filter)
    "table_name": "document_chunks",   # adjust to your schema
    "embedding_column": "embedding",
    "text_column": "text",
    "title_column": "title",
    "metadata_columns": ["year", "source_id", "url", "document_type",
                         "journal_or_org", "evidence_tier"],
}


# ─────────────────────────────────────────────────────────────────
# Connection pool
# ─────────────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            init=_set_hnsw_params,
        )
    return _pool


async def _set_hnsw_params(con: asyncpg.Connection) -> None:
    """Set HNSW ef_search on every new connection."""
    try:
        await con.execute(f"SET hnsw.ef_search = {HNSW_CONFIG['ef_search']}")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# Embedding function
# Uses the existing fastembed model already initialised in the codebase.
# ─────────────────────────────────────────────────────────────────

_embed_model = None


def _get_embedder():
    global _embed_model
    if _embed_model is None:
        try:
            from fastembed import TextEmbedding
            _embed_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
            logger.info("[HNSW] Embedding model loaded.")
        except Exception as e:
            logger.error(f"[HNSW] Failed to load embedding model: {e}")
    return _embed_model


def embed_query(query: str) -> List[float]:
    """Embed a query string. Returns a flat list of floats."""
    embedder = _get_embedder()
    if embedder is None:
        return []
    try:
        embeddings = list(embedder.embed([query]))
        return embeddings[0].tolist() if embeddings else []
    except Exception as e:
        logger.error(f"[HNSW] Embedding failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────
# Core retrieval function
# ─────────────────────────────────────────────────────────────────

async def _hnsw_retrieve_async(
    query: str,
    k: int = 14,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most similar chunks using the HNSW index.
    Returns list of chunk dicts compatible with the existing pipeline.
    """
    embedding = embed_query(query)
    if not embedding:
        logger.warning("[HNSW] Empty embedding — falling back to keyword search")
        return await _keyword_fallback(query, k)

    cfg = HNSW_CONFIG
    table = cfg["table_name"]
    emb_col = cfg["embedding_column"]

    # Build metadata column select
    meta_cols = ", ".join(
        f'"{c}"' for c in cfg["metadata_columns"]
        if c not in (cfg["text_column"], cfg["title_column"], emb_col)
    )
    select_cols = f'"{cfg["text_column"]}", "{cfg["title_column"]}"'
    if meta_cols:
        select_cols += f", {meta_cols}"

    # Cosine similarity: 1 - (embedding <=> query_vector)
    # pgvector <=> operator = cosine distance (lower = more similar)
    similarity_filter = ""
    params = [str(embedding), k]
    if cfg["similarity_threshold"] > 0:
        params.append(1 - cfg["similarity_threshold"])
        similarity_filter = f"WHERE 1 - ({emb_col} <=> $1::vector) >= $3"

    sql = f"""
        SELECT
            {select_cols},
            1 - ({emb_col} <=> $1::vector) AS similarity
        FROM {table}
        {similarity_filter}
        ORDER BY {emb_col} <=> $1::vector
        LIMIT $2
    """

    try:
        pool = await _get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch(sql, *params)
        results = []
        for row in rows:
            d = dict(row)
            d["score"] = float(d.pop("similarity", 0))
            # Normalise field names to match existing pipeline expectations
            d["text"]  = d.get(cfg["text_column"], "")
            d["title"] = d.get(cfg["title_column"], "")
            d["id"]    = d.get("source_id", "")
            results.append(d)
        logger.debug(f"[HNSW] Retrieved {len(results)} chunks for: {query[:60]}")
        return results
    except Exception as e:
        logger.error(f"[HNSW] Retrieval error: {e}")
        return await _keyword_fallback(query, k)


async def _keyword_fallback(query: str, k: int) -> List[Dict[str, Any]]:
    """
    Full-text search fallback when HNSW is unavailable.
    Uses Postgres tsvector — already supported without any extensions.
    """
    cfg = HNSW_CONFIG
    table = cfg["table_name"]
    sql = f"""
        SELECT
            "{cfg['text_column']}",
            "{cfg['title_column']}",
            ts_rank_cd(
                to_tsvector('english', "{cfg['text_column']}"),
                plainto_tsquery('english', $1)
            ) AS score
        FROM {table}
        WHERE to_tsvector('english', "{cfg['text_column']}")
              @@ plainto_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT $2
    """
    try:
        pool = await _get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch(sql, query, k)
        return [
            {
                "text":  dict(r)[cfg["text_column"]],
                "title": dict(r)[cfg["title_column"]],
                "score": float(dict(r)["score"]),
                "id":    "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"[HNSW] Keyword fallback also failed: {e}")
        return []


def _run_sync(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"[HNSW] sync wrapper error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────
# HNSWVectorRetriever — drop-in replacement for HNSWRetriever
# ─────────────────────────────────────────────────────────────────

class HNSWVectorRetriever:
    """
    Drop-in replacement for the HNSWRetriever stub in growth_engine.py.

    In growth_engine.py, replace:
        hnsw_retriever = HNSWRetriever()

    With:
        from app.api.hnsw_retriever import HNSWVectorRetriever
        hnsw_retriever = HNSWVectorRetriever()

    The retrieve() method signature is identical.
    """

    def retrieve(self, query: str, k: int = 14) -> List[Dict[str, Any]]:
        """Synchronous retrieve — compatible with existing engine call sites."""
        return _run_sync(_hnsw_retrieve_async(query, k)) or []

    async def retrieve_async(self, query: str, k: int = 14) -> List[Dict[str, Any]]:
        """Async retrieve — use this in async endpoints for better performance."""
        return await _hnsw_retrieve_async(query, k)

    def retrieve_multi(
        self,
        queries: List[str],
        k_per_query: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve for multiple queries in parallel and deduplicate.
        Used by the VeriDoc parallel retrieval pipeline.
        """
        import asyncio as _asyncio
        from concurrent.futures import ThreadPoolExecutor

        async def _multi():
            tasks = [_hnsw_retrieve_async(q, k_per_query) for q in queries]
            results = await _asyncio.gather(*tasks, return_exceptions=True)
            seen_ids = set()
            merged = []
            for batch in results:
                if isinstance(batch, Exception):
                    continue
                for chunk in batch:
                    cid = chunk.get("id") or chunk.get("text", "")[:80]
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        merged.append(chunk)
            # Sort by score descending
            merged.sort(key=lambda x: x.get("score", 0), reverse=True)
            return merged[:k_per_query * 2]

        return _run_sync(_multi()) or []


# ─────────────────────────────────────────────────────────────────
# Retrieve function — pass to AesthetiCiteEngine
# ─────────────────────────────────────────────────────────────────

_retriever = HNSWVectorRetriever()


def hnsw_retrieve_fn(query: str, k: int = 14) -> List[Dict[str, Any]]:
    """
    Pass this as the retrieve_fn to AesthetiCiteEngine.

    In the engine initialisation (wherever AesthetiCiteEngine is instantiated):

    BEFORE:
        engine = AesthetiCiteEngine(
            retrieve_fn=some_keyword_fn,
            ...
        )

    AFTER:
        from app.api.hnsw_retriever import hnsw_retrieve_fn
        engine = AesthetiCiteEngine(
            retrieve_fn=hnsw_retrieve_fn,
            ...
        )
    """
    return _retriever.retrieve(query, k)


# ─────────────────────────────────────────────────────────────────
# CLI: run migration
# python fix6_hnsw.py migrate
# ─────────────────────────────────────────────────────────────────

async def _run_migration():
    pool = await _get_pool()
    async with pool.acquire() as con:
        for statement in MIGRATION_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    await con.execute(stmt)
                    print(f"OK: {stmt[:60]}...")
                except Exception as e:
                    print(f"WARN: {e} — {stmt[:60]}")
    print("\nHNSW migration complete.")
    print("Note: CONCURRENTLY index build runs in the background.")
    print("Monitor with: SELECT phase, blocks_done, blocks_total FROM pg_stat_progress_create_index;")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        asyncio.run(_run_migration())
    else:
        print("Usage: python fix6_hnsw.py migrate")
        print("\nThis will create HNSW indexes on your pgvector database.")
        print("Estimated time: 1-10 minutes depending on corpus size.")
        print("The CONCURRENTLY option means the database stays online during indexing.")
