"""
AesthetiCite Safety Engine — v3.1.0
=====================================
Unified, production-ready clinical decision-support module.

Endpoints (all backward-compatible):
  GET  /api/complications/protocols       — list all protocols
  POST /api/complications/protocol        — JSON protocol + evidence + procedure insight
  POST /api/complications/print-view      — print-ready HTML
  POST /api/complications/export-pdf      — PDF download (reportlab)
  POST /api/complications/feedback        — clinician feedback capture
  POST /api/complications/log-case        — case logging for dataset building
  GET  /api/complications/stats           — case dataset statistics

Notes:
  - Replace DummyEvidenceRetriever with your real RAG/citation layer.
  - CASE_STORE is in-memory; replace with a database for production.
  - PDF files are written to AESTHETICITE_EXPORT_DIR (default: exports/).
  - Audit logs: AESTHETICITE_COMPLICATION_AUDIT_LOG (JSONL).
  - Feedback logs: AESTHETICITE_COMPLICATION_FEEDBACK_LOG (JSONL).
  - This is clinical decision support — not a substitute for clinician judgment.
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

router = APIRouter(prefix="/api/complications", tags=["AesthetiCite Complication Engine"])

ENGINE_VERSION = "3.1.0"
PROTOCOL_REVISION = "2026-03-13"

AUDIT_LOG_PATH = os.environ.get(
    "AESTHETICITE_COMPLICATION_AUDIT_LOG", "complication_audit_log.jsonl"
)
FEEDBACK_LOG_PATH = os.environ.get(
    "AESTHETICITE_COMPLICATION_FEEDBACK_LOG", "complication_feedback.jsonl"
)
EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────────

SeverityLevel = Literal["low", "moderate", "high", "critical"]
UrgencyLevel = Literal["routine", "same_day", "urgent", "immediate"]
EvidenceStrength = Literal["limited", "moderate", "strong"]


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class ClinicalContext(BaseModel):
    # Injection / procedure context
    region: Optional[str] = None
    procedure: Optional[str] = None
    product_type: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    time_since_injection_minutes: Optional[int] = None
    free_text: Optional[str] = None

    # Vascular / ischemia
    visual_symptoms: Optional[bool] = None
    skin_color_change: Optional[str] = None
    pain_score_10: Optional[int] = Field(default=None, ge=0, le=10)
    capillary_refill_delayed: Optional[bool] = None
    filler_confirmed_ha: Optional[bool] = None

    # Infection / inflammatory
    tenderness: Optional[bool] = None
    warmth: Optional[bool] = None
    erythema: Optional[bool] = None
    fluctuance: Optional[bool] = None
    drainage: Optional[bool] = None
    fever: Optional[bool] = None

    # Anaphylaxis / systemic allergic
    wheeze: Optional[bool] = None
    hypotension: Optional[bool] = None
    facial_or_tongue_swelling: Optional[bool] = None
    generalized_urticaria: Optional[bool] = None

    # Ptosis / toxin
    eyelid_droop: Optional[bool] = None
    brow_heaviness: Optional[bool] = None
    diplopia: Optional[bool] = None
    toxin_recent: Optional[bool] = None


class ProtocolRequest(BaseModel):
    query: str = Field(..., min_length=3)
    context: Optional[ClinicalContext] = None
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    mode: Literal["decision_support", "emergency", "teaching"] = "decision_support"


class EvidenceItem(BaseModel):
    source_id: str
    title: str
    note: str
    citation_text: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    relevance_score: Optional[float] = None


class ProtocolStep(BaseModel):
    step_number: int
    action: str
    rationale: str
    priority: Literal["primary", "secondary"] = "primary"


class DoseGuidance(BaseModel):
    substance: str
    recommendation: str
    notes: str


class ProcedureInsight(BaseModel):
    """Procedure-specific anatomic and technique intelligence, auto-detected from query and context."""
    procedure_name: str
    likely_plane: Optional[str] = None
    key_danger_zones: List[str] = Field(default_factory=list)
    technique_notes: List[str] = Field(default_factory=list)
    common_products_or_classes: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    risk_score: int = Field(..., ge=0, le=100)
    severity: SeverityLevel
    urgency: UrgencyLevel
    likely_time_critical: bool
    evidence_strength: EvidenceStrength


class ProtocolResponse(BaseModel):
    request_id: str
    engine_version: str
    protocol_revision: str
    generated_at_utc: str
    matched_protocol_key: str
    matched_protocol_name: str
    confidence: float
    risk_assessment: RiskAssessment
    clinical_summary: str
    immediate_actions: List[ProtocolStep]
    dose_guidance: List[DoseGuidance]
    procedure_insight: Optional[ProcedureInsight] = None
    red_flags: List[str]
    escalation: List[str]
    monitoring: List[str]
    limitations: List[str]
    follow_up_questions: List[str]
    evidence: List[EvidenceItem]
    disclaimer: str


class PrintViewResponse(BaseModel):
    request_id: str
    html: str


class ExportPDFResponse(BaseModel):
    request_id: str
    pdf_path: str
    filename: str


class FeedbackRequest(BaseModel):
    request_id: str
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    was_useful: bool
    comment: Optional[str] = None
    selected_protocol_key: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    request_id: str


class LogCaseRequest(BaseModel):
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    protocol_key: str
    region: Optional[str] = None
    procedure: Optional[str] = None
    product_type: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    outcome: Optional[str] = None


class LogCaseResponse(BaseModel):
    status: str
    case_id: str


class LoggedCase(BaseModel):
    case_id: str
    logged_at_utc: str
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    protocol_key: str
    region: Optional[str] = None
    procedure: Optional[str] = None
    product_type: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    outcome: Optional[str] = None


class DatasetStatsResponse(BaseModel):
    total_cases: int
    by_protocol: Dict[str, int]
    by_region: Dict[str, int]
    by_procedure: Dict[str, int]


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def joined_context_text(context: Optional[ClinicalContext]) -> str:
    """Build a single normalized string from all free-text context fields."""
    if not context:
        return ""
    parts: List[str] = []
    for field in (context.region, context.procedure, context.product_type, context.free_text):
        if field:
            parts.append(field)
    parts.extend(context.symptoms)
    return normalize(" ".join(parts))


def safe_write_jsonl(path: str, record: Dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # nosec B110
        pass


# ─────────────────────────────────────────────────────────────────────────────
# HTML helpers (for print-view endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def _html_list(items: List[str]) -> str:
    if not items:
        return "<ul><li>None</li></ul>"
    return "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"


def _html_steps(steps: List[ProtocolStep]) -> str:
    if not steps:
        return "<ol><li>No steps available</li></ol>"
    return (
        "<ol>"
        + "".join(
            f"<li><strong>{html.escape(s.action)}</strong><br>"
            f"<span style='color:#444'>{html.escape(s.rationale)}</span></li>"
            for s in steps
        )
        + "</ol>"
    )


def _html_doses(doses: List[DoseGuidance]) -> str:
    if not doses:
        return "<ul><li>No dose guidance available</li></ul>"
    return (
        "<ul>"
        + "".join(
            f"<li><strong>{html.escape(d.substance)}:</strong> {html.escape(d.recommendation)}"
            f"<br><span style='color:#444'>{html.escape(d.notes)}</span></li>"
            for d in doses
        )
        + "</ul>"
    )


def _html_evidence(evidence: List[EvidenceItem]) -> str:
    if not evidence:
        return "<ul><li>No evidence retrieved</li></ul>"
    rows = []
    for e in evidence:
        row = (
            f"<li><strong>[{html.escape(e.source_id)}] {html.escape(e.title)}</strong>"
            f"<br>{html.escape(e.note)}"
        )
        if e.citation_text:
            row += f"<br><em>{html.escape(e.citation_text)}</em>"
        row += "</li>"
        rows.append(row)
    return "<ul>" + "".join(rows) + "</ul>"


# ─────────────────────────────────────────────────────────────────────────────
# SQLite-backed case store (persistent across restarts)
# ─────────────────────────────────────────────────────────────────────────────

CASE_DB_PATH = os.environ.get("AESTHETICITE_CASE_DB", "complication_cases.db")
_case_db_lock = threading.Lock()


def _get_case_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CASE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_case_db() -> None:
    with _case_db_lock:
        conn = _get_case_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logged_cases (
                case_id        TEXT PRIMARY KEY,
                logged_at_utc  TEXT NOT NULL,
                clinic_id      TEXT,
                clinician_id   TEXT,
                protocol_key   TEXT,
                region         TEXT,
                procedure      TEXT,
                product_type   TEXT,
                symptoms       TEXT,
                outcome        TEXT
            )
        """)
        conn.commit()
        conn.close()


_init_case_db()


# ─────────────────────────────────────────────────────────────────────────────
# Procedure intelligence library
# ─────────────────────────────────────────────────────────────────────────────

PROCEDURE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "tear_trough_ha_filler": {
        "aliases": ["tear trough filler", "tear trough ha", "under eye filler", "periorbital filler"],
        "likely_plane": "Deep, controlled placement is preferred. Superficial deposition increases Tyndall effect risk significantly.",
        "danger_zones": [
            "Angular vessels",
            "Infraorbital neurovascular bundle",
            "Periorbital vascular territory",
        ],
        "technique_notes": [
            "Avoid superficial deposition — Tyndall effect is common with superficial HA in the tear trough.",
            "Very small volumes per pass reduce vascular risk in this high-risk region.",
            "Escalate immediately if pain, blanching, or any visual symptom occurs.",
        ],
        "products": ["Hyaluronic acid filler (low-viscosity preferred)"],
    },
    "nasolabial_fold_filler": {
        "aliases": ["nasolabial fold filler", "nlf filler", "nasolabial filler", "smile line filler"],
        "likely_plane": "Technique varies by product and anatomy. Vascular awareness is essential throughout this territory.",
        "danger_zones": [
            "Angular artery territory",
            "Facial artery branches",
            "Labial arteries",
        ],
        "technique_notes": [
            "Vascular compromise in this region can progress quickly — treatment must not be delayed.",
            "Pain, blanching, mottling, or delayed capillary refill should immediately trigger protocol review.",
            "Aspirate if using sharp needle; consider cannula technique for added safety.",
        ],
        "products": ["Hyaluronic acid filler", "Calcium hydroxylapatite (depending on local practice)"],
    },
    "glabellar_filler": {
        "aliases": ["glabellar filler", "glabella filler", "frown line filler", "glabellar ha filler"],
        "likely_plane": "Deep supraperiosteal or intramuscular preferred. Superficial placement in glabella is high-risk.",
        "danger_zones": [
            "Supratrochlear artery",
            "Supraorbital artery",
            "Ophthalmic artery territory",
        ],
        "technique_notes": [
            "Glabellar is one of the highest-risk zones for vascular occlusion and vision loss.",
            "Use minimum effective volume with aspiration technique.",
            "Any visual symptom after glabellar filler is a medical emergency — call emergency services immediately.",
        ],
        "products": ["Hyaluronic acid filler only (HA reversibility is essential in this region)"],
    },
    "glabellar_toxin": {
        "aliases": ["glabellar botox", "glabellar toxin", "frown line botox", "frown line toxin", "procerus toxin"],
        "likely_plane": "Toxin is typically placed intramuscular. Placement depth and volume affect diffusion risk.",
        "danger_zones": [
            "Levator palpebrae superioris (via diffusion)",
            "Corrugator supercilii / procerus",
        ],
        "technique_notes": [
            "Ptosis risk is linked to toxin diffusion through the orbital septum.",
            "Differentiate brow heaviness from true eyelid ptosis for appropriate management.",
            "Avoid over-injection near the orbital rim to reduce diffusion risk.",
        ],
        "products": ["Botulinum toxin A"],
    },
    "lip_filler": {
        "aliases": ["lip filler", "lip augmentation filler", "lip ha filler", "lip enhancement"],
        "likely_plane": "Submucosal or intramuscular depending on target. Labial arteries are superficial and easily occluded.",
        "danger_zones": [
            "Superior and inferior labial arteries",
            "Facial artery",
            "Angular artery (at commissure)",
        ],
        "technique_notes": [
            "The labial arteries run superficially and are easily cannulated by needle.",
            "Blanching, pain, or mottling after lip injection should trigger immediate hyaluronidase treatment.",
            "Use retrograde threading or cannula technique to minimize intravascular injection risk.",
        ],
        "products": ["Hyaluronic acid filler"],
    },
}


def detect_procedure_insight(
    query: str, context: Optional[ClinicalContext]
) -> Optional[ProcedureInsight]:
    """
    Auto-detects the aesthetic procedure from query and context, then returns
    structured anatomic and technique intelligence for that procedure.
    Returns None when no procedure can be matched.
    """
    blob = normalize(f"{query} {joined_context_text(context)}")
    if context and context.procedure:
        blob = normalize(f"{context.procedure} {blob}")

    for procedure_key, data in PROCEDURE_LIBRARY.items():
        if any(alias in blob for alias in data["aliases"]):
            return ProcedureInsight(
                procedure_name=procedure_key,
                likely_plane=data["likely_plane"],
                key_danger_zones=data["danger_zones"],
                technique_notes=data["technique_notes"],
                common_products_or_classes=data["products"],
            )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Evidence retriever
# ─────────────────────────────────────────────────────────────────────────────

class EvidenceRetriever:
    def retrieve(
        self, protocol_key: str, query: str, context: Optional[ClinicalContext]
    ) -> List[EvidenceItem]:
        raise NotImplementedError


class DummyEvidenceRetriever(EvidenceRetriever):
    """
    Placeholder — replace with your real RAG/pgvector retrieval layer.
    Evidence is keyed by protocol_key.
    """

    _DATA: Dict[str, List[EvidenceItem]] = {
        "vascular_occlusion_ha_filler": [
            EvidenceItem(
                source_id="S1",
                title="Expert consensus on management of vascular occlusion after HA fillers",
                note="Supports urgent territory-based hyaluronidase treatment and repeated reassessment.",
                citation_text="High-dose pulsed hyaluronidase is central to early management of HA filler-related ischemia.",
                source_type="consensus_review",
                relevance_score=0.97,
            ),
            EvidenceItem(
                source_id="S2",
                title="Clinical guidance for visual symptoms after filler injection",
                note="Supports immediate emergency escalation for any ocular symptoms after filler.",
                citation_text="Any visual symptom after filler injection should be treated as an emergency.",
                source_type="guideline_review",
                relevance_score=0.98,
            ),
            EvidenceItem(
                source_id="S3",
                title="Aesthetic medicine review on tissue ischemia after filler injection",
                note="Supports monitoring capillary refill and escalation for progressive ischemia.",
                citation_text="Treat the affected vascular territory rather than a single puncture point.",
                source_type="review",
                relevance_score=0.93,
            ),
        ],
        "filler_nodules_inflammatory_or_noninflammatory": [
            EvidenceItem(
                source_id="S10",
                title="Delayed-onset nodules after soft tissue fillers",
                note="Supports distinguishing inflammatory, infectious, and placement-related nodules.",
                citation_text="Assessment should separate noninflammatory filler deposition from inflammatory or infectious nodules.",
                source_type="review",
                relevance_score=0.91,
            ),
        ],
        "tyndall_effect_ha_filler": [
            EvidenceItem(
                source_id="S20",
                title="Superficial HA filler placement and Tyndall effect",
                note="Supports conservative targeted reversal when cosmetically indicated.",
                citation_text="Low-volume targeted hyaluronidase may correct superficial HA filler-related bluish discoloration.",
                source_type="review",
                relevance_score=0.90,
            ),
        ],
        "infection_or_biofilm_after_filler": [
            EvidenceItem(
                source_id="S30",
                title="Infectious complications after dermal fillers",
                note="Supports escalation for drainage, fluctuance, systemic symptoms, or progressive inflammation.",
                citation_text="Biofilm or infection should be considered when delayed swelling is painful, warm, and erythematous.",
                source_type="review",
                relevance_score=0.92,
            ),
        ],
        "anaphylaxis_allergic_reaction": [
            EvidenceItem(
                source_id="S40",
                title="Emergency management principles for anaphylaxis — resuscitation council consensus",
                note="Supports immediate IM epinephrine as first-line treatment without delay.",
                citation_text="Intramuscular adrenaline 0.5 mg into the outer thigh is first-line treatment for anaphylaxis in adults.",
                source_type="guideline",
                relevance_score=0.99,
            ),
            EvidenceItem(
                source_id="S41",
                title="Observation and escalation guidance after anaphylaxis",
                note="Supports emergency transfer, airway assessment, and extended observation for biphasic reactions.",
                citation_text="Airway, breathing, and circulation should be assessed urgently, with emergency transfer and observation.",
                source_type="guideline",
                relevance_score=0.95,
            ),
        ],
        "botulinum_toxin_ptosis": [
            EvidenceItem(
                source_id="S50",
                title="Botulinum toxin adverse effects and eyelid ptosis management",
                note="Supports recognition of toxin diffusion-related ptosis and symptomatic management.",
                citation_text="Eyelid ptosis after botulinum toxin is usually temporary and may be managed symptomatically.",
                source_type="review",
                relevance_score=0.91,
            ),
        ],
        "neuromodulator_resistance": [
            EvidenceItem(
                source_id="NR-01",
                title="Botulinum toxin resistance in aesthetic practice — mechanisms and management",
                note="Reviews true vs pseudo-resistance, antibody formation risk factors, and clinical management strategies.",
                source_type="Narrative Review",
                relevance_score=0.88,
            ),
            EvidenceItem(
                source_id="NR-02",
                title="IncobotulinumtoxinA: lower immunogenic protein load and clinical implications",
                note="Supports switching to Xeomin in antibody-mediated resistance due to absence of complexing proteins.",
                source_type="Clinical Review",
                relevance_score=0.82,
            ),
            EvidenceItem(
                source_id="NR-03",
                title="CMAC 2025 — Pseudo-resistance: a new concept in neuromodulator management",
                note="Introduced the clinical distinction between true resistance and pseudo-resistance, with technique reset protocol.",
                source_type="Conference Presentation",
                relevance_score=0.91,
            ),
        ],
    }

    def retrieve(
        self, protocol_key: str, query: str, context: Optional[ClinicalContext]
    ) -> List[EvidenceItem]:
        return list(self._DATA.get(protocol_key, []))


evidence_retriever: EvidenceRetriever = DummyEvidenceRetriever()


# ─────────────────────────────────────────────────────────────────────────────
# Protocol library
# ─────────────────────────────────────────────────────────────────────────────

PROTOCOL_LIBRARY: Dict[str, Dict[str, Any]] = {
    "vascular_occlusion_ha_filler": {
        "name": "Suspected vascular occlusion after hyaluronic acid filler",
        "base_severity": "critical",
        "base_urgency": "immediate",
        "evidence_strength": "moderate",
        "summary": (
            "This presentation is concerning for impending or established vascular compromise after "
            "hyaluronic acid filler. Time-critical intervention is required to restore perfusion and "
            "reduce the risk of tissue necrosis. Any visual symptom requires immediate emergency escalation."
        ),
        "keywords": [
            "vascular occlusion", "blanching", "mottling", "livedo", "ischemia",
            "pain after filler", "dusky discoloration", "capillary refill", "necrosis",
            "hyaluronic acid filler", "ha filler", "dusky", "violaceous",
        ],
        "steps": [
            {
                "action": "Stop injection immediately and do not place additional filler.",
                "rationale": "Further injection may worsen intravascular obstruction and ischemia.",
                "priority": "primary",
            },
            {
                "action": "Assess airway, breathing, and circulation. Then assess capillary refill, skin color, temperature, pain, and the full territory of blanching or livedo.",
                "rationale": "Rapid assessment defines extent and progression of tissue compromise.",
                "priority": "primary",
            },
            {
                "action": "Escalate immediately if any visual symptom is present — call emergency services without delay.",
                "rationale": "Ocular ischemia after filler is a medical emergency with risk of permanent vision loss.",
                "priority": "primary",
            },
            {
                "action": "Massage the area and apply warm compresses if not contraindicated.",
                "rationale": "May support vasodilation and mechanical dispersion of filler.",
                "priority": "secondary",
            },
            {
                "action": "Administer high-dose hyaluronidase promptly across the full affected vascular territory.",
                "rationale": "Rapid HA filler breakdown is the key reversible intervention — treat the territory, not just the puncture point.",
                "priority": "primary",
            },
            {
                "action": "Reassess perfusion after each treatment cycle and repeat hyaluronidase if ischemic signs persist.",
                "rationale": "Persistent blanching, pain, or delayed refill suggests ongoing obstruction.",
                "priority": "primary",
            },
            {
                "action": "Document timing, findings, photographs, dose, and response after each cycle.",
                "rationale": "Supports continuity of care and medicolegal documentation.",
                "priority": "secondary",
            },
        ],
        "dose_guidance": [
            {
                "substance": "Hyaluronidase",
                "recommendation": (
                    "Use high-dose pulsed treatment. A practical starting point is at least 500 IU per affected "
                    "ischemic area, with many expert protocols using 500 to 1500 IU or more depending on extent, "
                    "repeated at short intervals until reperfusion improves."
                ),
                "notes": "Inject across the full compromised vascular territory. Repeat according to persistent pain, blanching, livedo, and delayed refill.",
            },
            {
                "substance": "Aspirin",
                "recommendation": "Consider according to clinician judgment and local protocol when not contraindicated.",
                "notes": "Use depends on bleeding risk and local practice.",
            },
        ],
        "red_flags": [
            "Visual disturbance, blurred vision, diplopia, or vision loss",
            "Severe or escalating pain",
            "Rapidly spreading blanching or livedo",
            "Delayed or absent capillary refill",
            "Dusky or violaceous discoloration",
        ],
        "escalation": [
            "Immediate ophthalmology and emergency referral for any visual symptom",
            "Urgent senior clinician review if reperfusion does not improve after initial treatment",
            "Emergency department transfer if tissue compromise is progressive or extensive",
        ],
        "monitoring": [
            "Reassess capillary refill every 15 to 30 minutes initially",
            "Track pain progression and skin color changes",
            "Repeat photographs after each intervention cycle",
            "Continue close follow-up until reperfusion is stable or specialist care has taken over",
        ],
        "limitations": [
            "Evidence is based largely on expert consensus and review literature rather than randomized trials",
            "Optimal hyaluronidase dose and interval are not fully standardized",
            "This protocol applies only when HA filler is suspected or confirmed",
        ],
        "follow_up_questions": [
            "Was the product definitely hyaluronic acid filler?",
            "Which anatomical region was injected?",
            "Are there visual symptoms?",
            "How many minutes have passed since injection?",
            "Is capillary refill delayed or absent?",
        ],
    },

    "filler_nodules_inflammatory_or_noninflammatory": {
        "name": "Suspected filler nodules after injectable treatment",
        "base_severity": "moderate",
        "base_urgency": "same_day",
        "evidence_strength": "moderate",
        "summary": (
            "This presentation may represent noninflammatory filler deposition, inflammatory nodules, or a "
            "biofilm/infection-associated complication. Management depends on timing, tenderness, erythema, "
            "warmth, fluctuance, drainage, and filler identity."
        ),
        "keywords": [
            "filler nodule", "lump after filler", "bump after filler", "granuloma",
            "biofilm", "delayed nodule", "tender swelling", "filler lump",
        ],
        "steps": [
            {
                "action": "Assess onset timing, tenderness, erythema, warmth, fluctuance, drainage, and filler type.",
                "rationale": "This distinguishes placement-related irregularity from inflammatory or infectious complications.",
                "priority": "primary",
            },
            {
                "action": "Avoid aggressive massage when nodules are delayed, tender, inflamed, or diagnostically unclear.",
                "rationale": "Massage may worsen inflammation or obscure assessment findings.",
                "priority": "primary",
            },
            {
                "action": "If HA filler is confirmed and the lesion appears noninfectious, consider targeted hyaluronidase.",
                "rationale": "HA filler can often be enzymatically reduced.",
                "priority": "secondary",
            },
            {
                "action": "Escalate promptly if infection is suspected.",
                "rationale": "Infectious or biofilm-related complications require clinician-led management.",
                "priority": "primary",
            },
        ],
        "dose_guidance": [
            {
                "substance": "Hyaluronidase",
                "recommendation": "Use targeted dosing for confirmed HA filler when clinically appropriate.",
                "notes": "Dose depends on filler type, volume, chronicity, location, and clinical objective.",
            },
        ],
        "red_flags": [
            "Marked tenderness with erythema or warmth",
            "Fluctuance or drainage",
            "Systemic symptoms",
            "Progressive swelling",
        ],
        "escalation": [
            "Urgent clinician review if infection or abscess is suspected",
            "Senior review for recurrent or treatment-resistant nodules",
        ],
        "monitoring": [
            "Document size, tenderness, warmth, erythema, and change over time",
            "Reassess after each intervention",
        ],
        "limitations": [
            "Precise treatment depends on confirmed filler identity and whether inflammation or infection is present",
        ],
        "follow_up_questions": [
            "Is the filler confirmed HA?",
            "How long after injection did the nodule appear?",
            "Is it tender, red, or warm?",
            "Is there fluctuance or drainage?",
        ],
    },

    "tyndall_effect_ha_filler": {
        "name": "Suspected Tyndall effect after superficial hyaluronic acid filler",
        "base_severity": "low",
        "base_urgency": "routine",
        "evidence_strength": "moderate",
        "summary": (
            "This presentation is consistent with superficial HA filler causing bluish or blue-gray discoloration. "
            "It is usually not an emergency, but ischemia must first be excluded before any intervention."
        ),
        "keywords": [
            "tyndall", "blue discoloration", "bluish under eyes", "superficial filler",
            "ha filler too superficial", "blue-gray discoloration", "tear trough blue",
        ],
        "steps": [
            {
                "action": "Confirm there are no ischemic features such as pain, blanching, livedo, or delayed capillary refill.",
                "rationale": "Tyndall effect must be clearly distinguished from vascular compromise before any treatment.",
                "priority": "primary",
            },
            {
                "action": "Assess whether superficial HA filler placement is the likely cause.",
                "rationale": "Management depends on product identity and filler depth.",
                "priority": "primary",
            },
            {
                "action": "Consider conservative targeted low-volume hyaluronidase if correction is desired and ischemia is excluded.",
                "rationale": "Superficial HA filler can often be partially reversed with conservative dosing.",
                "priority": "secondary",
            },
        ],
        "dose_guidance": [
            {
                "substance": "Hyaluronidase",
                "recommendation": "Use conservative targeted dosing based on area and desired degree of correction.",
                "notes": "Avoid overcorrection. Reassess before repeating treatment.",
            },
        ],
        "red_flags": [
            "Pain",
            "Blanching",
            "Livedo or mottling",
            "Delayed capillary refill",
            "Rapid progression of any sign",
        ],
        "escalation": [
            "Escalate immediately if ischemic features are present — do not treat as cosmetic discoloration",
        ],
        "monitoring": [
            "Monitor cosmetic response and avoid overcorrection",
        ],
        "limitations": [
            "Requires confirmation that the product is HA and the finding is superficial placement rather than ischemia",
        ],
        "follow_up_questions": [
            "Is the discoloration blue-gray rather than pale or mottled?",
            "Was HA filler used?",
            "Is there pain or blanching?",
        ],
    },

    "infection_or_biofilm_after_filler": {
        "name": "Suspected infection or biofilm-related complication after filler",
        "base_severity": "high",
        "base_urgency": "urgent",
        "evidence_strength": "limited",
        "summary": (
            "This presentation raises concern for an infectious or biofilm-related complication after filler treatment. "
            "Tenderness, warmth, erythema, fluctuance, drainage, or fever increase concern and warrant urgent clinical review."
        ),
        "keywords": [
            "infection after filler", "biofilm after filler", "warm red swelling", "drainage after filler",
            "fluctuant swelling", "abscess after filler", "fever after filler",
        ],
        "steps": [
            {
                "action": "Assess for tenderness, warmth, erythema, fluctuance, drainage, fever, and systemic symptoms.",
                "rationale": "These features raise suspicion for infectious or biofilm-related complications.",
                "priority": "primary",
            },
            {
                "action": "Do not assume the lesion is a simple cosmetic irregularity if inflammatory signs are present.",
                "rationale": "Delayed recognition of infection can worsen outcomes.",
                "priority": "primary",
            },
            {
                "action": "Escalate for clinician-led infection assessment and management.",
                "rationale": "Antibiotic selection, drainage, and procedural decisions require clinical evaluation.",
                "priority": "primary",
            },
            {
                "action": "Document evolution, photographs, and prior filler history.",
                "rationale": "Complication evolution and prior treatment history affect diagnosis and management.",
                "priority": "secondary",
            },
        ],
        "dose_guidance": [],
        "red_flags": [
            "Fever",
            "Fluctuance",
            "Drainage",
            "Rapidly progressive swelling",
            "Marked tenderness with erythema and warmth",
        ],
        "escalation": [
            "Urgent in-person clinician review",
            "Emergency referral if systemic illness or rapidly progressive facial infection is suspected",
        ],
        "monitoring": [
            "Track swelling, tenderness, temperature, drainage, and systemic symptoms",
        ],
        "limitations": [
            "Management requires clinician assessment and may depend on local microbiology, drainage decisions, and procedural history",
        ],
        "follow_up_questions": [
            "Is there warmth, drainage, or fluctuance?",
            "Is the patient febrile?",
            "When did symptoms begin after injection?",
            "Has any antibiotic or dissolving treatment already been given?",
        ],
    },

    "anaphylaxis_allergic_reaction": {
        "name": "Suspected anaphylaxis or severe allergic reaction after aesthetic treatment",
        "base_severity": "critical",
        "base_urgency": "immediate",
        "evidence_strength": "strong",
        "summary": (
            "This presentation is concerning for anaphylaxis or severe systemic allergic reaction. "
            "Immediate recognition and emergency action are required — call emergency services without delay. "
            "Airway, breathing, and circulation must be assessed and treated immediately."
        ),
        "keywords": [
            "anaphylaxis", "allergic reaction", "urticaria", "angioedema", "throat swelling",
            "difficulty breathing", "hypotension", "collapse", "systemic reaction", "flushing rash",
            "wheeze", "stridor", "tongue swelling", "facial swelling",
        ],
        "steps": [
            {
                "action": "Stop the procedure immediately and call emergency services without delay.",
                "rationale": "Anaphylaxis is a medical emergency — immediate team response and emergency transfer are required.",
                "priority": "primary",
            },
            {
                "action": "Assess airway, breathing, circulation, mental status, and oxygen saturation if available.",
                "rationale": "Rapid ABC assessment identifies life-threatening compromise and guides immediate action.",
                "priority": "primary",
            },
            {
                "action": "Administer intramuscular epinephrine promptly — outer thigh, no delay.",
                "rationale": "Epinephrine is the only first-line treatment for anaphylaxis.",
                "priority": "primary",
            },
            {
                "action": "Place the patient supine with legs elevated unless contraindicated by breathing difficulty or vomiting.",
                "rationale": "Supports circulation and reduces risk of cardiovascular collapse.",
                "priority": "secondary",
            },
            {
                "action": "Provide high-flow oxygen if available and ensure emergency transfer is underway.",
                "rationale": "Respiratory and hemodynamic deterioration can be rapid and unpredictable.",
                "priority": "primary",
            },
            {
                "action": "Repeat epinephrine if symptoms persist or worsen after 5 minutes.",
                "rationale": "Refractory or biphasic anaphylaxis may require repeated dosing.",
                "priority": "primary",
            },
            {
                "action": "Document exact times of symptom onset and each medication given for emergency handover.",
                "rationale": "Accurate timeline supports emergency team management and medicolegal record.",
                "priority": "secondary",
            },
        ],
        "dose_guidance": [
            {
                "substance": "Epinephrine (adrenaline)",
                "recommendation": "0.5 mg (0.5 mL of 1:1000) IM into the outer thigh for adults. Repeat after 5 minutes if no improvement.",
                "notes": "Use auto-injector if available. Follow local emergency protocol. Do not delay — adjuncts (antihistamines, steroids) do not replace epinephrine.",
            },
            {
                "substance": "Adjunctive medications",
                "recommendation": "Antihistamines and corticosteroids may be considered as adjuncts only, after epinephrine.",
                "notes": "Airway and hemodynamic stabilization take priority. Adjuncts do not prevent or treat anaphylaxis shock.",
            },
        ],
        "red_flags": [
            "Airway swelling or stridor",
            "Wheeze or respiratory distress",
            "Hypotension or collapse",
            "Loss of consciousness",
            "Rapid progression of urticaria with cardiovascular or respiratory involvement",
        ],
        "escalation": [
            "Call emergency services immediately — do not delay for any reason",
            "Urgent airway support if swelling or respiratory compromise is present",
            "Emergency transfer — observe for biphasic reactions even after apparent recovery",
        ],
        "monitoring": [
            "Continuous observation of airway, breathing, and circulation",
            "Repeat vital signs frequently until emergency team arrives",
            "Document exact timing of symptom onset and each intervention",
        ],
        "limitations": [
            "This tool does not replace formal emergency protocols or clinician training",
            "Follow local emergency resuscitation and anaphylaxis policy",
        ],
        "follow_up_questions": [
            "Is there airway swelling or breathing difficulty?",
            "Is the patient hypotensive or collapsed?",
            "Have emergency services been called?",
            "Was epinephrine already given?",
        ],
    },

    "botulinum_toxin_ptosis": {
        "name": "Suspected eyelid or brow ptosis after botulinum toxin treatment",
        "base_severity": "moderate",
        "base_urgency": "same_day",
        "evidence_strength": "moderate",
        "summary": (
            "This presentation is consistent with toxin diffusion-related eyelid or brow ptosis after botulinum toxin. "
            "It is usually temporary and resolves within 4 to 12 weeks as toxin effect wanes. "
            "Visual symptoms, diplopia, or atypical neurologic findings require escalation."
        ),
        "keywords": [
            "ptosis after botox", "droopy eyelid", "eyelid droop", "brow ptosis", "brow heaviness",
            "botulinum toxin complication", "levator spread", "botox ptosis", "diplopia after botox",
            "toxin ptosis",
        ],
        "steps": [
            {
                "action": "Confirm recent botulinum toxin treatment and define whether the issue is eyelid ptosis, brow ptosis, or another pattern.",
                "rationale": "Pattern recognition guides reassurance, treatment selection, and decision to escalate.",
                "priority": "primary",
            },
            {
                "action": "Assess for diplopia, visual disturbance, anisocoria, or atypical neurologic signs.",
                "rationale": "These findings may indicate an alternative diagnosis requiring urgent escalation.",
                "priority": "primary",
            },
            {
                "action": "Reassure the patient that toxin-related ptosis is temporary and expected to improve with time.",
                "rationale": "Most cases resolve within 4 to 12 weeks as the toxin effect naturally wanes.",
                "priority": "secondary",
            },
            {
                "action": "Consider apraclonidine 0.5% eye drops for symptomatic relief of confirmed eyelid ptosis if no contraindication.",
                "rationale": "Alpha-agonist activity stimulates Müller's muscle, providing mild temporary eyelid elevation.",
                "priority": "secondary",
            },
            {
                "action": "Avoid repeat injections in the affected area until full recovery is documented.",
                "rationale": "Prevents cumulative toxin effect and worsening of ptosis.",
                "priority": "primary",
            },
            {
                "action": "Document timing, injection sites, dose, and onset of symptoms.",
                "rationale": "Supports clinical review and prevention planning for future treatments.",
                "priority": "secondary",
            },
        ],
        "dose_guidance": [
            {
                "substance": "Apraclonidine 0.5% eye drops",
                "recommendation": "1 drop to the affected eye up to three times daily for temporary symptomatic relief of eyelid ptosis.",
                "notes": "Prescription required. Check contraindications including cardiovascular conditions. This is symptomatic only — ptosis resolves as the toxin effect wanes.",
            },
            {
                "substance": "General symptomatic support",
                "recommendation": "Use according to clinician judgment and local prescribing practice.",
                "notes": "Expectant management is appropriate for uncomplicated toxin-related ptosis.",
            },
        ],
        "red_flags": [
            "Diplopia or double vision",
            "Visual disturbance",
            "Atypical or progressive neurologic findings",
            "Severe visual field obstruction",
            "Progressive systemic weakness or dysphagia",
        ],
        "escalation": [
            "Urgent clinician review if diplopia, atypical neurologic symptoms, or progressive findings are present",
            "Ophthalmology review if visual field is significantly affected",
            "Urgent neurology or emergency review if systemic weakness or dysphagia develops",
        ],
        "monitoring": [
            "Review weekly or fortnightly until resolution is documented",
            "Document visual function and expected recovery discussion at each review",
            "Monitor for symptom progression and functional impact on daily activities",
        ],
        "limitations": [
            "Management depends on confirming uncomplicated toxin diffusion rather than an alternative neurologic or ophthalmic diagnosis",
            "Most cases resolve without active intervention — apraclonidine evidence is largely case-report based",
        ],
        "follow_up_questions": [
            "Is the ptosis affecting the eyelid, brow, or both?",
            "Is there diplopia or other visual change?",
            "Is vision obstructed?",
            "How many days since injection?",
        ],
    },

    "neuromodulator_resistance": {
        "name": "Neuromodulator Resistance / Treatment Failure",
        "base_severity": "moderate",
        "base_urgency": "routine",
        "evidence_strength": "moderate",
        "summary": (
            "Neuromodulator treatment failure presents as reduced duration, no clinical response, "
            "or a specific area failing to respond despite adequate dosing. Two distinct mechanisms "
            "must be differentiated: true immunological resistance (antibody-mediated neutralisation "
            "of botulinum toxin) versus pseudo-resistance — inadequate dose, incorrect placement, "
            "altered anatomy, incorrect storage or reconstitution, or patient expectation mismatch. "
            "CMAC 2025 highlighted pseudo-resistance as the more common and more actionable cause. "
            "Management differs significantly between these two categories."
        ),
        "keywords": [
            "resistance", "not working", "wearing off", "no response", "shortened duration",
            "pseudo-resistance", "toxin failure", "botox failure", "botox not working",
            "botox wearing off", "botulinum resistance", "toxin not lasting",
            "dysport resistance", "xeomin resistance", "neuromodulator failure",
        ],
        "steps": [
            {
                "action": "Classify as true resistance vs pseudo-resistance.",
                "rationale": (
                    "True resistance: complete absence of any effect across multiple areas and multiple "
                    "products. Pseudo-resistance: partial response, one area not responding, or shortened "
                    "duration only. This classification drives all subsequent management."
                ),
                "priority": "primary",
            },
            {
                "action": "Audit dose, dilution, storage, and technique.",
                "rationale": (
                    "Check: was dilution correct? Was product stored properly (2–8°C, not frozen)? "
                    "Was dose adequate for the muscle mass and patient? Was injection depth correct? "
                    "Pseudo-resistance from these factors is the most common correctable cause."
                ),
                "priority": "primary",
            },
            {
                "action": "Assess anatomical factors and patient expectations.",
                "rationale": (
                    "Strong or hypertrophic muscles (masseter, frontalis) may require higher doses. "
                    "Dynamic anatomy changes (weight loss, GLP-1 patients) may alter muscle mass. "
                    "Some patients expect paralysis; others prefer mild softening — clarify expectations."
                ),
                "priority": "primary",
            },
            {
                "action": "For pseudo-resistance: adjust dose, depth, or technique.",
                "rationale": (
                    "Increase total dose incrementally. Reassess injection points against current anatomy. "
                    "Consider electromyographic (EMG) guidance for difficult cases. "
                    "Use a different dilution volume if diffusion is needed."
                ),
                "priority": "primary",
            },
            {
                "action": "For suspected true resistance: switch to a different serotype or formulation.",
                "rationale": (
                    "Antibody-mediated resistance is typically specific to the toxin serotype and often "
                    "the specific commercial preparation. Switching from OnabotulinumtoxinA to "
                    "IncobotulinumtoxinA (Xeomin, lowest antigenic protein load) may restore response. "
                    "High-frequency repeat dosing and high-dose treatments increase immunogenicity risk."
                ),
                "priority": "primary",
            },
            {
                "action": "Consider the CMAC 2025 'reset technique' for pseudo-resistance cases.",
                "rationale": (
                    "Described at CMAC 2025: a structured rest period followed by targeted re-injection "
                    "using EMG to confirm target muscle activity, with dose recalibration. "
                    "This has shown efficacy in a select group of patients with shortened duration "
                    "who were not truly antibody-resistant."
                ),
                "priority": "secondary",
            },
        ],
        "dose_guidance": [
            {
                "substance": "OnabotulinumtoxinA (Botox/Vistabel)",
                "recommendation": "Consider dose escalation 20–30% above prior ineffective dose before switching product.",
                "notes": "Document exact dose, injection points, and dilution for each session to track response patterns.",
            },
            {
                "substance": "IncobotulinumtoxinA (Xeomin)",
                "recommendation": "Switch to Xeomin if true resistance suspected — lowest complexing protein load reduces immunogenicity.",
                "notes": "Units are approximately equivalent to OnabotulinumtoxinA; adjust dose based on clinical response.",
            },
            {
                "substance": "AbobotulinumtoxinA (Dysport)",
                "recommendation": "Alternative if switching within serotype A; unit conversion ~2.5–3:1 relative to OnabotulinumtoxinA.",
                "notes": "Higher diffusion profile may be advantageous in some anatomical regions.",
            },
        ],
        "red_flags": [
            "Complete absence of ANY effect across multiple sites and multiple products — escalate to neurology for immunological testing.",
            "Neurological symptoms emerging alongside apparent toxin failure — immediate escalation required.",
            "Systemic symptoms (dysphagia, weakness beyond injection site) — emergency assessment.",
            "Resistance emerging after years of successful treatment — document and investigate systematically.",
        ],
        "escalation": [
            "Refer to dermatology or neurology for formal resistance testing if true immunological failure is suspected.",
            "Mouse hemidiaphragm assay or cell-based neutralisation assays can confirm antibody-mediated resistance.",
            "Consider referral to specialist centre if management remains unclear after 2–3 adjusted treatment cycles.",
        ],
        "monitoring": [
            "Photograph injection points and document dose precisely at each session.",
            "Track onset (days), duration (weeks), and peak effect systematically.",
            "Use validated scales (e.g. Wrinkle Severity Rating Scale) for objective response tracking.",
            "Monitor for any systemic symptoms at each review.",
        ],
        "limitations": [
            "True immunological resistance is rare (<1–3% of patients) but underdiagnosed due to poor documentation.",
            "Pseudo-resistance likely accounts for the majority of apparent treatment failures.",
            "Formal neutralising antibody testing is not widely available in clinical practice.",
            "Evidence base for management of resistance is mostly observational.",
        ],
        "follow_up_questions": [
            "Has the patient responded normally to neuromodulators in the past?",
            "Has anything changed in storage, dilution, or administration since the last successful treatment?",
            "Is the failure global (all areas) or regional (one specific area)?",
            "What is the patient's expectation — paralysis or softening?",
        ],
    },

    "skin_necrosis_after_filler": {
        "name": "Skin Necrosis / Impending Necrosis After Filler",
        "base_severity": "critical",
        "base_urgency": "immediate",
        "evidence_strength": "moderate",
        "summary": (
            "Filler-induced skin necrosis occurs when intravascular injection or external compression "
            "compromises arterial or venous supply to the overlying skin. Early recognition of the dusky-grey "
            "colour change, reticulate mottling (livedo), and increasing pain is critical — the window for "
            "reversal with hyaluronidase is narrow. Nose, glabella, and nasolabial fold carry the highest necrosis "
            "risk. Prompt aggressive hyaluronidase flooding gives the best outcomes."
        ),
        "keywords": [
            "necrosis", "skin necrosis", "tissue necrosis", "impending necrosis",
            "skin turning black", "skin turning grey", "skin turning gray",
            "skin turning dark", "turning dark", "turning grey", "turning gray",
            "tissue death", "eschar", "dusky skin", "dusky",
            "grey skin", "gray skin", "dark grey", "dark gray",
            "skin discolouration", "skin discoloration", "skin colour change",
            "livedo reticularis", "livedo", "mottling", "mottled",
            "purple skin", "skin looks dead", "necrotic", "ischaemia skin",
            "skin ischaemia", "skin ischemia", "ischemic skin",
        ],
        "steps": [
            {"action": "Stop injection and remove needle immediately.",
             "rationale": "Prevent further filler deposition into compromised territory.", "priority": "primary"},
            {"action": "Administer hyaluronidase — flood the entire affected area generously if HA filler was used.",
             "rationale": "Dissolves intravascular or compressive filler. Do not wait for colour to worsen.", "priority": "primary"},
            {"action": "Apply warm compresses and gentle massage to promote vasodilation.",
             "rationale": "Topical warmth improves local perfusion and assists filler dispersal.", "priority": "primary"},
            {"action": "Apply topical nitroglycerine paste (2%) if available.",
             "rationale": "Vasodilatory effect may improve perfusion in the ischaemic territory.", "priority": "secondary"},
            {"action": "Administer aspirin 300 mg orally (if no contraindication).",
             "rationale": "Antiplatelet effect reduces thrombotic extension.", "priority": "secondary"},
            {"action": "Escalate immediately if visual symptoms appear — call emergency services.",
             "rationale": "Visual symptoms indicate retrograde ophthalmic territory involvement.", "priority": "primary"},
            {"action": "Document the area with photographs and contact a senior clinician.",
             "rationale": "Early specialist input improves outcomes. Full-thickness necrosis may require plastic surgery.", "priority": "secondary"},
        ],
        "dose_guidance": [
            {
                "substance": "Hyaluronidase (Hyalase)",
                "recommendation": "300–1500 IU — flood entire affected region generously. Repeat every 1–2 hours if no improvement.",
                "notes": "Use liberal volumes. Inject into, around, and beyond the visible ischaemic zone.",
            },
            {
                "substance": "Aspirin",
                "recommendation": "300 mg orally stat, then 75–150 mg daily for 5–7 days.",
                "notes": "Antiplatelet prophylaxis during recovery phase. Contraindicated with active peptic ulcer.",
            },
        ],
        "red_flags": [
            "Full-thickness eschar or blackening — requires urgent wound care and surgical review",
            "Spreading grey/dusky zone despite hyaluronidase — may indicate arterial occlusion beyond HA territory",
            "Associated visual symptoms — escalate immediately",
            "Fever or systemic signs — consider superimposed infection of necrotic tissue",
        ],
        "escalation": [
            "Refer to emergency department if visual symptoms develop at any point",
            "Plastic surgery or wound care referral for established necrosis or eschar",
            "Vascular surgery input if large ischaemic zone, non-HA filler, or persistent ischaemia",
        ],
        "monitoring": [
            "Document colour change and extent every 15–30 minutes with photos",
            "Reassess capillary refill and sensation in the affected zone",
            "Monitor for signs of infection over the following 48–72 hours",
            "Follow-up at 24 hours, 72 hours, 1 week, and 4 weeks",
        ],
        "limitations": [
            "Non-HA fillers cannot be dissolved — management is supportive only",
            "Hyaluronidase does not restore circulation directly; it removes compressive or intravascular HA",
            "Delay beyond 30–60 minutes significantly worsens prognosis",
        ],
        "follow_up_questions": [
            "What filler type and volume was used?",
            "Which region and depth was injected?",
            "How long ago did the colour change appear?",
            "Are visual symptoms present?",
        ],
    },

    "vision_change_after_filler": {
        "name": "Vision Change / Ocular Compromise After Filler",
        "base_severity": "critical",
        "base_urgency": "immediate",
        "evidence_strength": "limited",
        "summary": (
            "Filler-induced visual loss is the most catastrophic complication of aesthetic injections, "
            "occurring when filler enters the ophthalmic arterial territory via the dorsal nasal, angular, "
            "or supratrochlear arteries. Retrograde embolisation causes retinal or cerebral infarction. "
            "The window for intervention is minutes to hours. Any visual symptom after periorbital, glabellar, "
            "nasal, or temporal injection must be treated as presumptive vascular occlusion until proven otherwise."
        ),
        "keywords": [
            "vision loss", "visual loss", "blurred vision", "blindness",
            "can't see", "cant see", "cannot see", "loss of vision",
            "double vision", "diplopia", "vision change", "vision after filler",
            "ophthalmic", "retinal", "amaurosis",
            "eye complication filler", "filler blindness", "ocular complication",
            "vision blurry after filler", "seeing spots after filler",
            "lost vision", "losing vision", "went blind", "vision lost",
            "blurry after filler", "blur after filler",
            "eye after filler", "ocular after filler",
        ],
        "steps": [
            {"action": "STOP injection immediately. Call emergency services (999/112/911) without delay.",
             "rationale": "Any visual symptom after filler injection is a medical emergency.", "priority": "primary"},
            {"action": "Position patient supine — do not sit them up.",
             "rationale": "Supine position reduces IOP and may facilitate perfusion.", "priority": "primary"},
            {"action": "Administer hyaluronidase retrobulbar injection (500–1500 IU) if trained and HA filler is the likely cause.",
             "rationale": "Retrobulbar hyaluronidase has reversed some cases of filler-induced CRAO. Only attempt if formally trained.", "priority": "primary"},
            {"action": "Contact the nearest ophthalmology emergency unit directly — do not wait for ambulance triage.",
             "rationale": "Central retinal artery occlusion has a 90–120 minute intervention window.", "priority": "primary"},
            {"action": "Document time of onset, filler used, volume, region, and depth.",
             "rationale": "Critical for the ophthalmologist and medicolegal documentation.", "priority": "secondary"},
            {"action": "Monitor for any neurological symptoms — facial drooping, speech change, arm weakness.",
             "rationale": "Neurological symptoms indicate cerebral territory involvement requiring neurology input.", "priority": "primary"},
        ],
        "dose_guidance": [
            {
                "substance": "Hyaluronidase retrobulbar (if trained)",
                "recommendation": "500–1500 IU retrobulbar injection. Only if formally trained in the technique.",
                "notes": "Requires anatomy training. Contact ophthalmology before attempting. Evidence limited to case reports.",
            },
        ],
        "red_flags": [
            "Complete loss of vision in one or both eyes — highest urgency",
            "Any neurological symptoms (facial drooping, speech change, arm weakness) — cerebral involvement",
            "Pain around the orbit combined with visual change",
            "Symptoms spreading despite hyaluronidase",
        ],
        "escalation": [
            "999/112/911 — this is a medical emergency, do not delay",
            "Direct ophthalmology emergency contact",
            "Neurology input if any neurological symptoms co-exist",
            "Incident report and medicolegal documentation regardless of outcome",
        ],
        "monitoring": [
            "Continuous monitoring of visual acuity (can patient see fingers moving?)",
            "Monitor for associated neurological symptoms throughout",
            "Document all interventions with timestamps",
        ],
        "limitations": [
            "Retrobulbar hyaluronidase evidence is limited to case reports — not an established standard of care",
            "Non-HA filler visual complications have no dissolution option",
            "The window for any intervention is extremely narrow",
        ],
        "follow_up_questions": [
            "Which eye is affected — ipsilateral or contralateral to injection side?",
            "Is vision totally absent or partially reduced?",
            "Are there any associated neurological symptoms?",
            "Which region was injected and at what depth?",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Protocol matching
# ─────────────────────────────────────────────────────────────────────────────

def score_protocol(
    query: str, context: Optional[ClinicalContext], protocol: Dict[str, Any]
) -> float:
    score = 0.0
    q = normalize(query)
    ctext = joined_context_text(context)
    name = protocol["name"].lower()

    for kw in protocol["keywords"]:
        if kw in q:
            score += 1.0
        if kw in ctext:
            score += 0.5

    if not context:
        return score

    # ── Vascular occlusion signals ──────────────────────────────────
    if "vascular occlusion" in name:
        if context.visual_symptoms:
            score += 3.0
        if context.capillary_refill_delayed:
            score += 2.0
        if context.skin_color_change:
            scc = context.skin_color_change.lower()
            if scc in ("blanching", "mottling", "dusky", "violaceous"):
                score += 2.0
        if context.pain_score_10 is not None and context.pain_score_10 >= 7:
            score += 1.5
        if context.time_since_injection_minutes is not None and context.time_since_injection_minutes <= 60:
            score += 1.5

    # ── Tyndall signals ─────────────────────────────────────────────
    if "tyndall" in name and context.skin_color_change:
        scc = context.skin_color_change.lower()
        if "blue" in scc or "blue-gray" in scc:
            score += 2.0

    # ── Anaphylaxis signals ─────────────────────────────────────────
    if "anaphylaxis" in name:
        if any([context.wheeze, context.hypotension,
                context.facial_or_tongue_swelling, context.generalized_urticaria]):
            score += 3.0

    # ── Ptosis / toxin signals ──────────────────────────────────────
    if "ptosis" in name:
        if any([context.eyelid_droop, context.brow_heaviness,
                context.diplopia, context.toxin_recent]):
            score += 2.5

    # ── Infection / biofilm signals ─────────────────────────────────
    if "infection" in name:
        if any([context.fever, context.fluctuance, context.drainage]):
            score += 2.0
        if any([context.tenderness, context.warmth, context.erythema]):
            score += 1.0

    # ── Nodule signals ──────────────────────────────────────────────
    if "nodule" in name:
        if any([context.tenderness, context.warmth, context.erythema]):
            score += 1.0

    # ── HA filler confirmation ──────────────────────────────────────
    if "hyaluronic acid filler" in name or "ha filler" in name:
        if context.filler_confirmed_ha:
            score += 1.25
        if context.product_type and "hyaluronic" in context.product_type.lower():
            score += 1.0

    return score


def select_protocol(
    query: str, context: Optional[ClinicalContext]
) -> Tuple[str, Dict[str, Any], float]:
    best_key: Optional[str] = None
    best_protocol: Optional[Dict[str, Any]] = None
    best_score = -1.0

    for key, protocol in PROTOCOL_LIBRARY.items():
        s = score_protocol(query, context, protocol)
        if s > best_score:
            best_score = s
            best_key = key
            best_protocol = protocol

    if best_key is None or best_protocol is None or best_score <= 0:
        raise HTTPException(
            status_code=404,
            detail="No matching complication protocol found. Provide more specific clinical details.",
        )

    confidence = min(0.99, round(0.45 + best_score * 0.06, 2))
    return best_key, best_protocol, confidence


# ─────────────────────────────────────────────────────────────────────────────
# Risk assessment
# ─────────────────────────────────────────────────────────────────────────────

def compute_risk_assessment(
    protocol_key: str,
    protocol: Dict[str, Any],
    context: Optional[ClinicalContext],
) -> RiskAssessment:
    base_map: Dict[str, int] = {"low": 20, "moderate": 50, "high": 75, "critical": 92}
    severity: SeverityLevel = protocol["base_severity"]
    urgency: UrgencyLevel = protocol["base_urgency"]
    score = base_map[severity]

    if context:
        if protocol_key == "vascular_occlusion_ha_filler":
            if context.visual_symptoms:
                score += 8
                severity = "critical"
                urgency = "immediate"
            if context.capillary_refill_delayed:
                score += 5
            if context.pain_score_10 is not None:
                score += 4 if context.pain_score_10 >= 8 else (2 if context.pain_score_10 >= 5 else 0)

        elif protocol_key == "anaphylaxis_allergic_reaction":
            if any([context.hypotension, context.wheeze, context.facial_or_tongue_swelling]):
                score += 6
                severity = "critical"
                urgency = "immediate"
            if context.generalized_urticaria:
                score += 2

        elif protocol_key == "botulinum_toxin_ptosis":
            if context.diplopia or context.visual_symptoms:
                score += 10
                severity = "high"
                urgency = "urgent"

        elif protocol_key == "infection_or_biofilm_after_filler":
            if any([context.fever, context.fluctuance, context.drainage]):
                score += 6
                severity = "high"
                urgency = "urgent"
            if any([context.erythema, context.warmth, context.tenderness]):
                score += 3

        elif protocol_key == "filler_nodules_inflammatory_or_noninflammatory":
            if any([context.tenderness, context.warmth, context.erythema]):
                score += 3

    score = max(0, min(100, score))
    return RiskAssessment(
        risk_score=score,
        severity=severity,
        urgency=urgency,
        likely_time_critical=urgency in ("urgent", "immediate"),
        evidence_strength=protocol["evidence_strength"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_steps(protocol: Dict[str, Any]) -> List[ProtocolStep]:
    return [
        ProtocolStep(
            step_number=i + 1,
            action=s["action"],
            rationale=s["rationale"],
            priority=s.get("priority", "primary"),
        )
        for i, s in enumerate(protocol["steps"])
    ]


def _build_doses(protocol: Dict[str, Any]) -> List[DoseGuidance]:
    return [
        DoseGuidance(
            substance=d["substance"],
            recommendation=d["recommendation"],
            notes=d["notes"],
        )
        for d in protocol["dose_guidance"]
    ]


def build_response(
    request_id: str,
    protocol_key: str,
    protocol: Dict[str, Any],
    confidence: float,
    context: Optional[ClinicalContext],
    query: str,
) -> ProtocolResponse:
    evidence = evidence_retriever.retrieve(
        protocol_key=protocol_key, query=query, context=context
    )
    risk = compute_risk_assessment(protocol_key, protocol, context)
    procedure_insight = detect_procedure_insight(query, context)

    red_flags = list(protocol["red_flags"])
    escalation = list(protocol["escalation"])

    # Inject ocular escalation at the top for any visual symptom
    if context and context.visual_symptoms:
        ocular_flag = "Visual disturbance, blurred vision, diplopia, or vision loss"
        if ocular_flag not in red_flags:
            red_flags.insert(0, ocular_flag)
        ocular_esc = "Immediate ophthalmology and emergency referral for any visual symptom"
        if ocular_esc not in escalation:
            escalation.insert(0, ocular_esc)

    return ProtocolResponse(
        request_id=request_id,
        engine_version=ENGINE_VERSION,
        protocol_revision=PROTOCOL_REVISION,
        generated_at_utc=now_utc_iso(),
        matched_protocol_key=protocol_key,
        matched_protocol_name=protocol["name"],
        confidence=confidence,
        risk_assessment=risk,
        clinical_summary=protocol["summary"],
        immediate_actions=_build_steps(protocol),
        dose_guidance=_build_doses(protocol),
        procedure_insight=procedure_insight,
        red_flags=red_flags,
        escalation=escalation,
        monitoring=list(protocol["monitoring"]),
        limitations=list(protocol["limitations"]),
        follow_up_questions=list(protocol["follow_up_questions"]),
        evidence=evidence,
        disclaimer=(
            "This output is clinical decision support and not a substitute for clinician judgment. "
            "Escalate immediately for visual symptoms, airway compromise, progressive ischemia, "
            "suspected infection, systemic illness, or diagnostic uncertainty."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML print view
# ─────────────────────────────────────────────────────────────────────────────

def build_print_html(response: ProtocolResponse) -> str:
    urgency_color = {
        "immediate": "#c00",
        "urgent": "#c66000",
        "same_day": "#0066cc",
        "routine": "#007700",
    }.get(response.risk_assessment.urgency, "#333")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AesthetiCite Protocol — {html.escape(response.matched_protocol_name)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #111; line-height: 1.6; max-width: 800px; }}
h1 {{ font-size: 22px; margin-bottom: 4px; }}
h2 {{ font-size: 16px; margin-top: 24px; margin-bottom: 6px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
.meta {{ font-size: 13px; color: #444; margin-bottom: 16px; }}
.summary {{ padding: 14px; border-left: 4px solid {urgency_color}; background: #fafafa; margin: 16px 0; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; color: #fff; background: {urgency_color}; }}
.risk {{ font-size: 13px; color: #444; margin-top: 8px; }}
.disclaimer {{ font-size: 11px; color: #555; margin-top: 24px; border-top: 1px solid #ddd; padding-top: 12px; }}
ul, ol {{ margin-top: 6px; padding-left: 20px; }}
li {{ margin-bottom: 6px; }}
</style>
</head>
<body>
<h1>AesthetiCite Clinical Complication Protocol</h1>
<div class="meta">
  <strong>Protocol:</strong> {html.escape(response.matched_protocol_name)}<br>
  <strong>Request ID:</strong> {html.escape(response.request_id)}<br>
  <strong>Generated:</strong> {html.escape(response.generated_at_utc)}<br>
  <strong>Engine v{html.escape(response.engine_version)} &nbsp;|&nbsp; Revision {html.escape(response.protocol_revision)}</strong>
</div>
<div>
  <span class="badge">{html.escape(response.risk_assessment.urgency.upper())}</span>
  &nbsp;
  <span class="badge" style="background:#555">{html.escape(response.risk_assessment.severity.upper())}</span>
</div>
<div class="risk">
  Risk score: <strong>{response.risk_assessment.risk_score}/100</strong> &nbsp;|&nbsp;
  Confidence: <strong>{response.confidence}</strong> &nbsp;|&nbsp;
  Evidence: <strong>{html.escape(response.risk_assessment.evidence_strength)}</strong>
</div>
<div class="summary"><strong>Clinical Summary</strong><br>{html.escape(response.clinical_summary)}</div>
<h2>Immediate Actions</h2>{_html_steps(response.immediate_actions)}
<h2>Dose Guidance</h2>{_html_doses(response.dose_guidance)}
<h2>Red Flags</h2>{_html_list(response.red_flags)}
<h2>Escalation</h2>{_html_list(response.escalation)}
<h2>Monitoring</h2>{_html_list(response.monitoring)}
<h2>Follow-up Questions</h2>{_html_list(response.follow_up_questions)}
<h2>Limitations</h2>{_html_list(response.limitations)}
<h2>Evidence</h2>{_html_evidence(response.evidence)}
<div class="disclaimer"><strong>Disclaimer:</strong> {html.escape(response.disclaimer)}</div>
</body>
</html>""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# PDF export (reportlab)
# ─────────────────────────────────────────────────────────────────────────────

class _PDFBuilder:
    def __init__(self, path: str) -> None:
        self.path = path
        self.c = rl_canvas.Canvas(path, pagesize=A4)
        self.width, self.height = A4
        self.left = 18 * mm
        self.right = self.width - 18 * mm
        self.top = self.height - 18 * mm
        self.bottom = 18 * mm
        self.y = self.top

    def _new_page(self) -> None:
        self.c.showPage()
        self.y = self.top

    def _ensure_space(self, needed: float) -> None:
        if self.y - needed < self.bottom:
            self._new_page()

    def line(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14) -> None:
        self._ensure_space(leading)
        self.c.setFont(font, size)
        self.c.drawString(self.left, self.y, text)
        self.y -= leading

    def wrapped(
        self,
        text: str,
        font: str = "Helvetica",
        size: int = 10,
        leading: int = 14,
        bullet: Optional[str] = None,
    ) -> None:
        max_width = self.right - self.left
        self.c.setFont(font, size)
        prefix = f"{bullet} " if bullet else ""
        prefix_w = stringWidth(prefix, font, size)
        words = text.split()
        current = ""
        first = True

        def flush(s: str, is_first: bool) -> None:
            self._ensure_space(leading)
            self.c.setFont(font, size)
            if is_first and bullet:
                self.c.drawString(self.left, self.y, prefix + s)
            else:
                self.c.drawString(self.left + prefix_w, self.y, s)
            self.y -= leading

        for word in words:
            test = word if not current else f"{current} {word}"
            limit = (max_width - prefix_w) if (not first or not bullet) else (max_width - prefix_w)
            if stringWidth(test, font, size) <= limit:
                current = test
            else:
                flush(current, first)
                first = False
                current = word
        if current:
            flush(current, first)

    def section(self, title: str) -> None:
        self.y -= 4
        self.line(title, font="Helvetica-Bold", size=12, leading=16)

    def save(self) -> None:
        self.c.save()


def export_protocol_pdf(response: ProtocolResponse) -> str:
    filename = f"protocol_{response.matched_protocol_key}_{response.request_id[:8]}.pdf"
    path = os.path.join(EXPORT_DIR, filename)
    pdf = _PDFBuilder(path)

    pdf.line("AesthetiCite Clinical Protocol Export", font="Helvetica-Bold", size=16, leading=22)
    pdf.line(f"Protocol: {response.matched_protocol_name}", font="Helvetica-Bold", size=11, leading=16)
    pdf.line(f"Request ID: {response.request_id}", size=9, leading=13)
    pdf.line(f"Generated: {response.generated_at_utc}", size=9, leading=13)
    pdf.line(
        f"Engine v{response.engine_version}  |  Revision {response.protocol_revision}",
        size=9, leading=13,
    )
    pdf.line(
        f"Risk Score: {response.risk_assessment.risk_score}/100  |  "
        f"Severity: {response.risk_assessment.severity.upper()}  |  "
        f"Urgency: {response.risk_assessment.urgency.upper()}  |  "
        f"Confidence: {response.confidence}",
        size=9, leading=15,
    )

    pdf.section("Clinical Summary")
    pdf.wrapped(response.clinical_summary)

    if response.procedure_insight:
        pi = response.procedure_insight
        pdf.section("Procedure Intelligence")
        pdf.wrapped(f"Procedure: {pi.procedure_name}", font="Helvetica-Bold")
        if pi.likely_plane:
            pdf.wrapped(f"Placement plane: {pi.likely_plane}")
        if pi.key_danger_zones:
            pdf.wrapped("Key danger zones:", font="Helvetica-Bold")
            for z in pi.key_danger_zones:
                pdf.wrapped(z, bullet="•")
        if pi.technique_notes:
            pdf.wrapped("Technique notes:", font="Helvetica-Bold")
            for n in pi.technique_notes:
                pdf.wrapped(n, bullet="•")
        if pi.common_products_or_classes:
            pdf.wrapped("Common products: " + ", ".join(pi.common_products_or_classes))

    pdf.section("Immediate Actions")
    for step in response.immediate_actions:
        pdf.wrapped(f"Step {step.step_number}: {step.action}", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(f"Rationale: {step.rationale}", bullet=" ")

    pdf.section("Dose Guidance")
    if response.dose_guidance:
        for d in response.dose_guidance:
            pdf.wrapped(f"{d.substance}: {d.recommendation}", font="Helvetica-Bold", bullet="•")
            pdf.wrapped(f"Notes: {d.notes}", bullet=" ")
    else:
        pdf.wrapped("No dose guidance available.", bullet="•")

    pdf.section("Red Flags")
    for item in response.red_flags:
        pdf.wrapped(item, bullet="•")

    pdf.section("Escalation")
    for item in response.escalation:
        pdf.wrapped(item, bullet="•")

    pdf.section("Monitoring")
    for item in response.monitoring:
        pdf.wrapped(item, bullet="•")

    pdf.section("Follow-up Questions")
    for item in response.follow_up_questions:
        pdf.wrapped(item, bullet="•")

    pdf.section("Limitations")
    for item in response.limitations:
        pdf.wrapped(item, bullet="•")

    pdf.section("Evidence")
    if response.evidence:
        for e in response.evidence:
            pdf.wrapped(f"[{e.source_id}] {e.title}", font="Helvetica-Bold", bullet="•")
            pdf.wrapped(e.note, bullet=" ")
            if e.citation_text:
                pdf.wrapped(f'Citation: "{e.citation_text}"', bullet=" ")
    else:
        pdf.wrapped("No evidence retrieved.", bullet="•")

    pdf.section("Disclaimer")
    pdf.wrapped(response.disclaimer)

    pdf.save()
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Audit and feedback logging
# ─────────────────────────────────────────────────────────────────────────────

def _log_protocol_request(payload: ProtocolRequest, response: ProtocolResponse) -> None:
    safe_write_jsonl(AUDIT_LOG_PATH, {
        "event_type": "protocol_generated",
        "logged_at_utc": now_utc_iso(),
        "request_id": response.request_id,
        "clinician_id": payload.clinician_id,
        "clinic_id": payload.clinic_id,
        "mode": payload.mode,
        "query": payload.query,
        "context": payload.context.model_dump() if payload.context else None,
        "matched_protocol_key": response.matched_protocol_key,
        "matched_protocol_name": response.matched_protocol_name,
        "confidence": response.confidence,
        "risk_score": response.risk_assessment.risk_score,
        "severity": response.risk_assessment.severity,
        "urgency": response.risk_assessment.urgency,
        "engine_version": response.engine_version,
    })


def _log_feedback(payload: FeedbackRequest) -> None:
    safe_write_jsonl(FEEDBACK_LOG_PATH, {
        "event_type": "protocol_feedback",
        "logged_at_utc": now_utc_iso(),
        "request_id": payload.request_id,
        "clinician_id": payload.clinician_id,
        "clinic_id": payload.clinic_id,
        "rating": payload.rating,
        "was_useful": payload.was_useful,
        "comment": payload.comment,
        "selected_protocol_key": payload.selected_protocol_key,
    })


# ─────────────────────────────────────────────────────────────────────────────
# API endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/protocols", summary="List all available complication protocols")
def list_protocols() -> List[Dict[str, Any]]:
    return [
        {
            "key": key,
            "name": p["name"],
            "severity": p["base_severity"],
            "urgency": p["base_urgency"],
            "evidence_strength": p["evidence_strength"],
            "keyword_count": len(p["keywords"]),
        }
        for key, p in PROTOCOL_LIBRARY.items()
    ]


@router.post("/protocol", response_model=ProtocolResponse, summary="Generate structured complication protocol + evidence")
def generate_protocol(payload: ProtocolRequest) -> ProtocolResponse:
    request_id = str(uuid.uuid4())
    protocol_key, protocol, confidence = select_protocol(payload.query, payload.context)
    response = build_response(
        request_id=request_id,
        protocol_key=protocol_key,
        protocol=protocol,
        confidence=confidence,
        context=payload.context,
        query=payload.query,
    )
    _log_protocol_request(payload, response)
    return response


@router.post("/print-view", response_model=PrintViewResponse, summary="Generate print-ready HTML protocol")
def generate_print_view(payload: ProtocolRequest) -> PrintViewResponse:
    request_id = str(uuid.uuid4())
    protocol_key, protocol, confidence = select_protocol(payload.query, payload.context)
    response = build_response(
        request_id=request_id,
        protocol_key=protocol_key,
        protocol=protocol,
        confidence=confidence,
        context=payload.context,
        query=payload.query,
    )
    _log_protocol_request(payload, response)
    return PrintViewResponse(request_id=request_id, html=build_print_html(response))


@router.post("/export-pdf", summary="Generate protocol + evidence PDF export")
def generate_pdf_export(payload: ProtocolRequest):
    request_id = str(uuid.uuid4())
    protocol_key, protocol, confidence = select_protocol(payload.query, payload.context)
    response = build_response(
        request_id=request_id,
        protocol_key=protocol_key,
        protocol=protocol,
        confidence=confidence,
        context=payload.context,
        query=payload.query,
    )
    _log_protocol_request(payload, response)
    pdf_path = export_protocol_pdf(response)
    return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))


@router.post("/feedback", response_model=FeedbackResponse, summary="Submit clinician feedback on a protocol")
def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    _log_feedback(payload)
    return FeedbackResponse(status="ok", request_id=payload.request_id)


@router.post("/log-case", response_model=LogCaseResponse, summary="Log a complication case for dataset building")
def log_case(payload: LogCaseRequest) -> LogCaseResponse:
    if payload.protocol_key not in PROTOCOL_LIBRARY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown protocol key: {payload.protocol_key!r}. "
                   f"Valid keys: {list(PROTOCOL_LIBRARY.keys())}",
        )
    case_id = str(uuid.uuid4())
    logged_at = now_utc_iso()
    with _case_db_lock:
        conn = _get_case_conn()
        conn.execute(
            """INSERT INTO logged_cases
               (case_id, logged_at_utc, clinic_id, clinician_id, protocol_key,
                region, procedure, product_type, symptoms, outcome)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                case_id, logged_at,
                payload.clinic_id, payload.clinician_id, payload.protocol_key,
                payload.region, payload.procedure, payload.product_type,
                json.dumps(payload.symptoms) if payload.symptoms else None,
                payload.outcome,
            ),
        )
        conn.commit()
        conn.close()
    safe_write_jsonl(AUDIT_LOG_PATH, {
        "event_type": "case_logged",
        "logged_at_utc": logged_at,
        "case_id": case_id,
        "clinic_id": payload.clinic_id,
        "clinician_id": payload.clinician_id,
        "protocol_key": payload.protocol_key,
        "region": payload.region,
        "procedure": payload.procedure,
        "outcome": payload.outcome,
    })
    return LogCaseResponse(status="ok", case_id=case_id)


@router.get("/stats", response_model=DatasetStatsResponse, summary="Case dataset statistics")
def dataset_stats() -> DatasetStatsResponse:
    with _case_db_lock:
        conn = _get_case_conn()
        total = conn.execute("SELECT COUNT(*) FROM logged_cases").fetchone()[0]
        by_protocol = dict(conn.execute(
            "SELECT protocol_key, COUNT(*) FROM logged_cases WHERE protocol_key IS NOT NULL GROUP BY protocol_key"
        ).fetchall())
        by_region = dict(conn.execute(
            "SELECT region, COUNT(*) FROM logged_cases WHERE region IS NOT NULL GROUP BY region"
        ).fetchall())
        by_procedure = dict(conn.execute(
            "SELECT procedure, COUNT(*) FROM logged_cases WHERE procedure IS NOT NULL GROUP BY procedure"
        ).fetchall())
        conn.close()
    return DatasetStatsResponse(
        total_cases=total,
        by_protocol=by_protocol,
        by_region=by_region,
        by_procedure=by_procedure,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Programmatic helper (callable from other Python modules)
# ─────────────────────────────────────────────────────────────────────────────

def run_complication_engine(
    query: str, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Call the engine directly from Python without going through HTTP."""
    ctx = ClinicalContext(**context) if context else None
    request_id = str(uuid.uuid4())
    protocol_key, protocol, confidence = select_protocol(query, ctx)
    response = build_response(
        request_id=request_id,
        protocol_key=protocol_key,
        protocol=protocol,
        confidence=confidence,
        context=ctx,
        query=query,
    )
    return response.model_dump()


# ══════════════════════════════════════════════════════════════════════════════
#  Pre-Scan Briefing Endpoint  POST /api/complications/prescan-briefing
#  Structured ultrasound checklist before injection in a given region.
#  Based on RSNA 2025, Journal of Cosmetic Dermatology 2025, CMAC 2025.
# ══════════════════════════════════════════════════════════════════════════════

PRESCAN_BRIEFINGS: Dict[str, Dict[str, Any]] = {
    "nose": {
        "label": "Nose / Nasal Dorsum",
        "risk_level": "very_high",
        "structures_to_identify": [
            "Dorsal nasal artery (runs along nasal dorsum — identify and avoid)",
            "Angular artery (at alar base — communicates with ophthalmic territory)",
            "Lateral nasal artery (branches off facial artery near alar groove)",
            "Columellar artery (runs along columella — thin skin, easily compressed)",
            "Existing filler (check for residual product from previous treatments)",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). B-mode + colour Doppler. Low wall filter for small vessels.",
        "key_findings_to_document": [
            "Location and course of dorsal nasal artery relative to planned injection point",
            "Any pre-existing filler material (hyperechoic zones)",
            "Skin thickness at planned injection site",
            "Vascular anomalies or unusual anatomy",
        ],
        "safe_windows": [
            "Supraperiosteal plane along nasal dorsum (deep to angular artery territory)",
            "Avoid superficial subcutaneous plane entirely in this region",
        ],
        "abort_criteria": [
            "Vessel directly in needle path with no safe deviation",
            "Existing filler within same tissue plane and unclear residual volume",
            "Patient cannot remain still during scan",
        ],
        "evidence_note": "RSNA 2025: 35% of nasal filler complications showed absent major vessel flow on ultrasound. Nasal vessels communicate with ophthalmic territory — vision loss risk.",
    },
    "temple": {
        "label": "Temple / Temporal Hollow",
        "risk_level": "high",
        "structures_to_identify": [
            "Superficial temporal artery and vein (palpable, runs within temporoparietal fascia)",
            "Middle temporal vein (deep to temporoparietal fascia, crosses injection zone)",
            "Zygomaticoorbital artery (branch of superficial temporal, periorbital area)",
            "Deep temporal arteries (below temporalis fascia — confirm injection plane is above)",
            "Existing filler deposits if repeat treatment",
        ],
        "doppler_settings": "High-frequency transducer (12–18 MHz). B-mode to identify filler/fat layer. Colour Doppler for vessel mapping.",
        "key_findings_to_document": [
            "Course of superficial temporal artery — mark on skin before injection",
            "Depth of preferred injection plane (deep to temporalis fascia for filler)",
            "Any vascular anomalies in the temporal hollow",
        ],
        "safe_windows": [
            "Deep subfascial plane (below superficial layer of deep temporal fascia) — below main vessel territory",
            "Periosteal plane over temporal bone — safest for structural filler",
        ],
        "abort_criteria": [
            "Superficial temporal artery crossing planned injection path without safe detour",
            "Extremely thin temporal fat pad with no identifiable safe plane",
        ],
        "evidence_note": "Temporal hollow filler carries significant risk of intravascular injection — STA is palpable in many patients but its exact course requires ultrasound confirmation.",
    },
    "forehead": {
        "label": "Forehead / Frontal",
        "risk_level": "high",
        "structures_to_identify": [
            "Supratrochlear artery (medial forehead — emerges above supraorbital rim)",
            "Supraorbital artery (lateral to supratrochlear — both supply forehead skin)",
            "Sentinel vein / zygomaticotemporal vein (lateral forehead — surgical landmark)",
            "Frontal branch of facial nerve (risk with deep injections laterally)",
            "Existing filler if repeat treatment",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). Colour Doppler to identify medial forehead vessels at supraorbital level.",
        "key_findings_to_document": [
            "Supratrochlear artery exit point from supraorbital foramen — mark before injection",
            "Supraorbital artery course across central forehead",
            "Planned injection plane relative to these vessels (periosteal preferred for filler)",
        ],
        "safe_windows": [
            "Deep periosteal plane — below the subgaleal plane, avoids main vessel territory",
            "Lateral forehead above brow: inject in midforehead away from medial vessel territory",
        ],
        "abort_criteria": [
            "Supratrochlear or supraorbital artery directly within planned injection path",
            "Existing large filler deposits altering anatomy",
        ],
        "evidence_note": "Supratrochlear and supraorbital vessels communicate with central retinal artery. Ischaemic complications in forehead can be vision-threatening.",
    },
    "tear trough": {
        "label": "Tear Trough / Periorbital",
        "risk_level": "high",
        "structures_to_identify": [
            "Infraorbital artery and vein (exits infraorbital foramen — map precisely)",
            "Angular artery (medial canthus — connects with ophthalmic territory)",
            "Orbicularis oculi muscle (identify correct injection plane relative to muscle)",
            "Periosteum (supraperiosteal plane is safest for deep filler placement)",
            "Existing filler material (common site for product accumulation over years)",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). Gentle pressure only — avoid compressing periorbital vessels. Colour Doppler for angular and infraorbital vessels.",
        "key_findings_to_document": [
            "Location of infraorbital foramen relative to planned injection vector",
            "Presence and volume of any residual filler from previous treatments",
            "Tissue plane: identify suborbicularis vs periosteal space",
            "Angular artery course at medial canthus",
        ],
        "safe_windows": [
            "Supraperiosteal plane lateral to infraorbital foramen — safest anatomical window",
            "Deep suborbicularis plane — avoids superficial Tyndall risk",
        ],
        "abort_criteria": [
            "Large volume of residual filler from previous treatments — defer until partially dissolved",
            "Infraorbital foramen directly in planned injection path",
            "Any patient-reported visual symptoms prior to treatment",
        ],
        "evidence_note": "Periorbital region carries Tyndall risk with superficial HA and vascular occlusion risk from angular artery proximity to ophthalmic territory.",
    },
    "glabella": {
        "label": "Glabella / Frown Lines",
        "risk_level": "very_high",
        "structures_to_identify": [
            "Supratrochlear artery (medial — immediately adjacent to corrugator injection sites)",
            "Supraorbital artery (lateral — both communicate with ophthalmic/retinal territory)",
            "Procerus muscle (identify depth and borders)",
            "Corrugator supercilii muscle (key toxin target — identify precisely)",
            "Any existing filler from previous treatments (HA only acceptable here)",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). Colour Doppler essential. Identify both supratrochlear vessels bilaterally before injection.",
        "key_findings_to_document": [
            "Exact location of bilateral supratrochlear arteries — mark on skin",
            "Depth of supratrochlear arteries relative to corrugator muscle",
            "Any pre-existing filler (filler in glabella is high-risk — consider dissolving first)",
        ],
        "safe_windows": [
            "Intramuscular plane of procerus/corrugator — for toxin only",
            "No safe plane for filler in central glabella — HA only and with extreme caution",
        ],
        "abort_criteria": [
            "For filler: any non-HA product planned — abort (non-reversible in this territory)",
            "Supratrochlear artery coursing through planned injection point",
            "Existing filler in glabella — dissolve first if any uncertainty about residual volume",
            "Junior or intermediate injector without senior supervision — this is a senior-only zone",
        ],
        "evidence_note": "Glabella has the highest documented rate of vision loss from filler-related vascular complications. Supratrochlear vessels directly communicate with retinal circulation.",
    },
    "nasolabial fold": {
        "label": "Nasolabial Fold",
        "risk_level": "moderate",
        "structures_to_identify": [
            "Facial artery (courses medially — confirm position varies between patients)",
            "Angular artery (superior NLF — often medial to fold, variable anatomy)",
            "Superior labial artery (at inferior NLF — enters lip territory)",
            "Infraorbital neurovascular bundle (superior NLF territory)",
        ],
        "doppler_settings": "High-frequency transducer (12–18 MHz). Colour Doppler to trace facial artery course along the NLF before injection.",
        "key_findings_to_document": [
            "Course of facial artery relative to NLF — medial, within, or lateral to fold",
            "Any vessel directly in planned injection path at mid-NLF level",
        ],
        "safe_windows": [
            "Subcutaneous plane lateral to facial artery — if artery can be mapped medially",
            "Dermal/subdermal plane for superficial correction with low volume",
        ],
        "abort_criteria": [
            "Facial artery running directly within planned injection path without safe lateral window",
        ],
        "evidence_note": "NLF facial artery course is highly variable — in some patients it runs within or immediately medial to the fold, creating significant occlusion risk.",
    },
}


class PreScanBriefingRequest(BaseModel):
    region: str = Field(..., min_length=2, description="Anatomical region for injection")
    procedure: Optional[str] = None
    injector_experience_level: Optional[str] = None
    has_ultrasound: bool = True


class PreScanBriefingResponse(BaseModel):
    request_id: str
    generated_at_utc: str
    region_label: str
    risk_level: str
    structures_to_identify: List[str]
    doppler_settings: str
    key_findings_to_document: List[str]
    safe_windows: List[str]
    abort_criteria: List[str]
    evidence_note: str
    disclaimer: str
    junior_note: Optional[str] = None


def _match_prescan_region(region: str) -> Optional[Dict[str, Any]]:
    r = region.lower().strip()
    for key, data in PRESCAN_BRIEFINGS.items():
        if key in r:
            return data
    if any(x in r for x in ["nose", "nasal", "dorsum", "rhinoplasty"]):
        return PRESCAN_BRIEFINGS["nose"]
    if any(x in r for x in ["temple", "temporal", "hollow"]):
        return PRESCAN_BRIEFINGS["temple"]
    if any(x in r for x in ["forehead", "frontal", "brow"]):
        return PRESCAN_BRIEFINGS["forehead"]
    if any(x in r for x in ["tear", "trough", "periorbital", "infraorbital", "under eye"]):
        return PRESCAN_BRIEFINGS["tear trough"]
    if any(x in r for x in ["glabella", "frown", "procerus", "corrugator"]):
        return PRESCAN_BRIEFINGS["glabella"]
    if any(x in r for x in ["nasolabial", "nlf", "smile line"]):
        return PRESCAN_BRIEFINGS["nasolabial fold"]
    return None


@router.post("/prescan-briefing", response_model=PreScanBriefingResponse, summary="Pre-scan ultrasound checklist before injection")
def prescan_briefing(payload: PreScanBriefingRequest) -> PreScanBriefingResponse:
    """
    POST /api/complications/prescan-briefing
    Returns a structured pre-scan checklist for ultrasound-guided injection.
    Based on RSNA 2025, Journal of Cosmetic Dermatology 2025, CMAC 2025.
    """
    data = _match_prescan_region(payload.region)
    if not data:
        data = {
            "label": payload.region.title(),
            "risk_level": "moderate",
            "structures_to_identify": [
                "Local arterial supply — identify named vessels for this region before injection",
                "Venous anatomy — map superficial and deep veins",
                "Any existing filler deposits from previous treatments",
                "Tissue planes — confirm depth of planned injection relative to identified structures",
            ],
            "doppler_settings": "High-frequency transducer (12–22 MHz depending on depth). B-mode + colour Doppler. Adjust gain to visualise small vessels.",
            "key_findings_to_document": [
                "Named vessels identified and their position relative to planned injection site",
                "Any pre-existing filler present",
                "Skin and subcutaneous tissue thickness",
            ],
            "safe_windows": ["Confirm injection plane is away from identified vessels"],
            "abort_criteria": ["Named vessel directly in needle path with no deviation possible"],
            "evidence_note": "Ultrasound guidance significantly reduces vascular complication rates across all injectable aesthetic procedures.",
        }
    junior_note = None
    if payload.injector_experience_level in ("junior", "intermediate"):
        junior_note = (
            "Junior/intermediate injector note: this region benefits from senior supervision "
            "when ultrasound is used for the first time. Ensure you have completed structured "
            "ultrasound training (e.g. AIA Ultrasound Fundamentals) before relying on real-time "
            "guidance for vascular avoidance in high-risk zones."
        )
    return PreScanBriefingResponse(
        request_id=str(uuid.uuid4()),
        generated_at_utc=now_utc_iso(),
        region_label=data["label"],
        risk_level=data["risk_level"],
        structures_to_identify=data["structures_to_identify"],
        doppler_settings=data["doppler_settings"],
        key_findings_to_document=data["key_findings_to_document"],
        safe_windows=data["safe_windows"],
        abort_criteria=data["abort_criteria"],
        evidence_note=data["evidence_note"],
        disclaimer=(
            "This pre-scan briefing is clinical decision support only. "
            "It does not replace formal ultrasound training, anatomical expertise, or clinical judgement. "
            "Ultrasound interpretation must be performed by a trained clinician."
        ),
        junior_note=junior_note,
    )
