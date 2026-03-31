#!/bin/sh
set -e

# Resolve the directory this script lives in (project root).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "[build.sh] Working directory: $(pwd)"
echo "[build.sh] Node: $(node --version 2>/dev/null || echo 'not found')"
echo "[build.sh] npm: $(npm --version 2>/dev/null || echo 'not found')"
echo "[build.sh] package.json present: $(test -f package.json && echo yes || echo NO)"

echo "[build.sh] Installing Node.js dependencies..."
npm install --no-audit --no-fund --loglevel=error

echo "[build.sh] Running TypeScript/Vite build..."
npm run build

# Apply Drizzle migrations against the Neon DB explicitly.
# This takes ownership of the migration step so Replit's platform
# auto-migration system does not need to run (and does not fail trying
# to connect to a local PostgreSQL that doesn't exist in this project).
echo "[build.sh] Applying Drizzle migrations to Neon DB..."
if npx drizzle-kit migrate 2>&1; then
  echo "[build.sh] Migrations applied successfully."
else
  echo "[build.sh] WARNING: Migration step returned non-zero (tables may already exist — continuing)."
fi

echo "[build.sh] Syncing Python dependencies..."
uv sync --frozen --no-dev

# ── Bytecode pre-compilation using the RUNTIME Python ─────────────────────
# The deployment copies files to the production VM and resets .py mtimes to
# the current timestamp.  Default .pyc files record the source mtime at
# compile-time; if the mtime changes after copy, Python discards the .pyc and
# recompiles from source (slow on a network filesystem, blocks startup 200+s).
# --invalidation-mode=unchecked-hash writes .pyc files that Python accepts
# without checking the source timestamp or hash — safe for immutable
# production packages.  We use the RUNTIME Python (.pythonlibs) to ensure
# magic-number compatibility with the process started by start.sh.
RUNTIME_PYTHON="${UV_PROJECT_ENVIRONMENT:-/home/runner/workspace/.pythonlibs}/bin/python3"
if [ ! -f "$RUNTIME_PYTHON" ]; then
  RUNTIME_PYTHON="python3"
fi
echo "[build.sh] Runtime Python: $RUNTIME_PYTHON ($(${RUNTIME_PYTHON} --version 2>&1))"

echo "[build.sh] Pre-compiling app/ bytecode (unchecked-hash)..."
"$RUNTIME_PYTHON" -m compileall -q --invalidation-mode=unchecked-hash app/ 2>/dev/null || true

echo "[build.sh] Pre-compiling site-packages bytecode (unchecked-hash)..."
SITE_PKG="${UV_PROJECT_ENVIRONMENT:-/home/runner/workspace/.pythonlibs}/lib/python3.11/site-packages"
for PKG in sqlalchemy pydantic pydantic_core fastapi starlette asyncpg anyio uvicorn slowapi; do
  if [ -d "${SITE_PKG}/${PKG}" ]; then
    "$RUNTIME_PYTHON" -m compileall -q --invalidation-mode=unchecked-hash \
      "${SITE_PKG}/${PKG}" 2>/dev/null || true
    echo "[build.sh]   compiled: ${PKG}"
  fi
done

# Warm ALL router modules so their bytecode is compiled and cached in the
# deployment image.  In production the startup event imports these 43+
# modules; if their .pyc files already exist the cold-disk penalty drops
# from ~8 minutes (parsing .py files) to ~30-60 seconds (reading .pyc).
echo "[build.sh] Warming router bytecode (pre-compiling all 43+ API modules)..."
export PYDANTIC_DISABLE_PLUGINS=1
(
  timeout 300 "$RUNTIME_PYTHON" -c "
import sys, time, importlib
t0 = time.time()

# Module-level imports (app/main.py scope)
print('[build-warmup] Importing app.main...', flush=True)
try:
    import app.main
    print(f'[build-warmup] app.main OK ({time.time()-t0:.1f}s)', flush=True)
except Exception as e:
    print(f'[build-warmup] app.main warning: {type(e).__name__}: {e}', flush=True)

# All deferred router modules (startup-handler scope)
routers = [
    'app.core.startup', 'app.core.env_check',
    'app.rag.cache', 'app.rag.async_retriever', 'app.db.session',
    'app.api.ask', 'app.api.ask_stream', 'app.api.admin',
    'app.api.admin_dashboard', 'app.api.auth', 'app.api.access',
    'app.api.analytics', 'app.api.sync', 'app.api.history',
    'app.api.tools', 'app.api.aesthetic_tools', 'app.api.languages',
    'app.api.admin_metrics', 'app.api.clinical_docs', 'app.api.voice',
    'app.api.oe_upgrade', 'app.api.benchmark', 'app.api.phase2_5',
    'app.api.aestheticite_top10', 'app.pilot_proof',
    'app.core.deepconsult_pdf_export', 'app.api.partner_preview',
    'app.api.ingest', 'app.api.cases', 'app.api.workflow_engine',
    'app.api.report_generator', 'app.api.ask_v2',
    'app.api.visual_counseling', 'app.api.vision_followup',
    'app.api.visual_differential', 'app.api.visual_enhancements',
    'app.api.vision_analysis', 'app.api.session_tracker',
    'app.api.complication_protocol_engine',
    'app.api.preprocedure_safety_engine_v2', 'app.api.growth_engine',
    'app.api.operational', 'app.api.mass_upload_api',
    'app.api.network_workspace', 'app.db.network_migrations',
    'app.api.risk_intelligence', 'app.api.complication_monitor',
    'app.api.llm_provider', 'app.api.org_analytics',
    'app.db.intelligence_migrations', 'app.api.clinical_decision',
    'app.api.clinical_reasoning', 'app.api.routes.cases',
    'app.api.vision_diagnosis', 'app.api.operational_readiness',
    'app.api.backup', 'app.api.rechunk', 'app.api.m5_ext',
    'app.api.neon_migrate',
]
print(f'[build-warmup] Importing {len(routers)} router modules...', flush=True)
ok = 0
for r in routers:
    try:
        importlib.import_module(r)
        ok += 1
    except Exception as e:
        print(f'[build-warmup]   {r}: {type(e).__name__}: {e}', flush=True)

elapsed = time.time() - t0
print(f'[build-warmup] Done: {ok}/{len(routers)} routers compiled in {elapsed:.1f}s', flush=True)
" 2>&1
) || echo "[build.sh] WARNING: Router warmup timed out/failed (non-fatal)"

echo "[build.sh] Build complete."
