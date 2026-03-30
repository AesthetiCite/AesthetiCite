#!/bin/sh

# ── Start FastAPI backend ────────────────────────────────────────────────────────────────
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

# ── Background watchdog ──────────────────────────────────────────────────────────────────
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
    echo "[watchdog] ${elapsed}s – python=${py_alive} node=${node_alive} port8000=${port_open}"
    if [ "${py_alive}" = "0" ]; then
      echo "[watchdog] Python process has exited – triggering shutdown"
      break
    fi
    # After 3 minutes without port 8000 open, request Python stack dump
    if [ "${elapsed}" = "180" ] && [ "${port_open}" = "0" ] && [ "${py_alive}" = "1" ]; then
      echo "[watchdog] 3min – port8000 still closed, sending SIGUSR1 for stack dump..."
      kill -USR1 "${PYTHON_PID}" 2>/dev/null || true
    fi
  done
}
_watchdog &
WATCHDOG_PID=$!

# ── Signal forwarding ────────────────────────────────────────────────────────────────────
cleanup() {
  echo "[start.sh] Shutting down..."
  kill "${WATCHDOG_PID:-}" 2>/dev/null || true
  kill "${PYTHON_PID:-}" "${NODE_PID:-}" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# Wait – if either process dies, exit so the platform can restart
wait -n "${PYTHON_PID}" "${NODE_PID}"
STATUS=$?
echo "[start.sh] A child process exited with status ${STATUS} – shutting down"
cleanup
exit "${STATUS}"