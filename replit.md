# AesthetiCite - AI-Powered Evidence Search

## Overview
AesthetiCite is an AI-powered research platform providing evidence-based answers to medical research questions with citations from trusted sources. It offers comprehensive, structured responses with inline citations, related questions, and source references. The platform aims to support clinicians and medical students, leveraging a React frontend with a real-time streaming search interface.

The project's ambition is to become a leading tool for evidence-based medicine, offering reliable information across various medical specialties and supporting multilingual access globally.

## User Preferences
Preferred communication style: Simple, everyday language.

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
  - **Data Flow**: User queries are validated, relevant evidence chunks are retrieved via RAG (semantic + keyword search), and an LLM synthesizes an evidence-grounded answer with strict citation enforcement, streaming the response via Server-Sent Events (SSE).

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
- **PostgreSQL**: Primary database, utilized with the `pgvector` extension.

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
- **NEVER run `npm run db:push --force`** on dev — the dev DB has 36 Python-managed tables (including 772K document corpus). `db:push --force` would drop all non-Drizzle tables, destroying the corpus.
- Use `npx drizzle-kit migrate` instead — it only CREATES tables, never drops anything.
- `drizzle.config.ts` has `tablesFilter: ["conversations", "messages", "search_history"]` to scope Drizzle to 3 Node-managed tables.
- Production build runs `npm run build && npx drizzle-kit migrate` to set up the 3 Node-managed tables in the fresh production DB.
- Python manages all other 36 tables (documents, chunks, users, etc.) directly via SQLAlchemy/psycopg.
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
