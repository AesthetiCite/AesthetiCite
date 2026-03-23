import glob
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import text

from app.core.config import settings
from app.core.limiter import limiter
from app.core.startup import ensure_users_table
from app.core.env_check import validate_env
from app.rag.cache import warm_embedding_cache
from app.rag.async_retriever import init_retrieval_pool, close_retrieval_pool
from app.db.session import SessionLocal
from app.api.ask import router as ask_router
from app.api.ask_stream import router as ask_stream_router
from app.api.admin import router as admin_router
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
from app.api.vision_followup import router as vision_followup_router
from app.api.complication_protocol_engine import router as complication_router
from app.api.preprocedure_safety_engine_v2 import router as preprocedure_safety_router
from app.api.growth_engine import router as growth_router
from app.api.preprocedure_safety_engine_v2 import router as safety_v2_router
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

app = FastAPI(title=settings.APP_NAME)

# NOTE: validate_env() and ensure_users_table() intentionally moved to the
# @app.on_event("startup") handler below so uvicorn can bind and respond to
# health checks immediately — even if the DB is slow to connect in production.
warm_embedding_cache()

origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "x-api-key", "X-Clinic-ID"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(access_router)
app.include_router(ask_router)
app.include_router(ask_stream_router)
app.include_router(history_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(sync_router)
app.include_router(tools_router)
app.include_router(dosing_admin_router)
app.include_router(aesthetic_tools_router)
app.include_router(languages_router)
app.include_router(admin_metrics_router)
app.include_router(clinical_docs_router)
app.include_router(voice_router)
app.include_router(oe_upgrade_router)
app.include_router(benchmark_router)
app.include_router(phase2_5_router)
app.include_router(top10_router)
app.include_router(pilot_router)
app.include_router(deepconsult_pdf_router)
app.include_router(partner_router)
app.include_router(ingest_router)
app.include_router(cases_router)
app.include_router(workflow_router)
app.include_router(report_router)
app.include_router(ask_v2_router)
app.include_router(visual_counseling_router)
app.include_router(vision_followup_router)
app.include_router(complication_router)
app.include_router(preprocedure_safety_router)
app.include_router(growth_router)
app.include_router(operational_router, prefix="/api/ops")
app.include_router(mass_upload_router)
app.include_router(network_workspace_router)
app.include_router(risk_intelligence_router)
app.include_router(complication_monitor_router)
app.include_router(llm_provider_router)
app.include_router(org_analytics_router)
app.include_router(decision_router)
app.include_router(reasoning_router)

from app.api.vision_diagnosis import router as vision_diagnosis_router
app.include_router(vision_diagnosis_router)

from app.api.operational_readiness import router as readiness_router
app.include_router(readiness_router)

from app.api.backup import router as backup_router
app.include_router(backup_router)

# ─── Migrations ───────────────────────────────────────────────────────────────

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


def _rebuild_missing_indexes_thread() -> None:
    """Background thread: rebuild search indexes dropped before deployment to shrink DB size."""
    from sqlalchemy import create_engine, text as _text
    import logging as _logging
    _log = _logging.getLogger(__name__)
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        _log.warning("[index_rebuild] DATABASE_URL not set — skipping index rebuild")
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
                        _log.info(f"[index_rebuild] {name}: present")
                        continue
                    _log.info(f"[index_rebuild] {name}: building (may take 5-30 min)…")
                    conn.execute(_text(ddl))
                    _log.info(f"[index_rebuild] {name}: done ✓")
                except Exception as exc:
                    _log.error(f"[index_rebuild] {name}: FAILED — {exc}")
        engine.dispose()
        _log.info("[index_rebuild] All indexes checked/rebuilt")
    except Exception as exc:
        _log.error(f"[index_rebuild] Cannot connect for rebuild: {exc}")


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


@app.on_event("startup")
async def _startup():
    """
    Startup handler — MUST return quickly so uvicorn can serve /health immediately.

    All slow operations (DB DDL, seeds, index rebuilds, mass-upload agent) are
    dispatched to a single background thread.  The async retrieval pool is started
    as a non-blocking asyncio task.  The startup handler itself returns in <1 s.
    """
    import asyncio as _asyncio
    import logging as _logging
    import threading
    _slog = _logging.getLogger(__name__)

    # ── Fast synchronous work (no I/O) ────────────────────────────────────────
    try:
        validate_env()
    except Exception as _e:
        _slog.error(f"[startup] Environment validation (non-fatal): {_e}")

    apply_operational_patches(app)

    # ── Start async retrieval pool (non-blocking task) ─────────────────────────
    _asyncio.create_task(init_retrieval_pool())

    # ── All slow DB / IO work → background thread ─────────────────────────────
    def _bg_init():
        import logging as _l
        _bg = _l.getLogger(__name__)

        # 1. Core table DDL
        try:
            ensure_users_table()
        except Exception as _e:
            _bg.error(f"[startup/bg] ensure_users_table: {_e}")

        # 2. Legacy migration SQL (column additions etc.)
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
            _bg.error(f"[startup/bg] migration SQL (non-fatal): {_e}")

        # 3. Network workspace DDL + idempotent seed
        try:
            run_network_migrations()
            # run_network_seed()  # dev/demo only — uncomment to seed sample data
        except Exception as _e:
            _bg.error(f"[startup/bg] network workspace DDL/seed (non-fatal): {_e}")

        # 3b. Intelligence tables (risk scores, alerts, monitors, LLM configs, events)
        try:
            run_intelligence_migrations()
        except Exception as _e:
            _bg.error(f"[startup/bg] intelligence DDL (non-fatal): {_e}")

        # 4. Clean up old PDF exports
        try:
            _removed = _cleanup_old_exports()
            if _removed:
                _bg.info(f"[startup/bg] Cleaned {_removed} expired PDF export(s)")
        except Exception as _e:
            _bg.error(f"[startup/bg] cleanup: {_e}")

        # 5. Speed optimizer — precompute hot query embeddings
        try:
            from app.engine.speed_optimizer import precompute_hot_queries
            from app.db.session import SessionLocal as _SpeedSL
            from app.rag.retriever import retrieve_db as _speed_retrieve_db
            with _SpeedSL() as _speed_db:
                precompute_hot_queries(
                    lambda _q, _k: _speed_retrieve_db(db=_speed_db, question=_q, k=_k),
                    max_queries=10,
                    verbose=True,
                )
        except Exception as _e:
            _bg.warning(f"[startup/bg] speed optimizer precompute (non-fatal): {_e}")

        # 6. Mass upload agent
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
            _bg.info("[startup/bg] Mass upload agent started")
        except Exception as _e:
            _bg.error(f"[startup/bg] mass upload: {_e}")

        # 6. Index rebuild
        try:
            import threading as _thr2
            _idx_t = _thr2.Thread(target=_rebuild_missing_indexes_thread, name="index-rebuild", daemon=True)
            _idx_t.start()
            _bg.info("[startup/bg] Index rebuild thread started")
        except Exception as _e:
            _bg.error(f"[startup/bg] index rebuild: {_e}")

        _bg.info("[startup/bg] Background initialization complete")

    _bg_thread = threading.Thread(target=_bg_init, name="startup-bg", daemon=True)
    _bg_thread.start()
    _slog.info("[startup] Background init dispatched — server ready to handle /health immediately")


@app.on_event("shutdown")
async def _shutdown():
    await close_retrieval_pool()


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.get("/health/deep")
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


@app.get("/ready")
def ready():
    import app.rag.async_retriever as _retriever
    from fastapi import Response
    if _retriever._pool is None:
        return Response(
            content='{"status":"not_ready","reason":"retrieval_pool_not_initialised"}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ready"}


@app.get("/api/speed/stats")
def speed_stats():
    from app.engine.speed_optimizer import get_speed_stats
    return get_speed_stats()


@app.get("/metrics-lite")
def metrics_lite():
    with SessionLocal() as db:
        q = db.execute(text("SELECT COUNT(*) FROM queries;")).scalar_one_or_none() or 0
        d = db.execute(text("SELECT COUNT(*) FROM documents;")).scalar_one_or_none() or 0
        c = db.execute(text("SELECT COUNT(*) FROM chunks;")).scalar_one_or_none() or 0
        u = db.execute(text("SELECT COUNT(*) FROM users;")).scalar_one_or_none() or 0
    return {"queries": q, "documents": d, "chunks": c, "users": u}
