"""
app/scripts/rechunk_missing.py  (v2 — optimised)

Re-chunk documents that have NO chunks at all.

Optimisations over v1:
  1. Pre-fetch all unchunked doc IDs once — avoids the expensive
     NOT EXISTS scan on every paginated query.
  2. chunk_index always starts at 0 (these docs have *no* existing
     chunks), so no SELECT MAX(chunk_index) needed per batch.
  3. executemany for inserts instead of per-row execute.
  4. Larger default batch (128) — fewer round trips.
  5. Fires an initial progress_cb with the total so the API can
     display it immediately.

Usage (standalone):
    python app/scripts/rechunk_missing.py
    python app/scripts/rechunk_missing.py --batch 256 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from typing import Callable, List, Optional, Tuple

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rechunk")

DATABASE_URL: str = os.environ["DATABASE_URL"]
CHUNK_SIZE   = 800   # chars — matches m5_ingest.py
BATCH_SIZE   = 128   # chunks per embed+insert round
FETCH_PAGE   = 1000  # doc IDs fetched from docs table per page


# ── Chunking ──────────────────────────────────────────────────────────────────

def make_chunks(title: str, abstract: str, chunk_size: int = CHUNK_SIZE) -> List[str]:
    """Identical to m5_ingest.py — 20 % word overlap."""
    title    = (title    or "").strip()
    abstract = (abstract or "").strip()
    full_text = f"{title}. {abstract}".strip(". ")
    if not full_text:
        return []
    words = full_text.split()
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            chunks.append(" ".join(current))
            overlap = max(1, len(current) // 5)
            current = current[-overlap:]
            current_len = sum(len(w) + 1 for w in current)
    if current:
        chunks.append(" ".join(current))
    return chunks if chunks else [full_text[:chunk_size]]


# ── Embedding ─────────────────────────────────────────────────────────────────

_embed_model = None

def _get_model():
    global _embed_model
    if _embed_model is None:
        from fastembed import TextEmbedding
        logger.info("Loading BAAI/bge-small-en-v1.5 …")
        _embed_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        logger.info("Embedding model ready.")
    return _embed_model


def embed_batch(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    return [v.tolist() for v in model.embed(texts)]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _vec_str(vec: List[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def _flush(conn, batch: List[Tuple[str, str, int]]) -> int:
    """
    Embed and insert a batch of (doc_id, chunk_text, chunk_index).
    Returns rows written.
    """
    if not batch:
        return 0
    _, texts, _ = zip(*batch)
    try:
        embeddings = embed_batch(list(texts))
    except Exception as exc:
        logger.error(f"Embedding failed ({len(batch)} chunks): {exc}")
        return 0

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO chunks (id, document_id, chunk_index, text, embedding, created_at)
            VALUES %s
            ON CONFLICT DO NOTHING
            """,
            [
                (str(uuid.uuid4()), doc_id, ci, text, _vec_str(emb))
                for (doc_id, text, ci), emb in zip(batch, embeddings)
            ],
            template="(%s, %s::uuid, %s, %s, %s::vector, NOW())",
            page_size=256,
        )
    conn.commit()
    return len(batch)


# ── Main re-chunk loop ────────────────────────────────────────────────────────

def run(
    batch_size: int = BATCH_SIZE,
    dry_run: bool = False,
    stop_flag=None,            # threading.Event — set to request cancellation
    progress_cb: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Find every document with no chunks and create + embed them.
    progress_cb(state) is called after each page of documents.
    Returns final stats dict.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    # ── Step 1: collect all unchunked doc IDs in one query ──────────────────
    logger.info("Collecting unchunked doc IDs …")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT d.id
            FROM documents d
            WHERE NOT EXISTS (
                SELECT 1 FROM chunks c WHERE c.document_id = d.id
            )
            ORDER BY d.id
        """)
        all_ids: List[str] = [r[0] for r in cur.fetchall()]

    total = len(all_ids)
    logger.info(f"Unchunked documents: {total:,}")

    if total == 0:
        conn.close()
        return {"total": 0, "processed": 0, "chunks_written": 0, "skipped": 0}

    stats = {
        "total": total,
        "processed": 0,
        "chunks_written": 0,
        "skipped": 0,
        "started_at": time.time(),
    }

    # Fire initial callback so the API shows total immediately
    if progress_cb:
        progress_cb({**stats, "elapsed_s": 0, "rate": 0.0, "eta_s": 0})

    # ── Step 2: iterate in pages fetching title+abstract by ID ──────────────
    chunk_batch: List[Tuple[str, str, int]] = []  # (doc_id, text, chunk_index)

    for page_start in range(0, total, FETCH_PAGE):
        if stop_flag and stop_flag.is_set():
            logger.info("Stop flag set — exiting loop.")
            break

        page_ids = all_ids[page_start: page_start + FETCH_PAGE]

        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT id, title, abstract FROM documents WHERE id = ANY(%s::uuid[])",
                (page_ids,),
            )
            rows = cur.fetchall()

        for row in rows:
            if stop_flag and stop_flag.is_set():
                break

            doc_id   = row["id"]
            title    = (row["title"]    or "").strip()
            abstract = (row["abstract"] or "").strip()

            if not title and not abstract:
                stats["skipped"] += 1
                continue

            chunks = make_chunks(title, abstract)
            for ci, chunk_text in enumerate(chunks):
                chunk_batch.append((doc_id, chunk_text, ci))
                if len(chunk_batch) >= batch_size:
                    if not dry_run:
                        written = _flush(conn, chunk_batch)
                        stats["chunks_written"] += written
                    chunk_batch = []

            stats["processed"] += 1

        elapsed = time.time() - stats["started_at"]
        rate    = stats["processed"] / elapsed if elapsed > 0 else 0
        eta     = (total - stats["processed"]) / rate if rate > 0 else 0
        pct     = stats["processed"] / total * 100

        logger.info(
            f"Progress: {stats['processed']:,}/{total:,} ({pct:.1f}%) | "
            f"chunks={stats['chunks_written']:,} | "
            f"rate={rate:.1f} docs/s | ETA={eta/60:.1f} min"
        )

        if progress_cb:
            progress_cb({**stats, "elapsed_s": elapsed, "rate": rate, "eta_s": eta})

    # Flush remainder
    if chunk_batch and not dry_run:
        written = _flush(conn, chunk_batch)
        stats["chunks_written"] += written

    conn.close()
    stats["elapsed_s"] = time.time() - stats["started_at"]
    logger.info(
        f"Done — {stats['processed']:,} docs re-chunked, "
        f"{stats['chunks_written']:,} chunks written, "
        f"{stats['skipped']:,} skipped (no text), "
        f"elapsed={stats['elapsed_s']/60:.1f} min"
    )
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch",   type=int, default=BATCH_SIZE, help="Chunks per embed batch")
    ap.add_argument("--dry-run", action="store_true",          help="Count only, no inserts")
    args = ap.parse_args()
    run(batch_size=args.batch, dry_run=args.dry_run)
