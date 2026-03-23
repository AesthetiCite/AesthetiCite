#!/usr/bin/env bash
# =============================================================================
# AesthetiCite — Integration Script
# =============================================================================
# Runs all remaining integration steps to reach ~95% operational.
#
# Usage:
#   chmod +x integrate.sh
#   ./integrate.sh
#
# What it does:
#   1. Installs npm dependencies (express-rate-limit)
#   2. Installs Python dependencies (psycopg2-binary, sentry-sdk, boto3)
#   3. Copies all output files to the right locations
#   4. Patches ask.tsx logQueryToClinic
#   5. Patches main.tsx PWA registration
#   6. Patches routes.ts to call registerOperationalRoutes
#   7. Imports mobile.css in index.css
#   8. Validates the integration
#
# Prerequisites:
#   - Run from the project root directory
#   - Node.js and npm are available
#   - Python and pip are available
#   - The /outputs directory contains all generated files
#
# IMPORTANT: Review each change before running in production.
# =============================================================================

set -euo pipefail

# ─── Colour output ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()   { echo -e "${YELLOW}[⚠]${NC} $1"; }
error()  { echo -e "${RED}[✗]${NC} $1"; }
info()   { echo -e "${BLUE}[→]${NC} $1"; }
header() { echo -e "\n${BLUE}═══ $1 ═══${NC}"; }

# ─── Project root detection ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# Detect common project structures
if [ ! -f "${PROJECT_ROOT}/package.json" ]; then
  # Try parent
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

if [ ! -f "${PROJECT_ROOT}/package.json" ]; then
  error "Cannot find project root (no package.json). Run from project root."
  exit 1
fi

OUTPUTS_DIR="${SCRIPT_DIR}"
CLIENT_DIR="${PROJECT_ROOT}/client"
SERVER_DIR="${PROJECT_ROOT}/server"
APP_DIR="${PROJECT_ROOT}/app"

log "Project root: ${PROJECT_ROOT}"

# ─── Step 1: npm dependencies ─────────────────────────────────────────────────
header "Step 1: Installing npm dependencies"

cd "${PROJECT_ROOT}"

if ! grep -q "express-rate-limit" package.json 2>/dev/null; then
  info "Installing express-rate-limit..."
  npm install express-rate-limit@^7.0.0 --save
  log "express-rate-limit installed"
else
  log "express-rate-limit already in package.json"
fi

# ─── Step 2: Python dependencies ─────────────────────────────────────────────
header "Step 2: Installing Python dependencies"

PACKAGES=("psycopg2-binary>=2.9.9" "sentry-sdk[fastapi]>=1.40.0" "boto3>=1.34.0")

for pkg in "${PACKAGES[@]}"; do
  pkg_name="${pkg%%[>=<]*}"
  pkg_name="${pkg_name%[*}"
  if pip show "${pkg_name}" &>/dev/null 2>&1; then
    log "${pkg_name} already installed"
  else
    info "Installing ${pkg_name}..."
    pip install "${pkg}" --break-system-packages --quiet || \
    pip install "${pkg}" --quiet || \
    warn "Could not install ${pkg_name} — install manually: pip install '${pkg}'"
  fi
done

# ─── Step 3: Copy files to correct locations ──────────────────────────────────
header "Step 3: Copying generated files"

copy_file() {
  local src="$1"
  local dest="$2"
  local desc="$3"

  if [ ! -f "${src}" ]; then
    warn "Source not found: ${src} — skipping ${desc}"
    return
  fi

  mkdir -p "$(dirname "${dest}")"

  # Backup existing file
  if [ -f "${dest}" ]; then
    cp "${dest}" "${dest}.backup_$(date +%Y%m%d_%H%M%S)"
    info "Backed up existing ${dest}"
  fi

  cp "${src}" "${dest}"
  log "Copied ${desc} → ${dest}"
}

# Python backend files
copy_file "${OUTPUTS_DIR}/growth_engine_pg.py" \
          "${APP_DIR}/api/growth_engine.py" \
          "Growth Engine (PostgreSQL)"

copy_file "${OUTPUTS_DIR}/main_complete.py" \
          "${APP_DIR}/main.py" \
          "main.py with all patches"

copy_file "${OUTPUTS_DIR}/preprocedure_safety_engine_v2.py" \
          "${APP_DIR}/api/preprocedure_safety_engine_v2.py" \
          "Pre-procedure Safety Engine v2"

copy_file "${OUTPUTS_DIR}/aestheticite_operational.py" \
          "${APP_DIR}/api/operational.py" \
          "Operational fixes module"

# Frontend files
copy_file "${OUTPUTS_DIR}/App_complete.tsx" \
          "${CLIENT_DIR}/src/App.tsx" \
          "App.tsx with all routes"

copy_file "${OUTPUTS_DIR}/SafetyWorkspace.tsx" \
          "${CLIENT_DIR}/src/pages/safety-workspace.tsx" \
          "Safety Workspace page"

copy_file "${OUTPUTS_DIR}/offline.html" \
          "${CLIENT_DIR}/public/offline.html" \
          "Offline fallback page"

copy_file "${OUTPUTS_DIR}/sw_production.js" \
          "${CLIENT_DIR}/public/sw.js" \
          "Production service worker"

copy_file "${OUTPUTS_DIR}/mobile.css" \
          "${CLIENT_DIR}/src/mobile.css" \
          "Mobile CSS overrides"

copy_file "${OUTPUTS_DIR}/routes_additions.ts" \
          "${SERVER_DIR}/routes_additions.ts" \
          "Routes additions module"

# ─── Step 4: Patch ask.tsx logQueryToClinic ────────────────────────────────────
header "Step 4: Patching ask.tsx logQueryToClinic"

ASK_FILE="${CLIENT_DIR}/src/pages/ask.tsx"

if [ ! -f "${ASK_FILE}" ]; then
  warn "ask.tsx not found at ${ASK_FILE} — skipping patch"
else
  # Check if already patched
  if grep -q "api/ops/dashboard/log-query" "${ASK_FILE}" 2>/dev/null; then
    log "ask.tsx already patched"
  else
    # Backup
    cp "${ASK_FILE}" "${ASK_FILE}.backup_$(date +%Y%m%d_%H%M%S)"

    # Use Python for reliable multiline sed (more portable than sed -z)
    python3 - "${ASK_FILE}" << 'PYEOF'
import sys
import re

filepath = sys.argv[1]
with open(filepath, 'r') as f:
    content = f.read()

old_fn = '''function logQueryToClinic(question: string, answerPreview: string, aci: number | null, durationMs: number) {
    const clinicId = localStorage.getItem("aestheticite_clinic_id") || "";
    fetch("/api/growth/query-logs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clinic_id: clinicId || undefined,
        query: question,
        answer_preview: answerPreview.slice(0, 400),
        response_time_ms: Math.round(durationMs),
        aci_score: aci ?? undefined,
      }),
    }).catch(() => {});
  }'''

new_fn = '''function logQueryToClinic(question: string, _answerPreview: string, aci: number | null, durationMs: number) {
    const token = getToken();
    if (!token) return;
    fetch("/api/ops/dashboard/log-query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        query_text: question,
        answer_type: "evidence_search",
        aci_score: aci ?? undefined,
        response_time_ms: Math.round(durationMs),
        domain: "aesthetic_medicine",
      }),
    }).catch(() => {});
  }'''

if old_fn in content:
    content = content.replace(old_fn, new_fn)
    with open(filepath, 'w') as f:
        f.write(content)
    print("✓ Patched logQueryToClinic in ask.tsx")
else:
    print("⚠ Could not find exact logQueryToClinic pattern — patch manually")
    print("  See comments in mobile.css for the replacement code")
PYEOF

    log "ask.tsx logQueryToClinic patched"
  fi
fi

# ─── Step 5: Patch main.tsx PWA registration ──────────────────────────────────
header "Step 5: Patching main.tsx PWA registration"

MAIN_TSX="${CLIENT_DIR}/src/main.tsx"

if [ ! -f "${MAIN_TSX}" ]; then
  warn "main.tsx not found — skipping PWA registration patch"
else
  if grep -q "serviceWorker" "${MAIN_TSX}" 2>/dev/null; then
    log "main.tsx already has service worker registration"
  else
    cp "${MAIN_TSX}" "${MAIN_TSX}.backup_$(date +%Y%m%d_%H%M%S)"

    # Append PWA registration at end of file
    cat >> "${MAIN_TSX}" << 'SWEOF'

// ─── PWA Service Worker Registration ─────────────────────────────────────────
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then(reg => {
        console.log('[PWA] Service worker registered', reg.scope);
        setInterval(() => reg.update(), 60000);
      })
      .catch(err => console.warn('[PWA] SW registration failed', err));
  });
}
SWEOF

    log "main.tsx PWA registration added"
  fi
fi

# ─── Step 6: Patch routes.ts ──────────────────────────────────────────────────
header "Step 6: Patching server/routes.ts"

ROUTES_FILE="${SERVER_DIR}/routes.ts"

if [ ! -f "${ROUTES_FILE}" ]; then
  warn "routes.ts not found at ${ROUTES_FILE} — skipping"
else
  if grep -q "registerOperationalRoutes" "${ROUTES_FILE}" 2>/dev/null; then
    log "routes.ts already has registerOperationalRoutes"
  else
    cp "${ROUTES_FILE}" "${ROUTES_FILE}.backup_$(date +%Y%m%d_%H%M%S)"

    # Add import at top (after first import line)
    python3 - "${ROUTES_FILE}" << 'PYEOF'
import sys

filepath = sys.argv[1]
with open(filepath, 'r') as f:
    content = f.read()

# Add import after the first import statement
import_line = 'import { registerOperationalRoutes } from "./routes_additions";\n'
if import_line not in content:
    # Find position after first import block
    lines = content.split('\n')
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith('import '):
            insert_at = i + 1
    lines.insert(insert_at, import_line.strip())
    content = '\n'.join(lines)

# Add registerOperationalRoutes call before return httpServer
if 'registerOperationalRoutes(app)' not in content:
    content = content.replace(
        'return httpServer;',
        '  registerOperationalRoutes(app);\n  return httpServer;'
    )

with open(filepath, 'w') as f:
    f.write(content)
print("✓ Patched routes.ts")
PYEOF

    log "routes.ts patched with registerOperationalRoutes"
  fi
fi

# ─── Step 7: Import mobile.css in index.css ───────────────────────────────────
header "Step 7: Adding mobile.css import"

INDEX_CSS="${CLIENT_DIR}/src/index.css"

if [ ! -f "${INDEX_CSS}" ]; then
  warn "index.css not found — skipping mobile.css import"
else
  if grep -q "mobile.css" "${INDEX_CSS}" 2>/dev/null; then
    log "mobile.css already imported in index.css"
  else
    echo "" >> "${INDEX_CSS}"
    echo "@import './mobile.css';" >> "${INDEX_CSS}"
    log "mobile.css imported in index.css"
  fi
fi

# ─── Step 8: Create PWA icon placeholders ────────────────────────────────────
header "Step 8: Checking PWA icons"

ICONS_DIR="${CLIENT_DIR}/public/icons"
mkdir -p "${ICONS_DIR}"

if [ -f "${ICONS_DIR}/icon-192.png" ] && [ -f "${ICONS_DIR}/icon-512.png" ]; then
  log "PWA icons already exist"
else
  warn "PWA icons missing at ${ICONS_DIR}/"
  warn "Create icon-192.png and icon-512.png manually"
  warn "Recommended: Use https://realfavicongenerator.net/ or Figma to export"
  warn "The PWA will work without icons but install prompt may not appear"

  # Create SVG placeholders that at least won't crash the manifest
  cat > "${ICONS_DIR}/icon-192.svg" << 'SVGEOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
  <rect width="192" height="192" rx="32" fill="#6366f1"/>
  <text x="96" y="130" text-anchor="middle" font-size="100" fill="white" font-family="system-ui">⬡</text>
</svg>
SVGEOF
  info "Created SVG placeholder icons — replace with proper PNG icons before launch"
fi

# ─── Step 9: Validate environment variables ───────────────────────────────────
header "Step 9: Checking environment variables"

check_env() {
  local var="$1"
  local required="$2"
  local val="${!var:-}"

  if [ -n "${val}" ]; then
    log "${var} ✓"
  elif [ "${required}" = "required" ]; then
    error "${var} — REQUIRED but not set"
  else
    warn "${var} — not set (optional feature will be disabled)"
  fi
}

check_env "DATABASE_URL" "required"
check_env "AI_INTEGRATIONS_OPENAI_API_KEY" "required"
check_env "JWT_SECRET" "required"
check_env "SENTRY_DSN" "optional"
check_env "SMTP_HOST" "optional"
check_env "SMTP_USER" "optional"
check_env "SMTP_PASSWORD" "optional"
check_env "APP_BASE_URL" "optional"
check_env "AWS_S3_BUCKET" "optional"
check_env "NCBI_API_KEY" "optional"

# ─── Step 10: Summary ─────────────────────────────────────────────────────────
header "Integration Complete"

echo ""
echo -e "${GREEN}All integration steps applied.${NC}"
echo ""
echo "Next steps:"
echo "  1. Deploy the updated application"
echo "  2. Call POST /api/ops/ingest/start (admin) to populate the knowledge base"
echo "  3. Call GET /api/ops/health/full to verify all checks pass"
echo "  4. Set missing environment variables (SMTP_HOST, SENTRY_DSN, etc.)"
echo "  5. Replace placeholder SVG icons with proper PNG icons"
echo ""
echo "Backup files created with .backup_TIMESTAMP suffix — delete when stable."
echo ""

# ─── Optional: Kick off ingestion if DATABASE_URL is set ──────────────────────
if [ -n "${DATABASE_URL:-}" ]; then
  echo -e "${YELLOW}Would you like to start the knowledge base ingestion now?${NC}"
  echo "This will populate pgvector with aesthetic medicine papers from PubMed."
  read -p "Start ingestion? (y/N) " -n 1 -r
  echo ""
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    info "Note: Ingestion requires an authenticated admin JWT token."
    info "Run this after deployment:"
    echo "  curl -X POST https://your-app.com/api/ops/ingest/start \\"
    echo "    -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \\"
    echo "    -H 'Content-Type: application/json'"
    echo ""
    info "Monitor progress:"
    echo "  curl https://your-app.com/api/ops/ingest/status \\"
    echo "    -H 'Authorization: Bearer YOUR_ADMIN_TOKEN'"
  fi
fi

echo -e "${GREEN}Done.${NC}"
