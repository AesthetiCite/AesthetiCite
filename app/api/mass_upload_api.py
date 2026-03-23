"""
Mass Upload API — persistent background thread inside the FastAPI server.

Endpoints:
  POST /api/mass-upload/start         — Start engine (idempotent; resumes from saved index)
  GET  /api/mass-upload/status        — Full state: phase flags, policy flags, recommendation
  POST /api/mass-upload/stop          — Graceful stop after current batch
  POST /api/mass-upload/set-policy    — Set one or more operational policy flags
  POST /api/mass-upload/reset-phase   — Force a phase to re-run (admin only)

Execution roadmap (enforced in engine):
  1. M1 — Clean corpus          (SQL cleanup; skipped only if m1_completed)
  2. M2 — Authoritative corpus  (guideline ingestion; MANDATORY, never skipped by count)
  ── GATE: guideline_priority_enabled must be True ───────────────────────────────────
  ── GATE: multilang_retrieval_fixed must be True  ───────────────────────────────────
  3. M3 — Globally usable       (multilingual ingestion; hard-blocked until both gates pass)
  4. M4 — Broad & defensible    (full sweep; warns if guideline_priority is still False)

Policy flags (set via /set-policy):
  corpus_cleanup_verified   — soft requirement before M2 (warns if False, doesn't block)
  guideline_priority_enabled — hard gate before M3/M4 (engine halts if False after M2)
  multilang_retrieval_fixed  — hard gate before M3 (engine halts if False)
"""
from __future__ import annotations

import threading
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.admin_auth import require_admin

logger = logging.getLogger("mass_upload_api")
router = APIRouter(prefix="/api/mass-upload", tags=["mass-upload"])

_thread: threading.Thread | None = None


def _run_in_thread():
    """Wrapper: 15s boot delay, then runs the corpus engine."""
    import time
    time.sleep(15)
    from app.agents.mass_upload import run_mass_upload, _state, _lock
    try:
        run_mass_upload()
    except Exception as e:
        logger.error(f"Mass upload crashed: {e}")
        with _lock:
            _state["running"] = False
            _state["error"] = str(e)


# ─── Request / Response schemas ──────────────────────────────────────────────

class RebuildIndexResponse(BaseModel):
    status: str
    message: str


_index_rebuild_status: dict = {"running": False, "done": False, "error": None, "started_at": None}
_index_rebuild_lock = threading.Lock()


def _do_rebuild_index():
    """Run inside a background thread (already in server process — survives idle-timeout)."""
    import time, os
    import psycopg2
    global _index_rebuild_status
    try:
        # keepalives prevent the Replit network proxy from silently dropping a 
        # long-running idle TCP connection during the CREATE INDEX build.
        conn = psycopg2.connect(
            os.environ["DATABASE_URL"],
            keepalives=1,
            keepalives_idle=30,       # start probing after 30s of silence
            keepalives_interval=10,   # probe every 10s
            keepalives_count=5,       # 5 failures → connection dead
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw")
        logger.info("[index-rebuild] Old index dropped. Building IVFFlat (lists=100, non-concurrent)...")
        # Non-concurrent: single-pass build — avoids multi-phase TCP timeout on Replit's network proxy.
        # No DML on chunks during the gate-pause, so blocking lock is acceptable.
        cur.execute("SET max_parallel_maintenance_workers = 0")
        cur.execute("SET maintenance_work_mem = '32MB'")
        cur.execute("SET lock_timeout = '0'")          # no timeout on lock acquisition
        cur.execute("SET statement_timeout = '0'")     # no timeout on the build itself
        cur.execute("""
            CREATE INDEX idx_chunks_embedding_hnsw
            ON chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
        cur.execute("""
            SELECT indexname, indisvalid FROM pg_indexes i
            JOIN pg_class c ON c.relname=i.indexname
            JOIN pg_index ix ON ix.indexrelid=c.oid
            WHERE i.indexname='idx_chunks_embedding_hnsw'
        """)
        row = cur.fetchone()
        conn.close()
        with _index_rebuild_lock:
            _index_rebuild_status["running"] = False
            _index_rebuild_status["done"] = True
            _index_rebuild_status["error"] = None if (row and row[1]) else "index created but invalid"
        logger.info(f"[index-rebuild] Done — valid={row[1] if row else 'missing'}")
    except Exception as e:
        logger.error(f"[index-rebuild] Failed: {e}")
        with _index_rebuild_lock:
            _index_rebuild_status["running"] = False
            _index_rebuild_status["error"] = str(e)


class SetPolicyRequest(BaseModel):
    """
    Set one or more operational policy flags.
    Only fields explicitly included in the request are updated.
    Omit a field to leave its current value unchanged.
    """
    corpus_cleanup_verified: Optional[bool] = None
    guideline_priority_enabled: Optional[bool] = None
    multilang_retrieval_fixed: Optional[bool] = None


class StatusResponse(BaseModel):
    # ── Runtime ──────────────────────────────────────────────────────────────
    running: bool
    started_at: Optional[str]
    milestone: int
    milestone_label: str
    milestones: dict
    docs_start: int
    docs_inserted: int
    docs_skipped: int
    docs_failed: int
    queries_done: int
    queries_total: int
    current_db_count: int
    target: int
    pct_complete: float
    last_query: str
    quality_op: str
    error: Optional[str]
    # ── Phase completion flags ────────────────────────────────────────────────
    m1_completed: bool
    m2_completed: bool
    m3_completed: bool
    m4_completed: bool
    m5_completed: bool
    # ── Operational policy flags ──────────────────────────────────────────────
    corpus_cleanup_verified: bool
    guideline_priority_enabled: bool
    multilang_retrieval_fixed: bool
    # ── Resumability ─────────────────────────────────────────────────────────
    current_phase: int
    current_query_index: int
    last_run_at: Optional[str]
    # ── Recommendation ────────────────────────────────────────────────────────
    next_recommended_phase: int
    next_recommended_action: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/start")
def start_upload(_: str = Depends(require_admin)):
    """
    Start the corpus engine.  Idempotent — no-op if already running.
    Loads progress from disk and resumes from the last saved query index.

    Phase order: M1 → M2 → [guideline_priority gate] → [multilang gate] → M3 → M4.
    M2 is always run unless m2_completed is already True.
    """
    global _thread
    from app.agents.mass_upload import _state, _lock, TARGET_DOCS
    with _lock:
        if _state["running"]:
            return {"status": "already_running", "message": "Upload is already in progress"}
        _state["running"] = True
        _state["stop_requested"] = False
        _state["started_at"] = datetime.utcnow().isoformat()
        _state["docs_inserted"] = 0
        _state["docs_skipped"] = 0
        _state["docs_failed"] = 0
        _state["queries_done"] = 0
        _state["error"] = None

    _thread = threading.Thread(target=_run_in_thread, name="mass-upload", daemon=True)
    _thread.start()
    return {
        "status": "started",
        "message": (
            f"Corpus engine started — target {TARGET_DOCS:,}. "
            "Phase order: M1 (clean) → M2 (authoritative) → "
            "[guideline_priority gate] → [multilang gate] → M3 (global) → M4 (broad). "
            "Check /status for current recommendation."
        ),
    }


@router.post("/stop")
def stop_upload(_: str = Depends(require_admin)):
    """
    Graceful stop.  Engine halts after the current PubMed fetch batch
    and saves the query index for exact resumption on next start.
    """
    from app.agents.mass_upload import _state, _lock
    with _lock:
        if not _state["running"]:
            return {"status": "not_running"}
        _state["stop_requested"] = True
    return {
        "status": "stop_requested",
        "message": "Engine will halt after current batch and save progress for resumability.",
    }


@router.post("/rebuild-index", response_model=RebuildIndexResponse)
def rebuild_index(_: str = Depends(require_admin)):
    """
    Start a background rebuild of the vector similarity index (IVFFlat, lists=1000).
    Runs inside the server process — immune to Replit idle-timeout kills.
    Call GET /rebuild-index-status to monitor progress.
    """
    from datetime import datetime
    with _index_rebuild_lock:
        if _index_rebuild_status["running"]:
            return RebuildIndexResponse(status="already_running", message="Index rebuild already in progress.")
        _index_rebuild_status["running"] = True
        _index_rebuild_status["done"] = False
        _index_rebuild_status["error"] = None
        _index_rebuild_status["started_at"] = datetime.utcnow().isoformat()
    t = threading.Thread(target=_do_rebuild_index, name="index-rebuild", daemon=True)
    t.start()
    return RebuildIndexResponse(
        status="started",
        message="IVFFlat index rebuild started in background. Poll /api/mass-upload/rebuild-index-status for progress."
    )


@router.get("/rebuild-index-status")
def rebuild_index_status(_: str = Depends(require_admin)):
    """Check the status of a running or completed index rebuild."""
    with _index_rebuild_lock:
        return dict(_index_rebuild_status)


@router.post("/set-policy")
def set_policy(body: SetPolicyRequest, _: str = Depends(require_admin)):
    """
    Set one or more operational policy flags.

    corpus_cleanup_verified (bool):
      Signals that M1 results have been manually reviewed — evidence levels
      spot-checked, mislabeled documents corrected.
      Effect: removes the M2 pre-flight warning.

    guideline_priority_enabled (bool):
      Signals that the retrieval layer now explicitly boosts guidelines and
      consensus documents in ranking.
      Effect: unblocks the gate between M2 and M3/M4.
      Requirement: implement guideline boosting in the retrieval layer first.

    multilang_retrieval_fixed (bool):
      Signals that the multilingual retrieval strategy is corrected.
      Correct strategy: language detection → translate-to-English retrieval →
      answer translation back to user language.
      Effect: unblocks M3.
      Requirement: confirm all three steps above are live in production.
    """
    from app.agents.mass_upload import _state, _lock, _save_progress, _compute_next_recommended

    updates: dict = {}
    if body.corpus_cleanup_verified is not None:
        updates["corpus_cleanup_verified"] = body.corpus_cleanup_verified
    if body.guideline_priority_enabled is not None:
        updates["guideline_priority_enabled"] = body.guideline_priority_enabled
    if body.multilang_retrieval_fixed is not None:
        updates["multilang_retrieval_fixed"] = body.multilang_retrieval_fixed

    if not updates:
        raise HTTPException(status_code=400, detail="No policy fields provided.")

    with _lock:
        for k, v in updates.items():
            _state[k] = v
        rec = _compute_next_recommended()
        _state["next_recommended_phase"] = rec.phase
        _state["next_recommended_action"] = rec.action

    _save_progress()
    logger.info(f"[policy] Updated: {updates}")

    return {
        "status": "ok",
        "updated": updates,
        "next_recommended_phase": rec.phase,
        "next_recommended_action": rec.action,
    }


@router.post("/reset-phase")
def reset_phase(phase: int, _: str = Depends(require_admin)):
    """
    Clear the completion flag for a specific phase (1–5) so it re-runs on next start.
    Also resets current_query_index if that phase was the last active one.
    """
    if phase not in (1, 2, 3, 4, 5):
        raise HTTPException(status_code=400, detail="phase must be 1, 2, 3, 4, or 5")
    from app.agents.mass_upload import _state, _lock, _save_progress
    with _lock:
        _state[f"m{phase}_completed"] = False
        if _state.get("current_phase") == phase:
            _state["current_query_index"] = 0
    _save_progress()
    return {
        "status": "ok",
        "message": f"M{phase} completion flag cleared — will re-run on next engine start.",
    }


@router.get("/status", response_model=StatusResponse)
def get_status():
    """
    Returns complete engine state:
    - Runtime counters (docs inserted, skipped, failed)
    - Phase completion flags (m1_completed … m5_completed)
    - Operational policy flags (corpus_cleanup_verified, guideline_priority_enabled,
      multilang_retrieval_fixed)
    - Resumability info (current_phase, current_query_index)
    - Next recommended phase and human-readable action string
    """
    from app.agents.mass_upload import _state, _lock, TARGET_DOCS, MILESTONES
    with _lock:
        count = _state.get("current_db_count", 0)
        pct   = round(count / TARGET_DOCS * 100, 2) if TARGET_DOCS > 0 else 0
        return StatusResponse(
            running                   = _state["running"],
            started_at                = _state.get("started_at"),
            milestone                 = _state.get("milestone", 0),
            milestone_label           = _state.get("milestone_label", ""),
            milestones                = {str(k): v for k, v in MILESTONES.items()},
            docs_start                = _state.get("docs_start", 0),
            docs_inserted             = _state.get("docs_inserted", 0),
            docs_skipped              = _state.get("docs_skipped", 0),
            docs_failed               = _state.get("docs_failed", 0),
            queries_done              = _state.get("queries_done", 0),
            queries_total             = _state.get("queries_total", 0),
            current_db_count          = count,
            target                    = TARGET_DOCS,
            pct_complete              = pct,
            last_query                = _state.get("last_query", ""),
            quality_op                = _state.get("quality_op", ""),
            error                     = _state.get("error"),
            m1_completed              = _state.get("m1_completed", False),
            m2_completed              = _state.get("m2_completed", False),
            m3_completed              = _state.get("m3_completed", False),
            m4_completed              = _state.get("m4_completed", False),
            m5_completed              = _state.get("m5_completed", False),
            corpus_cleanup_verified   = _state.get("corpus_cleanup_verified", False),
            guideline_priority_enabled= _state.get("guideline_priority_enabled", False),
            multilang_retrieval_fixed = _state.get("multilang_retrieval_fixed", False),
            current_phase             = _state.get("current_phase", 0),
            current_query_index       = _state.get("current_query_index", 0),
            last_run_at               = _state.get("last_run_at"),
            next_recommended_phase    = _state.get("next_recommended_phase", 1),
            next_recommended_action   = _state.get("next_recommended_action", ""),
        )
