"""
retrieval_hardening.py
AesthetiCite — Post-M2 retrieval hardening module

Usage:
    # Run database migration (indexes, cleanup, evidence levels):
    python app/rag/retrieval_hardening.py --migrate

    # Test retrieval with a query:
    python app/rag/retrieval_hardening.py --test "vascular occlusion after filler with blanching and pain"

    # Test with custom k and ef_search:
    python app/rag/retrieval_hardening.py --test "hyaluronidase protocol" --k 12 --ef-search 40

Environment:
    DATABASE_URL=postgresql://...
    AI_INTEGRATIONS_OPENAI_API_KEY=...   (same key FastAPI uses)
    AI_INTEGRATIONS_OPENAI_BASE_URL=...  (optional proxy — same as FastAPI)

Integration in FastAPI:
    from app.rag.retrieval_hardening import HardenedRetrieverAsync

    # In ask_v2.py startup:
    _hardened = HardenedRetrieverAsync()

    # In the stream handler:
    result = await _hardened.search(q, pool=_ar._pool, k=12)
    chunks  = result["chunks"]   # existing chunk dict format, drop-in for retrieve_db()
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

OPENAI_API_KEY: str = (
    os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or
    os.environ.get("OPENAI_API_KEY") or
    ""
)
OPENAI_BASE_URL: Optional[str] = (
    os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL") or None
)
OPENAI_ANSWER_MODEL = "gpt-4o-mini"


# ─────────────────────────────────────────────────────────────────────────────
# Migration SQL — schema-corrected for AesthetiCite production DB
# Column fixes vs. original:
#   chunks.content → chunks.text
#   documents.specialty_tag → documents.specialty
#   documents.publication_types → removed (column does not exist; doc_type used instead)
# ─────────────────────────────────────────────────────────────────────────────

_MIGRATION_TRANSACTIONAL = """
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Supporting indexes ───────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_documents_document_type
    ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_language
    ON documents(language);
CREATE INDEX IF NOT EXISTS idx_documents_year
    ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_specialty
    ON documents(specialty);
CREATE INDEX IF NOT EXISTS idx_documents_updated_at
    ON documents(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id
    ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index
    ON chunks(chunk_index);

-- ── Full-text search index on documents ─────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_documents_fts
    ON documents
    USING GIN (
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' || coalesce(abstract, '')
        )
    );

-- ── Cleanup: relabel obvious mislabels ───────────────────────────────────────

UPDATE documents
SET document_type = 'guideline'
WHERE (
    lower(coalesce(title, ''))
        ~ '(guideline|guidelines|consensus|recommendation|position statement|practice advisory|best practice)'
    OR lower(coalesce(abstract, ''))
        ~ '(guideline|consensus|recommendation|position statement|practice advisory|best practice)'
)
AND coalesce(document_type, '') <> 'guideline';

UPDATE documents
SET document_type = 'review'
WHERE (
    lower(coalesce(title, ''))
        ~ '(systematic review|meta-analysis|meta analysis|umbrella review|scoping review|narrative review)'
)
AND coalesce(document_type, '') NOT IN ('review', 'guideline');

UPDATE documents
SET document_type = 'journal_article'
WHERE coalesce(document_type, '') = 'prescribing_information'
AND (
    pmid IS NOT NULL
    OR (lower(coalesce(organization_or_journal, '')) <> '')
    OR lower(coalesce(title, ''))
        ~ '(trial|study|cohort|retrospective|prospective|analysis|review|randomized|case-control|observational)'
);

UPDATE documents
SET document_type = 'prescribing_information'
WHERE (
    lower(coalesce(title, ''))
        ~ '(prescribing information|package insert|summary of product characteristics|smpc|instructions for use)'
    OR lower(coalesce(abstract, ''))
        ~ '(prescribing information|package insert|summary of product characteristics|smpc)'
)
AND coalesce(document_type, '') <> 'prescribing_information';

-- ── Evidence levels: align chunk evidence_level with document type ────────────
UPDATE chunks c
SET evidence_level = CASE
    WHEN d.document_type = 'guideline'
        THEN 'I'
    WHEN d.document_type = 'review'
        AND lower(coalesce(d.title, '')) ~ '(systematic review|meta-analysis|meta analysis)'
        THEN 'I'
    WHEN d.document_type = 'review'
        THEN 'II'
    WHEN d.document_type = 'journal_article'
        AND lower(coalesce(d.title, ''))
            ~ '(randomized|randomised|trial|double-blind|placebo-controlled|phase ii|phase iii)'
        THEN 'II'
    WHEN d.document_type = 'journal_article'
        THEN 'III'
    WHEN d.document_type = 'case_series'
        THEN 'III'
    WHEN d.document_type IN ('case_report', 'prescribing_information')
        THEN 'IV'
    ELSE coalesce(c.evidence_level, 'III')
END
FROM documents d
WHERE c.document_id = d.id;
"""

_HNSW_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw
ON chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
"""


# ─────────────────────────────────────────────────────────────────────────────
# Migration runner
# ─────────────────────────────────────────────────────────────────────────────

def run_migration(database_url: str = DATABASE_URL) -> None:
    import psycopg2

    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")

    conn = psycopg2.connect(database_url, connect_timeout=10)

    print("Step 1/3: Running indexes, cleanup, evidence level alignment...")
    try:
        conn.autocommit = False
        stmts = [s.strip() for s in _MIGRATION_TRANSACTIONAL.split(";") if s.strip()]
        with conn.cursor() as cur:
            for stmt in stmts:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    logger.warning(f"  Statement warning (non-fatal): {e}")
                    conn.rollback()
        conn.commit()
        print("  ✓ Done")
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Migration failed: {e}") from e

    print("Step 2/3: Checking vector index...")
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname, indexdef FROM pg_indexes
                WHERE tablename = 'chunks'
                  AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')
            """)
            existing = cur.fetchall()
            if existing:
                print(f"  ✓ Vector index already present: {existing[0][0]} (skipping CONCURRENTLY build)")
            else:
                print("  Creating IVFFlat index (no /dev/shm for HNSW)...")
                t0 = time.time()
                cur.execute("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw
                    ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
                """)
                print(f"  ✓ IVFFlat index created in {time.time()-t0:.0f}s")
    except Exception as e:
        print(f"  ⚠ Index step: {e}")
    finally:
        conn.autocommit = False

    print("Step 3/3: Verifying...")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
                FROM pg_indexes WHERE tablename = 'chunks' ORDER BY indexname
            """)
            for row in cur.fetchall():
                print(f"    {row[0]}: {row[1]}")

            cur.execute("SELECT COUNT(*) FROM chunks")
            print(f"  Chunk count: {cur.fetchone()[0]:,}")

            cur.execute("""
                SELECT document_type, COUNT(*) AS n
                FROM documents GROUP BY document_type ORDER BY n DESC LIMIT 10
            """)
            print("  Document type distribution:")
            for row in cur.fetchall():
                print(f"    {row[0] or 'NULL'}: {row[1]:,}")
    except Exception as e:
        print(f"  ⚠ Verification query failed: {e}")

    conn.close()
    print("\n✓ Migration complete. Restart FastAPI to pick up new indexes.")


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval SQL — schema-corrected
# ─────────────────────────────────────────────────────────────────────────────

# IVFFlat probe count used in place of hnsw.ef_search
_IVFFLAT_PROBES = 5

# Secondary ORDER BY sort injected for protocol-mode queries.
# Promotes guidelines → consensus → sys-reviews → Level II → reviews → other,
# surfacing the most actionable evidence first within the same final_score tier.
# Sourced from protocol_engine_app.py and merged here per the scratchpad plan.
_PROTOCOL_SORT_SQL = (
    "CASE"
    "\n        WHEN document_type = 'guideline' THEN 0"
    "\n        WHEN lower(coalesce(title, '')) ~"
    " '(consensus|position statement|recommendation|best practice|practice advisory)'"
    " THEN 1"
    "\n        WHEN document_type = 'review'"
    " AND lower(coalesce(title, '')) ~"
    " '(systematic review|meta-analysis|meta analysis|umbrella review)'"
    " THEN 2"
    "\n        WHEN evidence_level = 'II' THEN 3"
    "\n        WHEN document_type = 'review' THEN 4"
    "\n        ELSE 5"
    "\n    END"
)

_RETRIEVAL_SQL = """
SET ivfflat.probes = {ivfflat_probes};
SET hnsw.ef_search = {ef_search};

WITH
-- IMPORTANT: vector_ids has NO JOIN so PostgreSQL can use the IVFFlat index
-- for ORDER BY + LIMIT (joining inside the CTE forces a full table scan).
vector_ids AS (
    SELECT c.id AS chunk_id,
           (c.embedding <=> $1::vector) AS vector_distance,
           0.0::float AS text_rank
    FROM chunks c
    WHERE c.embedding IS NOT NULL
    ORDER BY c.embedding <=> $1::vector
    LIMIT 120
),
text_ids AS (
    SELECT c.id AS chunk_id,
           1.0::float AS vector_distance,
           ts_rank_cd(c.tsv, plainto_tsquery('english', $2)) AS text_rank
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'active'
      AND c.tsv @@ plainto_tsquery('english', $2)
    ORDER BY text_rank DESC
    LIMIT 120
),
candidate_ids AS (
    SELECT chunk_id, vector_distance, text_rank FROM vector_ids
    UNION ALL
    SELECT chunk_id, vector_distance, text_rank FROM text_ids
),
merged AS (
    SELECT chunk_id,
           min(vector_distance) AS vector_distance,
           max(text_rank)       AS text_rank
    FROM candidate_ids
    GROUP BY chunk_id
),
-- Now join the full document metadata only for the (much smaller) merged set
enriched AS (
    SELECT
        m.chunk_id,
        m.vector_distance,
        m.text_rank,
        c.document_id,
        c.chunk_index,
        c.text           AS content,
        c.evidence_level,
        d.source_id,
        d.title,
        d.abstract,
        d.url,
        d.organization_or_journal,
        d.journal,
        d.year,
        d.language,
        d.document_type,
        d.specialty
    FROM merged m
    JOIN chunks c ON c.id = m.chunk_id
    JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'active'
),
dedup AS (
    SELECT DISTINCT ON (chunk_id) *
    FROM enriched
),
scored AS (
    SELECT
        *,
        (1.0 - LEAST(vector_distance, 1.0))  AS vector_score,
        LEAST(text_rank, 1.0)                 AS keyword_score,
        CASE
            WHEN document_type = 'guideline'
                THEN 5.0
            WHEN lower(coalesce(title, '')) ~
                '(consensus|position statement|recommendation|best practice|practice advisory)'
                THEN 4.6
            WHEN document_type = 'review'
                AND lower(coalesce(title, '')) ~
                    '(systematic review|meta-analysis|meta analysis|umbrella review)'
                THEN 4.2
            WHEN document_type = 'review'
                THEN 3.1
            WHEN document_type = 'journal_article'
                AND lower(coalesce(title, '')) ~
                    '(randomized|randomised|trial|double-blind|placebo-controlled|phase ii|phase iii)'
                THEN 3.5
            WHEN document_type = 'journal_article'
                THEN 2.4
            WHEN document_type = 'case_series'
                THEN 1.7
            WHEN document_type = 'case_report'
                THEN 1.2
            WHEN document_type = 'prescribing_information'
                THEN 0.9
            ELSE 1.0
        END AS evidence_boost,
        CASE
            WHEN evidence_level = 'I'   THEN 1.8
            WHEN evidence_level = 'II'  THEN 1.4
            WHEN evidence_level = 'III' THEN 1.0
            WHEN evidence_level = 'IV'  THEN 0.7
            ELSE 1.0
        END AS level_boost,
        CASE
            WHEN year >= 2022 THEN 1.15
            WHEN year >= 2018 THEN 1.08
            WHEN year >= 2010 THEN 1.00
            ELSE 0.92
        END AS recency_boost,
        CASE
            WHEN lower(coalesce(specialty, '')) ~
                '(aesthetic|dermatology|injectables|skin procedures|energy devices|plastic surgery|body contouring)'
            THEN 1.12
            ELSE 1.0
        END AS specialty_boost
    FROM dedup
),
final AS (
    SELECT
        chunk_id,
        document_id,
        chunk_index,
        content,
        evidence_level,
        source_id,
        title,
        abstract,
        url,
        organization_or_journal,
        journal,
        year,
        language,
        document_type,
        specialty,
        ROUND((
            ((vector_score * 0.52) + (keyword_score * 0.48))
            * evidence_boost
            * level_boost
            * recency_boost
            * specialty_boost
        )::numeric, 6) AS final_score
    FROM scored
)
SELECT * FROM final
ORDER BY final_score DESC, year DESC NULLS LAST
LIMIT $3;
"""
# Note: protocol_mode secondary sort is injected at call time via
# sql.replace(...) in search() — see _PROTOCOL_SORT_SQL above.
# The placeholder string below is what gets replaced when protocol_mode=True.
_ORDER_BY_PLAIN = "ORDER BY final_score DESC, year DESC NULLS LAST"


# ─────────────────────────────────────────────────────────────────────────────
# Language helpers
# ─────────────────────────────────────────────────────────────────────────────

def detect_answer_language(query: str) -> str:
    if re.search(r"[àâçéèêëîïôûùüÿœæ]", query.lower()):
        return "French"
    if re.search(r"[áéíóúñ¿¡ü]", query.lower()):
        return "Spanish"
    if re.search(r"[\u0600-\u06FF]", query):
        return "Arabic"
    if re.search(r"[\u4e00-\u9fff]", query):
        return "Chinese"
    return "English"


def translate_to_english(query: str) -> str:
    if not OPENAI_API_KEY:
        return query
    detected_lang = detect_answer_language(query)
    if detected_lang == "English":
        return query
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        resp = client.chat.completions.create(
            model=OPENAI_ANSWER_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "Translate this medical search query to concise professional English for retrieval.\n"
                    "Keep drug names, anatomy, procedures, and symptoms precise.\n"
                    "Return only the translated query, nothing else.\n\n"
                    f"Query: {query}"
                )
            }],
            max_tokens=200,
            temperature=0.0,
        )
        translated = resp.choices[0].message.content.strip()
        return translated if translated else query
    except Exception as e:
        logger.warning(f"Translation failed, using original query: {e}")
        return query


def build_tsquery(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"[^\w\s\-\/]", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Row → existing chunk dict adapter
# Maps hardened retriever rows to the format expected by ask_v2.py and
# ask_stream.py (_build_citations_payload, _build_single_call_prompt, etc.)
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_chunk(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": row.get("source_id") or str(row.get("document_id", "")),
        "id": str(row.get("chunk_id", "")),
        "title": row.get("title", ""),
        "text": row.get("content", ""),
        "year": row.get("year"),
        "organization_or_journal": (
            row.get("organization_or_journal") or row.get("journal", "")
        ),
        "journal": row.get("journal", "") or row.get("organization_or_journal", ""),
        "page_or_section": (
            str(row.get("chunk_index")) if row.get("chunk_index") is not None else ""
        ),
        "evidence_level": row.get("evidence_level"),
        "document_type": row.get("document_type"),
        "domain": row.get("specialty", ""),
        "language": row.get("language", ""),
        "abstract": row.get("abstract", ""),
        "url": row.get("url", "") or "",
        "_score": float(row.get("final_score") or 0.0),
        "vdist": None,
        "krank": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────────────────────────────────────

_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        import os, pathlib
        if not os.environ.get("FASTEMBED_CACHE_PATH"):
            os.environ["FASTEMBED_CACHE_PATH"] = str(
                pathlib.Path(__file__).resolve().parents[2] / ".fastembed_cache"
            )
        from fastembed import TextEmbedding
        _embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
    return _embedding_model


def embed_query(text: str) -> List[float]:
    model = _get_embedding_model()
    vectors = list(model.embed([text]))
    return vectors[0].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Synchronous retriever (CLI testing + migration)
# ─────────────────────────────────────────────────────────────────────────────

class HardenedRetrieverSync:
    def __init__(self, database_url: str = DATABASE_URL):
        import psycopg2
        import psycopg2.extras
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set.")
        self.conn = psycopg2.connect(database_url, connect_timeout=10)
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras

    def search(
        self,
        user_query: str,
        k: int = 8,
        ef_search: int = 40,
        protocol_mode: bool = False,
    ) -> Dict[str, Any]:
        retrieval_query = translate_to_english(user_query)
        answer_language = detect_answer_language(user_query)
        embedding = embed_query(retrieval_query)
        keyword_q = build_tsquery(retrieval_query)

        sql = _RETRIEVAL_SQL.format(
            ef_search=int(ef_search),
            ivfflat_probes=int(_IVFFLAT_PROBES),
        )
        if protocol_mode:
            sql = sql.replace(
                _ORDER_BY_PLAIN,
                f"ORDER BY final_score DESC, {_PROTOCOL_SORT_SQL}, year DESC NULLS LAST",
            )

        t0 = time.perf_counter()
        with self.conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
            cur.execute(sql, (embedding, keyword_q, k))
            rows = cur.fetchall()
        retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)

        evidence = [dict(r) for r in rows]
        chunks = [_row_to_chunk(r) for r in evidence]
        citations = _build_citations(evidence)

        return {
            "query": user_query,
            "retrieval_query_en": retrieval_query,
            "answer_language": answer_language,
            "retrieval_ms": retrieval_ms,
            "evidence": evidence,
            "chunks": chunks,
            "citations": citations,
            "citations_grounded": bool(citations),
            "citation_mode": "strict-server-grounded",
        }

    def search_with_answer(
        self,
        user_query: str,
        k: int = 8,
        ef_search: int = 40,
    ) -> Dict[str, Any]:
        result = self.search(user_query, k=k, ef_search=ef_search)
        result["answer"] = _generate_answer(
            user_query=user_query,
            answer_language=result["answer_language"],
            citations=result["citations"],
        )
        return sanitize_grounded_payload(result)

    def close(self) -> None:
        self.conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Async retriever — FastAPI integration
# ─────────────────────────────────────────────────────────────────────────────

class HardenedRetrieverAsync:
    """
    Async retriever using the existing asyncpg pool from app.rag.async_retriever.

    Usage in FastAPI (ask_v2.py):
        from app.rag.retrieval_hardening import HardenedRetrieverAsync
        from app.rag import async_retriever as _ar

        _hardened = HardenedRetrieverAsync()

        # In the stream handler:
        result = await _hardened.search(q, pool=_ar._pool, k=12)
        chunks = result["chunks"]   # drop-in for retrieve_db() output
    """

    async def search(
        self,
        user_query: str,
        pool: Any,
        k: int = 12,
        ef_search: int = 40,
        protocol_mode: bool = False,
    ) -> Dict[str, Any]:
        import asyncio

        if pool is None:
            raise RuntimeError("asyncpg pool is not initialised.")

        retrieval_query = await asyncio.to_thread(translate_to_english, user_query)
        answer_language = detect_answer_language(user_query)

        # IMPORTANT: use the same embedding model that was used to create the
        # production chunk embeddings (all-MiniLM-L6-v2 via app.rag.embedder).
        # The local embed_query() uses BAAI/bge-small-en-v1.5 which is a
        # DIFFERENT vector space — using it would produce garbage retrieval.
        # asyncpg also requires the vector as a pgvector string "[v1,v2,...]",
        # NOT a Python list.
        try:
            from app.rag.embedder import embed_text as _embed_text_prod
            _embedding_raw = await asyncio.to_thread(_embed_text_prod, retrieval_query)
        except Exception:
            _embedding_raw = await asyncio.to_thread(embed_query, retrieval_query)
        embedding = "[" + ",".join(str(v) for v in _embedding_raw) + "]"
        keyword_q = build_tsquery(retrieval_query)

        set_sql = (
            f"SET ivfflat.probes = {_IVFFLAT_PROBES}; "
            f"SET hnsw.ef_search = {int(ef_search)};"
        )
        # Strip the SET lines from the template (first two lines)
        query_lines = _RETRIEVAL_SQL.strip().splitlines()
        query_sql = "\n".join(
            l for l in query_lines
            if not l.strip().startswith("SET ")
        )
        if protocol_mode:
            query_sql = query_sql.replace(
                _ORDER_BY_PLAIN,
                f"ORDER BY final_score DESC, {_PROTOCOL_SORT_SQL}, year DESC NULLS LAST",
            )

        t0 = time.perf_counter()
        async with pool.acquire() as conn:
            await conn.execute(set_sql)
            rows = await conn.fetch(query_sql, embedding, keyword_q, k)
        retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)

        evidence = [dict(r) for r in rows]
        chunks = [_row_to_chunk(r) for r in evidence]
        citations = _build_citations(evidence)

        return {
            "query": user_query,
            "retrieval_query_en": retrieval_query,
            "answer_language": answer_language,
            "retrieval_ms": retrieval_ms,
            "evidence": evidence,
            "chunks": chunks,
            "citations": citations,
            "citations_grounded": bool(citations),
            "citation_mode": "strict-server-grounded",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Citation builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_citations(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": f"S{i + 1}",
            "chunk_id": str(r.get("chunk_id", "")),
            "document_id": str(r.get("document_id", "")),
            "source_id": r.get("source_id") or str(r.get("document_id", "")),
            "title": r.get("title") or f"Source {i + 1}",
            "locator": f"Chunk {r['chunk_index']}" if r.get("chunk_index") is not None else "",
            "snippet": (r.get("content") or "")[:500],
            "url": r.get("url"),
            "document_type": r.get("document_type"),
            "evidence_level": r.get("evidence_level"),
            "year": r.get("year"),
            "journal": r.get("journal") or r.get("organization_or_journal", ""),
            "score": float(r.get("final_score") or 0.0),
        }
        for i, r in enumerate(evidence)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Answer generation
# ─────────────────────────────────────────────────────────────────────────────

def _generate_answer(
    user_query: str,
    answer_language: str,
    citations: List[Dict[str, Any]],
) -> str:
    if not OPENAI_API_KEY:
        return (
            "Grounded retrieval complete. "
            "Answer generation is disabled (AI_INTEGRATIONS_OPENAI_API_KEY not set)."
        )

    if not citations:
        return "Evidence insufficient — no sources were retrieved for this query."

    evidence_block = "\n\n".join(
        f"[{c['id']}] {c['title']} | "
        f"{c.get('document_type', '')} | "
        f"Level {c.get('evidence_level', '?')} | "
        f"{c.get('journal', '')} {c.get('year', '')}\n"
        f"{c.get('snippet', '')}"
        for c in citations
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        resp = client.chat.completions.create(
            model=OPENAI_ANSWER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a clinical evidence assistant for AesthetiCite. "
                        "Answer only from the provided evidence. "
                        "Prefer guidelines and systematic reviews when they exist. "
                        "If evidence is weak or mixed, say so explicitly. "
                        "Never invent citations, journals, study names, or URLs. "
                        f"Answer in {answer_language}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {user_query}\n\n"
                        f"Evidence:\n{evidence_block}\n\n"
                        "Instructions: Cite only using the provided IDs (e.g. [S1]). "
                        "If the evidence does not support a claim, do not make it."
                    ),
                },
            ],
            max_tokens=1200,
            temperature=0.15,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Answer generation failed: {e}")
        return f"Answer generation failed. Retrieval succeeded with {len(citations)} sources."


# ─────────────────────────────────────────────────────────────────────────────
# Citation sanitizer
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_grounded_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    citations: List[Dict[str, Any]] = payload.get("citations") or []
    valid_ids: set = {str(c["id"]) for c in citations if c.get("id")}
    answer: str = payload.get("answer") or ""

    if answer:
        def _keep_if_valid(m: re.Match) -> str:
            return m.group(0) if m.group(1).strip() in valid_ids else ""

        answer = re.sub(r"\[([^\[\]]+)\]", _keep_if_valid, answer)
        answer = re.sub(r"【([^】]+)】", _keep_if_valid, answer)
        answer = re.sub(r"\[\^([^\]]+)\]", _keep_if_valid, answer)
        answer = re.sub(r"[ \t]+(\n|$)", r"\1", answer)
        answer = re.sub(r"\n{3,}", "\n\n", answer).strip()

    return {
        **payload,
        "answer": answer,
        "citations": citations,
        "citations_grounded": bool(citations),
        "citation_mode": "strict-server-grounded",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AesthetiCite retrieval hardening — migration and test tool"
    )
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--test", type=str, default="", metavar="QUERY")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--ef-search", type=int, default=40)
    parser.add_argument("--no-answer", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.migrate and not args.test:
        parser.print_help()
        return

    if args.migrate:
        run_migration()

    if args.test:
        print(f"\nQuery: {args.test}")
        print(f"k={args.k}  ef_search={args.ef_search}\n")
        engine = HardenedRetrieverSync()
        try:
            if args.no_answer:
                result = engine.search(args.test, k=args.k, ef_search=args.ef_search)
            else:
                result = engine.search_with_answer(args.test, k=args.k, ef_search=args.ef_search)
            display = {k: v for k, v in result.items() if k not in ("evidence", "chunks")}
            display["top_sources"] = [
                {
                    "id": c["id"],
                    "title": c["title"],
                    "type": c.get("document_type"),
                    "level": c.get("evidence_level"),
                    "year": c.get("year"),
                    "score": c.get("score"),
                }
                for c in result.get("citations", [])
            ]
            print(json.dumps(display, indent=2, ensure_ascii=False, default=str))
        finally:
            engine.close()


if __name__ == "__main__":
    main()
