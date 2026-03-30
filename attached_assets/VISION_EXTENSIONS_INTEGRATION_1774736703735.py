# Vision Extensions — Integration Guide
# =======================================
# Two file changes needed. Everything else is self-contained in vision_extensions.py.

# ─────────────────────────────────────────────────────────────────────────────
# 1. app/main.py
# Add after the existing visual_counseling_router include:
# ─────────────────────────────────────────────────────────────────────────────

# from app.api.vision_extensions import router as vision_ext_router
# app.include_router(vision_ext_router)

# ─────────────────────────────────────────────────────────────────────────────
# 2. server/routes.ts  (Express proxy — add 6 new routes)
# ─────────────────────────────────────────────────────────────────────────────

ROUTES_TS_PATCH = """
  // Vision Extensions
  app.post("/api/visual/export-pdf", (req, res) => proxyToFastAPI(req, res, "/visual/export-pdf"));
  app.get("/api/visual/download-pdf/:filename", (req, res) =>
    proxyToFastAPI(req, res, `/visual/download-pdf/${req.params.filename}`)
  );
  app.post("/api/visual/log-serial-case", (req, res) => proxyToFastAPI(req, res, "/visual/log-serial-case"));
  app.get("/api/visual/serial-cases", (req, res) => proxyToFastAPI(req, res, "/visual/serial-cases"));
  app.get("/api/visual/glossary", (req, res) => proxyToFastAPI(req, res, "/visual/glossary"));
  app.get("/api/visual/glossary/:term", (req, res) =>
    proxyToFastAPI(req, res, `/visual/glossary/${req.params.term}`)
  );
  app.post("/api/visual/preprocedure-from-vision", (req, res) =>
    proxyToFastAPI(req, res, "/visual/preprocedure-from-vision")
  );
"""

# ─────────────────────────────────────────────────────────────────────────────
# 3. New file placement
# ─────────────────────────────────────────────────────────────────────────────

FILE = "app/api/vision_extensions.py"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Frontend integration summary (TypeScript)
# ─────────────────────────────────────────────────────────────────────────────

FRONTEND_NOTES = """
GAP 1 — PDF Export
  After analysis completes, show a "Download Session Report" button.
  POST /api/visual/export-pdf with:
    { analysis_text, triggered_protocols, serial_comparison_summary, notes, patient_ref }
  On response, open /api/visual/download-pdf/:filename

GAP 2 — Serial Case Log
  In the Healing Tracker tab, after /serial-compare returns:
  POST /api/visual/log-serial-case with outcome, procedure, region, comparison_summary
  Show a small "Case logged ✓" badge.

GAP 3 — Live Glossary
  Replace the static glossary render with:
    GET /api/visual/glossary  — load all terms on tab open
    GET /api/visual/glossary/:term  — on tooltip hover (debounced, cached)
  Each term now returns .evidence[] — render as citation cards below definition.

GAP 4 — Pre-Procedure from Vision
  After vision analysis AND if clinician fills a short procedure form (procedure/region/product):
  POST /api/visual/preprocedure-from-vision
  Returns full pre-procedure safety response + vision_context block showing
  what was inferred vs manually entered.
  Render with the same PreProcedureSafetyCard component used on /safety-check.
"""
