# AesthetiCite - AI-Powered Evidence Search

## Security Hardening (March 2026 — 5-patch sequence complete)

All 5 security patches applied:

### Patch 1 — main.py
- **CORS fail-closed**: reads `CORS_ORIGINS` env var; raises `RuntimeError` in production if unset; expands allowed headers
- **SecurityHeadersMiddleware** injected after CORS: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy; Cache-Control: no-store on all `/api/` paths
- **`/metrics-lite` locked** behind `Depends(require_admin_user)` — requires valid JWT with admin role
- **`audit_log` table SQL** added to `DOC_META_MIGRATION_SQL` (created on startup): id, logged_at, event_type, request_id, user_id, email, ip_address, path, event_data (JSONB), indexes on user_id + event_type + logged_at

### Patch 2 — Input sanitisation + rate limits
- **`sanitize_input()`** applied to all LLM-facing fields in: `vision_analysis.py` (procedure_type, injected_region, product_type, clinical_notes, patient_symptoms), `clinical_tools_engine.py` (all 5 endpoints)
- **Rate limits** added to all 5 clinical_tools endpoints (`@limiter.limit("20/minute")` / `10/minute` for consent)
- **Server-side magic bytes check** in `visual_counseling.py` upload: `_detect_mime_fallback()` validates file signature independently of client-supplied Content-Type header

### Patch 3 — Auth hardening
- **`create_refresh_token()`** / **`decode_refresh_token()`** added to `app/core/auth.py` (30-day, type=refresh claim)
- **Brute-force lockout** in `app/api/auth.py`: 5-attempt threshold, exponential backoff (30s base, doubles per extra failure)
- **`POST /auth/refresh`** endpoint added; proxied via `server/routes.ts` at `/api/auth/refresh`
- **Login response** now returns `refresh_token`, `expires_in` alongside `access_token`
- **`TokenResponse` schema** updated: optional `refresh_token` + `expires_in` fields

### Patch 4 — Durable audit log
- **`app/core/audit.py`** created: async `write_audit_event()`, sync `write_audit_sync()`, `get_recent_events()` admin helper
- **`governance.py`** now calls `write_audit_sync("query_answered", ...)` for every answered clinical query — events persist in Postgres, survive deploys

### Patch 5 — Frontend security
- **`client/src/lib/auth.ts`**: `getRefreshToken()`, `setRefreshToken()`, `clearRefreshToken()`, `refreshAccessToken()`, `authedFetch()` (auto-refresh wrapper); `login()` now stores refresh token
- **`client/src/main.tsx`**: Sentry SDK initialised conditionally on `VITE_SENTRY_DSN` env var; auth paths scrubbed before send
- **`client/index.html`**: security meta tags (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, robots noindex, Cache-Control)
- **`@sentry/react`** installed

## Overview
AesthetiCite is an AI-powered research platform providing evidence-based answers to medical research questions with citations from trusted sources. It offers comprehensive, structured responses with inline citations, related questions, and source references. The platform aims to support clinicians and medical students, leveraging a React frontend with a real-time streaming search interface.

The project's ambition is to become a leading tool for evidence-based medicine, offering reliable information across various medical specialties and supporting multilingual access globally.

## User Preferences
Preferred communication style: Simple, everyday language.

## Vision Engine — Consultation Flow (March 2026)

### New Components
- **`app/api/skingpt_integration.py`** — SkinGPT × Haut.AI outcome simulation engine. 5 complication scenario types (Tyndall, erythema, swelling, infection, vascular compromise), each with treated vs untreated simulations. Mock mode active until `HAUTAI_API_KEY` + `HAUTAI_MOCK_MODE=false` are set.
- **`client/src/components/vision/PoseCaptureGuide.tsx`** — DermEngine-style 3-angle standardised capture (front 0°, left 45°, right 45°) with SVG anatomical overlays and serial comparison protocol.
- **`client/src/components/vision/VisualScoreCard.tsx`** — VISIA-inspired clinical scoring card. Displays 7 structured signals (perfusion, swelling, infection, asymmetry, ptosis, Tyndall, Fitzpatrick) with score bars and flag badges.
- **`client/src/components/vision/ConsultationFlow.tsx`** — Nextmotion-style 5-step orchestrator: Capture → Analyse (GPT-4o stream) → Signals (protocol bridge) → Simulate (SkinGPT) → Export PDF. Key bug fix: SSE `visual_scores` payload accessed as `data.data` (not `data.scores`).

### Wiring
- `skingpt_router` registered in `app/main.py` at `/visual` prefix
- 3 new Express proxy routes in `server/routes.ts`: `POST /api/visual/simulate-outcome`, `POST /api/visual/simulate-scenarios`, `GET /api/visual/available-scenarios`
- `ConsultationFlow` added as default "Consult" tab in `vision-analysis.tsx` (existing Analyse/Ask/Healing tabs preserved)

### SkinGPT Mock Mode
`HAUTAI_API_KEY` not set → runs in mock mode. Returns structured placeholder simulations. Contact haut.ai/contact for B2B pricing to enable live photorealistic outcome simulation.

## Vision Engine v2 + Landmarks + PWA Offline (March 2026)

### New Backend — `app/api/vision_engine_v2.py`
Router prefix: `/visual/v2`. Implements improvements 1, 2, 3, 5, 7, 8, 9, 10.

| Endpoint | Method | Description |
|---|---|---|
| `/visual/v2/analyse` | POST | Full pipeline: preprocessing → model routing → calibrated scoring → protocol bridge |
| `/visual/v2/stream` | POST | Real-time SSE streaming (improvement 2): status → content tokens → visual_scores → protocol_alert → done |
| `/visual/v2/multi-analyse` | POST | Before+after images in a single model call (improvement 3) — coherent change comparison |
| `/visual/v2/video` | POST | Video frame extraction + per-frame scoring with trajectory (improvement 7) — requires opencv |
| `/visual/v2/dicom-export` | POST | DICOM-wrapped image export for PACS/EMR (improvement 8) — requires pydicom |
| `/visual/v2/similar` | POST | CLIP embedding similarity search across indexed cases (improvement 9) |
| `/visual/v2/index-case` | POST | Add a case image to the in-memory CLIP embedding store |
| `/visual/v2/calibrate-scores` | POST | Build per-field AI correction offsets from clinician-labelled cases (improvement 10) |
| `/visual/v2/calibration-table` | GET | Return current correction offsets |

Key internals:
- `_get_vision_model()` — routes to Claude 3.7 or GPT-4o based on `VISION_MODEL` env var (improvement 1)
- `preprocess_image()` — PIL auto-contrast + unsharp mask + colour enhancement (improvement 5)
- `apply_calibration()` — applies `_CALIBRATION_TABLE` correction offsets to raw scores
- `_EMBEDDING_STORE` — in-memory CLIP embedding store (swap for pgvector in production)

### New Backend — `app/api/vision_landmarks.py`
Router prefix: `/visual`. Implements improvement 4.

| Endpoint | Method | Description |
|---|---|---|
| `/visual/landmark-analyse` | POST | Haar cascade face detection → 9 zone crops → zone-specific GPT-4o JSON per zone → aggregated report |
| `/visual/landmark-preview` | POST | Returns JPEG with face bounding box and zone outlines drawn |

Zone set: forehead, glabella, right/left periorbital, nose, right/left cheek, lips/perioral, chin/jawline.
Each zone has mapped danger zones (e.g. supratrochlear artery for glabella) and relevant complications.
Cascade XML auto-downloaded from opencv/opencv GitHub on first use; cached to `/tmp/aestheticite_cascades/`.

### New Frontend — `client/src/components/vision/VisionStreamingAnalysis.tsx`
React component for the `/api/visual/v2/stream` SSE endpoint (improvement 2 frontend).
Features: offline detection, IndexedDB queue banner (PWA), live token display with cursor blink,
protocol alert cards mid-stream, 3-score summary grid on completion.
Props: `file`, `token`, `question?`, `context?`, `onDone?`.

### New Frontend — `client/public/vision-sw.js`
Service worker for offline PWA mode (improvement 6).
- Caches `/visual-counsel` and icon assets for offline access
- Queues POST to vision analysis endpoints in IndexedDB when offline (202 Accepted response)
- Replays queue on reconnect via `online` event + periodic sync
- Safety-critical routes (`/api/complications/`, `/api/ask/`) always network-first (never cached)

Registration: add `if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/vision-sw.js'); }` to `client/src/main.tsx` when enabling offline mode.

## Vision Advanced (March 2026)

### New Backend — `app/api/vision_advanced.py`
9 new endpoints under the `/visual` prefix (shares router prefix with `skingpt_integration.py`):

| Endpoint | Method | Description |
|---|---|---|
| `/visual/serial-delta` | POST | Quantified score diff between two visits — per-field deltas (% change, direction), overall trajectory |
| `/visual/confidence-badge` | POST | Confidence score 0–100 from image quality + signal count + structured output completeness |
| `/visual/symmetry` | POST | Bilateral symmetry score via GPT-4o — left/right balance, asymmetry regions, clinical significance |
| `/visual/share` | POST | Time-limited shared review link (1–168h) with SHA-256 audit trail; stores in `_STORE` dict |
| `/visual/share/{token}` | GET | Retrieve shared session; returns `is_expired` flag; access logged |
| `/visual/calibrate-colour` | POST | Colour calibration from uploaded image; detects reference card, notes colour shift |
| `/visual/population-baseline` | POST | Expected appearance at day-N post-procedure with amber/red flags; RAG-enriched from 846K-chunk corpus |
| `/visual/auto-log` | POST | 1-click session log → `_AUTO_LOG_STORE` + `CASE_STORE` (if protocol triggered) + `_TRAINING_CASES` |
| `/visual/auto-log/stats` | GET | Dataset accumulator stats |

### New Frontend — `client/src/components/vision/VisionAdvancedUI.tsx`
8 exported React components:
- `ImageAnnotator` — canvas drawing layer: pen, arrow, circle, text label, eraser, colour picker, export
- `MeasurementRuler` — click-to-calibrate + click-to-measure distance overlay in mm
- `SerialDeltaDisplay` — renders serial delta API response as scored cards with direction arrows and % change
- `AnalysisConfidenceBadge` — expandable badge showing confidence score and limiting factors
- `ColourCalibrationGuide` — pre-capture instructions with light condition examples
- `SharedReviewBanner` — shows active/expired share link with copy button and countdown
- `PopulationBaseline` — collapsible card showing expected day-N appearance with amber/red flag lists
- `AutoLogButton` — 1-click log with loading/done/error states

### Wiring
- `vision_advanced_router` registered in `app/main.py` after `clinical_workflow_v2_router`
- 9 Express proxy routes added to `server/routes.ts` in the Vision Advanced block

## RAG Engine v2 + ClinicalUIKit (March 2026)

### New Engine Files
- **`app/engine/self_rag.py`** — Self-RAG iterative retrieval (improvements #1, #3, #14). After initial retrieval, GPT-4o-mini evaluates evidence sufficiency; if insufficient, reformulates the query and retrieves again (max 2 iterations). Injects a calibration confidence block into the answer prompt. Controlled by `SELF_RAG_ENABLED` env var (default: `true`).
- **`app/engine/model_router.py`** — Model router + Graph RAG + Prompt optimizer (improvements #2, #4, #10, #15). Contains: `route_model()` for DeepSeek-R1 routing on DeepConsult/complex queries; `ComplicationGraph` — in-memory aesthetic medicine knowledge graph with 30+ nodes and 40+ edges; `graph_enrich_query()` — returns entity context string to prepend to answer prompts; `PromptOptimizer` — offline DSPy-style A/B evaluator.
- **`app/api/clinical_workflow_v2.py`** — Clinical workflow router (improvements #5, #6, #7, #13). Endpoints: `POST /workflow/consultation-note` (voice→structured note), `POST /workflow/consent` (digital consent with SHA-256 audit hash), `GET /workflow/consent/{id}`, `POST /workflow/preflight` (8 red-flag rules + medication check), `POST /workflow/tag-chunk` (NER tagging with 6 entity categories).

### New Frontend
- **`client/src/components/ClinicalUIKit.tsx`** — 6-component UI library (improvements #8, #9, #11, #12, #13): `EmergencyDropdown` (3-tap protocol access, Alt+E keyboard shortcut), `ClinicalTooltip` + `CLINICAL_TOOLTIPS`, `MHRABadge` (regulatory status, compact & full), `RoleSwitch` (clinician / clinic-owner toggle), `useAutoDarkMode`, `NERTagsDisplay`.

### Wiring
- `clinical_workflow_v2_router` registered in `app/main.py` at `/workflow` prefix
- 5 new Express proxy routes in `server/routes.ts`: `/api/workflow/{consultation-note,consent,consent/:id,preflight,tag-chunk}`
- `ask.tsx`: Emergency button replaced with `EmergencyDropdown` (Alt+E, 1–3 keyboard shortcuts); `MHRABadge compact` added to header
- `ask_v2.py`: Self-RAG wraps initial retrieval; graph context prepended to every answer prompt; self_rag metadata (`iterations`, `sufficient`, `calibration_level`) emitted in SSE `meta` event

## Clinical State Engine (March 2026)

### DB Session Fix
- `app/db/session.py` now bypasses Pydantic Settings and resolves the canonical DB URL directly via `os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")`. This fixes a split-brain where Pydantic was overriding the NEON priority with the local helium DB URL.
- Both sync and async sessions now connect to the Neon production DB.

### Clinical State Integration
All 5 uploaded files are now wired and live:

| File | Path | Status |
|---|---|---|
| `cases.py` | `app/api/routes/cases.py` | Live at `/api/clinical-cases/*` |
| `live_view_service.py` | `app/services/live_view_service.py` | Serving `GET /api/clinical-cases/{id}/live-view` |
| `audit_service.py` | `app/services/audit_service.py` | Called on every mutating route |
| `seed_vascular_occlusion.sql` | Run against Neon | 2 protocols seeded: `vascular-occlusion-v1`, `anaphylaxis-v1` |
| `supabase-queries.ts` | `client/src/lib/case-queries.ts` + `clinical-state-types.ts` | Adapted to project backend (no Supabase SDK) |

### New DB Tables (Neon)
`protocol_definitions`, `case_sessions`, `patient_contexts`, `procedure_contexts`, `clinical_state_snapshots`, `clinical_impressions`, `protocol_runs`, `protocol_run_steps`, `intervention_events`, `reassessment_events`, `disposition_plans`, `audit_events`, `evidence_bundles`

### New Python Modules
- `app/models/clinical_state.py` — SQLAlchemy 2.0 ORM models (13 mapped classes)
- `app/schemas/clinical_state.py` — Pydantic schemas (all Create/Read/Update + live view)
- `app/services/audit_service.py` — async audit trail helper
- `app/services/live_view_service.py` — assembles live view from 8 async DB reads
- `app/api/routes/cases.py` — 16 endpoints (14 CRUD + 2 protocol lookup)

### Async Session
`app/db/session.py` now exports both `get_db` (sync, legacy routes) and `get_async_db` (async, clinical state routes) using SQLAlchemy's `create_async_engine` with psycopg3.

### Route Prefixes
- Clinical cases CRUD: `/api/clinical-cases/*`
- Protocol definitions: `GET /api/protocols`, `GET /api/protocols/{id}`
- Protocol run management: `PATCH /api/protocol-runs/{id}`, `PATCH /api/protocol-run-steps/{id}`

## Audit Fixes (March 2026)
All 14 TypeScript errors resolved and 2 API/routing bugs fixed:

### TypeScript fixes
- `ask.tsx` — Added missing import of `ClinicalReasoningSection`; fixed citation type casts (`as unknown as EHCitation[]`); fixed `streamingPhase`/`handleStop` scope by passing as props to `StructuredAnswer` component
- `similar-cases.tsx` — Added `procedure`, `region`, `product` optional props to `LogCaseButtonProps`
- `favorites-button.tsx` — Fixed `getMe()` called with zero args (pass token)
- `bookmarks.tsx` / `paper-alerts.tsx` — Same `getMe(token)` fix + import `getToken`
- `risk-intelligence.tsx` / `workflow.tsx` — Fixed `[...new Set()]` spread → `Array.from(new Set())`
- `admin-analytics.tsx` — Wrapped `onClick={fetchData}` → `onClick={() => fetchData()}`
- `header.tsx` — Removed unused `MouseEvent` parameter from `handleHomeClick`

### API/routing fixes
- `server/routes.ts` — Added missing Express proxy `GET /api/speed/stats` → FastAPI
- `auth.ts` — Fixed default `domain` from `"medicine"` → `"aesthetic_medicine"` in `askQuestion` and `askQuestionStream` (FastAPI `Domain` literal type requires `aesthetic_medicine | dental_medicine | general_medicine`)

## System Architecture

### Frontend
- **Framework**: React 18 with TypeScript
- **UI Components**: shadcn/ui built on Radix UI, styled with Tailwind CSS (light/dark mode support)
- **Routing**: Wouter
- **State Management**: TanStack React Query

### Backend
- **Node.js Frontend Server**: Express 5 with TypeScript, serving the React app and handling API calls.
- **Python FastAPI Evidence API**: FastAPI with uvicorn for core logic, evidence retrieval, and AI integration.
  - **Database**: PostgreSQL with pgvector for semantic search.
  - **Embeddings**: fastembed (all-MiniLM-L6-v2).
  - **Authentication**: JWT-based for users, API-key based for admin.
  - **Data Flow**: User queries are validated, hot-cache is checked first (~250ms if hit), then relevant evidence chunks are retrieved via asyncpg pool (RAG: vector IVFFlat + keyword FTS hybrid), and an LLM synthesizes a concise 3-section evidence-grounded answer with strict citation enforcement. Streaming via SSE. `/ask` endpoint is async (`async def ask`) using `retrieve_db_async` from the asyncpg pool.

### Clinical Decision Engine (Master Build v1 — newest)
- **Page**: `/decide` — single-screen real-time interface. 8 quick-select complication buttons + symptom chips → 6 structured sections rendered in <300ms.
- **Backend**: `app/api/clinical_decision.py` — 7 endpoints under `/api/decide`:
  - `POST /api/decide` — master endpoint: diagnosis, workflow, safety, ranked evidence, similar cases, hyal calc. LRU cache (5-min TTL, 500 entries).
  - `POST /api/decide/reasoning` — clinical reasoning block only (Glass Health-inspired)
  - `POST /api/decide/workflow` — step-by-step workflow
  - `POST /api/decide/hyaluronidase` — dose calculator (region × severity, vascular occlusion min 1500 IU)
  - `POST /api/decide/report` — medico-legal PDF report (reportlab, binary stream proxy)
  - `GET /api/decide/protocols` — all 8 protocol summaries
  - `GET /api/decide/similar-cases` — anonymised case_logs query
- **8 workflows**: vascular_occlusion, anaphylaxis, ptosis, nodule, infection, tyndall, necrosis, DIR
- **UI features**: progress bar (tap-to-complete steps), auto emergency banner (call_emergency flag), report modal with 14-field form → PDF export, evidence hierarchy badges, latency display, cache-hit indicator
- **Evidence ranking**: evidence_score() = similarity×0.6 + type_weight×0.3 + recency×0.1. Guidelines always surface first.
- **Proxy routes**: 7 routes added to `server/routes.ts` incl. binary PDF stream handler for `/api/decide/report`

### Unicorn Intelligence Features (new)
- **Risk Intelligence** (`/risk-intelligence`): Practitioner-level safety scoring, 5 pattern detection rules (vascular cluster, necrosis, visual events, unresolved spike, product clustering), complication heatmap (procedure × region). Routes: `/api/risk/*`.
- **Complication Monitor** (`/complication-monitor`): Async post-procedure photo monitoring. GPT-4o vision screens each submitted image for blanching, necrosis, infection, oedema. Auto-triggers escalation alerts. Routes: `/api/monitor/*`.
- **Org Analytics** (`/org-analytics`): Cross-clinic network benchmarks (Pigment-inspired), session interaction heatmap (Contentsquare-inspired), LLM provider config per org (Mistral-inspired). Routes: `/api/analytics/*`, `/api/llm/*`.
- **Intelligence DB Tables**: `practitioner_risk_scores`, `complication_alerts`, `complication_monitors`, `monitor_submissions`, `llm_provider_configs`, `clinician_events` — created via `app/db/intelligence_migrations.py` on startup.

### Key Features
- **Multilingual Support**: Supports 25 languages with automatic script-based detection and multilingual retrieval strategies.
- **LLM Answer Synthesis**: Employs strict citation rules, uses an "Evidence Pack" for context, and includes quality guards to refuse insufficient evidence.
- **VeriDoc v2 Engine**: Features parallel multi-query retrieval, caching, LLM-based intent classification, batched claim planning and grounding, numeric guardrails, pairwise conflict detection, structured evidence grading, and time-budgeted pipelines. Includes ACI Scoring for answer quality and a Documents Meta Table for persistent source classification.
- **AesthetiCite Safety Engine v3.1.0** (`app/api/complication_protocol_engine.py`): Unified, production-ready engine with 6 complication protocols (vascular occlusion, anaphylaxis, Tyndall effect, ptosis, infection/biofilm, filler nodules), procedure intelligence layer (5 procedures: tear trough, nasolabial fold, glabellar filler, glabellar toxin, lip filler), case logging, dataset statistics, and one-click PDF export via reportlab. Endpoints: `GET /api/complications/protocols`, `POST /api/complications/protocol`, `POST /api/complications/print-view`, `POST /api/complications/export-pdf`, `POST /api/complications/feedback`, `POST /api/complications/log-case`, `GET /api/complications/stats`. Frontend page: `client/src/pages/complication-protocol.tsx` at route `/complications` — renders all 7 ProtocolResponse fields (risk_assessment, dose_guidance, red_flags, escalation, monitoring, follow_up_questions, limitations), quick-scenario chips for 7 common presentations, mode selector (decision_support/emergency/teaching), PDF export, clinician feedback.
- **Vision Diagnosis Engine v1.0.0** (`app/api/vision_diagnosis.py`): VisualDX-inspired complication differential diagnosis from clinical photographs. GPT-4o vision with 9-complication sign dictionary (vascular_occlusion, skin_necrosis, infection_cellulitis, tyndall_effect, inflammatory_nodule, severe_oedema, haematoma_bruising, asymmetry, normal_post_procedure). Returns ranked differential with confidence bars, urgency badges, visual evidence, protocol bridge links. Endpoints: `POST /api/vision/diagnose` (single image), `POST /api/vision/diagnose-compare` (baseline+followup pair), `GET /api/vision/complication-signs`. Frontend components in `client/src/components/vision-diagnosis-result.tsx`: VisionDiagnoseResultPanel, VisionCompareResultPanel, VisionDiagnoseButton. Integrated into visual-counseling.tsx (after upload) and vision-followup.tsx (after serial analysis). Proxy routes in server/routes.ts.
- **AesthetiCite Vision v1.0.0** (`app/api/vision_followup.py`): Serial post-procedure image analysis engine. Uploads 2–10 chronological photos, detects redness/asymmetry/brightness trends via OpenCV, flags emergencies (blanching, visual symptoms), exports clinical PDF reports. Endpoints: `POST /api/vision/analyze`, `POST /api/vision/analyze/export`, `GET /api/vision/procedures`. Frontend page: `client/src/pages/vision-followup.tsx` at route `/vision-followup` — renders slider comparison (baseline vs latest), timeline strip, urgency banners (danger/warn/ok), collapsible findings/metrics/patient message, PDF export. Accessible from sidebar Safety Engine section as "Vision Follow-up". opencv-python-headless installed.
- **Growth Engine v2.0.0** (`app/api/growth_engine.py`): PostgreSQL rewrite of the growth engine. Identical endpoints, fully backward-compatible. 10 features: bookmarks, session safety reports (multi-procedure, PDF export), clinic dashboard (query log metrics: total queries, avg ACI, avg response time, top questions, evidence level distribution), patient-readable export, PWA support (manifest.json + production sw.js), HNSW-ready search adapter (keyword fallback, pgvector-ready), clinic API key management (ac_-prefixed keys, SHA-256 hashed), new paper alerts (subscribe by topic, run digest via NCBI), and drug interaction checker. All under `/api/growth/*`. PostgreSQL persistence via psycopg2.
- **Pre-Procedure Safety Engine v2.1.0** (`app/api/preprocedure_safety_engine_v2.py`): Unified safety workspace replacing v1. All 7 procedure rule sets, 6 complication protocols, 10 drug rule classes, batch endpoint, workspace bootstrap, PubMed 6h cache, dashboard logging. Endpoints under `/api/safety/v2/*`. Legacy aliases at `/api/safety/*` preserved for backward compatibility.
- **Operational Module** (`app/api/operational.py`): Provides `apply_operational_patches`, `pdf_storage` helper, `/api/ops/health/full`, and `/api/ops/dashboard/log-query` (JWT-aware query logging proxy). Registered at `/api/ops` prefix.
- **Rate Limiting** (`server/routes.ts`): Per-user rate limiting via express-rate-limit — 60 req/min on search/ask, 30 req/min on safety checks, 10 req/15min on auth endpoints. Key derived from JWT sub claim.
- **Clinical Utility Tracker** (`app/engine/clinical_utility_feature.py`): Standalone FastAPI module for pilot/investor metrics. Tracks clinicians, query sessions, feedback (usefulness, speed, trust, adoption, accuracy), and feature events. Provides `/metrics/pilot`, `/metrics/retention`, `/summary/executive`, and investor-readiness scoring. Uses SQLite. Includes `/demo/seed`.
- **Aesthetic Medicine Enhancements**: Aesthetic Query Classification, Aesthetic Chunk Tagging, and Aesthetic-Aware Retrieval Boosts for specialized content.
- **Inline Tool Execution**: Automatic clinical tool triggering during answer synthesis (e.g., hyaluronidase_helper, botox_dilution_helper).
- **Visual Counseling (Beta)**: Patient photo upload with evidence-grounded counseling for long-term scenarios and complication assessment.
- **Multi-Turn Conversation Memory**: Postgres-backed conversation tracking with context carry-over.
- **Evidence Type Classification**: Automatic categorization of sources with a ranked evidence hierarchy.
- **Enhanced Mode (OpenEvidence-level AI)**: Advanced evidence-based answering with evidence tiering, claim planning, numeric consistency guard, conflict detection, and clinical summary extraction.
- **DeepConsult PhD Agent**: Multi-study synthesis for complex research questions with academic formatting and literature disagreement detection.
- **Clinical Tools API**: Offers a suite of medical calculators, a drug interaction checker, and advanced aesthetic medicine safety tools.
- **Automated Publication Sync**: Daily ingestion of new papers from PubMed Central across all supported languages and medical specialties. Includes a Journal-Targeted Sync Pipeline for high-impact journals.
- **Mass Upload Engine v1.0** (`app/agents/mass_upload.py`, `app/api/mass_upload_api.py`): Four-milestone ingestion strategy auto-started on server boot. M1=100k clean & ranked (evidence levels assigned, doc types fixed), M2=250k guideline/review priority (118 queries, starts with guidelines, RCTs, Cochrane) — COMPLETE at 760,815 docs, M3=500k multilingual (20 languages × 15 topics = 300 queries) — IN PROGRESS, M4=1M full breadth + dedup + fast search (6 year ranges × 24 topics = 144 queries). Quality operation runs at each milestone: evidence level assignment, doc-type audit, language normalisation, title-based deduplication. Status: `GET /api/mass-upload/status`. Control: `POST /api/mass-upload/start|stop`. Additional endpoints: `POST /api/mass-upload/rebuild-index` (IVFFlat index rebuild), `GET /api/mass-upload/rebuild-index-status`. Policy gates: guideline_priority_enabled, multilang_retrieval_fixed (both set to true; M3/M4 unlocked).
- **Vector Index**: IVFFlat (lists=100) instead of HNSW — HNSW requires >64MB of /dev/shm which Replit does not provide. IVFFlat builds with minimal shared memory and provides ~93% recall with `ivfflat.probes=5`. Index name: `idx_chunks_embedding_hnsw` (backward-compatible). Retriever sets `SET LOCAL ivfflat.probes = 5` at query time alongside `hnsw.ef_search = 80`.
- **Keepalive Fix**: `_keepalive_loop()` in mass_upload.py now runs `while True` (previously `while _state.get("running")` — caused the server to die after 5 min at the policy gate when the engine was paused).
- **Knowledge Base**: Contains 772,770+ documents from peer-reviewed medical journals across 7 languages and 25+ specialties, with a strong focus on Aesthetic Medicine. Growing to 1,500,000 via M5 ingestion (aesthetic deep-dive, recency sweep, safety data — currently running). Five-milestone strategy: M1=clean corpus, M2=authoritative guideline ingestion, M3=multilingual, M4=broad coverage, M5=aesthetic medicine deep-dive (173 subspecialty queries across injectables, energy devices, biostimulators, anatomy, patient safety, hair, body contouring, psychosocial outcomes, skin science, thread lifts, surgical aesthetics, evidence infrastructure + 2023–2025 recency sweep).
- **Evidence Grading System**: Citations are graded (Level I to IV) and displayed with color-coded badges.
- **UI/UX**: OpenEvidence-inspired design with a collapsible sidebar, prominent stats display, color-coded evidence levels, and expandable citations.

### Design Patterns
- **Streaming Responses**: SSE for real-time AI response display.
- **Schema Validation**: Shared Zod schemas between frontend and backend.
- **Modular Component Architecture**: For UI components.
- **Theme System**: CSS variable-based for theming.

## External Dependencies

### AI Services
- **OpenAI API**: Used for text generation, image generation, speech-to-text, and text-to-speech.

### Database
- **PostgreSQL (Neon)**: Primary database migrated to Neon (PostgreSQL 17.8 at `ep-odd-star-amqythz1.c-5.us-east-1.aws.neon.tech`). pgvector 0.8.0 and pg_trgm enabled. Connection via `NEON_DATABASE_URL` env var which overrides the Replit-managed `DATABASE_URL` at startup in `server/index.ts`.
  - **1,988,360 active documents**, **846,442 chunks** (all with 384-dim embeddings)
  - **6 indexes on chunks**: `chunks_pkey` (PK), `idx_chunks_document_id`, `idx_chunks_chunk_index`, `chunks_tsv_gin` (GIN FTS), `chunks_text_norm_trgm` (GIN trgm), `idx_chunks_embedding_hnsw` (IVFFlat, lists=100)
  - **IVFFlat SQL optimization** (March 2026): Removed JOIN from vector CTE in `SQL_UNIFIED_ALL` and `SQL_UNIFIED_DOMAIN` to allow IVFFlat index usage. Active-doc filtering deferred to final SELECT. Reduced retrieval from 66s → 9s (7× speedup).
  - **asyncpg pool**: min=1, max=20 connections, `ivfflat.probes=5` set at session level in `_init_connection`, `statement_timeout=120s`. Maintains persistent connections to keep Neon compute warm.
  - **Performance profile** (March 2026): Cold questions average 6-7s end-to-end (1-8s retrieval + 2.5-3.5s LLM); hot-cache hits serve in ~250ms. Hot answer cache (1-hour TTL) in `app/engine/speed_optimizer.py`.

### APIs
- **NIH RxNav API**: Used for drug interaction checking within the Clinical Tools API.

### Core Libraries/Tools
- **React**, **TypeScript**, **Node.js**, **Express**, **FastAPI**, **uvicorn**, **TanStack React Query**, **shadcn/ui**, **Tailwind CSS**, **Zod**, **Wouter**, **Drizzle ORM**, **fastembed**.

## Critical Production Notes

### Python Startup (IMPORTANT)
- `validate_env()` and `ensure_users_table()` run inside `@app.on_event("startup")` NOT at module level. This ensures uvicorn binds to port 8000 immediately and `/health` responds within seconds in production.
- `ensure_users_table()` is run in a thread executor inside the async startup handler to avoid blocking the asyncio event loop.
- Python is spawned via `uv run uvicorn` (falls back to `python3 -m uvicorn` if `uv` unavailable).
- DB engine has `connect_timeout=10` to prevent hung connections from blocking startup.

### Database Schema Management (CRITICAL)
- **NEVER run `npm run db:push --force`** — this project uses Neon with 53 Python-managed tables including 1.988M document corpus + GIN/tsvector indexes. `db:push --force` would drop all non-Drizzle tables/sequences, destroying everything.
- Use `npx drizzle-kit migrate` instead — it only CREATES tables, never drops anything.
- `drizzle.config.ts` has `tablesFilter: ["conversations", "messages", "search_history"]` to scope Drizzle to 3 Node-managed tables.
- Python manages all other 50+ tables (documents, chunks, users, etc.) directly via SQLAlchemy/psycopg.
- **Neon DB connection**: `NEON_DATABASE_URL` env var → overridden as `DATABASE_URL` at startup in `server/index.ts` line 10. This affects both Node.js Drizzle and Python asyncpg/SQLAlchemy.

## Clinic Network Safety Workspace (Implemented 2026-03-19)

### Route
- `/network-safety-workspace` — 5-tab workspace page
  - Tab 1: Live Guidance — structured complication intake + evidence-reranked guidance workflow
  - Tab 2: Case Log — CRUD complication case management with CSV export and filters
  - Tab 3: Saved Protocols — Protocol library with pin/approve/archive actions (role-gated approve)
  - Tab 4: Reports — Safety reports generated from cases or guidance, with patient/clinical view
  - Tab 5: Admin Dashboard — KPI cards + top complications + high-risk topics + queries-over-time chart (admin-role only)

### Python API (`app/api/network_workspace.py`)
Router prefix: `/api/workspace/` — 20 routes total:
- `GET /api/workspace/orgs/me`, `GET /api/workspace/clinics/me`, `POST /api/workspace/clinics/select`
- `POST /api/workspace/network-guidance/query`
- `POST/GET/PATCH /api/workspace/case-logs`, `GET /api/workspace/case-logs/{id}`, `GET /api/workspace/case-logs/export/csv`
- `POST/GET/PATCH /api/workspace/protocols/{id}`
- `POST /api/workspace/reports/from-case/{id}`, `POST /api/workspace/reports/from-guidance`, `GET /api/workspace/reports/{id}`
- `GET /api/workspace/admin/analytics/overview`, `GET /api/workspace/admin/analytics/trends`

### Database Migrations (`app/db/network_migrations.py`)
- `run_migrations()` — idempotent DDL, called at startup (non-blocking background thread)
- `run_seed()` — dev/demo seed: 1 org, 2 clinics, sample memberships, 10 case logs, 1 protocol, 1 report (commented out in production)
- Tables: `organizations`, `clinics`, `memberships`, `case_logs`, `saved_protocols`, `safety_reports`, `analytics_events`

### Frontend Context (`client/src/hooks/use-clinic-context.tsx`, `client/src/components/clinic-switcher.tsx`)
- `ClinicProvider` wraps the entire app inside `TooltipProvider`
- `useClinicContext()` hook exposes `selectedClinic`, `memberships`, `selectClinic`, `role`, `canAdmin`, `isReady`
- `ClinicSwitcher` dropdown in workspace header — groups clinics by org, shows role badges, persists selection to localStorage

### Node Proxy Routes (server/routes.ts)
- 20 `/api/workspace/*` proxy routes added before `return httpServer`

### Seed Data (dev only)
- Org: "Aesthetic Clinic Group" (slug: acg) — ID: a1000000-…
- Clinics: London Clinic (b1000000-…), Manchester Clinic (b2000000-…)
- Membership IDs: admin c1000000-…, clinician c2000000-…, reviewer c3000000-…
- Uncomment `run_network_seed()` in app/main.py bg thread to populate sample data

## Corpus & Background Jobs (March 2026)

### Corpus status
- **Documents**: 975,888+ (target: 1,000,000)
- **Chunks**: ~800K+ (re-chunking ongoing; target: all 971K+ docs chunked)
- **Embedding model**: `BAAI/bge-small-en-v1.5` (384-dim, via fastembed ONNX) — matches ingest pipeline

### Active background jobs (persist across workflow restarts — must be re-started manually)
Both jobs must be relaunched after each workflow restart by calling their API endpoints with the ADMIN_API_KEY:

**M5 Extension** (`/api/m5ext/start?target=1000000`)
- Script: `app/scripts/m5_extension.py` | API: `app/api/m5_ext.py`
- Phase D: 21 new journals (Dermatologic Surgery, JCD, Aesthetic PS, JPRAS, etc.)
- Phase E: 88 aesthetic-medicine topic queries (biostimulators, thread lift, energy devices, patient outcomes…)
- Uses `fetch_full_abstracts=False` for speed (10x faster — esummary abstract is used)
- Self-stops when corpus reaches 1,000,000 docs
- Status: `GET /api/m5ext/status`

**Re-chunk missing docs** (`/api/rechunk/start?batch=64`)
- Script: `app/scripts/rechunk_missing.py` | API: `app/api/rechunk.py`
- Chunks all documents that have zero existing chunks (~164K remaining as of March 2026)
- Model: `BAAI/bge-small-en-v1.5` (matches existing chunks for vector-space consistency)
- Idempotent — safe to restart; resumes from unchunked docs automatically
- Status: `GET /api/rechunk/status`

### Critical schema rules
- NEVER run `npm run db:push` or `npm run db:push --force` — drizzle-kit 0.31.x bug drops Python-managed sequences and corrupts GIN/tsvector indexes
- Use ONLY `npx drizzle-kit migrate` for schema changes
- Python-managed tables: `documents`, `chunks`, `ingestion_runs`, `pipeline_checkpoints`, `pmid_queue`, `publication_syncs`

## Production Deployment Fix (March 2026)

### Root cause of "Python API failed to become healthy within timeout"
**Two-phase analysis:**

**Phase 1 (earlier fix):** `warm_embedding_cache()` was called at module level, triggering an 83 MB ONNX model download before uvicorn bound. Fixed by moving it to a background thread.

**Phase 2 (final fix):** Even after Phase 1, port 8000 stayed closed for 8–11 minutes in production. Stack dump (SIGUSR1) confirmed Python was stuck in `exec_module` — running module-level import code. The real cause: **43+ router modules were imported at module level** in `app/main.py` (lines 31–74). On a fresh production VM with a cold disk, reading thousands of `.py`/`.pyc` files for the first time (numpy, sqlalchemy, fastembed, asyncpg, openai, etc.) takes 8–11 minutes before uvicorn even gets a chance to bind.

### Final fixes applied (Phase 2)
1. **`app/main.py` — deferred router loading**: All 43+ `from app.api.* import router` statements moved from module level into `@app.on_event("startup")`. Only 7 lightweight packages remain at module level (fastapi, cors, slowapi, sqlalchemy.text, config, limiter). Result: module import ~1s → uvicorn binds in ~1–2s → `port8000=1` at the first 15s watchdog probe. The startup handler imports routers over ~30–60s (acceptable within the 600s Node.js wait window).
2. **`build.sh` — explicit router bytecode warmup**: Build step now explicitly imports all 43 router modules (not just `compileall app/`) so their `.pyc` files are in the deployment image. Cold-disk `.pyc` reads are ~10× faster than compiling `.py` files.

### Earlier fixes (Phase 1)
1. **`app/main.py`**: `warm_embedding_cache()` moved from module level to startup background thread
2. **`start.sh`**: `PYTHONUNBUFFERED=1`; 15-second watchdog logging Python/Node/port8000 status; SIGUSR1 stack dump trigger at 3 min
3. **`app/rag/async_retriever.py`**: `timeout=15` on pool creation; `min_size=2` for faster cold start
4. **`app/rag/cache.py`**: `_fastembed_model_is_cached()` guard prevents ONNX download on startup

### Database architecture
- `DATABASE_URL` = Replit-managed local PostgreSQL (Drizzle 3 tables: conversations, messages, search_history)
- `NEON_DATABASE_URL` = Neon (Python RAG: 1.9M+ docs, 846K chunks, pgvector)
- These are fully decoupled — NEVER set `DATABASE_URL = NEON_DATABASE_URL`
