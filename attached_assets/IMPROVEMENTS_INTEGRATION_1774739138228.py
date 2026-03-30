# AesthetiCite — 15 Improvements Integration Guide
# =====================================================
# Maps each improvement to its file, integration point, and priority.

IMPROVEMENTS = {

    # ── BACKEND ──────────────────────────────────────────────────────────────

    1: {
        "title":   "Agentic / iterative Self-RAG",
        "file":    "self_rag.py → app/engine/self_rag.py",
        "where":   "app/api/ask_v2.py — after initial retrieve_db() call",
        "lines":   """
from app.engine.self_rag import wrap_with_self_rag
chunks, self_rag_meta = await wrap_with_self_rag(
    question=question,
    initial_chunks=chunks,
    retrieve_fn=lambda q, k=8: retrieve_db(q, k=k),
    max_iterations=2,
)
meta_payload["self_rag"] = self_rag_meta
""",
    },

    3: {
        "title":   "Clinical confidence calibration",
        "file":    "self_rag.py → app/engine/self_rag.py (build_calibration_block)",
        "where":   "app/api/ask_v2.py — prepend calibration block to answer prompt",
        "lines":   """
calibration = self_rag_meta["calibration_block"]
prompt = build_single_call_prompt(question, chunks, ...) + calibration
""",
    },

    14: {
        "title":   "Self-RAG hallucination reduction (same as #1)",
        "file":    "self_rag.py",
        "note":    "Covered by improvement #1. SELF_RAG_ENABLED=true env var activates it.",
    },

    4: {
        "title":   "DeepSeek-R1 routing for complex queries",
        "file":    "model_router.py → app/engine/model_router.py",
        "where":   "app/api/ask_v2.py or veridoc.py — before LLM call",
        "env":     "DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL",
        "lines":   """
from app.engine.model_router import route_model
model_config = route_model(question, mode=mode)
# Then use model_config.model_id, model_config.base_url, model_config.api_key
# in your httpx/OpenAI call
""",
    },

    15: {
        "title":   "DSPy-style prompt optimization",
        "file":    "model_router.py → PromptOptimizer class",
        "where":   "Offline evaluation script — run before production deploys",
        "lines":   """
# In a separate eval script (not in request path):
from app.engine.model_router import PromptOptimizer
opt = PromptOptimizer()
results = await opt.run_eval(
    questions=your_eval_set,
    compute_aci_fn=your_aci_fn,
    n_questions=50,
)
print(opt.report())
""",
    },

    2: {
        "title":   "Graph RAG complication entity graph",
        "file":    "model_router.py → AESTHETIC_GRAPH, graph_enrich_query()",
        "where":   "app/engine/veridoc.py or ask_v2.py — before answer prompt",
        "lines":   """
from app.engine.model_router import graph_enrich_query
graph_ctx = graph_enrich_query(question)
if graph_ctx:
    prompt = f"KNOWLEDGE GRAPH CONTEXT:\\n{graph_ctx}\\n\\n" + prompt
""",
    },

    10: {
        "title":   "Complication relationship graph",
        "file":    "model_router.py → ComplicationGraph (same as #2)",
        "note":    "Covered by improvement #2. Use get_protocol_for_query() to pre-load relevant protocols.",
    },

    5: {
        "title":   "Voice → structured consultation note",
        "file":    "clinical_workflow_v2.py → app/api/clinical_workflow_v2.py",
        "route":   "POST /workflow/consultation-note",
        "express": 'app.post("/api/workflow/consultation-note", (req, res) => proxyToFastAPI(req, res, "/workflow/consultation-note"));',
    },

    6: {
        "title":   "Digital consent with audit trail",
        "file":    "clinical_workflow_v2.py → app/api/clinical_workflow_v2.py",
        "routes":  [
            "POST /workflow/consent",
            "GET  /workflow/consent/:id",
        ],
        "express": [
            'app.post("/api/workflow/consent", (req, res) => proxyToFastAPI(req, res, "/workflow/consent"));',
            'app.get("/api/workflow/consent/:id", (req, res) => proxyToFastAPI(req, res, `/workflow/consent/${req.params.id}`));',
        ],
    },

    7: {
        "title":   "Red flag pre-appointment questionnaire",
        "file":    "clinical_workflow_v2.py → app/api/clinical_workflow_v2.py",
        "route":   "POST /workflow/preflight",
        "express": 'app.post("/api/workflow/preflight", (req, res) => proxyToFastAPI(req, res, "/workflow/preflight"));',
        "frontend_note": "Surface PreflightResult in the clinic dashboard / patient record view with a red/orange banner",
    },

    13: {
        "title":   "OpenMed NER for richer chunk tagging",
        "file":    "clinical_workflow_v2.py → tag_chunk_ner()",
        "where":   "app/api/ingest.py — call tag_chunk_ner() on each chunk during ingestion",
        "lines":   """
from app.api.clinical_workflow_v2 import tag_chunk_ner
# In your ingestion loop:
chunk["ner_tags"] = tag_chunk_ner(chunk.get("text", ""), chunk.get("title", ""))
""",
    },

    # ── FRONTEND ─────────────────────────────────────────────────────────────

    12: {
        "title":   "3-tap emergency protocol access",
        "file":    "ClinicalUIKit.tsx → EmergencyDropdown",
        "where":   "client/src/pages/ask.tsx — replace current Emergency button in header",
        "lines":   """
import { EmergencyDropdown } from "@/components/ClinicalUIKit";
// Replace: <Button variant="destructive">Emergency</Button>
// With:    <EmergencyDropdown />
""",
    },

    8: {
        "title":   "MHRA SaMD regulatory badge",
        "file":    "ClinicalUIKit.tsx → MHRABadge",
        "where":   "client/src/pages/governance.tsx and footer/header",
        "lines":   """
import { MHRABadge } from "@/components/ClinicalUIKit";
<MHRABadge />                 // full card
<MHRABadge compact />         // inline badge with tooltip
""",
    },

    9: {
        "title":   "Role-specific interfaces",
        "file":    "ClinicalUIKit.tsx → RoleSwitch, getRoleNavItems",
        "where":   "client/src/pages/ask.tsx header — replace static nav with role-aware nav",
        "lines":   """
import { RoleSwitch, getRoleNavItems } from "@/components/ClinicalUIKit";
const [role, setRole] = useState<"clinician" | "clinic_owner">("clinician");
const navItems = getRoleNavItems(role);

<RoleSwitch currentRole={role} onRoleChange={setRole} />
// Then render navItems instead of hardcoded links
""",
    },

    11: {
        "title":   "Dark mode intelligent default",
        "file":    "ClinicalUIKit.tsx → useAutoDarkMode hook",
        "where":   "client/src/components/theme-provider.tsx",
        "lines":   """
import { useAutoDarkMode } from "@/components/ClinicalUIKit";
const { shouldUseDark } = useAutoDarkMode();
// Apply shouldUseDark to your ThemeProvider defaultTheme logic
""",
    },

    "tooltips_bonus": {
        "title":   "Clinical tooltips for ACI / evidence terms (Improvement #8 extra)",
        "file":    "ClinicalUIKit.tsx → ClinicalTooltip, CLINICAL_TOOLTIPS",
        "where":   "Any component showing ACI score, evidence badge, or medical terms",
        "lines":   """
import { ClinicalTooltip, CLINICAL_TOOLTIPS } from "@/components/ClinicalUIKit";
<ClinicalTooltip content={CLINICAL_TOOLTIPS.aci_score}>
  ACI {score}
</ClinicalTooltip>
""",
    },
}

# ── File placement summary ────────────────────────────────────────────────────

FILES = {
    "app/engine/self_rag.py":              "Improvements #1 #3 #14",
    "app/engine/model_router.py":          "Improvements #2 #4 #10 #15",
    "app/api/clinical_workflow_v2.py":     "Improvements #5 #6 #7 #13",
    "client/src/components/ClinicalUIKit.tsx": "Improvements #8 #9 #11 #12 #13",
}

# ── main.py additions ────────────────────────────────────────────────────────

MAIN_PY_ADDITIONS = """
from app.api.clinical_workflow_v2 import router as clinical_workflow_v2_router
app.include_router(clinical_workflow_v2_router)
"""

# ── server/routes.ts additions ───────────────────────────────────────────────

ROUTES_TS_ADDITIONS = """
  // Clinical Workflow v2 (improvements #5, #6, #7, #13)
  app.post("/api/workflow/consultation-note", (req, res) => proxyToFastAPI(req, res, "/workflow/consultation-note"));
  app.post("/api/workflow/consent",           (req, res) => proxyToFastAPI(req, res, "/workflow/consent"));
  app.get ("/api/workflow/consent/:id",       (req, res) => proxyToFastAPI(req, res, `/workflow/consent/${req.params.id}`));
  app.post("/api/workflow/preflight",         (req, res) => proxyToFastAPI(req, res, "/workflow/preflight"));
  app.post("/api/workflow/tag-chunk",         (req, res) => proxyToFastAPI(req, res, "/workflow/tag-chunk"));
"""
