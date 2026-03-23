#!/bin/bash
set -euo pipefail

# Resolve Python binary — same priority as server/index.ts but evaluated by bash
# so it works regardless of Node.js environment variable availability.
PYTHON_BIN=""

if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ] && [ -f "${UV_PROJECT_ENVIRONMENT}/bin/python3" ]; then
  PYTHON_BIN="${UV_PROJECT_ENVIRONMENT}/bin/python3"
  echo "[start.sh] Python binary: ${PYTHON_BIN} (from UV_PROJECT_ENVIRONMENT)"
elif [ -f "/home/runner/workspace/.pythonlibs/bin/python3" ]; then
  PYTHON_BIN="/home/runner/workspace/.pythonlibs/bin/python3"
  echo "[start.sh] Python binary: ${PYTHON_BIN} (hardcoded .pythonlibs path)"
elif command -v uv &>/dev/null; then
  PYTHON_BIN="uv"
  echo "[start.sh] Python binary: uv run --no-sync (uv in PATH)"
else
  PYTHON_BIN="python3"
  echo "[start.sh] Python binary: python3 (system fallback)"
fi

# Start FastAPI backend
echo "[start.sh] Starting FastAPI on port 8000..."
if [ "$PYTHON_BIN" = "uv" ]; then
  uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 &
else
  "${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
fi
PYTHON_PID=$!
echo "[start.sh] FastAPI PID: ${PYTHON_PID}"

# Start Node.js frontend/proxy — tell it Python is already running externally
echo "[start.sh] Starting Node.js on port 5000..."
PYTHON_MANAGED_EXTERNALLY=1 node dist/index.cjs &
NODE_PID=$!
echo "[start.sh] Node.js PID: ${NODE_PID}"

# Forward signals to children
cleanup() {
  echo "[start.sh] Shutting down..."
  kill "${PYTHON_PID}" "${NODE_PID}" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# Wait — if either process dies, exit so the platform can restart
wait -n "${PYTHON_PID}" "${NODE_PID}"
STATUS=$?
echo "[start.sh] A child process exited with status ${STATUS} — shutting down"
cleanup
exit "${STATUS}"
