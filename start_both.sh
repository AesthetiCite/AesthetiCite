#!/bin/bash
# Start both the Node.js frontend and Python FastAPI backend
cd /home/runner/workspace

# Start Python API in background
echo "Starting Python API on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PYTHON_PID=$!

# Wait for Python API to start
sleep 3

# Check if Python API started
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "Python API started successfully"
else
    echo "Warning: Python API may not be fully ready yet"
fi

# Start Node.js frontend (this will block)
echo "Starting Node.js frontend on port 5000..."
npm run dev

# If Node.js exits, also kill Python
kill $PYTHON_PID 2>/dev/null
