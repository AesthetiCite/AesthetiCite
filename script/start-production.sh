#!/bin/bash
echo "Starting Python FastAPI backend..."
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PYTHON_PID=$!

echo "Waiting for Python backend to start..."
sleep 3

echo "Starting Node.js frontend..."
NODE_ENV=production node dist/index.cjs &
NODE_PID=$!

trap "kill $PYTHON_PID $NODE_PID 2>/dev/null" EXIT

wait
