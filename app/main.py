"""
app/main.py — AesthetiCite FastAPI application

## Production startup strategy (slow network filesystem fix)

On Replit's production network filesystem, reading Python package .pyc files is
~50× slower than local disk.  Importing FastAPI + SQLAlchemy + pydantic takes
300+ seconds.  Uvicorn binds port 8000 only AFTER the lifespan startup event
completes, so the watchdog timeout fires before port 8000 ever opens.

### Solution

1.  Module level: STDLIB ONLY.  app.main imports in < 1 s.
2.  Lifespan startup event: start a background THREAD, then return IMMEDIATELY.
    Uvicorn sees lifespan.startup.complete → binds port 8000 in ~2 s.
    Watchdog at 15 s sees port8000=1 → deployment succeeds.
3.  Background thread: imports all third-party packages (300 s on slow NFS),
    builds the real FastAPI app, registers all routers, and sets _real_app.
4.  During initialisation:
      GET /health   → 200 {"status":"starting"}   (instant stdlib response)
      all other     → 503 {"status":"starting"}
5.  After _real_app is set, all requests are transparently proxied.
"""

# ─── STDLIB ONLY — zero third-party imports at module level ─────────────────
import asyncio as _asyncio
import glob
import json as _json
import logging as _logging
import os
import signal as _signal
import threading as _threading
import time

_IMPORT_START_T = time.time()
_logging.basicConfig(level=_logging.INFO)
_log = _logging.getLogger(__name__)
_log.info(f"[main] Module import started at {_IMPORT_START_T:.2f}")

# Register SIGUSR1 → faulthandler stack dump so watchdog can trigger diagnostics
try:
    import faulthandler as _fh
    _fh.register(_signal.SIGUSR1)
except Exception:
    pass


# ─── SQL migration constants (pure strings, zero imports) ────────────────────

DOC_META_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS documents_meta (
    source_id      TEXT PRIMARY KEY,
    doi            TEXT,
    pmid           TEXT,
    url            TEXT,
    title          TEXT,
    journal        TEXT,
    year           INTEGER,
    publication_type TEXT,
    source_tier    TEXT,
    evidence_type  TEXT,
    evidence_rank  INTEGER,
    organization   TEXT,
    updated_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_docs_meta_pubtype   ON documents_meta(publication_type);
CREATE INDEX IF NOT EXISTS idx_docs_meta_evidtype  ON documents_meta(evidence_type);
CREATE INDEX IF NOT EXISTS idx_docs_meta_source_tier ON documents_meta(source_tier);
CREATE INDEX IF NOT EXISTS idx_docs_meta_pmid      ON documents_meta(pmid);
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    logged_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type  TEXT        NOT NULL,
    request_id  TEXT,
    user_id     TEXT,
    email       TEXT,
    ip_address  TEXT,
    path        TEXT,
    event_data  JSONB
);
CREATE INDEX IF NOT EXISTS idx_audit_user  ON audit_log(user_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_time  ON audit_log(logged_at DESC);
"""

USERS_CLINIC_MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS clinic_id        TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified   BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_users_clinic ON users(clinic_id);
"""

_REBUILD_INDEX_DEFS = [
    (
        "idx_chunks_embedding_hnsw",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists='100')",
    ),
    (
        "chunks_text_norm_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS chunks_text_norm_trgm "
        "ON chunks USING gin (text_norm gin_trgm_ops)",
    ),
    (
        "chunks_tsv_gin",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS chunks_tsv_gin "
        "ON chunks USING gin (tsv)",
    ),
    (
        "idx_documents_trgm_title",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_trgm_title "
        "ON documents USING gin (title gin_trgm_ops)",
    ),
    (
        "idx_documents_fts",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_fts ON documents USING gin ("
        "to_tsvector('english'::regconfig, "
        "((COALESCE(title, ''::text) || ' '::text) || COALESCE(abstract, ''::text))))",
    ),
]


# ─── Shared state ─────────────────────────────────────────────────────────────

_real_app = None          # Set to the real FastAPI app once ready
_uvicorn_loop = None      # Asyncio event loop captured at lifespan startup


# ─── Stdlib helper functions ──────────────────────────────────────────────────

def _cleanup_old_exports(export_dir: str = "exports", max_age_hours: int = 24) -> int:
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for f in glob.glob(os.path.join(export_dir, "*.pdf")):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
                removed += 1
        except Exception:  # nosec B110
            pass
    return removed


def _rebuild_missing_indexes_thread() -> None:
    """Background thread: rebuild search indexes dropped before deployment."""
    from sqlalchemy import create_engine, text as _text
    import logging as _logging
    _log2 = _logging.getLogger(__name__)
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        _log2.warning("[index_rebuild] DATABASE_URL not set — skipping")
        return
    try:
        engine = create_engine(db_url, isolation_level="AUTOCOMMIT", echo=False)
        with engine.connect() as conn:
            for name, ddl in _REBUILD_INDEX_DEFS:
                try:
                    exists = conn.execute(
                        _text("SELECT 1 FROM pg_indexes WHERE indexname = :n"), {"n": name}
                    ).first()
                    if exists:
                        _log2.info(f"[index_rebuild] {name}: present")
                        continue
                    _log2.info(f"[index_rebuild] {name}: building (may take 5-30 min)…")
                    conn.execute(_text(ddl))
                    _log2.info(f"[index_rebuild] {name}: done ✓")
                except Exception as exc:
                    _log2.error(f"[index_rebuild] {name}: FAILED — {exc}")
        engine.dispose()
        _log2.info("[index_rebuild] All indexes checked/rebuilt")
    except Exception as exc:
        _log2.error(f"[index_rebuild] Cannot connect for rebuild: {exc}")


# ─── Minimal stdlib ASGI proxy ───────────────────────────────────────────────

class _StartupProxy:
    """
    Minimal ASGI application — stdlib only at module level.

    Uvicorn lifecycle:
      1.  Uvicorn imports app.main → gets _StartupProxy() as `app`  (<1 s)
      2.  Uvicorn sends lifespan.startup → _StartupProxy._lifespan() runs
      3.  _lifespan() starts a background OS thread for all heavy init,
          then immediately sends lifespan.startup.complete
      4.  Uvicorn binds port 8000 (< 2 s after step 1)
      5.  Background thread slowly imports FastAPI, SQLAlchemy, etc.
          and sets _real_app when done (≈300 s on slow NFS)
      6.  _StartupProxy routes:
            /health, /api/health  → 200 always (even before _real_app is ready)
            everything else       → 503 until _real_app is set, then proxy
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._lifespan(scope, receive, send)
        elif scope["type"] == "http":
            path = scope.get("path", "")
            if path in ("/health", "/api/health"):
                await self._health(scope, receive, send)
            elif _real_app is not None:
                await _real_app(scope, receive, send)
            else:
                await self._starting(scope, receive, send)
        elif scope["type"] == "websocket":
            if _real_app is not None:
                await _real_app(scope, receive, send)
            else:
                await receive()
                await send({"type": "websocket.close", "code": 1013})

    async def _health(self, scope, receive, send):
        await receive()
        status = "ready" if _real_app is not None else "starting"
        body = _json.dumps({"status": status, "app": "AesthetiCite"}).encode()
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})

    async def _starting(self, scope, receive, send):
        await receive()
        body = b'{"status":"starting","message":"FastAPI initializing, please retry in 30s"}'
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", b"30"),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def _lifespan(self, scope, receive, send):
        global _uvicorn_loop
        message = await receive()
        if message["type"] != "lifespan.startup":
            return

        # Capture the uvicorn event loop so background thread can schedule coroutines
        _uvicorn_loop = _asyncio.get_event_loop()

        # ── CRITICAL: start heavy init in a background OS thread, then return ──
        # Returning lifespan.startup.complete immediately causes uvicorn to bind
        # port 8000 right away.  The watchdog sees port8000=1 within seconds.
        # The background thread then takes however long it needs (300 s on slow
        # NFS) without blocking port 8000.
        _t = _threading.Thread(
            target=_init_background,
            name="fastapi-bg-init",
            daemon=True,
        )
        _t.start()

        await send({"type": "lifespan.startup.complete"})
        _log.info(
            "[startup] Lifespan startup.complete sent — "
            "port 8000 now open, FastAPI initialising in background thread"
        )

        # Park here until uvicorn sends shutdown
        message = await receive()
        if message["type"] == "lifespan.shutdown":
            try:
                from app.rag.async_retriever import close_retrieval_pool
                await close_retrieval_pool()
            except Exception as exc:
                _log.error(f"[shutdown] {exc}")
            await send({"type": "lifespan.shutdown.complete"})


app = _StartupProxy()


# ─── Background initialisation (runs in a separate OS thread) ─────────────────

def _init_background() -> None:
    """
    All heavy third-party imports + FastAPI setup happen here.

    Runs in a daemon thread so uvicorn can bind port 8000 without waiting.
    Sets _real_app when the FastAPI app is fully built and ready.
    """
    global _real_app

    import logging as _logging
    import threading
    _slog = _logging.getLogger(__name__)
    _t0 = time.time()

    try:
        _slog.info("[bg-init] Starting — importing FastAPI + SQLAlchemy + pydantic…")

        # ── Pre-import SQLAlchemy BEFORE FastAPI/pydantic ─────────────────────
        # pydantic-core (Rust) can spawn background threads that race to import
        # sqlalchemy.sql.schema/util, causing deadlocks.  Import SA first.
        import sqlalchemy as _sa          # noqa: F401
        import sqlalchemy.sql.schema      # noqa: F401
        import sqlalchemy.sql.util        # noqa: F401
        from sqlalchemy import text

        from fastapi import FastAPI, Response, Depends
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi import Request as _Request
        from starlette.middleware.base import BaseHTTPMiddleware
        from slowapi.errors import RateLimitExceeded
        from slowapi import _rate_limit_exceeded_handler

        from app.core.config import settings
        from app.core.limiter import limiter

        _slog.info(f"[bg-init] FastAPI+deps imported in {time.time()-_t0:.1f}s")

        # ── Create FastAPI app ────────────────────────────────────────────────
        fastapi_app = FastAPI(title=settings.APP_NAME)

        # CORS — fail-closed in production
        _origins_raw = os.environ.get("CORS_ORIGINS", "").strip()
        if not _origins_raw:
            if os.environ.get("ENV", "dev").lower() == "production":
                raise RuntimeError(
                    "CORS_ORIGINS must be set in production. "
                    "Set it to your frontend domain e.g. https://aestheticite.com"
                )
            _origins = settings.cors_origins_list or ["http://localhost:3000", "http://localhost:5173"]
        else:
            _origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]

        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key", "x-api-key",
                           "X-Clinic-ID", "X-Admin-Api-Key", "X-Partner-Session"],
        )

        # Security headers middleware
        class SecurityHeadersMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: _Request, call_next):
                response = await call_next(request)
                if request.url.path.startswith("/api/"):
                    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                    response.headers["Pragma"]        = "no-cache"
                response.headers["Strict-Transport-Security"] = (
                    "max-age=63072000; includeSubDomains; preload"
                )
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"]        = "DENY"
                response.headers["X-XSS-Protection"]       = "1; mode=block"
                response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"]     = (
                    "camera=(), microphone=(), geolocation=(), payment=()"
                )
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                    "style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: blob: https:; "
                    "font-src 'self' data:; "
                    "connect-src 'self' https://api.openai.com https://*.neon.tech wss:; "
                    "frame-ancestors 'none'; "
                    "base-uri 'self'; "
                    "form-action 'self';"
                )
                return response

        fastapi_app.add_middleware(SecurityHeadersMiddleware)

        fastapi_app.state.limiter = limiter
        fastapi_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        # ── Import all routers ────────────────────────────────────────────────
        _slog.info("[bg-init] Importing routers…")
        _r0 = time.time()

        from app.core.startup import ensure_users_table
        from app.core.env_check import validate_env
        from app.rag.cache import warm_embedding_cache
        from app.rag.async_retriever import init_retrieval_pool, close_retrieval_pool
        from app.db.session import SessionLocal

        from app.api.ask import router as ask_router
        from app.api.ask_stream import router as ask_stream_router
        from app.api.admin import router as admin_router
        from app.api.admin_dashboard import router as admin_dashboard_router
        from app.api.auth import router as auth_router
        from app.api.access import router as access_router
        from app.api.analytics import router as analytics_router
        from app.api.sync import router as sync_router
        from app.api.history import router as history_router
        from app.api.tools import router as tools_router, admin_router as dosing_admin_router
        from app.api.aesthetic_tools import router as aesthetic_tools_router
        from app.api.languages import router as languages_router
        from app.api.admin_metrics import router as admin_metrics_router
        from app.api.clinical_docs import router as clinical_docs_router
        from app.api.voice import router as voice_router
        from app.api.oe_upgrade import router as oe_upgrade_router
        from app.api.benchmark import router as benchmark_router
        from app.api.phase2_5 import router as phase2_5_router
        from app.api.aestheticite_top10 import router as top10_router
        from app.pilot_proof import router as pilot_router
        from app.core.deepconsult_pdf_export import router as deepconsult_pdf_router
        from app.api.partner_preview import router as partner_router
        from app.api.ingest import router as ingest_router
        from app.api.cases import router as cases_router
        from app.api.workflow_engine import router as workflow_router
        from app.api.report_generator import router as report_router
        from app.api.ask_v2 import router as ask_v2_router
        from app.api.visual_counseling import router as visual_counseling_router
        from app.api.vision_extensions import router as vision_ext_router
        from app.engine.vision_quality import router as vision_quality_router
        from app.api.skingpt_integration import router as skingpt_router
        from app.api.clinical_workflow_v2 import router as clinical_workflow_v2_router
        from app.api.vision_advanced import router as vision_advanced_router
        from app.api.visual_differential import router as visual_diff_router
        from app.api.visual_enhancements import router as visual_enhance_router
        from app.api.vision_analysis import router as vision_router
        from app.api.vision_followup import router as vision_followup_router
        from app.api.complication_protocol_engine import router as complication_router
        from app.api.preprocedure_safety_engine_v2 import router as preprocedure_safety_router
        from app.api.growth_engine import router as growth_router
        from app.api.operational import router as operational_router, apply_operational_patches
        from app.api.mass_upload_api import router as mass_upload_router
        from app.api.network_workspace import router as network_workspace_router
        from app.db.network_migrations import run_migrations as run_network_migrations, run_seed as run_network_seed
        from app.api.risk_intelligence import router as risk_intelligence_router
        from app.api.complication_monitor import router as complication_monitor_router
        from app.api.llm_provider import router as llm_provider_router
        from app.api.org_analytics import router as org_analytics_router
        from app.db.intelligence_migrations import run_intelligence_migrations
        from app.api.clinical_decision import router as decision_router
        from app.api.clinical_reasoning import router as reasoning_router
        from app.api.routes.cases import router as clinical_cases_router, protocol_router as clinical_protocol_router
        from app.api.vision_diagnosis import router as vision_diagnosis_router
        from app.api.operational_readiness import router as readiness_router
        from app.api.backup import router as backup_router
        from app.api.rechunk import router as rechunk_router
        from app.api.m5_ext import router as m5ext_router
        from app.api.neon_migrate import router as neon_migrate_router
        from app.api.session_tracker import router as session_tracker_router
        from app.api.vision_engine_v2 import router as vision_v2_router
        from app.api.vision_landmarks import router as landmark_router
        from app.api.clinical_tools_engine import router as tools_engine_router

        _slog.info(f"[bg-init] Routers imported in {time.time()-_r0:.1f}s — registering…")

        # ── Register all routers ──────────────────────────────────────────────
        fastapi_app.include_router(auth_router)
        fastapi_app.include_router(access_router)
        fastapi_app.include_router(ask_router)
        fastapi_app.include_router(ask_stream_router)
        fastapi_app.include_router(history_router)
        fastapi_app.include_router(admin_router)
        fastapi_app.include_router(analytics_router)
        fastapi_app.include_router(sync_router)
        fastapi_app.include_router(tools_router)
        fastapi_app.include_router(dosing_admin_router)
        fastapi_app.include_router(aesthetic_tools_router)
        fastapi_app.include_router(languages_router)
        fastapi_app.include_router(admin_metrics_router)
        fastapi_app.include_router(clinical_docs_router)
        fastapi_app.include_router(voice_router)
        fastapi_app.include_router(oe_upgrade_router)
        fastapi_app.include_router(benchmark_router)
        fastapi_app.include_router(phase2_5_router)
        fastapi_app.include_router(top10_router)
        fastapi_app.include_router(pilot_router)
        fastapi_app.include_router(deepconsult_pdf_router)
        fastapi_app.include_router(partner_router)
        fastapi_app.include_router(ingest_router)
        fastapi_app.include_router(cases_router)
        fastapi_app.include_router(workflow_router)
        fastapi_app.include_router(report_router)
        fastapi_app.include_router(ask_v2_router)
        fastapi_app.include_router(visual_counseling_router)
        fastapi_app.include_router(vision_ext_router)
        fastapi_app.include_router(vision_quality_router)
        fastapi_app.include_router(skingpt_router)
        fastapi_app.include_router(clinical_workflow_v2_router)
        fastapi_app.include_router(vision_advanced_router)
        fastapi_app.include_router(visual_diff_router, prefix="/api/visual")
        fastapi_app.include_router(visual_enhance_router, prefix="/api/visual")
        fastapi_app.include_router(vision_router, prefix="/api/vision")
        fastapi_app.include_router(vision_followup_router)
        fastapi_app.include_router(complication_router)
        fastapi_app.include_router(preprocedure_safety_router)
        fastapi_app.include_router(growth_router)
        fastapi_app.include_router(operational_router, prefix="/api/ops")
        fastapi_app.include_router(mass_upload_router)
        fastapi_app.include_router(network_workspace_router)
        fastapi_app.include_router(risk_intelligence_router)
        fastapi_app.include_router(complication_monitor_router)
        fastapi_app.include_router(llm_provider_router)
        fastapi_app.include_router(org_analytics_router)
        fastapi_app.include_router(decision_router)
        fastapi_app.include_router(reasoning_router)
        fastapi_app.include_router(clinical_cases_router)
        fastapi_app.include_router(clinical_protocol_router)
        fastapi_app.include_router(vision_diagnosis_router)
        fastapi_app.include_router(readiness_router)
        fastapi_app.include_router(backup_router)
        fastapi_app.include_router(rechunk_router)
        fastapi_app.include_router(m5ext_router)
        fastapi_app.include_router(neon_migrate_router)
        fastapi_app.include_router(admin_dashboard_router)
        fastapi_app.include_router(session_tracker_router)
        fastapi_app.include_router(vision_v2_router)
        fastapi_app.include_router(landmark_router)
        fastapi_app.include_router(tools_engine_router)

        _slog.info(f"[bg-init] All routers registered in {time.time()-_r0:.1f}s total")

        # ── Fast synchronous work ─────────────────────────────────────────────
        try:
            validate_env()
        except Exception as _e:
            _slog.error(f"[bg-init] env validation (non-fatal): {_e}")

        try:
            apply_operational_patches(fastapi_app)
        except Exception as _e:
            _slog.error(f"[bg-init] operational patches (non-fatal): {_e}")

        # ── Register inline endpoints ─────────────────────────────────────────

        @fastapi_app.get("/health")
        def health():
            return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}

        @fastapi_app.get("/health/deep")
        def health_deep():
            import app.rag.async_retriever as _retriever
            checks: dict = {}
            try:
                with SessionLocal() as db:
                    db.execute(text("SELECT 1"))
                checks["db"] = "ok"
            except Exception as exc:
                checks["db"] = f"error: {exc}"
            checks["retrieval_pool"] = "ok" if _retriever._pool is not None else "not_initialised"
            try:
                with SessionLocal() as db:
                    count = db.execute(text("SELECT COUNT(*) FROM chunks")).scalar_one()
                checks["chunks"] = count
                checks["chunks_ok"] = count > 1000
            except Exception as exc:
                checks["chunks"] = f"error: {exc}"
                checks["chunks_ok"] = False
            overall = "ok" if all(
                v == "ok" or (isinstance(v, (int, bool)) and v is not False)
                for v in checks.values()
            ) else "degraded"
            return {"status": overall, "checks": checks}

        @fastapi_app.get("/ready")
        def ready():
            import app.rag.async_retriever as _retriever
            if _retriever._pool is None:
                return Response(
                    content='{"status":"not_ready","reason":"retrieval_pool_not_initialised"}',
                    status_code=503,
                    media_type="application/json",
                )
            return {"status": "ready"}

        @fastapi_app.get("/api/speed/stats")
        def speed_stats():
            from app.engine.speed_optimizer import get_speed_stats
            return get_speed_stats()

        from app.core.auth import require_admin_user as _require_admin

        @fastapi_app.get("/metrics-lite")
        def metrics_lite(_user=Depends(_require_admin)):
            with SessionLocal() as db:
                q = db.execute(text("SELECT COUNT(*) FROM queries;")).scalar_one_or_none() or 0
                d = db.execute(text("SELECT COUNT(*) FROM documents;")).scalar_one_or_none() or 0
                c = db.execute(text("SELECT COUNT(*) FROM chunks;")).scalar_one_or_none() or 0
                u = db.execute(text("SELECT COUNT(*) FROM users;")).scalar_one_or_none() or 0
            return {"queries": q, "documents": d, "chunks": c, "users": u}

        # ── CRITICAL: expose the real FastAPI app — requests proxy here now ──
        _real_app = fastapi_app
        elapsed = time.time() - _t0
        _slog.info(
            f"[bg-init] FastAPI app READY — "
            f"total build time {elapsed:.1f}s, all requests now proxied"
        )

        # ── Async operations: scheduled in uvicorn's event loop ───────────────
        # These need to run in the uvicorn event loop (not in this thread).
        # Use run_coroutine_threadsafe to safely schedule them.
        if _uvicorn_loop is not None:
            _asyncio.run_coroutine_threadsafe(
                _async_init(fastapi_app, settings, SessionLocal, text), _uvicorn_loop
            )

        # ── Slow DB / IO work → another background thread ─────────────────────
        def _bg_init():
            import logging as _l
            _bg = _l.getLogger(__name__)

            try:
                warm_embedding_cache()
            except Exception as _e:
                _bg.warning(f"[bg-init/db] embedding cache warm: {_e}")

            try:
                ensure_users_table()
                from app.api.case_store import create_table_sync
                create_table_sync()
                from app.api.session_tracker import create_tables_sync as _st_create
                _st_create()
            except Exception as _e:
                _bg.error(f"[bg-init/db] table DDL: {_e}")

            try:
                from app.db.session import SessionLocal as _SL
                from sqlalchemy import text as _text
                with _SL() as _db:
                    for _sql_block in [DOC_META_MIGRATION_SQL, USERS_CLINIC_MIGRATION_SQL]:
                        for _stmt in _sql_block.strip().split(";"):
                            _stmt = _stmt.strip()
                            if _stmt:
                                try:
                                    _db.execute(_text(_stmt))
                                except Exception:
                                    pass
                    _db.commit()
            except Exception as _e:
                _bg.error(f"[bg-init/db] migration SQL (non-fatal): {_e}")

            try:
                run_network_migrations()
            except Exception as _e:
                _bg.error(f"[bg-init/db] network workspace DDL (non-fatal): {_e}")

            try:
                run_intelligence_migrations()
            except Exception as _e:
                _bg.error(f"[bg-init/db] intelligence DDL (non-fatal): {_e}")

            try:
                _removed = _cleanup_old_exports()
                if _removed:
                    _bg.info(f"[bg-init/db] Cleaned {_removed} expired PDF export(s)")
            except Exception as _e:
                _bg.error(f"[bg-init/db] cleanup: {_e}")

            _bg.info("[bg-init/db] Speed optimizer precompute disabled — hot cache on demand")

            try:
                from datetime import datetime as _dt
                from app.agents.mass_upload import _state, _lock
                from app.api.mass_upload_api import _run_in_thread
                import threading as _thr
                with _lock:
                    if not _state["running"]:
                        _state["running"] = True
                        _state["stop_requested"] = False
                        _state["started_at"] = _dt.utcnow().isoformat()
                _mu_t = _thr.Thread(target=_run_in_thread, name="mass-upload-auto", daemon=True)
                _mu_t.start()
                _bg.info("[bg-init/db] Mass upload agent started")
            except Exception as _e:
                _bg.error(f"[bg-init/db] mass upload: {_e}")

            try:
                import threading as _thr2
                _idx_t = _thr2.Thread(
                    target=_rebuild_missing_indexes_thread,
                    name="index-rebuild",
                    daemon=True,
                )
                _idx_t.start()
                _bg.info("[bg-init/db] Index rebuild thread started")
            except Exception as _e:
                _bg.error(f"[bg-init/db] index rebuild: {_e}")

            _bg.info("[bg-init/db] DB background init complete")

        _db_thread = threading.Thread(target=_bg_init, name="startup-db", daemon=True)
        _db_thread.start()

    except Exception as exc:
        _log.error(f"[bg-init] FATAL — FastAPI build failed: {exc}", exc_info=True)


async def _neon_keepalive() -> None:
    """
    Prevents Neon auto-suspend during active clinic sessions.
    Sends a lightweight ping every 4 minutes.
    On free Neon tier: first query after 5min inactivity adds ~500ms.
    On paid tier: disable auto-suspend in Neon console instead.
    """
    import logging as _logging
    _ka_log = _logging.getLogger(__name__)
    while True:
        await _asyncio.sleep(240)  # 4 minutes
        try:
            import asyncpg as _asyncpg
            _ka_pool = await _asyncpg.create_pool(
                os.environ.get("DATABASE_URL", ""),
                min_size=1, max_size=1, ssl="require",
            )
            await _ka_pool.fetchval("SELECT 1")
            await _ka_pool.close()
        except Exception as _e:
            _ka_log.debug(f"[Keepalive] ping failed (non-critical): {_e}")


async def _async_init(fastapi_app, settings, SessionLocal, text) -> None:
    """
    Async operations that must run in uvicorn's event loop.
    Called via run_coroutine_threadsafe() from _init_background().
    """
    import logging as _logging
    _slog = _logging.getLogger(__name__)

    try:
        from app.api.case_store_postgres import init_cases_table
        await _asyncio.wait_for(init_cases_table(), timeout=15.0)
        _slog.info("[bg-init/async] complication_cases table ready")
    except _asyncio.TimeoutError:
        _slog.warning("[bg-init/async] case_store_postgres init timed out (non-fatal)")
    except Exception as _e:
        _slog.warning(f"[bg-init/async] case_store_postgres init (non-fatal): {_e}")

    try:
        from app.rag.async_retriever import init_retrieval_pool
        _asyncio.create_task(init_retrieval_pool())
        _slog.info("[bg-init/async] retrieval pool init task scheduled")
    except Exception as _e:
        _slog.error(f"[bg-init/async] retrieval pool init (non-fatal): {_e}")

    try:
        _asyncio.create_task(_neon_keepalive())
        _slog.info("[bg-init/async] Neon keepalive task started")
    except Exception as _e:
        _slog.warning(f"[bg-init/async] keepalive task (non-fatal): {_e}")
