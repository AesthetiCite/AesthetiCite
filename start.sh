#!/bin/bash
set -euo pipefail

# Resolve Python binary.
# Priority:
#   1. $UV_PROJECT_ENVIRONMENT/bin/python3  (Replit dev env)
#   2. /home/runner/workspace/.pythonlibs/bin/python3  (Replit legacy path)
#   3. .venv/bin/python3  (created by `uv sync` during the build step — production VM)
#   4. uv run --no-sync  (if uv is in PATH)
#   5. python3  (bare system Python, last resort)
PYTHON_BIN=""

if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ] && [ -f "${UV_PROJECT_ENVIRONMENT}/bin/python3" ]; then
  PYTHON_BIN="${UV_PROJECT_ENVIRONMENT}/bin/python3"
  echo "[start.sh] Python binary: ${PYTHON_BIN} (from UV_PROJECT_ENVIRONMENT)"
elif [ -f "/home/runner/workspace/.pythonlibs/bin/python3" ]; then
  PYTHON_BIN="/home/runner/workspace/.pythonlibs/bin/python3"
  echo "[start.sh] Python binary: ${PYTHON_BIN} (.pythonlibs)"
elif [ -f ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
  echo "[start.sh] Python binary: ${PYTHON_BIN} (uv-created .venv)"
elif command -v uv &>/dev/null; then
  PYTHON_BIN="uv"
  echo "[start.sh] Python binary: uv run --no-sync (uv in PATH)"
else
  PYTHON_BIN="python3"
  echo "[start.sh] Python binary: python3 (system fallback)"
fi

# Always force unbuffered Python output so logs appear immediately in deployment logs.
export PYTHONUNBUFFERED=1
# Print Python stack traces on fatal signals (segfault, SIGABRT, etc.)
export PYTHONFAULTHANDLER=1
# Cache fastembed ONNX model in the workspace directory so it persists across
# build → runtime.  Without this it defaults to /tmp/fastembed_cache/ which is
# wiped between the build step and the runtime container, forcing a re-download
# on every cold start (unauthenticated HuggingFace, rate-limited, slow).
export FASTEMBED_CACHE_PATH="${FASTEMBED_CACHE_PATH:-/home/runner/workspace/.fastembed_cache}"

_run_python() {
  if [ "$PYTHON_BIN" = "uv" ]; then
    uv run --no-sync python3 "$@"
  else
    "${PYTHON_BIN}" "$@"
  fi
}

# ── Disable pydantic plugin scan — critical for fast startup ──────────────────
# pydantic's get_plugins() calls importlib_metadata.distributions() which reads
# every .dist-info directory in the Python environment on every pydantic model
# class definition.  In production (network filesystem, 400+ packages) this
# takes 200-500 s per scan.  PYDANTIC_DISABLE_PLUGINS=1 short-circuits to
# "return ()" immediately.  We use no pydantic plugins, so this is safe.
# Set this BEFORE the sanity check (which imports fastapi → pydantic) and
# before uvicorn.
export PYDANTIC_DISABLE_PLUGINS=1

# ── Start Node.js FIRST — port 5000 must respond before anything else ──────────
# The Promote phase health check hits port 5000 immediately after start.
# Node.js responds on port 5000 right away (Python readiness is checked async).
echo "[start.sh] Starting Node.js on port 5000..."
PYTHON_MANAGED_EXTERNALLY=1 node dist/index.cjs &
NODE_PID=$!
echo "[start.sh] Node.js PID: ${NODE_PID}"

# ── Quick sanity-check (stdlib only — no third-party imports) ─────────────────
# Heavy imports (uvicorn, fastapi, asyncpg) have been REMOVED from the sanity
# check.  On the production network filesystem they took 116 s and needlessly
# delayed the FastAPI PID.  Those packages are now imported inside _build_real_app()
# which runs AFTER uvicorn has already bound port 8000.
echo "[start.sh] Verifying Python environment..."
_run_python -c "
import sys, os
print('[sanity] Python', sys.version)
print('[sanity] cwd:', os.getcwd())
print('[sanity] PYDANTIC_DISABLE_PLUGINS:', os.environ.get('PYDANTIC_DISABLE_PLUGINS', 'not set'))
db_url = os.environ.get('DATABASE_URL', os.environ.get('NEON_DATABASE_URL', ''))
if db_url:
    masked = db_url[:40] + '...' if len(db_url) > 40 else db_url
    print('[sanity] DATABASE_URL:', masked)
else:
    print('[sanity] WARNING — DATABASE_URL not set')
print('[sanity] NEON_DATABASE_URL set:', bool(os.environ.get('NEON_DATABASE_URL')))
print('[sanity] Done')
" 2>&1 || echo "[start.sh] WARNING: sanity check script failed (non-fatal)"

# ── Start FastAPI backend ──────────────────────────────────────────────────────
echo "[start.sh] Starting FastAPI on port 8000..."
if [ "$PYTHON_BIN" = "uv" ]; then
  PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1 uv run --no-sync uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --log-level info 2>&1 &
else
  PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1 "${PYTHON_BIN}" -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --log-level info 2>&1 &
fi
PYTHON_PID=$!
echo "[start.sh] FastAPI PID: ${PYTHON_PID}"

# ── Background watchdog ────────────────────────────────────────────────────────
_watchdog() {
  local elapsed=0
  while true; do
    sleep 15
    elapsed=$((elapsed + 15))
    py_alive=0
    node_alive=0
    kill -0 "${PYTHON_PID}" 2>/dev/null && py_alive=1
    kill -0 "${NODE_PID}" 2>/dev/null && node_alive=1
    port_open=0
    (echo "" > /dev/tcp/localhost/8000) 2>/dev/null && port_open=1
    echo "[watchdog] ${elapsed}s — python=${py_alive} node=${node_alive} port8000=${port_open}"
    if [ "${py_alive}" = "0" ]; then
      echo "[watchdog] Python process has exited — triggering shutdown"
      break
    fi
    # After 3 minutes without port 8000 open, request Python stack dump
    if [ "${elapsed}" = "180" ] && [ "${port_open}" = "0" ] && [ "${py_alive}" = "1" ]; then
      echo "[watchdog] 3min — port8000 still closed, sending SIGUSR1 for stack dump..."
      kill -USR1 "${PYTHON_PID}" 2>/dev/null || true
    fi
  done
}
_watchdog &
WATCHDOG_PID=$!

# ── Signal forwarding ──────────────────────────────────────────────────────────
cleanup() {
  echo "[start.sh] Shutting down..."
  kill "${WATCHDOG_PID:-}" 2>/dev/null || true
  kill "${PYTHON_PID:-}" "${NODE_PID:-}" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# Wait — if either process dies, exit so the platform can restart
wait -n "${PYTHON_PID}" "${NODE_PID}"
STATUS=$?
echo "[start.sh] A child process exited with status ${STATUS} — shutting down"
cleanup
exit "${STATUS}"
