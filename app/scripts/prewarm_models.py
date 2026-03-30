#!/usr/bin/env python3
"""
Build-time model pre-warm script.
Run during the Replit build step to bake the fastembed ONNX model
into the deployment container so it is available on cold start
without any network download.

Usage (in build command):
    python3 app/scripts/prewarm_models.py
"""
import os
import sys
import time
import pathlib

# Use the workspace-relative cache path that start.sh also sets at runtime.
# This must match FASTEMBED_CACHE_PATH in start.sh.
CACHE_PATH = os.environ.get(
    "FASTEMBED_CACHE_PATH",
    str(pathlib.Path(__file__).resolve().parents[2] / ".fastembed_cache"),
)
os.environ["FASTEMBED_CACHE_PATH"] = CACHE_PATH

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

print(f"[prewarm] FASTEMBED_CACHE_PATH = {CACHE_PATH}", flush=True)
print(f"[prewarm] Downloading / verifying model: {MODEL_NAME}", flush=True)

t0 = time.time()
try:
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=MODEL_NAME)
    # Force a real inference pass to ensure the ONNX runtime is warmed up
    test_vec = list(model.embed(["aesthetic medicine complication protocol"]))
    dim = len(list(test_vec[0]))
    elapsed = time.time() - t0
    print(f"[prewarm] Model ready. dim={dim}  elapsed={elapsed:.1f}s", flush=True)

    # Report cache size
    cache_dir = pathlib.Path(CACHE_PATH)
    if cache_dir.exists():
        total_bytes = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
        print(f"[prewarm] Cache size: {total_bytes / 1024 / 1024:.1f} MB  path={cache_dir}", flush=True)
    else:
        print("[prewarm] WARNING: cache dir does not exist after download!", flush=True)

except Exception as exc:
    print(f"[prewarm] WARNING: model pre-warm failed (will download at runtime): {exc}", flush=True)
    import traceback
    traceback.print_exc()
    # Non-fatal: the model will be downloaded lazily at runtime in a background thread.
    # Do NOT sys.exit(1) here — that would fail the entire build step.

print("[prewarm] Done.", flush=True)
