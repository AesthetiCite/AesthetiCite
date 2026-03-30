"""
PATCH FILE — Three production fixes for Neon + Railway
=======================================================

PATCH 1: Pooled connection + SSL in every asyncpg pool
PATCH 2: Neon keepalive task in main.py
PATCH 3: Gunicorn start command

Apply each section to the file indicated.
No new dependencies except gunicorn (pip install gunicorn).
"""

# ═══════════════════════════════════════════════════════════════
# PATCH 1 — asyncpg pool: pooled URL + explicit SSL
# ═══════════════════════════════════════════════════════════════
#
# Apply to EVERY file that creates an asyncpg pool:
#   app/api/case_store.py
#   app/api/session_tracker.py
#   app/api/growth_postgres.py (if migrated)
#   app/api/hnsw_retriever.py
#   Any other file using asyncpg.create_pool()
#
# In each file, find the _get_pool() function and replace it
# with the version below. The only changes are:
#   1. ssl="require"  (explicit — don't trust URL parameter alone)
#   2. max_size=8     (safe for 4 workers × 8 = 32 connections on Neon)
#   3. max_inactive_connection_lifetime=300  (release idle connections)
# ─────────────────────────────────────────────────────────────────
#
# FIND (in each file):
#     _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
#
# REPLACE WITH:
#     _pool = await asyncpg.create_pool(
#         DATABASE_URL,
#         min_size=2,
#         max_size=8,
#         ssl="require",
#         command_timeout=30,
#         max_inactive_connection_lifetime=300,
#     )
#
# Also add this near the top of each file, after the DATABASE_URL line:
#
# FIND:
#     DATABASE_URL = os.environ.get("DATABASE_URL", "")
#
# REPLACE WITH:
#     # Use pooled Neon URL at runtime, direct URL only for migrations
#     DATABASE_URL = os.environ.get("DATABASE_URL", "")
#     if not DATABASE_URL:
#         raise RuntimeError("DATABASE_URL environment variable is not set.")


# ═══════════════════════════════════════════════════════════════
# PATCH 2 — Neon keepalive + startup improvements
# ═══════════════════════════════════════════════════════════════
#
# File: app/main.py
#
# STEP A: Add import at the top with the other imports:
#
#     import asyncio
#
# (it may already be imported — check first)
#
#
# STEP B: Add this function anywhere before the @app.on_event("startup"):
#
# ─────────────────────────────────────────────────────────────────
KEEPALIVE_FUNCTION = '''
async def _neon_keepalive():
    """
    Prevents Neon auto-suspend during active clinic sessions.
    Sends a lightweight ping every 4 minutes.
    On free Neon tier: first query after 5min inactivity adds ~500ms.
    On paid tier: disable auto-suspend in Neon console instead.
    """
    import logging
    logger = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(240)  # 4 minutes
        try:
            import asyncpg, os
            pool = await asyncpg.create_pool(
                os.environ.get("DATABASE_URL", ""),
                min_size=1, max_size=1, ssl="require",
            )
            await pool.fetchval("SELECT 1")
            await pool.close()
        except Exception as e:
            logger.debug(f"[Keepalive] ping failed (non-critical): {e}")
'''
# ─────────────────────────────────────────────────────────────────
#
#
# STEP C: Inside the existing @app.on_event("startup") function,
# add one line at the END of the function body:
#
# FIND the startup function — it currently looks something like:
#
#     @app.on_event("startup")
#     async def _startup():
#         with SessionLocal() as db:
#             for stmt in DOC_META_MIGRATION_SQL.strip().split(";"):
#                 stmt = stmt.strip()
#                 if stmt:
#                     db.execute(text(stmt))
#             db.commit()
#         await init_retrieval_pool()
#
# ADD these two lines at the end of _startup():
#
#         # Neon keepalive — prevents auto-suspend between requests
#         asyncio.create_task(_neon_keepalive())
#         logger.info("[Startup] Neon keepalive task started")
#
#
# FULL RESULT after both changes (STEP B + C):
# ─────────────────────────────────────────────────────────────────
STARTUP_RESULT = '''
async def _neon_keepalive():
    import logging
    logger = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(240)
        try:
            import asyncpg, os
            pool = await asyncpg.create_pool(
                os.environ.get("DATABASE_URL", ""),
                min_size=1, max_size=1, ssl="require",
            )
            await pool.fetchval("SELECT 1")
            await pool.close()
        except Exception as e:
            logger.debug(f"[Keepalive] ping failed: {e}")


@app.on_event("startup")
async def _startup():
    with SessionLocal() as db:
        for stmt in DOC_META_MIGRATION_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.execute(text(stmt))
        db.commit()
    await init_retrieval_pool()
    asyncio.create_task(_neon_keepalive())   # <-- ADD THIS LINE
'''
# ─────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════
# PATCH 3 — Gunicorn start command
# ═══════════════════════════════════════════════════════════════
#
# Step A: Install gunicorn
#     pip install gunicorn
#     Add to requirements.txt:  gunicorn>=21.0.0
#
#
# Step B: Create file  Procfile  in the ROOT of your project
# (same level as main.py or pyproject.toml):
#
# ─────────────────────────────────────────────────────────────────
PROCFILE_CONTENT = """web: gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --timeout 120 --graceful-timeout 30 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100"""
# ─────────────────────────────────────────────────────────────────
#
# That is the entire Procfile — one line.
#
# Explanation of each flag:
#   --workers 4                : 4 parallel workers (safe for 2 CPU cores)
#   --worker-class UvicornWorker: each worker runs async uvicorn
#   --timeout 120              : DeepConsult / long LLM calls can take 90s+
#   --graceful-timeout 30      : wait 30s for in-flight requests on shutdown
#   --keep-alive 5             : HTTP keep-alive for connection reuse
#   --max-requests 1000        : recycle each worker after 1000 requests
#   --max-requests-jitter 100  : stagger recycling to avoid all workers
#                                restarting simultaneously
#
#
# Step C: On Railway, set your start command to:
#     gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120 --graceful-timeout 30 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100
#
# OR: Railway auto-detects the Procfile — just push with the Procfile
# and Railway will use it automatically.
#
#
# Step D: Also add to your requirements.txt if not already there:
#     gunicorn>=21.0.0
#     uvicorn[standard]>=0.24.0
#
# NOTE: The NODE frontend (Express) runs separately on Railway.
# The Procfile is only for the Python FastAPI service.
# Railway runs them as two separate services — FastAPI on one,
# Node/Express on another.


# ═══════════════════════════════════════════════════════════════
# SUMMARY — what changes and what it fixes
# ═══════════════════════════════════════════════════════════════
#
# PATCH 1 (SSL + pool tuning):
#   Before: asyncpg may silently ignore SSL on some Neon endpoints
#           causing intermittent connection drops
#   After:  SSL enforced, connections released when idle,
#           safe connection count for 4 workers
#
# PATCH 2 (keepalive):
#   Before: First query after 5min inactivity = 500ms Neon cold start
#           Clinicians opening the platform after lunch see a slow response
#   After:  Database stays warm during any active server session
#           Cold start only on full server restart (Railway deploy)
#
# PATCH 3 (gunicorn):
#   Before: Single uvicorn worker — one slow DeepConsult or vision
#           call blocks ALL other users for up to 90 seconds
#   After:  4 independent workers — one slow call affects at most
#           25% of concurrent capacity, not 100%
#           Workers auto-recycle after 1000 requests preventing memory leaks
