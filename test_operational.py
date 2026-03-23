#!/usr/bin/env python3
"""
AesthetiCite — Operational Test Suite
======================================
Run from Replit Shell:
    python3 test_operational.py

No extra installs needed — uses only stdlib + packages already in your project.

Tests every layer:
  1. Environment variables
  2. Python FastAPI server (port 8000)
  3. Node/Express server (port 5000)
  4. PostgreSQL + pgvector
  5. Knowledge base population
  6. All safety engine endpoints
  7. Growth engine (PostgreSQL)
  8. Auth flow
  9. PDF export directory
 10. Evidence retrieval (live vs dummy)
 11. Dashboard logging
 12. Frontend reachability
 13. Service worker / PWA
 14. Operational readiness endpoint (if deployed)

Produces:
  - Colour-coded pass/fail per check
  - Weighted score out of 100
  - Exact fix instructions for every failure
  - JSON report saved to  test_report.json
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ─── Colour helpers ────────────────────────────────────────────────────────────

SUPPORTS_COLOUR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def c(text: str, code: str) -> str:
    if not SUPPORTS_COLOUR:
        return text
    return f"\033[{code}m{text}\033[0m"

GREEN   = lambda t: c(t, "32")
RED     = lambda t: c(t, "31")
YELLOW  = lambda t: c(t, "33")
BLUE    = lambda t: c(t, "34")
CYAN    = lambda t: c(t, "36")
BOLD    = lambda t: c(t, "1")
DIM     = lambda t: c(t, "2")
MAGENTA = lambda t: c(t, "35")

def tick(ok: bool) -> str:
    return GREEN("  ✓") if ok else RED("  ✗")

def warn_icon() -> str:
    return YELLOW("  ⚠")

# ─── HTTP helper ───────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 5, token: str = "") -> Tuple[int, Any]:
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            return e.code, json.loads(body) if body else {}
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, str(e)


def http_post(url: str, payload: Dict, timeout: int = 10, token: str = "") -> Tuple[int, Any]:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            return e.code, json.loads(body) if body else {}
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, str(e)


# ─── Database helper ───────────────────────────────────────────────────────────

def db_query(sql: str) -> Tuple[bool, Any]:
    try:
        import psycopg2
        import psycopg2.extras
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            return False, "DATABASE_URL not set"
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        conn.close()
        return True, result
    except ImportError:
        # Try via sqlalchemy if psycopg2 not available
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(os.environ.get("DATABASE_URL", ""))
            with engine.connect() as conn:
                result = conn.execute(text(sql)).fetchall()
            return True, result
        except Exception as e2:
            return False, str(e2)
    except Exception as e:
        return False, str(e)


def db_scalar(sql: str, default: Any = None) -> Any:
    ok, result = db_query(sql)
    if ok and result and result[0]:
        return result[0][0]
    return default


# ─── Test result accumulator ───────────────────────────────────────────────────

class TestResult:
    def __init__(self, id: str, label: str, weight: int, category: str):
        self.id = id
        self.label = label
        self.weight = weight
        self.category = category
        self.ok: bool = False
        self.detail: str = ""
        self.fix: str = ""
        self.value: Any = None

    def passed(self, detail: str = "", value: Any = None) -> "TestResult":
        self.ok = True
        self.detail = detail
        self.value = value
        return self

    def failed(self, detail: str, fix: str = "") -> "TestResult":
        self.ok = False
        self.detail = detail
        self.fix = fix
        return self

    def warn(self, detail: str, fix: str = "") -> "TestResult":
        """Treat as passed but show warning."""
        self.ok = True
        self.detail = f"⚠ {detail}"
        self.fix = fix
        return self


results: List[TestResult] = []

def test(id: str, label: str, weight: int, category: str = "general") -> TestResult:
    r = TestResult(id, label, weight, category)
    results.append(r)
    return r


# ─── SECTION 1: Environment variables ─────────────────────────────────────────

def check_environment():
    print(BOLD(BLUE("\n─── 1. Environment Variables ───────────────────────────────────")))

    checks = [
        ("DATABASE_URL",                     "DATABASE_URL",                12, True),
        ("AI_INTEGRATIONS_OPENAI_API_KEY",   "OpenAI API key",              10, True),
        ("JWT_SECRET",                        "JWT_SECRET",                  8,  True),
        ("SENTRY_DSN",                        "Sentry DSN",                  3,  False),
        ("SMTP_HOST",                         "SMTP host",                   4,  False),
        ("SMTP_USER",                         "SMTP user",                   4,  False),
        ("APP_BASE_URL",                      "APP_BASE_URL",                4,  False),
        ("AWS_S3_BUCKET",                     "S3 bucket",                   2,  False),
        ("NCBI_API_KEY",                      "NCBI API key (PubMed)",        2,  False),
        ("AESTHETICITE_PGVECTOR_ENABLED",     "pgvector flag",               3,  False),
    ]

    for env_key, label, weight, required in checks:
        val = os.environ.get(env_key, "")
        r = test(f"env_{env_key.lower()}", f"{label} ({env_key})", weight, "environment")
        if val:
            display = val[:6] + "…" if len(val) > 10 else val
            r.passed(f"set ({display})")
        elif required:
            r.failed(
                f"{env_key} is not set",
                f"In Replit: Secrets tab → Add secret → Key: {env_key}"
            )
        else:
            r.warn(
                f"{env_key} not set — feature will be disabled",
                f"Optional: Secrets tab → Add secret → Key: {env_key}"
            )

        status = tick(r.ok) if required or r.ok else warn_icon()
        print(f"{status}  {label:<40} {DIM(r.detail)}")


# ─── SECTION 2: Python FastAPI server ─────────────────────────────────────────

def check_python_server():
    print(BOLD(BLUE("\n─── 2. Python FastAPI Server (port 8000) ───────────────────────")))

    base = "http://localhost:8000"

    # Health
    r = test("fastapi_health", "FastAPI health endpoint", 10, "infrastructure")
    status, body = http_get(f"{base}/health", timeout=5)
    if status == 200 and isinstance(body, dict):
        r.passed(f"status={body.get('status', 'unknown')}")
    else:
        r.failed(
            f"HTTP {status} — FastAPI may not be running",
            "In Replit Shell: check if uvicorn is running. Run: ps aux | grep uvicorn"
        )
    print(f"{tick(r.ok)}  FastAPI /health                         {DIM(r.detail)}")

    # Complications protocols
    r = test("fastapi_complications", "Complication protocols endpoint", 6, "safety")
    status, body = http_get(f"{base}/api/complications/protocols", timeout=5)
    if status == 200 and isinstance(body, list):
        r.passed(f"{len(body)} protocols loaded")
    else:
        r.failed(f"HTTP {status}", "Check complication_protocol_engine.py is registered in main.py")
    print(f"{tick(r.ok)}  /api/complications/protocols            {DIM(r.detail)}")

    # Pre-procedure safety
    r = test("fastapi_preprocedure", "Pre-procedure safety check", 8, "safety")
    status, body = http_post(f"{base}/api/safety/preprocedure-check", {
        "procedure": "lip filler",
        "region": "lip",
        "product_type": "hyaluronic acid filler"
    }, timeout=8)
    if status == 200 and isinstance(body, dict) and "safety_assessment" in body:
        decision = body.get("safety_assessment", {}).get("decision", "?")
        score = body.get("safety_assessment", {}).get("overall_risk_score", "?")
        r.passed(f"decision={decision}, score={score}/100")
    else:
        r.failed(f"HTTP {status}: {str(body)[:80]}", "Check preprocedure_safety_engine.py is registered in main.py")
    print(f"{tick(r.ok)}  /api/safety/preprocedure-check          {DIM(r.detail)}")

    # Drug interactions
    r = test("fastapi_drug", "Drug interaction checker", 4, "safety")
    status, body = http_post(f"{base}/api/growth/drug-interactions", {
        "medications": ["warfarin"],
        "planned_products": ["hyaluronic acid filler"]
    }, timeout=5)
    if status == 200 and isinstance(body, dict) and "items" in body:
        r.passed(f"{len(body.get('items', []))} interaction(s) found")
    else:
        r.failed(f"HTTP {status}", "Check growth_engine.py drug-interactions endpoint")
    print(f"{tick(r.ok)}  /api/growth/drug-interactions            {DIM(r.detail)}")

    # Metrics lite
    r = test("fastapi_metrics", "Metrics lite endpoint", 3, "infrastructure")
    status, body = http_get(f"{base}/metrics-lite", timeout=5)
    if status == 200 and isinstance(body, dict):
        docs = body.get("documents", 0)
        chunks = body.get("chunks", 0)
        r.passed(f"docs={docs}, chunks={chunks}")
        if docs == 0:
            r.warn(f"docs=0 — knowledge base is empty!", "Run: POST /api/ops/ingest/start (admin)")
    else:
        r.failed(f"HTTP {status}", "Check /metrics-lite in main.py")
    print(f"{tick(r.ok)}  /metrics-lite                           {DIM(r.detail)}")


# ─── SECTION 3: Express / Node server ─────────────────────────────────────────

def check_express_server():
    print(BOLD(BLUE("\n─── 3. Express / Node Server (port 5000) ───────────────────────")))

    base = "http://localhost:5000"

    # Root page
    r = test("express_root", "Express server responding", 8, "infrastructure")
    status, body = http_get(f"{base}/", timeout=5)
    if status in (200, 304):
        r.passed("HTML served")
    else:
        r.failed(f"HTTP {status}", "In Replit Shell: npm run dev — or check if server is running")
    print(f"{tick(r.ok)}  GET /                                   {DIM(r.detail)}")

    # Health proxy
    r = test("express_health_proxy", "Express → FastAPI health proxy", 6, "infrastructure")
    status, body = http_get(f"{base}/api/health", timeout=5)
    if status == 200:
        r.passed("proxy working")
    else:
        r.failed(f"HTTP {status}", "Check /api/health proxy in routes.ts")
    print(f"{tick(r.ok)}  GET /api/health                         {DIM(r.detail)}")

    # Manifest
    r = test("express_manifest", "PWA manifest.json", 2, "pwa")
    status, body = http_get(f"{base}/manifest.json", timeout=5)
    if status == 200 and isinstance(body, dict) and "name" in body:
        r.passed(f"name={body.get('name', '?')}")
    else:
        r.failed(f"HTTP {status}", "Check manifest.json route in routes.ts")
    print(f"{tick(r.ok)}  GET /manifest.json                      {DIM(r.detail)}")

    # Service worker
    r = test("express_sw", "Service worker (sw.js)", 2, "pwa")
    status, body = http_get(f"{base}/sw.js", timeout=5)
    if status == 200 and isinstance(body, str) and "addEventListener" in body:
        is_stub = "pass-through" in body.lower() or len(body) < 200
        if is_stub:
            r.warn("sw.js is pass-through stub — not real PWA", "Replace with sw_production.js from outputs/")
        else:
            r.passed("production service worker")
    else:
        r.failed(f"HTTP {status}", "Check sw.js route in routes.ts, or copy sw_production.js to client/public/sw.js")
    print(f"{tick(r.ok)}  GET /sw.js                              {DIM(r.detail)}")

    # Safety check proxy
    r = test("express_safety_proxy", "Safety check proxy", 5, "safety")
    status, body = http_post(f"{base}/api/safety/preprocedure-check", {
        "procedure": "tear trough filler",
        "region": "tear trough",
        "product_type": "hyaluronic acid filler"
    }, timeout=10)
    if status == 200 and isinstance(body, dict) and "safety_assessment" in body:
        r.passed("proxy + engine working end-to-end")
    else:
        r.failed(f"HTTP {status}", "Check /api/safety/preprocedure-check proxy in routes.ts")
    print(f"{tick(r.ok)}  POST /api/safety/preprocedure-check     {DIM(r.detail)}")

    # Dashboard log-query (expects 401 without token — that's fine, means route exists)
    r = test("express_dashboard_route", "Dashboard log-query route exists", 3, "dashboard")
    status, _ = http_post(f"{base}/api/ops/dashboard/log-query", {}, timeout=5)
    if status in (200, 401, 403, 422):
        r.passed(f"route exists (HTTP {status})")
    else:
        r.failed(f"HTTP {status} — route missing", "Add /api/ops/dashboard/log-query proxy to routes.ts")
    print(f"{tick(r.ok)}  POST /api/ops/dashboard/log-query       {DIM(r.detail)}")

    # Reset password route
    r = test("express_reset_route", "Password reset route exists", 3, "auth")
    status, _ = http_post(f"{base}/api/ops/auth/forgot-password", {"email": "test@test.com"}, timeout=5)
    if status in (200, 400, 401, 422):
        r.passed(f"route exists (HTTP {status})")
    else:
        r.failed(f"HTTP {status} — route missing", "Add /api/ops/auth/forgot-password proxy to routes.ts")
    print(f"{tick(r.ok)}  POST /api/ops/auth/forgot-password      {DIM(r.detail)}")


# ─── SECTION 4: PostgreSQL + pgvector ─────────────────────────────────────────

def check_database():
    print(BOLD(BLUE("\n─── 4. PostgreSQL + pgvector ───────────────────────────────────")))

    # Connection
    r = test("db_connection", "PostgreSQL connected", 12, "database")
    ok, result = db_query("SELECT version()")
    if ok and result:
        version = str(result[0][0])[:50]
        r.passed(version)
    else:
        r.failed(
            str(result)[:80],
            "Check DATABASE_URL secret in Replit. Format: postgresql://user:pass@host:5432/db"
        )
    print(f"{tick(r.ok)}  PostgreSQL connection                   {DIM(r.detail)}")

    if not r.ok:
        print(DIM("     Skipping remaining DB checks — no connection"))
        for skip_id in ["db_pgvector", "db_users", "db_documents", "db_chunks",
                         "db_embeddings", "db_growth_tables", "db_auth_tables",
                         "db_safety_tables"]:
            results.append(test(skip_id, f"DB: {skip_id}", 0, "database").failed("skipped"))
        return

    # pgvector extension
    r = test("db_pgvector", "pgvector extension installed", 8, "database")
    ok, result = db_query("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    if ok and result:
        r.passed("vector extension present")
    else:
        r.failed(
            "pgvector not installed",
            "Run in Replit Shell: python3 -c \"from app.api.operational_readiness import run_auto_fix; run_auto_fix()\""
            " OR: psql $DATABASE_URL -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
        )
    print(f"{tick(r.ok)}  pgvector extension                      {DIM(r.detail)}")

    # Users table
    r = test("db_users", "Users table exists", 5, "database")
    count = db_scalar("SELECT COUNT(*) FROM users", None)
    if count is not None:
        r.passed(f"{count} users")
    else:
        r.failed("users table missing", "Run database migrations")
    print(f"{tick(r.ok)}  users table                             {DIM(r.detail)}")

    # Documents
    r = test("db_documents", "Documents table populated", 8, "database")
    doc_count = db_scalar("SELECT COUNT(*) FROM documents", 0)
    aesthetic_count = db_scalar(
        "SELECT COUNT(*) FROM documents WHERE domain = 'aesthetic_medicine'", 0
    )
    if (doc_count or 0) > 100:
        r.passed(f"{doc_count} total, {aesthetic_count} aesthetic")
    elif (doc_count or 0) > 0:
        r.warn(
            f"Only {doc_count} documents — needs more",
            "Run: POST /api/ops/ingest/start to populate from PubMed"
        )
    else:
        r.failed(
            "Knowledge base is EMPTY",
            "CRITICAL: Run ingestion — POST /api/ops/ingest/start with admin token"
        )
    print(f"{tick(r.ok)}  documents table ({doc_count} docs)          {DIM(r.detail)}")

    # Chunks with embeddings
    r = test("db_embeddings", "Chunks with embeddings", 6, "database")
    chunk_count = db_scalar("SELECT COUNT(*) FROM chunks", 0)
    embedded_count = db_scalar(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL", 0
    )
    if (embedded_count or 0) > 50:
        r.passed(f"{embedded_count}/{chunk_count} chunks embedded")
    elif (chunk_count or 0) > 0:
        r.warn(
            f"{embedded_count}/{chunk_count} chunks have embeddings",
            "Re-run ingestion to regenerate embeddings: POST /api/ops/ingest/start"
        )
    else:
        r.failed("No chunks with embeddings", "Run ingestion pipeline first")
    print(f"{tick(r.ok)}  chunks with embeddings                  {DIM(r.detail)}")

    # Growth engine tables
    r = test("db_growth_tables", "Growth engine tables (PostgreSQL)", 6, "database")
    _growth_table_queries = {
        "growth_bookmarks":         "SELECT COUNT(*) FROM growth_bookmarks",
        "growth_session_reports":   "SELECT COUNT(*) FROM growth_session_reports",
        "growth_query_logs":        "SELECT COUNT(*) FROM growth_query_logs",
        "growth_patient_exports":   "SELECT COUNT(*) FROM growth_patient_exports",
        "growth_api_keys":          "SELECT COUNT(*) FROM growth_api_keys",
        "growth_paper_subscriptions": "SELECT COUNT(*) FROM growth_paper_subscriptions",
    }
    missing = []
    for table, query in _growth_table_queries.items():
        count = db_scalar(query, None)
        if count is None:
            missing.append(table)
    if not missing:
        r.passed(f"all {len(_growth_table_queries)} tables present")
    else:
        r.failed(
            f"Missing: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}",
            "Run: POST /api/ops/readiness/fix (admin) OR copy growth_engine_pg.py to app/api/growth_engine.py and restart"
        )
    print(f"{tick(r.ok)}  growth engine tables                    {DIM(r.detail)}")

    # Auth tables
    r = test("db_auth_tables", "Auth & operational tables", 5, "database")
    _auth_table_queries = {
        "auth_tokens":       "SELECT COUNT(*) FROM auth_tokens",
        "query_logs_v2":     "SELECT COUNT(*) FROM query_logs_v2",
        "complication_cases": "SELECT COUNT(*) FROM complication_cases",
    }
    missing_auth = []
    for table, query in _auth_table_queries.items():
        count = db_scalar(query, None)
        if count is None:
            missing_auth.append(table)

    # Also check user columns
    email_col = db_scalar(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='users' AND column_name='email_verified'", 0
    )
    clinic_col = db_scalar(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='users' AND column_name='clinic_id'", 0
    )
    if not missing_auth and email_col and clinic_col:
        r.passed("auth_tokens, query_logs_v2, complication_cases + user columns")
    else:
        issues = missing_auth[:]
        if not email_col:
            issues.append("users.email_verified column")
        if not clinic_col:
            issues.append("users.clinic_id column")
        r.failed(
            f"Missing: {', '.join(issues[:3])}",
            "Run: POST /api/ops/readiness/fix (admin) to auto-create all tables"
        )
    print(f"{tick(r.ok)}  auth & operational tables               {DIM(r.detail)}")


# ─── SECTION 5: Safety engines ────────────────────────────────────────────────

def check_safety_engines():
    print(BOLD(BLUE("\n─── 5. Safety Engines ──────────────────────────────────────────")))

    base_py = "http://localhost:8000"

    # Check if using live vs dummy retriever
    r = test("safety_retriever", "Evidence retriever (live vs dummy)", 8, "safety")
    try:
        sys.path.insert(0, os.getcwd())
        from app.api import preprocedure_safety_engine as pse
        cls_name = type(pse.evidence_retriever).__name__
        if "Dummy" in cls_name:
            r.failed(
                f"Still using {cls_name} — evidence cards are static placeholder data",
                "Run: POST /api/ops/readiness/fix OR set AESTHETICITE_PGVECTOR_ENABLED=1 in Secrets and restart"
            )
        else:
            r.passed(f"Using {cls_name} — live retrieval active")
    except Exception as e:
        r.warn(f"Could not import engine: {str(e)[:60]}", "Ensure Python path is correct")
    print(f"{tick(r.ok)}  Evidence retriever type                 {DIM(r.detail)}")

    # Complication protocol — vascular occlusion
    r = test("safety_protocol_vascular", "Vascular occlusion protocol", 5, "safety")
    status, body = http_post(f"{base_py}/api/complications/protocol", {
        "query": "vascular occlusion blanching after filler",
        "context": {"visual_symptoms": True}
    }, timeout=8)
    if status == 200 and isinstance(body, dict) and "matched_protocol_key" in body:
        key = body.get("matched_protocol_key", "?")
        score = body.get("risk_assessment", {}).get("risk_score", "?")
        r.passed(f"matched={key}, risk={score}/100")
    else:
        r.failed(f"HTTP {status}: {str(body)[:60]}", "Check complication_protocol_engine.py")
    print(f"{tick(r.ok)}  Vascular occlusion protocol             {DIM(r.detail)}")

    # Pre-procedure — high risk scenario
    r = test("safety_high_risk", "High-risk procedure scoring", 5, "safety")
    status, body = http_post(f"{base_py}/api/safety/preprocedure-check", {
        "procedure": "glabellar filler",
        "region": "glabella",
        "product_type": "hyaluronic acid filler",
        "injector_experience_level": "junior",
        "patient_factors": {"prior_vascular_event": True}
    }, timeout=8)
    if status == 200 and isinstance(body, dict):
        score = body.get("safety_assessment", {}).get("overall_risk_score", 0)
        decision = body.get("safety_assessment", {}).get("decision", "?")
        # Glabella + junior + prior vascular event should score high
        if score and score >= 70:
            r.passed(f"correctly scored HIGH: {score}/100, decision={decision}")
        elif score:
            r.warn(f"score={score}/100 — lower than expected for high-risk case", "Check risk scoring logic")
        else:
            r.failed("no score returned", "Check safety engine response structure")
    else:
        r.failed(f"HTTP {status}", "Check pre-procedure safety engine")
    print(f"{tick(r.ok)}  High-risk scenario scoring              {DIM(r.detail)}")

    # PDF export
    r = test("safety_pdf_export", "Safety check PDF export", 4, "safety")
    export_dir = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
    status, body = http_post(f"{base_py}/api/safety/preprocedure-check/export-pdf", {
        "procedure": "lip filler",
        "region": "lip",
        "product_type": "hyaluronic acid filler"
    }, timeout=10)
    if status == 200 and isinstance(body, dict) and "filename" in body:
        filename = body.get("filename", "")
        filepath = os.path.join(export_dir, filename)
        exists = os.path.exists(filepath)
        if exists:
            size = os.path.getsize(filepath)
            r.passed(f"{filename} ({size} bytes)")
        else:
            r.warn(f"API returned filename but file not found at {filepath}", "Check AESTHETICITE_EXPORT_DIR")
    else:
        r.failed(f"HTTP {status}: {str(body)[:60]}", "Check export_dir is writable: mkdir -p exports")
    print(f"{tick(r.ok)}  PDF export                              {DIM(r.detail)}")


# ─── SECTION 6: Growth engine ─────────────────────────────────────────────────

def check_growth_engine():
    print(BOLD(BLUE("\n─── 6. Growth Engine ───────────────────────────────────────────")))

    base_py = "http://localhost:8000"

    # Info endpoint
    r = test("growth_info", "Growth engine info", 3, "growth")
    status, body = http_get(f"{base_py}/api/growth/info", timeout=5)
    if status == 200 and isinstance(body, dict):
        version = body.get("version", "?")
        storage = body.get("storage", "?")
        r.passed(f"v{version}, storage={storage}")
        if storage == "SQLite":
            r.warn(
                "Growth engine is still using SQLite — not production-safe",
                "Replace app/api/growth_engine.py with growth_engine_pg.py from outputs/"
            )
    else:
        r.failed(f"HTTP {status}", "Check growth_engine.py is registered in main.py")
    print(f"{tick(r.ok)}  Growth engine info                      {DIM(r.detail)}")

    # Drug interactions endpoint
    r = test("growth_drug", "Drug interactions (growth engine)", 3, "growth")
    status, body = http_get(f"{base_py}/api/growth/info", timeout=5)
    status2, body2 = http_post(f"{base_py}/api/growth/drug-interactions", {
        "medications": ["aspirin", "sertraline"],
        "planned_products": ["ha filler"]
    }, timeout=5)
    if status2 == 200 and isinstance(body2, dict) and "items" in body2:
        count = len(body2.get("items", []))
        r.passed(f"{count} interactions found")
    else:
        r.failed(f"HTTP {status2}", "Check drug-interactions endpoint in growth_engine.py")
    print(f"{tick(r.ok)}  Drug interactions endpoint              {DIM(r.detail)}")

    # Dashboard — check if any logs exist
    r = test("growth_dashboard_data", "Dashboard has query data", 5, "growth")
    count = db_scalar("SELECT COUNT(*) FROM growth_query_logs", None)
    if count is None:
        count = db_scalar("SELECT COUNT(*) FROM query_logs_v2", None)

    if count and count > 0:
        r.passed(f"{count} query logs recorded")
    elif count == 0:
        r.warn(
            "No query logs yet — dashboard will show empty data",
            "Use the app to run searches. logQueryToClinic in ask.tsx must call /api/ops/dashboard/log-query"
        )
    else:
        r.failed("Could not read query logs", "Check growth_query_logs or query_logs_v2 table exists")
    print(f"{tick(r.ok)}  Dashboard query data                    {DIM(r.detail)}")

    # Session reports
    r = test("growth_session_reports", "Session reports table", 3, "growth")
    count = db_scalar("SELECT COUNT(*) FROM growth_session_reports", None)
    if count is not None:
        r.passed(f"{count} session reports")
    else:
        r.failed("growth_session_reports table missing", "Run growth engine PostgreSQL migration")
    print(f"{tick(r.ok)}  Session reports table                   {DIM(r.detail)}")


# ─── SECTION 7: Auth flow ─────────────────────────────────────────────────────

def check_auth_flow():
    print(BOLD(BLUE("\n─── 7. Auth Flow ───────────────────────────────────────────────")))

    base_ex = "http://localhost:5000"

    # Login endpoint
    r = test("auth_login", "Login endpoint", 5, "auth")
    status, body = http_post(f"{base_ex}/api/auth/login", {
        "email": "nonexistent@test.com",
        "password": "wrongpassword"
    }, timeout=5)
    if status in (401, 400, 422, 200):
        r.passed(f"endpoint responding (HTTP {status})")
    else:
        r.failed(f"HTTP {status} — login endpoint broken", "Check /api/auth/login proxy in routes.ts")
    print(f"{tick(r.ok)}  POST /api/auth/login                    {DIM(r.detail)}")

    # Forgot password
    r = test("auth_forgot_password", "Forgot password endpoint", 4, "auth")
    status, body = http_post(f"{base_ex}/api/ops/auth/forgot-password", {
        "email": "test@clinic.com"
    }, timeout=5)
    if status in (200, 400, 422):
        r.passed(f"HTTP {status} — endpoint exists")
        if not os.environ.get("SMTP_HOST"):
            r.warn("endpoint exists but SMTP not configured — emails won't send", "Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, APP_BASE_URL in Replit Secrets")
    else:
        r.failed(f"HTTP {status} — route missing", "Add /api/ops/auth/forgot-password proxy to routes.ts, deploy operational.py")
    print(f"{tick(r.ok)}  POST /api/ops/auth/forgot-password      {DIM(r.detail)}")

    # Verify email
    r = test("auth_verify_email", "Email verify endpoint", 3, "auth")
    status, body = http_post(f"{base_ex}/api/ops/auth/verify-email", {
        "token": "invalid_test_token_12345"
    }, timeout=5)
    if status in (400, 422, 200):
        r.passed(f"HTTP {status} — endpoint exists")
    else:
        r.failed(f"HTTP {status} — route missing", "Add /api/ops/auth/verify-email proxy to routes.ts")
    print(f"{tick(r.ok)}  POST /api/ops/auth/verify-email         {DIM(r.detail)}")

    # Auth tokens table
    r = test("auth_tokens_table", "auth_tokens table exists", 4, "auth")
    count = db_scalar("SELECT COUNT(*) FROM auth_tokens", None)
    if count is not None:
        r.passed(f"table exists ({count} tokens)")
    else:
        r.failed("auth_tokens table missing", "Run: POST /api/ops/readiness/fix")
    print(f"{tick(r.ok)}  auth_tokens table                       {DIM(r.detail)}")


# ─── SECTION 8: File system ────────────────────────────────────────────────────

def check_filesystem():
    print(BOLD(BLUE("\n─── 8. File System ─────────────────────────────────────────────")))

    # Export directory
    export_dir = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
    r = test("fs_export_dir", f"Export directory ({export_dir})", 4, "filesystem")
    if os.path.isdir(export_dir) and os.access(export_dir, os.W_OK):
        pdfs = [f for f in os.listdir(export_dir) if f.endswith(".pdf")]
        r.passed(f"writable, {len(pdfs)} PDFs")
    elif os.path.isdir(export_dir):
        r.failed(f"{export_dir} exists but not writable", f"Run: chmod 755 {export_dir}")
    else:
        r.failed(f"{export_dir} does not exist", f"Run: mkdir -p {export_dir}")
    print(f"{tick(r.ok)}  Export directory                        {DIM(r.detail)}")

    # Service worker
    sw_path = os.path.join("client", "public", "sw.js")
    r = test("fs_sw_js", "Service worker file (sw.js)", 2, "filesystem")
    if os.path.exists(sw_path):
        size = os.path.getsize(sw_path)
        with open(sw_path, "r") as f:
            content = f.read()
        if "pass-through" in content.lower() or "/* pass-through */" in content:
            r.warn(f"sw.js is stub ({size} bytes) — not real PWA", "Copy sw_production.js from outputs/ to client/public/sw.js")
        elif size > 500:
            r.passed(f"production sw.js ({size} bytes)")
        else:
            r.warn(f"sw.js is very small ({size} bytes)", "Replace with sw_production.js")
    else:
        r.failed("sw.js not found", "Copy sw_production.js from outputs/ to client/public/sw.js")
    print(f"{tick(r.ok)}  client/public/sw.js                     {DIM(r.detail)}")

    # PWA icons
    r = test("fs_pwa_icons", "PWA icons (icon-192.png, icon-512.png)", 2, "filesystem")
    icon192 = os.path.join("client", "public", "icons", "icon-192.png")
    icon512 = os.path.join("client", "public", "icons", "icon-512.png")
    has_192 = os.path.exists(icon192)
    has_512 = os.path.exists(icon512)
    if has_192 and has_512:
        r.passed("both icons present")
    elif has_192 or has_512:
        r.warn(f"{'icon-192' if not has_192 else 'icon-512'} missing", "Create both icons at 192x192 and 512x512 PNG")
    else:
        r.warn("no PWA icons — install prompt won't work", "Create client/public/icons/icon-192.png and icon-512.png")
    print(f"{tick(r.ok)}  PWA icons                               {DIM(r.detail)}")

    # Offline page
    offline_path = os.path.join("client", "public", "offline.html")
    r = test("fs_offline", "Offline fallback page (offline.html)", 2, "filesystem")
    if os.path.exists(offline_path):
        r.passed(f"{os.path.getsize(offline_path)} bytes")
    else:
        r.failed("offline.html missing", "Copy offline.html from outputs/ to client/public/offline.html")
    print(f"{tick(r.ok)}  client/public/offline.html              {DIM(r.detail)}")

    # Safety workspace page
    sw_page = os.path.join("client", "src", "pages", "safety-workspace.tsx")
    r = test("fs_safety_workspace", "Safety Workspace page exists", 3, "filesystem")
    if os.path.exists(sw_page):
        r.passed(f"{os.path.getsize(sw_page)} bytes")
    else:
        r.failed("safety-workspace.tsx missing", "Copy SafetyWorkspace.tsx from outputs/ to client/src/pages/safety-workspace.tsx")
    print(f"{tick(r.ok)}  pages/safety-workspace.tsx              {DIM(r.detail)}")

    # Mobile CSS
    mobile_css = os.path.join("client", "src", "mobile.css")
    r = test("fs_mobile_css", "Mobile CSS overrides", 2, "filesystem")
    if os.path.exists(mobile_css):
        r.passed(f"{os.path.getsize(mobile_css)} bytes")
    else:
        r.warn("mobile.css missing", "Copy mobile.css from outputs/ to client/src/mobile.css, import in index.css")
    print(f"{tick(r.ok)}  client/src/mobile.css                   {DIM(r.detail)}")


# ─── SECTION 9: Operational modules ───────────────────────────────────────────

def check_operational_modules():
    print(BOLD(BLUE("\n─── 9. Operational Modules ─────────────────────────────────────")))

    base_py = "http://localhost:8000"
    base_ex = "http://localhost:5000"

    # Readiness endpoint
    r = test("ops_readiness", "Readiness endpoint (/api/ops/readiness)", 4, "operational")
    status, body = http_get(f"{base_ex}/api/ops/readiness", timeout=8)
    if status == 200 and isinstance(body, dict) and "summary" in body:
        score = body.get("summary", {}).get("readiness_score", 0)
        status_label = body.get("summary", {}).get("status_label", "?")
        r.passed(f"score={score}/100, status={status_label}")
    elif status in (401, 403):
        r.warn(f"HTTP {status} — route exists but needs auth", "This is expected if readiness requires admin token")
    else:
        r.failed(f"HTTP {status} — endpoint missing", "Add operational_readiness.py to main.py and proxy route to routes.ts")
    print(f"{tick(r.ok)}  GET /api/ops/readiness                  {DIM(r.detail)}")

    # Full health check
    r = test("ops_health_full", "Full health check (/api/ops/health/full)", 3, "operational")
    status, body = http_get(f"{base_ex}/api/ops/health/full", timeout=8)
    if status == 200 and isinstance(body, dict) and "checks" in body:
        overall = body.get("status", "?")
        r.passed(f"status={overall}")
    elif status in (401, 403):
        r.warn("exists but requires auth token", "")
    else:
        r.failed(f"HTTP {status}", "Deploy operational.py and add /api/ops/health/full proxy to routes.ts")
    print(f"{tick(r.ok)}  GET /api/ops/health/full                {DIM(r.detail)}")

    # Ingestion status
    r = test("ops_ingest_status", "Ingestion pipeline status", 3, "operational")
    status, body = http_get(f"{base_ex}/api/ops/ingest/status", timeout=5)
    if status == 200 and isinstance(body, dict) and "state" in body:
        state = body.get("state", {})
        ingest_status = state.get("status", "unknown")
        docs = state.get("papers_inserted", 0)
        r.passed(f"status={ingest_status}, papers_inserted={docs}")
        if ingest_status == "idle" and docs == 0:
            r.warn("Ingestion never run", "Run: POST /api/ops/ingest/start (admin)")
    elif status in (401, 403):
        r.warn("exists but requires auth", "")
    else:
        r.failed(f"HTTP {status}", "Deploy operational.py and add /api/ops/ingest/status proxy to routes.ts")
    print(f"{tick(r.ok)}  GET /api/ops/ingest/status              {DIM(r.detail)}")

    # Evidence retrieval test
    r = test("ops_evidence_test", "Evidence retrieval test", 5, "operational")
    status, body = http_get(
        f"{base_ex}/api/ops/evidence/test?procedure=lip+filler&region=lip&product_type=hyaluronic+acid",
        timeout=8
    )
    if status == 200 and isinstance(body, dict):
        live = body.get("using_live_retrieval", False)
        count = body.get("results_count", 0)
        if live and count > 0:
            r.passed(f"live retrieval working, {count} results")
        elif count > 0:
            r.warn(f"{count} results but not flagged as live", "")
        else:
            r.failed("0 results — evidence retrieval not working", "Run ingestion pipeline first: POST /api/ops/ingest/start")
    elif status in (401, 403):
        r.warn("exists but requires auth", "")
    else:
        r.failed(f"HTTP {status}", "Deploy operational.py and add /api/ops/evidence/test proxy to routes.ts")
    print(f"{tick(r.ok)}  GET /api/ops/evidence/test              {DIM(r.detail)}")


# ─── SECTION 10: Quick end-to-end smoke test ──────────────────────────────────

def check_e2e():
    print(BOLD(BLUE("\n─── 10. End-to-End Smoke Test ──────────────────────────────────")))

    base_ex = "http://localhost:5000"

    # Full safety check round-trip through Express → FastAPI
    r = test("e2e_safety_check", "Full safety check (Express → FastAPI)", 8, "e2e")
    t0 = time.time()
    status, body = http_post(f"{base_ex}/api/safety/preprocedure-check", {
        "procedure": "nasolabial fold filler",
        "region": "nasolabial fold",
        "product_type": "hyaluronic acid filler",
        "technique": "cannula",
        "injector_experience_level": "intermediate",
        "patient_factors": {
            "prior_filler_in_same_area": True,
            "anticoagulation": True
        }
    }, timeout=15)
    elapsed = round((time.time() - t0) * 1000)

    if status == 200 and isinstance(body, dict) and "safety_assessment" in body:
        sa = body["safety_assessment"]
        risks = body.get("top_risks", [])
        evidence = body.get("evidence", [])
        flags = body.get("caution_flags", [])

        checks_passed = []
        checks_failed = []

        if sa.get("overall_risk_score", 0) > 0:
            checks_passed.append(f"score={sa['overall_risk_score']}/100")
        else:
            checks_failed.append("no risk score")

        if sa.get("decision") in ("go", "caution", "high_risk"):
            checks_passed.append(f"decision={sa['decision']}")
        else:
            checks_failed.append("no decision")

        if risks:
            checks_passed.append(f"{len(risks)} risks")
        else:
            checks_failed.append("no risks")

        if evidence:
            is_dummy = any("S0" in e.get("source_id", "") or "S1" == e.get("source_id", "") for e in evidence[:1])
            checks_passed.append(f"{len(evidence)} evidence items{'(static)' if is_dummy else '(live)'}")
        else:
            checks_failed.append("no evidence")

        if flags:
            checks_passed.append(f"{len(flags)} caution flags")

        all_ok = len(checks_failed) == 0
        detail = f"{', '.join(checks_passed)} | {elapsed}ms"
        if all_ok:
            r.passed(detail)
        else:
            r.warn(f"{detail} | issues: {', '.join(checks_failed)}", "Check safety engine response structure")
    else:
        r.failed(
            f"HTTP {status} in {elapsed}ms: {str(body)[:60]}",
            "Full end-to-end chain broken — check Express→FastAPI proxy and safety engine"
        )
    print(f"{tick(r.ok)}  Safety check round-trip ({elapsed}ms)     {DIM(r.detail)}")

    # Drug interaction check round-trip
    r = test("e2e_drug_check", "Drug interaction check round-trip", 4, "e2e")
    status, body = http_post(f"{base_ex}/api/growth/drug-interactions", {
        "medications": ["warfarin", "aspirin", "ibuprofen"],
        "planned_products": ["hyaluronic acid filler"]
    }, timeout=8)
    if status == 200 and isinstance(body, dict) and "items" in body:
        count = len(body.get("items", []))
        has_high = any(i.get("severity") == "high" for i in body.get("items", []))
        r.passed(f"{count} interactions, high_severity={has_high}")
    else:
        r.failed(f"HTTP {status}", "Check drug interactions in growth_engine.py")
    print(f"{tick(r.ok)}  Drug interaction round-trip             {DIM(r.detail)}")


# ─── SCORING & REPORT ─────────────────────────────────────────────────────────

def compute_score() -> Tuple[int, str]:
    valid = [r for r in results if r.weight > 0]
    total = sum(r.weight for r in valid)
    achieved = sum(r.weight for r in valid if r.ok)
    score = round((achieved / total) * 100) if total else 0

    if score >= 92:
        status = "FULLY OPERATIONAL"
    elif score >= 80:
        status = "NEAR FULLY OPERATIONAL"
    elif score >= 65:
        status = "CLINIC PILOT READY"
    elif score >= 45:
        status = "DEMO READY"
    else:
        status = "NOT OPERATIONAL"

    return score, status


def print_summary():
    score, status = compute_score()
    passed = sum(1 for r in results if r.ok and r.weight > 0)
    total_checks = sum(1 for r in results if r.weight > 0)
    failed = [r for r in results if not r.ok and r.weight > 0]
    failed.sort(key=lambda r: r.weight, reverse=True)

    colour = GREEN if score >= 80 else (YELLOW if score >= 60 else RED)

    print("\n" + "═" * 65)
    print(BOLD(f"  AesthetiCite Operational Test — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"))
    print("═" * 65)
    print(f"\n  Score:   {colour(BOLD(f'{score}/100'))}")
    print(f"  Status:  {colour(BOLD(status))}")
    print(f"  Checks:  {GREEN(str(passed))} passed, {RED(str(len(failed)))} failed / {total_checks} total\n")

    # Category breakdown
    categories: Dict[str, Dict] = {}
    for r in results:
        if r.weight == 0:
            continue
        cat = r.category
        if cat not in categories:
            categories[cat] = {"total": 0, "achieved": 0}
        categories[cat]["total"] += r.weight
        if r.ok:
            categories[cat]["achieved"] += r.weight

    print("  By category:")
    for cat, data in sorted(categories.items(), key=lambda x: -x[1]["achieved"]/max(x[1]["total"],1)):
        t = data["total"]
        a = data["achieved"]
        pct = round((a / t) * 100) if t else 0
        bar_len = 20
        filled = round(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        bar_col = GREEN if pct >= 90 else (YELLOW if pct >= 65 else RED)
        print(f"    {cat:<18} {bar_col(bar)} {pct:>3}%")

    # Top blockers
    if failed:
        print(f"\n  {BOLD(RED('Top blockers (by weight):'))}")
        for r in failed[:8]:
            print(f"\n  {RED('✗')} [{r.weight}pt] {BOLD(r.label)}")
            print(f"    {DIM(r.detail)}")
            if r.fix:
                print(f"    {CYAN('→')} {r.fix}")

    # What to do next
    print(f"\n  {BOLD('Recommended next steps:')}")
    if score < 50:
        print(f"  1. {YELLOW('Ensure both servers are running:')} npm run dev (port 5000) + uvicorn (port 8000)")
        print(f"  2. {YELLOW('Set required secrets:')} DATABASE_URL, AI_INTEGRATIONS_OPENAI_API_KEY, JWT_SECRET")
        print(f"  3. {YELLOW('Check Replit console for startup errors')}")
    elif score < 70:
        print(f"  1. {YELLOW('Run auto-fix:')} POST /api/ops/readiness/fix (admin token)")
        print(f"  2. {YELLOW('Populate knowledge base:')} POST /api/ops/ingest/start (admin token)")
        print(f"  3. {YELLOW('Set missing secrets:')} SMTP_HOST, APP_BASE_URL, SENTRY_DSN")
    elif score < 85:
        print(f"  1. {YELLOW('Run ingestion if not done:')} POST /api/ops/ingest/start")
        print(f"  2. {YELLOW('Set SMTP + APP_BASE_URL for email flows')}")
        print(f"  3. {YELLOW('Replace stub sw.js with production service worker')}")
    else:
        print(f"  1. {GREEN('Set SMTP + APP_BASE_URL')} to enable password reset emails")
        print(f"  2. {GREEN('Create PWA icons')} at client/public/icons/")
        print(f"  3. {GREEN('Start a clinic pilot')} — the platform is ready")

    print("\n" + "═" * 65)
    print(f"  Full report saved to: {CYAN('test_report.json')}")
    print("═" * 65 + "\n")


def save_report():
    score, status = compute_score()
    report = {
        "product": "AesthetiCite",
        "test_run_utc": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "status": status,
        "checks_passed": sum(1 for r in results if r.ok and r.weight > 0),
        "checks_total": sum(1 for r in results if r.weight > 0),
        "results": [
            {
                "id": r.id,
                "label": r.label,
                "ok": r.ok,
                "weight": r.weight,
                "category": r.category,
                "detail": r.detail,
                "fix": r.fix,
            }
            for r in results if r.weight > 0
        ],
        "blockers": [
            {"id": r.id, "label": r.label, "detail": r.detail, "fix": r.fix, "weight": r.weight}
            for r in sorted(results, key=lambda x: -x.weight)
            if not r.ok and r.weight >= 3
        ],
    }
    with open("test_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    print(BOLD(CYAN("\n╔══════════════════════════════════════════════════════════════╗")))
    print(BOLD(CYAN("║  AesthetiCite — Operational Test Suite                       ║")))
    print(BOLD(CYAN("║  Run from Replit Shell: python3 test_operational.py           ║")))
    print(BOLD(CYAN("╚══════════════════════════════════════════════════════════════╝")))

    t_start = time.time()

    check_environment()
    check_python_server()
    check_express_server()
    check_database()
    check_safety_engines()
    check_growth_engine()
    check_auth_flow()
    check_filesystem()
    check_operational_modules()
    check_e2e()

    elapsed = round(time.time() - t_start, 1)
    print(DIM(f"\n  Tests completed in {elapsed}s"))

    print_summary()
    save_report()

    # Exit code: 0 if score >= 80, 1 otherwise
    score, _ = compute_score()
    sys.exit(0 if score >= 80 else 1)


if __name__ == "__main__":
    main()
