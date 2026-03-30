"""
Rechunk API — finds all documents with no chunks and re-chunks them inside
the uvicorn process as a persistent background thread.

Endpoints (admin-key protected):
  POST /api/rechunk/start    – launch re-chunk job
  GET  /api/rechunk/status   – live progress
  POST /api/rechunk/stop     – cancel job
"""

import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/rechunk", tags=["rechunk"])

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")

# ── Shared state ────────────────────────────────────────────────────────────────
_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "total": None,
    "processed": 0,
    "chunks_written": 0,
    "skipped": 0,
    "rate": 0.0,
    "eta_s": None,
    "error": None,
    "log_tail": [],
}
_lock      = threading.Lock()
_stop_flag = threading.Event()


def _require_admin(key: Optional[str]) -> None:
    if not key or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin API key required")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(f"[rechunk] {line}", flush=True)
    with _lock:
        _state["log_tail"].append(line)
        if len(_state["log_tail"]) > 200:
            _state["log_tail"] = _state["log_tail"][-200:]


def _progress_cb(snap: dict) -> None:
    with _lock:
        _state.update({
            "total":         snap.get("total"),
            "processed":     snap["processed"],
            "chunks_written": snap["chunks_written"],
            "skipped":       snap["skipped"],
            "rate":          round(snap.get("rate", 0), 1),
            "eta_s":         round(snap["eta_s"]) if snap.get("eta_s") else None,
        })


def _worker(batch_size: int) -> None:
    _stop_flag.clear()
    with _lock:
        _state.update({
            "running": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "total": None,
            "processed": 0,
            "chunks_written": 0,
            "skipped": 0,
            "rate": 0.0,
            "eta_s": None,
            "error": None,
            "log_tail": [],
        })

    _log(f"Re-chunk job started (batch={batch_size})")
    try:
        from app.scripts.rechunk_missing import run
        stats = run(
            batch_size=batch_size,
            stop_flag=_stop_flag,
            progress_cb=_progress_cb,
        )
        with _lock:
            _state.update({
                "running":       False,
                "finished_at":   datetime.now(timezone.utc).isoformat(),
                "total":         stats["total"],
                "processed":     stats["processed"],
                "chunks_written": stats["chunks_written"],
                "skipped":       stats["skipped"],
                "error":         None,
            })
        _log(
            f"Done — {stats['processed']:,} docs, "
            f"{stats['chunks_written']:,} chunks, "
            f"elapsed={stats.get('elapsed_s', 0)/60:.1f} min"
        )
    except Exception as exc:
        with _lock:
            _state.update({
                "running":     False,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error":       str(exc),
            })
        _log(f"ERROR: {exc}")


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.post("/start")
def start_rechunk(
    batch: int = 128,
    x_api_key: Optional[str] = Header(None),
):
    _require_admin(x_api_key)
    with _lock:
        if _state["running"]:
            return {"status": "already_running",
                    "detail": "Re-chunk job is already in progress"}
        _state["running"] = True

    threading.Thread(
        target=_worker, args=(batch,),
        daemon=False, name="rechunk-missing",
    ).start()
    return {
        "status":     "started",
        "batch_size": batch,
        "detail":     "Re-chunk thread launched inside uvicorn process",
    }


@router.post("/stop")
def stop_rechunk(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        if not _state["running"]:
            return {"status": "not_running"}
    _stop_flag.set()
    return {"status": "stop_requested"}


@router.get("/status")
def rechunk_status(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        snap = dict(_state)

    total = snap.get("total") or 0
    if total > 0:
        snap["pct"] = round(snap["processed"] / total * 100, 1)
    else:
        snap["pct"] = 0.0

    if snap.get("eta_s") is not None:
        snap["eta_min"] = round(snap["eta_s"] / 60, 1)
    else:
        snap["eta_min"] = None

    return snap
