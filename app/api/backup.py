"""
Backup API — runs pg_dump / tar+split inside the FastAPI process as persistent threads.
Background shell processes die on workflow restart; threads inside uvicorn survive.

Endpoints (admin-key protected):
  POST /api/backup/start        – dump DB to custom + plain SQL format
  GET  /api/backup/status       – live progress, file sizes, log tail
  POST /api/backup/stop         – cancel running backup
  GET  /api/backup/files        – list completed backup files
  POST /api/backup/split        – tar+gzip backups/ and split into 500 MB chunks
  GET  /api/backup/split/status – split job progress
"""

import os
import signal
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/backup", tags=["backup"])

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")

# ── Backup state ───────────────────────────────────────────────────────────────
_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "current_step": None,
    "steps": {},
    "log_lines": [],
    "error": None,
}
_lock = threading.Lock()
_stop_event = threading.Event()
_active_proc: Optional[subprocess.Popen] = None

# ── Split state ────────────────────────────────────────────────────────────────
_split_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "parts": [],
    "log_lines": [],
    "error": None,
}
_split_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _lock:
        _state["log_lines"].append(line)
        if len(_state["log_lines"]) > 500:
            _state["log_lines"] = _state["log_lines"][-500:]
    print(f"[backup] {line}")


def _slog(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _split_lock:
        _split_state["log_lines"].append(line)
        if len(_split_state["log_lines"]) > 200:
            _split_state["log_lines"] = _split_state["log_lines"][-200:]
    print(f"[split] {line}")


def _require_admin(x_api_key: Optional[str]) -> None:
    if not x_api_key or x_api_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin API key required")


# ── Backup worker ──────────────────────────────────────────────────────────────

def _run_dump(step_name: str, db_url: str, fmt: str, out_file: Path) -> bool:
    global _active_proc

    with _lock:
        _state["current_step"] = step_name
        _state["steps"][step_name] = {
            "status": "running",
            "started": datetime.now(timezone.utc).isoformat(),
            "finished": None,
            "file": str(out_file),
            "size_bytes": 0,
        }

    _log(f"{step_name}: starting pg_dump -F {fmt} → {out_file.name}")

    env = os.environ.copy()
    env["PGSSLMODE"] = "disable"
    cmd = ["pg_dump", db_url, "--no-owner", "--no-privileges", "-F", fmt, "-f", str(out_file)]

    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        _active_proc = proc

        for line in proc.stdout:
            if _stop_event.is_set():
                proc.send_signal(signal.SIGTERM)
                break
            line = line.rstrip()
            if line:
                _log(f"  {line}")

        proc.wait()
        _active_proc = None

        size = out_file.stat().st_size if out_file.exists() else 0
        stopped = _stop_event.is_set()
        success = proc.returncode == 0 and size > 0 and not stopped

        with _lock:
            _state["steps"][step_name].update({
                "status": "stopped" if stopped else ("done" if success else "failed"),
                "finished": datetime.now(timezone.utc).isoformat(),
                "size_bytes": size,
            })

        _log(f"{step_name}: {'STOPPED' if stopped else ('DONE' if success else 'FAILED')} "
             f"— {out_file.name} ({size / 1_048_576:.1f} MB)")
        return success

    except Exception as exc:
        _log(f"{step_name}: EXCEPTION — {exc}")
        with _lock:
            _state["steps"][step_name].update({
                "status": "failed",
                "finished": datetime.now(timezone.utc).isoformat(),
            })
        _active_proc = None
        return False


def _backup_worker() -> None:
    _stop_event.clear()
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        with _lock:
            _state["error"] = "DATABASE_URL not set"
            _state["running"] = False
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump_file = BACKUP_DIR / f"aestheticite_{ts}.dump"
    sql_file  = BACKUP_DIR / f"aestheticite_{ts}.sql"

    with _lock:
        _state.update({"started_at": datetime.now(timezone.utc).isoformat(),
                       "error": None, "log_lines": [], "steps": {}})

    _log(f"Backup started — {dump_file.name}, {sql_file.name}")

    ok1 = _run_dump("custom_dump", db_url, "c", dump_file)
    ok2 = False if _stop_event.is_set() else _run_dump("plain_sql", db_url, "p", sql_file)

    with _lock:
        _state.update({
            "running": False,
            "current_step": None,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": None if (ok1 and ok2) else ("stopped" if _stop_event.is_set()
                              else ("custom_dump failed" if not ok1 else "plain_sql failed")),
        })
    _log(f"Backup finished — custom={'OK' if ok1 else 'FAIL'}, sql={'OK' if ok2 else 'FAIL'}")


# ── Split worker ───────────────────────────────────────────────────────────────

def _split_worker(folder: str, chunk_mb: int, prefix: str) -> None:
    _slog(f"Split started — folder={folder}, chunk={chunk_mb}MB, prefix={prefix}")

    with _split_lock:
        _split_state.update({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error": None, "log_lines": _split_state["log_lines"], "parts": [],
        })

    tar_cmd  = ["tar", "-czvf", "-", folder]
    split_cmd = ["split", f"-b{chunk_mb}M", "-", prefix]

    try:
        tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        split_proc = subprocess.Popen(split_cmd, stdin=tar_proc.stdout,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tar_proc.stdout.close()

        _, split_err = split_proc.communicate()
        tar_proc.wait()

        if split_err:
            _slog(f"split stderr: {split_err.decode().strip()}")

        success = split_proc.returncode == 0 and tar_proc.returncode == 0

        # Collect part files
        from pathlib import Path as P
        parts = sorted(P(".").glob(f"{prefix}*"))
        part_info = [{"name": p.name, "size_mb": round(p.stat().st_size / 1_048_576, 1)}
                     for p in parts]

        with _split_lock:
            _split_state.update({
                "running": False,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "parts": part_info,
                "error": None if success else f"tar={tar_proc.returncode} split={split_proc.returncode}",
            })

        _slog(f"Split {'DONE' if success else 'FAILED'} — {len(part_info)} parts created")
        for p in part_info:
            _slog(f"  {p['name']}  {p['size_mb']} MB")

    except Exception as exc:
        _slog(f"EXCEPTION — {exc}")
        with _split_lock:
            _split_state.update({
                "running": False,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            })


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/start")
def start_backup(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        if _state["running"]:
            return {"status": "already_running"}
        _state["running"] = True
    threading.Thread(target=_backup_worker, daemon=False, name="db-backup").start()
    return {"status": "started", "detail": "Backup thread launched inside uvicorn process"}


@router.post("/stop")
def stop_backup(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        if not _state["running"]:
            return {"status": "not_running"}
    _stop_event.set()
    if _active_proc:
        try:
            _active_proc.send_signal(signal.SIGTERM)
        except Exception:
            pass
    return {"status": "stop_requested", "detail": "SIGTERM sent to pg_dump"}


@router.get("/status")
def backup_status(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _lock:
        snap = {k: v for k, v in _state.items() if k != "log_lines"}
        snap["log_tail"] = _state["log_lines"][-40:]
        snap["steps"] = dict(_state["steps"])

    for step in snap["steps"].values():
        fpath = Path(step.get("file", ""))
        if fpath.exists():
            step["size_bytes"] = fpath.stat().st_size
            step["size_mb"] = round(step["size_bytes"] / 1_048_576, 2)

    return snap


@router.get("/files")
def list_backup_files(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    files = []
    for f in sorted(BACKUP_DIR.iterdir()):
        if f.suffix in (".dump", ".sql"):
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_mb": round(stat.st_size / 1_048_576, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    return {"files": files, "count": len(files)}


@router.post("/split")
def start_split(
    folder: str = "backups",
    chunk_mb: int = 500,
    prefix: str = "aestheticite_part_",
    x_api_key: Optional[str] = Header(None),
):
    _require_admin(x_api_key)
    with _split_lock:
        if _split_state["running"]:
            return {"status": "already_running"}
        _split_state["running"] = True
        _split_state["log_lines"] = []

    threading.Thread(
        target=_split_worker,
        args=(folder, chunk_mb, prefix),
        daemon=False,
        name="db-split",
    ).start()
    return {
        "status": "started",
        "folder": folder,
        "chunk_mb": chunk_mb,
        "prefix": prefix,
        "detail": "tar+split thread launched — check /api/backup/split/status",
    }


@router.get("/split/status")
def split_status(x_api_key: Optional[str] = Header(None)):
    _require_admin(x_api_key)
    with _split_lock:
        snap = {k: v for k, v in _split_state.items() if k != "log_lines"}
        snap["log_tail"] = _split_state["log_lines"][-30:]
    return snap
