"""
M5 Extension API — run Phase D + E ingest (to 1,000,000 documents) as a
persistent background thread inside the uvicorn process.

Endpoints (admin-key protected):
  POST /api/m5ext/start    – launch ingest job
  GET  /api/m5ext/status   – live progress
  POST /api/m5ext/stop     – cancel job
"""

import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/m5ext", tags=["m5ext"])

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")

# ── Shared state ───────────────────────────────────────────────────────────────
_state: dict = {
    "running":          False,
    "started_at":       None,
    "finished_at":      None,
    "target":           1_000_000,
    "docs_at_start":    None,
    "docs_now":         None,
    "docs_needed":      None,
    "docs_inserted":    0,
    "chunks_inserted":  0,
    "phase":            None,
    "current_item":     "",
    "items_done":       0,
    "items_total":      0,
    "pct_complete":     0.0,
    "elapsed_s":        0,
    "error":            None,
    "log_tail":         [],
}
_lock      = threading.Lock()
_stop_flag = threading.Event()


def _require_admin(key: Optional[str]) -> None:
    if not key or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin API key required")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(f"[m5ext] {line}", flush=True)
    with _lock:
        _state["log_tail"].append(line)
        if len(_state["log_tail"]) > 300:
            _state["log_tail"] = _state["log_tail"][-300:]


def _progress_cb(snap: dict) -> None:
    target    = snap.get("target", 1_000_000)
    docs_now  = snap.get("docs_now") or 0
    needed    = snap.get("docs_needed", 0) or 0
    inserted  = snap.get("docs_inserted", 0) or 0
    total     = snap.get("items_total", 0) or 0
    done      = snap.get("items_done", 0) or 0
    pct_items = round(done / total * 100, 1) if total > 0 else 0.0

    with _lock:
        _state.update({
            "target":          target,
            "docs_at_start":   snap.get("docs_at_start"),
            "docs_now":        docs_now,
            "docs_needed":     needed,
            "docs_inserted":   inserted,
            "chunks_inserted": snap.get("chunks_inserted", 0),
            "phase":           snap.get("phase"),
            "current_item":    snap.get("current_item", ""),
            "items_done":      done,
            "items_total":     total,
            "pct_complete":    pct_items,
            "elapsed_s":       round(snap.get("elapsed_s", 0)),
        })


def _worker(target: int, dry_run: bool) -> None:
    _stop_flag.clear()
    with _lock:
        _state.update({
            "running":         True,
            "started_at":      datetime.now(timezone.utc).isoformat(),
            "finished_at":     None,
            "docs_at_start":   None,
            "docs_now":        None,
            "docs_needed":     None,
            "docs_inserted":   0,
            "chunks_inserted": 0,
            "phase":           "initialising",
            "current_item":    "",
            "items_done":      0,
            "pct_complete":    0.0,
            "error":           None,
            "log_tail":        [],
        })

    _log(f"M5 Extension started (target={target:,}, dry_run={dry_run})")
    try:
        from app.scripts.m5_extension import run
        stats = run(
            target=target,
            dry_run=dry_run,
            stop_flag=_stop_flag,
            progress_cb=_progress_cb,
        )
        with _lock:
            _state.update({
                "running":      False,
                "finished_at":  datetime.now(timezone.utc).isoformat(),
                "phase":        stats.get("phase", "complete"),
                "error":        None,
            })
        _log(
            f"Done — corpus={stats.get('docs_now', '?'):,} | "
            f"inserted={stats.get('docs_inserted', 0):,} docs, "
            f"{stats.get('chunks_inserted', 0):,} chunks | "
            f"target {'REACHED' if stats.get('done') else 'not yet reached'}"
        )
    except Exception as exc:
        with _lock:
            _state.update({
                "running":     False,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error":       str(exc),
                "phase":       "error",
            })
        _log(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start")
def start_m5ext(
    target:  int  = 1_000_000,
    dry_run: bool = False,
    x_api_key: Optional[str] = Header(None),
):
    _require_admin(x_api_key)
    with _lock:
        if _state["running"]:
            return {"status": "already_running",
                    "detail": "M5 extension job is already in progress"}
        _state["running"] = True
        _state["target"]  = target

    threading.Thread(
        target=_worker, args=(target, dry_run),
        daemon=False, name="m5-extension",
    ).start()
    return {
        "status":  "started",
        "target":  target,
        "dry_run": dry_run,
        "detail":  "M5 extension thread launched (Phase D journals + Phase E topics)",
    }


@router.post("/stop")
def stop_m5ext(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        if not _state["running"]:
            return {"status": "not_running"}
    _stop_flag.set()
    return {"status": "stop_requested"}


@router.get("/status")
def m5ext_status(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        snap = dict(_state)

    target   = snap.get("target") or 1_000_000
    docs_now = snap.get("docs_now") or 0
    if docs_now > 0:
        snap["pct_of_target"] = round(docs_now / target * 100, 2)
    else:
        snap["pct_of_target"] = 0.0

    elapsed = snap.get("elapsed_s", 0)
    if elapsed > 0:
        snap["elapsed_min"] = round(elapsed / 60, 1)

    return snap
