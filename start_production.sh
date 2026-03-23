#!/bin/bash
# Production startup script - runs both Node.js and Python servers
cd /home/runner/workspace

echo "Starting EvidenceDoc production servers..."

# Start Python FastAPI backend in background
echo "Starting Python API on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PYTHON_PID=$!

# Wait for Python API to start
sleep 3
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "Python API started successfully (PID: $PYTHON_PID)"
else
    echo "Warning: Python API startup may be slow"
fi

# Start Node.js production server in foreground
echo "Starting Node.js server on port 5000..."
exec node ./dist/index.cjs
