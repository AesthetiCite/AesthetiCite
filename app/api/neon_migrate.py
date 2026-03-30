"""
Neon Migration API — streams the chunks table from the current (Replit) DB
to Neon PostgreSQL using psql binary COPY for maximum speed.

After the data is copied, removes duplicates, then creates indexes.

Endpoints (admin-key protected):
  POST /api/neon-migrate/start?skip_copy=true  – launch (skip_copy to skip COPY phase)
  GET  /api/neon-migrate/status                – live progress
  POST /api/neon-migrate/stop                  – cancel job
"""

import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2

from fastapi import APIRouter, Header, HTTPException, Query

router = APIRouter(prefix="/api/neon-migrate", tags=["neon-migrate"])

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
SOURCE_URL = os.getenv("DATABASE_URL", "")
NEON_URL = (
    "postgresql://neondb_owner:npg_puKL9Pd7UMfG"
    "@ep-odd-star-amqythz1.c-5.us-east-1.aws.neon.tech"
    "/neondb?sslmode=require"
)

COPY_COLS = "id, document_id, chunk_index, text, page_or_section, evidence_level, embedding, created_at"

_state: dict = {
    "running": False,
    "phase": None,
    "started_at": None,
    "finished_at": None,
    "copy_done": False,
    "dedup_done": False,
    "indexes_done": False,
    "neon_rows": 0,
    "elapsed_s": 0.0,
    "error": None,
    "log_tail": [],
}
_lock = threading.Lock()
_stop_flag = threading.Event()


def _require_admin(key: Optional[str]) -> None:
    if not key or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin API key required")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(f"[neon-migrate] {line}", flush=True)
    with _lock:
        _state["log_tail"].append(line)
        if len(_state["log_tail"]) > 300:
            _state["log_tail"] = _state["log_tail"][-300:]


def _neon_conn(timeout: int = 300):
    conn = psycopg2.connect(NEON_URL, connect_timeout=30, options=f"-c statement_timeout={timeout * 1000}")
    conn.autocommit = True
    return conn


def _count_neon_rows() -> int:
    try:
        conn = psycopg2.connect(NEON_URL, connect_timeout=15)
        cur = conn.cursor()
        cur.execute(
            "SELECT reltuples::bigint FROM pg_class "
            "WHERE relname='chunks' AND relnamespace='public'::regnamespace"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return int(row[0]) if row and row[0] else 0
    except Exception:
        return -1


def _run_migration(skip_copy: bool = False) -> None:
    t_start = time.time()

    try:
        # ── Phase 1: COPY data ────────────────────────────────────────────────
        if skip_copy:
            _log("skip_copy=True — data already on Neon, skipping COPY")
            with _lock:
                _state["copy_done"] = True
                _state["phase"] = "De-duplicating chunks on Neon"
        else:
            with _lock:
                _state["phase"] = "COPY chunks → Neon"
            _log("Phase 1: Binary COPY from source to Neon")

            copy_out_sql = f"COPY (SELECT {COPY_COLS} FROM chunks) TO STDOUT WITH (FORMAT binary)"
            copy_in_sql  = f"COPY chunks ({COPY_COLS}) FROM STDIN WITH (FORMAT binary)"

            psql_out = subprocess.Popen(
                ["psql", SOURCE_URL, "-c", copy_out_sql],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            psql_in = subprocess.Popen(
                ["psql", NEON_URL, "-c", copy_in_sql],
                stdin=psql_out.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            psql_out.stdout.close()

            _log("COPY pipeline active — binary stream running")
            while True:
                if _stop_flag.is_set():
                    psql_out.kill(); psql_in.kill()
                    with _lock:
                        _state.update({"running": False, "phase": "stopped"})
                    return
                try:
                    psql_in.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.time() - t_start
                    with _lock:
                        _state["elapsed_s"] = elapsed
                    _log(f"  COPY running... {elapsed/60:.1f} min")

            out_stdout, out_stderr = psql_in.communicate()
            _src_out, src_stderr = psql_out.communicate()
            rc_in, rc_out = psql_in.returncode, psql_out.returncode

            if rc_out != 0:
                raise RuntimeError(f"Source COPY failed: {src_stderr.decode()[:400]}")
            if rc_in != 0:
                raise RuntimeError(f"Neon COPY failed: {out_stderr.decode()[:400]}")

            elapsed = time.time() - t_start
            _log(f"COPY done in {elapsed/60:.1f} min. Neon: {out_stdout.decode().strip()}")
            with _lock:
                _state["copy_done"] = True
                _state["phase"] = "ANALYZE + de-dup"

            _log("Running ANALYZE on Neon chunks...")
            try:
                conn = _neon_conn(600)
                conn.cursor().execute("ANALYZE chunks")
                conn.close()
                _log("ANALYZE done")
            except Exception as e:
                _log(f"ANALYZE warning: {e}")

        # ── Phase 2: De-duplicate ─────────────────────────────────────────────
        with _lock:
            _state["phase"] = "De-duplicating chunks on Neon"

        neon_rows_before = _count_neon_rows()
        with _lock:
            _state["neon_rows"] = neon_rows_before
        _log(f"Neon chunks before de-dup: {neon_rows_before:,}")

        _log("Removing duplicate chunk rows (keep min ctid per id)...")
        t_dedup = time.time()
        try:
            conn = _neon_conn(3600)
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM chunks a
                USING chunks b
                WHERE a.id = b.id
                  AND a.ctid > b.ctid
            """)
            deleted = cur.rowcount
            cur.close()
            conn.close()
            _log(f"De-dup done in {time.time()-t_dedup:.1f}s — removed {deleted:,} duplicates")
        except Exception as e:
            _log(f"De-dup warning (may already be clean): {e}")
            deleted = 0

        with _lock:
            _state["dedup_done"] = True

        neon_rows_after = _count_neon_rows()
        with _lock:
            _state["neon_rows"] = neon_rows_after
        _log(f"Neon chunks after de-dup: {neon_rows_after:,}")

        if _stop_flag.is_set():
            with _lock:
                _state.update({"running": False, "phase": "stopped"})
            return

        # ── Phase 3: Create indexes ───────────────────────────────────────────
        with _lock:
            _state["phase"] = "Creating indexes on Neon"
        _log("Phase 3: Creating indexes on Neon chunks")

        index_defs = [
            ("chunks_pkey",
             "ALTER TABLE chunks ADD CONSTRAINT chunks_pkey PRIMARY KEY (id)"),
            ("idx_chunks_document_id",
             "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks (document_id)"),
            ("idx_chunks_chunk_index",
             "CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON chunks (chunk_index)"),
            ("chunks_tsv_gin",
             "CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin(tsv)"),
            ("chunks_text_norm_trgm",
             "CREATE INDEX IF NOT EXISTS chunks_text_norm_trgm ON chunks USING gin(text_norm gin_trgm_ops)"),
            ("idx_chunks_embedding_hnsw",
             "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw "
             "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"),
        ]

        conn = _neon_conn(7200)
        cur = conn.cursor()

        for idx_name, idx_sql in index_defs:
            if _stop_flag.is_set():
                cur.close(); conn.close()
                with _lock:
                    _state.update({"running": False, "phase": "stopped"})
                return
            _log(f"  Creating {idx_name}...")
            t_idx = time.time()
            try:
                cur.execute(idx_sql)
                _log(f"  ✓ {idx_name} done in {time.time()-t_idx:.1f}s")
            except Exception as e:
                if "already exists" in str(e):
                    _log(f"  ✓ {idx_name} already exists")
                else:
                    _log(f"  ✗ {idx_name} FAILED: {e}")

        cur.close()
        conn.close()

        total_elapsed = time.time() - t_start
        with _lock:
            _state.update({
                "running": False,
                "phase": "complete",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "indexes_done": True,
                "elapsed_s": total_elapsed,
            })

        _log(f"Migration COMPLETE in {total_elapsed/60:.1f} min")
        _log("Next: update DATABASE_URL secret to Neon pooler URL and restart app")

    except Exception as exc:
        import traceback
        total_elapsed = time.time() - t_start
        _log(f"FATAL ERROR: {exc}")
        _log(traceback.format_exc())
        with _lock:
            _state.update({
                "running": False,
                "phase": "error",
                "error": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_s": total_elapsed,
            })


@router.post("/start")
async def start_migration(
    x_admin_key: Optional[str] = Header(None),
    skip_copy: bool = Query(False, description="Skip COPY phase — use if data already on Neon"),
):
    _require_admin(x_admin_key)

    with _lock:
        if _state["running"]:
            return {"status": "already_running", "state": _state}

    _stop_flag.clear()
    with _lock:
        _state.update({
            "running": True,
            "phase": "starting",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "copy_done": skip_copy,
            "dedup_done": False,
            "indexes_done": False,
            "neon_rows": 0,
            "elapsed_s": 0.0,
            "error": None,
            "log_tail": [],
        })

    t = threading.Thread(target=_run_migration, args=(skip_copy,), daemon=True)
    t.start()

    mode = "indexes-only (skip_copy)" if skip_copy else "full migration"
    return {"status": "started", "mode": mode}


@router.get("/status")
async def get_status(x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    with _lock:
        return dict(_state)


@router.post("/stop")
async def stop_migration(x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    _stop_flag.set()
    return {"status": "stop_requested"}
