#!/bin/bash
# Start the Python FastAPI backend
cd /home/runner/workspace
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
