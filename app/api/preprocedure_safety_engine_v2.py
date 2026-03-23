"""
AesthetiCite — Unified Pre-Procedure Safety Engine v2.1.0
=========================================================
Key upgrades over v1.0.0
------------------------
1. Preserves current API contract (legacy aliases for /api/safety/preprocedure-check)
2. Batch endpoint for Session Safety Report
3. Workspace bootstrap endpoint for unified Safety Workspace UI
4. Paper digest caching (6 h TTL) to avoid repeated slow PubMed calls
5. Real dashboard query logging with response-time tracking
6. Safer SQLite handling with context managers
7. Expanded drug interaction rules (10 rule classes)
8. Complication protocols embedded (6 protocols)
9. Onboarding hints per procedure
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

router = APIRouter(tags=["AesthetiCite Safety Engine v2"])

ENGINE_VERSION = "2.2.0"
KNOWLEDGE_REVISION = "2026-03-19"
EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
DB_PATH = os.environ.get("AESTHETICITE_GROWTH_DB", "aestheticite_growth.db")
os.makedirs(EXPORT_DIR, exist_ok=True)

RiskLevel = Literal["low", "moderate", "high", "very_high"]
DecisionLevel = Literal["go", "caution", "high_risk"]

PAPER_CACHE_TTL_SECONDS = int(os.environ.get("AESTHETICITE_PAPER_CACHE_TTL", "21600"))
_paper_cache_lock = threading.Lock()
_paper_cache: Dict[str, Dict[str, Any]] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def new_id() -> str:
    return str(uuid.uuid4())

def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def risk_level_from_score(score: int) -> RiskLevel:
    if score >= 75: return "very_high"
    if score >= 55: return "high"
    if score >= 35: return "moderate"
    return "low"

def decision_from_score(score: int) -> DecisionLevel:
    if score >= 70: return "high_risk"
    if score >= 45: return "caution"
    return "go"

def safe_filename(prefix: str, request_id: str) -> str:
    return f"{prefix}_{request_id}.pdf"


# ──────────────────────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_cursor():
    conn = get_db()
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    finally:
        conn.close()

def init_db() -> None:
    with db_cursor() as (_, cur):
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS safety_cases (
                id TEXT PRIMARY KEY,
                clinic_id TEXT,
                clinician_id TEXT,
                procedure TEXT,
                region TEXT,
                product_type TEXT,
                technique TEXT,
                decision TEXT,
                risk_score INTEGER,
                patient_factors_json TEXT,
                outcome TEXT,
                notes TEXT,
                created_at_utc TEXT
            );
            CREATE TABLE IF NOT EXISTS query_logs (
                id TEXT PRIMARY KEY,
                clinic_id TEXT,
                clinician_id TEXT,
                query_text TEXT,
                answer_type TEXT,
                aci_score REAL,
                response_time_ms REAL,
                evidence_level TEXT,
                created_at_utc TEXT
            );
        """)

init_db()


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class PatientFactors(BaseModel):
    prior_filler_in_same_area: Optional[bool] = None
    prior_vascular_event: Optional[bool] = None
    autoimmune_history: Optional[bool] = None
    allergy_history: Optional[bool] = None
    active_infection_near_site: Optional[bool] = None
    anticoagulation: Optional[bool] = None
    vascular_disease: Optional[bool] = None
    smoking: Optional[bool] = None
    nsaid_use: Optional[bool] = None
    ssri_use: Optional[bool] = None
    pregnancy: Optional[bool] = None
    immunosuppression: Optional[bool] = None
    glp1_patient: Optional[bool] = None


class PreProcedureRequest(BaseModel):
    procedure: str = Field(..., min_length=2)
    region: str = Field(..., min_length=2)
    product_type: str = Field(..., min_length=2)
    technique: Optional[str] = None
    injector_experience_level: Optional[Literal["junior", "intermediate", "senior"]] = None
    patient_factors: Optional[PatientFactors] = None
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    log_to_dashboard: bool = True


class BatchPreProcedureRequest(BaseModel):
    items: List[PreProcedureRequest] = Field(default_factory=list, min_length=1, max_length=50)


class EvidenceItem(BaseModel):
    source_id: str
    title: str
    note: str
    citation_text: Optional[str] = None
    source_type: Optional[str] = None
    relevance_score: Optional[float] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None


class RiskItem(BaseModel):
    complication: str
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    why_it_matters: str


class SafetyAssessment(BaseModel):
    overall_risk_score: int = Field(..., ge=0, le=100)
    overall_risk_level: RiskLevel
    decision: DecisionLevel
    rationale: str


class ProcedureInsight(BaseModel):
    procedure_name: str
    region: str
    likely_plane_or_target: Optional[str] = None
    danger_zones: List[str] = Field(default_factory=list)
    technical_notes: List[str] = Field(default_factory=list)
    ultrasound_recommended: bool = False
    ultrasound_note: Optional[str] = None


# ─── Ultrasound flag logic (RSNA 2025 / CMAC 2025) ───────────────────────────

ULTRASOUND_RECOMMENDED_REGIONS: set = {
    "nose", "nasal", "nasal tip", "nasal bridge", "dorsum",
    "temple", "temporal",
    "forehead", "frontal",
    "tear trough", "infraorbital", "periorbital",
    "glabella",
}

ULTRASOUND_NOTES: Dict[str, str] = {
    "nose": (
        "Nasal vasculature communicates with the ophthalmic territory via the dorsal nasal "
        "and angular arteries. RSNA 2025 data: 35% of nasal filler-related adverse events "
        "showed absent major vessel flow. Ultrasound with Doppler strongly advised before "
        "injection to confirm vessel positions in this high-risk zone."
    ),
    "temple": (
        "The superficial temporal artery is highly variable and palpable in most patients. "
        "Ultrasound with Doppler enables real-time vessel mapping and avoidance of direct "
        "arterial injection. Recommended before any filler in the temporal hollow."
    ),
    "forehead": (
        "Supratrochlear and supraorbital arteries carry intracranial connections. "
        "Ultrasound guidance for deep periosteal filler placement in the forehead significantly "
        "reduces risk of inadvertent arterial injection."
    ),
    "tear trough": (
        "The periorbital vasculature is delicate and patient-variable. "
        "Ultrasound can identify the infraorbital foramen and periorbital vascular structures "
        "to guide safe, deep filler placement and avoid superficial deposition (Tyndall risk)."
    ),
    "glabella": (
        "The glabellar region is among the highest-risk zones for filler-related vascular "
        "complications and vision loss. Ultrasound is advisable for any filler in this region "
        "to identify the supratrochlear and supraorbital vessels."
    ),
}


def get_ultrasound_flag(region: str) -> Tuple[bool, Optional[str]]:
    """Return (recommended: bool, note: Optional[str]) for a given region string."""
    r = region.lower().strip()
    for key in ULTRASOUND_RECOMMENDED_REGIONS:
        if key in r:
            note = next((v for k, v in ULTRASOUND_NOTES.items() if k in r), None)
            return True, note
    return False, None


class OnboardingHint(BaseModel):
    procedure: str
    what_this_checks: str
    key_fields_to_fill: List[str]
    clinical_tip: str


class PreProcedureResponse(BaseModel):
    request_id: str
    generated_at_utc: str
    engine_version: str
    knowledge_revision: str
    safety_assessment: SafetyAssessment
    top_risks: List[RiskItem]
    procedure_insight: ProcedureInsight
    mitigation_steps: List[str]
    caution_flags: List[str]
    evidence: List[EvidenceItem]
    onboarding_hint: Optional[OnboardingHint] = None
    related_papers: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str


class BatchPreProcedureResponse(BaseModel):
    batch_id: str
    generated_at_utc: str
    engine_version: str
    total: int
    items: List[PreProcedureResponse]
    summary: Dict[str, Any]


class ExportPDFResponse(BaseModel):
    request_id: str
    filename: str
    pdf_path: str


class CaseLogRequest(BaseModel):
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    procedure: str
    region: str
    product_type: Optional[str] = None
    technique: Optional[str] = None
    decision: Optional[str] = None
    risk_score: Optional[int] = None
    patient_factors: Optional[PatientFactors] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


class CaseLogResponse(BaseModel):
    status: str
    case_id: str


class DrugCheckRequest(BaseModel):
    medications: List[str]
    planned_products: List[str] = Field(default_factory=list)


class DrugInteractionItem(BaseModel):
    medication: str
    product_or_context: str
    severity: Literal["high", "moderate", "low"]
    explanation: str
    action: str


class DrugCheckResponse(BaseModel):
    interactions: List[DrugInteractionItem]
    summary: str
    proceed_with_caution: bool


class ComplicationProtocolRequest(BaseModel):
    query: str
    region: Optional[str] = None
    product_type: Optional[str] = None
    time_since_injection_minutes: Optional[int] = None
    visual_symptoms: Optional[bool] = None
    skin_color_change: Optional[str] = None
    pain_score: Optional[int] = None
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None


class ProtocolStep(BaseModel):
    step_number: int
    action: str
    rationale: str
    priority: str = "primary"


class DoseGuidance(BaseModel):
    substance: str
    recommendation: str
    notes: str


class ComplicationProtocolResponse(BaseModel):
    request_id: str
    generated_at_utc: str
    engine_version: str
    matched_protocol_key: str
    matched_protocol_name: str
    confidence: float
    risk_score: int
    severity: str
    urgency: str
    clinical_summary: str
    immediate_actions: List[ProtocolStep]
    dose_guidance: List[DoseGuidance]
    red_flags: List[str]
    escalation: List[str]
    monitoring: List[str]
    follow_up_questions: List[str]
    limitations: List[str]
    evidence: List[EvidenceItem]
    disclaimer: str


class WorkspaceBootstrapResponse(BaseModel):
    engine_version: str
    knowledge_revision: str
    default_session_title: str
    supported_experience_levels: List[str]
    available_protocol_count: int
    ui_labels: Dict[str, str]
    feature_flags: Dict[str, bool]


# ──────────────────────────────────────────────────────────────────────────────
# Curated evidence library
# ──────────────────────────────────────────────────────────────────────────────

CURATED_EVIDENCE: Dict[str, List[EvidenceItem]] = {
    "vascular": [
        EvidenceItem(
            source_id="S1",
            title="Expert consensus on vascular occlusion after HA filler",
            note="Rapid recognition and access to hyaluronidase are central to HA filler safety. High-dose pulsed hyaluronidase is the primary reversible intervention.",
            citation_text="Rapid recognition and access to hyaluronidase are central to HA filler safety.",
            source_type="consensus_review",
            relevance_score=0.96,
            journal="Journal of Cosmetic Dermatology",
            year=2023,
        )
    ],
    "necrosis": [
        EvidenceItem(
            source_id="S2",
            title="Skin necrosis following aesthetic filler: prevention and management",
            note="Vascular compromise untreated within the first hour significantly increases risk of irreversible tissue injury.",
            source_type="review",
            relevance_score=0.93,
            journal="Aesthetic Surgery Journal",
            year=2022,
        )
    ],
    "vision_loss": [
        EvidenceItem(
            source_id="S3",
            title="Vision loss after filler injection — case series and prevention",
            note="Ophthalmic artery occlusion after aesthetic filler carries risk of permanent vision loss. Any visual symptom requires emergency escalation.",
            citation_text="Visual symptoms after filler require immediate emergency escalation without exception.",
            source_type="case_series",
            relevance_score=0.99,
            journal="Aesthetic Surgery Journal",
            year=2023,
        )
    ],
    "tear_trough": [
        EvidenceItem(
            source_id="S20",
            title="Superficial HA filler placement and Tyndall effect in the tear trough",
            note="Superficial HA placement in the tear trough may produce blue-gray discoloration (Tyndall effect). Conservative volume and appropriate depth reduce this risk.",
            citation_text="Superficial HA placement in the tear trough may produce blue-gray discoloration.",
            source_type="review",
            relevance_score=0.90,
            journal="Journal of Cosmetic Dermatology",
            year=2022,
        )
    ],
    "lip": [
        EvidenceItem(
            source_id="S10",
            title="Vascular complications in lip augmentation — review and management",
            note="Labial vascular territory requires careful injection planning. Slow injection and small aliquots reduce risk significantly.",
            source_type="review",
            relevance_score=0.88,
            journal="Journal of Cosmetic Dermatology",
            year=2023,
        )
    ],
    "glabella": [
        EvidenceItem(
            source_id="S15",
            title="Glabellar filler safety: anatomical risk and clinical guidelines",
            note="The glabellar region carries disproportionately high risk of vascular occlusion due to vessel density and anastomoses with ophthalmic territory.",
            citation_text="Glabellar filler is associated with one of the highest rates of vision-threatening vascular events.",
            source_type="consensus_review",
            relevance_score=0.95,
            journal="Aesthetic Surgery Journal",
            year=2022,
        )
    ],
    "toxin": [
        EvidenceItem(
            source_id="S30",
            title="Botulinum toxin adverse effects and ptosis management",
            note="Ptosis after botulinum toxin is usually related to diffusion and is temporary, resolving in 4–12 weeks. Apraclonidine drops provide symptomatic relief.",
            citation_text="Ptosis after botulinum toxin is usually related to diffusion and is often temporary.",
            source_type="review",
            relevance_score=0.91,
            journal="Journal of Cosmetic Dermatology",
            year=2023,
        )
    ],
    "anaphylaxis": [
        EvidenceItem(
            source_id="S40",
            title="Management of anaphylaxis in aesthetic practice",
            note="Epinephrine is the only first-line treatment for anaphylaxis. All aesthetic practitioners must have epinephrine immediately available and be trained in its use.",
            citation_text="Epinephrine IM is the only first-line treatment for anaphylaxis; antihistamines and steroids are adjuncts only.",
            source_type="review",
            relevance_score=0.97,
            year=2023,
        )
    ],
    "infection": [
        EvidenceItem(
            source_id="S45",
            title="Biofilm and infection after aesthetic filler — diagnosis and management",
            note="Delayed inflammatory nodules after filler may represent biofilm. Early recognition and appropriate antimicrobial management improve outcomes.",
            source_type="review",
            relevance_score=0.89,
            year=2022,
        )
    ],
    "nodule": [
        EvidenceItem(
            source_id="S46",
            title="Filler nodules: classification, causes, and management options",
            note="Filler nodules range from benign placement irregularities to inflammatory or infectious complications. Filler type, timing, and clinical features guide management.",
            source_type="review",
            relevance_score=0.86,
            year=2023,
        )
    ],
    "nasal": [
        EvidenceItem(
            source_id="S42",
            title="Vascular complications of nasal filler — case series and management",
            note="Nasal filler is associated with a disproportionately high rate of severe vascular complications including vision loss. High expertise and immediate hyaluronidase access are mandatory.",
            citation_text="Nasal filler is associated with a disproportionately high rate of severe vascular complications.",
            source_type="case_series",
            relevance_score=0.97,
            year=2023,
        )
    ],
    "default": [
        EvidenceItem(
            source_id="S0",
            title="Aesthetic injectables — general safety principles",
            note="Emergency preparedness, anatomical knowledge, and conservative technique reduce complication risk in all aesthetic injectable procedures.",
            source_type="review",
            relevance_score=0.80,
            journal="Aesthetic Medicine",
            year=2023,
        )
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# Procedure rules (all 7 regions)
# ──────────────────────────────────────────────────────────────────────────────

PROCEDURE_RULES: List[Dict[str, Any]] = [
    {
        "procedure_aliases": ["nasolabial fold filler", "nlf filler", "smile line filler", "ha filler"],
        "region_aliases": ["nasolabial fold", "nlf"],
        "product_aliases": ["hyaluronic acid", "ha filler", "filler", "calcium hydroxylapatite"],
        "base_risk": 42,
        "complications": [
            ("vascular occlusion", 58, "Angular artery territory makes this region high-risk for ischemia."),
            ("skin necrosis", 40, "Untreated vascular compromise can progress to tissue necrosis."),
            ("bruising", 28, "Vascular trauma risk is technique-dependent."),
        ],
        "danger_zones": ["Angular artery territory", "Facial artery branches", "Labial arteries"],
        "plane": "Technique varies by anatomy and product; vascular awareness is critical throughout.",
        "tech_notes": [
            "Use small aliquots — large bolus injections raise vascular risk significantly.",
            "Any pain, blanching, or mottling requires immediate protocol review.",
            "Aspiration does not reliably exclude intravascular placement — treat symptoms immediately.",
        ],
        "mitigation": [
            "Have hyaluronidase immediately available before starting.",
            "Use cannula technique where appropriate for this region.",
            "Inject slowly with constant pressure assessment.",
            "Ensure patient can report pain immediately.",
            "Confirm capillary refill before and after each deposit.",
        ],
        "evidence_key": "vascular",
    },
    {
        "procedure_aliases": ["tear trough filler", "under eye filler", "periorbital filler"],
        "region_aliases": ["tear trough", "under eye", "infraorbital", "periorbital"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 48,
        "complications": [
            ("vascular occlusion", 52, "Periorbital anatomy makes vascular complications especially sensitive."),
            ("tyndall effect", 54, "Superficial HA placement can produce blue-gray discoloration."),
            ("edema", 45, "This area is prone to persistent swelling."),
        ],
        "danger_zones": ["Periorbital vascular territory", "Infraorbital region", "Angular artery"],
        "plane": "Usually deeper, controlled placement is preferred; superficial placement increases Tyndall risk.",
        "tech_notes": [
            "Avoid superficial deposition.",
            "Product selection and volume discipline are critical.",
            "Escalate immediately for pain, blanching, or visual symptoms.",
        ],
        "mitigation": [
            "Avoid superficial placement.",
            "Use conservative volume.",
            "Reassess symmetry before further product placement.",
            "Escalate immediately for pain, blanching, or visual symptoms.",
        ],
        "evidence_key": "tear_trough",
    },
    {
        "procedure_aliases": ["lip filler", "lip augmentation", "lip enhancement"],
        "region_aliases": ["lip", "lips", "labial"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 38,
        "complications": [
            ("vascular occlusion", 47, "Lip vascularity requires careful injection planning."),
            ("swelling", 44, "Post-procedure swelling is common and can be significant."),
            ("bruising", 34, "The lip is highly vascular."),
        ],
        "danger_zones": ["Labial vascular territory", "Superior labial artery", "Inferior labial artery"],
        "plane": "Technique varies by lip subunit and aesthetic objective.",
        "tech_notes": [
            "Avoid large bolus deposition.",
            "Careful reassessment helps avoid overcorrection.",
            "Monitor for disproportionate pain or blanching throughout.",
        ],
        "mitigation": [
            "Use controlled volume and slow injection.",
            "Avoid large boluses.",
            "Monitor for disproportionate pain or blanching.",
            "Have hyaluronidase available for HA filler procedures.",
        ],
        "evidence_key": "lip",
    },
    {
        "procedure_aliases": ["glabellar toxin", "frown line botox", "glabella botox", "glabellar botox", "glabellar filler"],
        "region_aliases": ["glabella", "frown lines", "glabellar", "between eyebrows"],
        "product_aliases": ["botulinum toxin", "toxin", "botox", "dysport", "xeomin", "hyaluronic acid filler", "ha filler"],
        "base_risk": 24,
        "complications": [
            ("ptosis", 46, "Unwanted toxin diffusion can affect eyelid or brow function."),
            ("asymmetry", 32, "Uneven muscle effect may alter brow balance."),
            ("vascular occlusion", 28, "Glabellar filler carries anastomotic connections to ophthalmic territory."),
        ],
        "danger_zones": ["Unwanted diffusion toward eyelid elevators", "Supratrochlear artery", "Supraorbital artery"],
        "plane": "Target muscles and dose pattern vary by anatomy and facial dynamics; respect anastomotic risk for fillers.",
        "tech_notes": [
            "Differentiate brow heaviness from true eyelid ptosis.",
            "Precise placement matters more than total dose alone.",
            "Glabellar filler carries one of the highest rates of vision-threatening vascular events.",
        ],
        "mitigation": [
            "Respect diffusion risk near structures affecting eyelid position.",
            "Use conservative placement strategy in higher-risk anatomy.",
            "Document exact injection points and dose.",
            "Have hyaluronidase immediately available for any filler in this region.",
        ],
        "evidence_key": "glabella",
    },
    {
        "procedure_aliases": ["jawline filler", "chin filler", "cheek filler", "jawline augmentation", "cheek augmentation"],
        "region_aliases": ["jawline", "chin", "cheek", "mandible"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "calcium hydroxylapatite", "filler", "poly-l-lactic acid"],
        "base_risk": 34,
        "complications": [
            ("vascular occlusion", 36, "Deep structural injection still requires vascular awareness."),
            ("asymmetry", 29, "Volumetric imbalance can become apparent after swelling settles."),
            ("nodules", 24, "Product placement and tissue plane influence palpability."),
        ],
        "danger_zones": ["Regional arterial branches vary by area", "Facial artery", "Mental artery"],
        "plane": "Plane depends on aesthetic goal, product, and anatomy.",
        "tech_notes": [
            "Respect regional anatomy and product rheology.",
            "Reassess after each increment.",
            "Higher-viscosity products require careful volumetric control.",
        ],
        "mitigation": [
            "Inject incrementally.",
            "Use anatomy-driven technique selection.",
            "Reassess projection and symmetry before additional product.",
        ],
        "evidence_key": "vascular",
    },
    {
        "procedure_aliases": ["forehead filler", "temple filler", "forehead botox", "temple botox", "temple augmentation"],
        "region_aliases": ["forehead", "temple", "frontal", "temporal"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler", "botulinum toxin", "toxin", "botox"],
        "base_risk": 45,
        "complications": [
            ("vascular occlusion", 55, "Temple and forehead carry significant vascular density and anastomotic connections."),
            ("intracranial embolism", 30, "Superficial temporal and supratrochlear vessels have central connections."),
            ("skin necrosis", 28, "Ischemic injury in this territory can be vision- or life-threatening."),
        ],
        "danger_zones": ["Superficial temporal artery", "Supratrochlear artery", "Supraorbital artery", "Frontal branch of facial nerve"],
        "plane": "Requires deep periosteal plane for fillers; toxin targets frontalis and corrugators specifically.",
        "tech_notes": [
            "High-risk vascular territory — treat with same vigilance as glabella.",
            "Avoid injection over palpable vessels.",
            "Aspirate carefully; use small aliquots.",
        ],
        "mitigation": [
            "Deep periosteal placement preferred for fillers in this region.",
            "Avoid injection directly over palpable temporal vessels.",
            "Have full emergency protocol ready before starting.",
            "Use very small volumes per pass.",
        ],
        "evidence_key": "vascular",
    },
    {
        "procedure_aliases": ["nose filler", "rhinoplasty filler", "nose reshaping filler", "non-surgical rhinoplasty", "nasal filler"],
        "region_aliases": ["nose", "nasal", "nasal tip", "nasal bridge", "dorsum"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 72,
        "complications": [
            ("vascular occlusion", 82, "The nasal dorsum and tip are among the highest-risk zones for ischemic events."),
            ("skin necrosis", 70, "Thin overlying skin and limited collateral supply make necrosis a real risk."),
            ("visual loss", 35, "Dorsal nasal vessels communicate with ophthalmic territory."),
        ],
        "danger_zones": ["Dorsal nasal artery", "Angular artery", "Ophthalmic territory connections", "Alar subunit"],
        "plane": "Supraperiosteal or deep subcutaneous preferred; superficial placement dramatically increases risk.",
        "tech_notes": [
            "This is one of the highest-risk aesthetic filler zones.",
            "Blanching at any stage = stop immediately and treat.",
            "Expertise level matters significantly in this region.",
        ],
        "mitigation": [
            "Ensure hyaluronidase is immediately available at the start.",
            "Use smallest possible volumes and linear threading.",
            "Stop on any blanching or patient-reported pain change.",
            "Have ophthalmology emergency contact confirmed before starting.",
        ],
        "evidence_key": "nasal",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Onboarding hints
# ──────────────────────────────────────────────────────────────────────────────

ONBOARDING_HINTS: Dict[str, OnboardingHint] = {
    "default": OnboardingHint(
        procedure="Injectable procedure",
        what_this_checks="This check scores overall procedural risk based on your technique, patient factors, and anatomy.",
        key_fields_to_fill=["Procedure", "Region", "Product type", "Technique", "Patient risk factors"],
        clinical_tip="Fill in all patient risk factors for the most accurate safety score.",
    ),
    "tear_trough": OnboardingHint(
        procedure="Tear trough filler",
        what_this_checks="Evaluates Tyndall risk, periorbital vascular anatomy, and product placement plane.",
        key_fields_to_fill=["Product type", "Technique", "Prior filler in same area", "Anticoagulation"],
        clinical_tip="Conservative volume and appropriate depth are the two most important variables for tear trough safety.",
    ),
    "lip": OnboardingHint(
        procedure="Lip filler",
        what_this_checks="Scores labial vascular risk, technique selection, and anticipated post-procedure swelling.",
        key_fields_to_fill=["Product type", "Technique", "Anticoagulation", "Prior filler in same area"],
        clinical_tip="Small aliquots and slow injection substantially reduce labial vascular risk.",
    ),
    "glabella": OnboardingHint(
        procedure="Glabellar procedure",
        what_this_checks="Assesses diffusion risk for toxin and vision-threatening vascular risk for fillers in this high-risk region.",
        key_fields_to_fill=["Product type", "Technique", "Injector experience", "Prior vascular event"],
        clinical_tip="The glabellar region has one of the highest rates of vision-threatening vascular events from filler. Hyaluronidase must be immediately available.",
    ),
    "nose": OnboardingHint(
        procedure="Nasal filler",
        what_this_checks="Flags the highest-risk vascular territory in aesthetic filler practice. Scores vision-threatening risk from nasal vessel connections.",
        key_fields_to_fill=["Injector experience", "Technique", "Prior vascular event", "Prior filler in same area"],
        clinical_tip="This is the highest-risk aesthetic filler region. Ophthalmology emergency contact must be confirmed before starting.",
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Complication protocols (6 protocols)
# ──────────────────────────────────────────────────────────────────────────────

COMPLICATION_PROTOCOLS: Dict[str, Dict[str, Any]] = {
    "vascular_occlusion_ha_filler": {
        "name": "Suspected vascular occlusion after hyaluronic acid filler",
        "severity": "critical",
        "urgency": "immediate",
        "base_score": 92,
        "keywords": ["vascular occlusion", "blanching", "mottling", "ischemia", "livedo", "capillary refill", "necrosis", "dusky", "pain after filler"],
        "evidence_key": "vascular",
        "summary": "This presentation is concerning for impending or established vascular compromise after HA filler. Time-critical intervention is required to restore perfusion.",
        "steps": [
            {"action": "Stop the procedure immediately.", "rationale": "Continued injection worsens ischemia.", "priority": "primary"},
            {"action": "Assess capillary refill, skin color, temperature, pain, and full territory of blanching.", "rationale": "Defines extent and progression of tissue compromise.", "priority": "primary"},
            {"action": "Escalate immediately if any visual symptom is present — call emergency services.", "rationale": "Ocular ischemia is a medical emergency with risk of permanent vision loss.", "priority": "primary"},
            {"action": "Massage the area and apply warm compresses if not contraindicated.", "rationale": "May support vasodilation and mechanical dispersion.", "priority": "secondary"},
            {"action": "Administer high-dose hyaluronidase across the full affected vascular territory.", "rationale": "Rapid HA filler breakdown is the key reversible intervention.", "priority": "primary"},
            {"action": "Reassess and repeat hyaluronidase if ischemic signs persist.", "rationale": "Persistent signs suggest ongoing obstruction.", "priority": "primary"},
        ],
        "dose_guidance": [
            {"substance": "Hyaluronidase", "recommendation": "At least 500 IU per affected territory; many protocols use 500–1500 IU or more.", "notes": "Inject across the full compromised vascular territory. Repeat according to persistent signs."},
            {"substance": "Aspirin", "recommendation": "Consider according to clinician judgment when not contraindicated.", "notes": "Follow local protocol."},
        ],
        "red_flags": ["Visual disturbance or vision loss", "Severe or escalating pain", "Rapidly spreading blanching or livedo", "Delayed or absent capillary refill"],
        "escalation": ["Immediate emergency referral for any visual symptom", "Urgent senior review if reperfusion does not improve", "Emergency department transfer if progressive"],
        "monitoring": ["Reassess capillary refill every 15–30 minutes", "Track pain progression and skin color", "Repeat photographs after each intervention cycle"],
        "follow_up_questions": ["Was the product HA filler?", "Which region was injected?", "Are there visual symptoms?", "How many minutes since injection?"],
        "limitations": ["Evidence based largely on expert consensus", "Optimal hyaluronidase dose is not fully standardized", "Applies only when HA filler is suspected"],
    },

    "filler_nodules_inflammatory_or_noninflammatory": {
        "name": "Suspected filler nodules after injectable treatment",
        "severity": "moderate",
        "urgency": "same_day",
        "base_score": 45,
        "keywords": ["filler nodule", "lump after filler", "bump after filler", "granuloma", "biofilm", "delayed nodule", "tender swelling"],
        "evidence_key": "nodule",
        "summary": "This presentation may represent noninflammatory filler deposition, inflammatory nodules, or a biofilm/infection-associated complication.",
        "steps": [
            {"action": "Assess onset timing, tenderness, erythema, warmth, fluctuance, and filler type.", "rationale": "Distinguishes placement irregularity from inflammatory or infectious complications.", "priority": "primary"},
            {"action": "Avoid aggressive massage when nodules are delayed, tender, or inflamed.", "rationale": "Massage may worsen inflammation or obscure assessment.", "priority": "primary"},
            {"action": "If HA filler confirmed and lesion appears noninfectious, consider targeted hyaluronidase.", "rationale": "HA filler can often be enzymatically reduced.", "priority": "secondary"},
            {"action": "Escalate promptly if infection is suspected.", "rationale": "Infectious complications require clinician-led management.", "priority": "primary"},
        ],
        "dose_guidance": [
            {"substance": "Hyaluronidase", "recommendation": "Targeted dosing for confirmed HA filler when clinically appropriate.", "notes": "Dose depends on filler type, volume, chronicity, and location."},
        ],
        "red_flags": ["Marked tenderness with erythema or warmth", "Fluctuance or drainage", "Systemic symptoms", "Progressive swelling"],
        "escalation": ["Urgent clinician review if infection or abscess is suspected", "Senior review for recurrent nodules"],
        "monitoring": ["Document size, tenderness, warmth, erythema, and change over time"],
        "follow_up_questions": ["Is the filler confirmed HA?", "How long after injection did the nodule appear?", "Is it tender, red, or warm?"],
        "limitations": ["Treatment depends on confirmed filler identity and whether infection is present"],
    },

    "tyndall_effect_ha_filler": {
        "name": "Suspected Tyndall effect after superficial hyaluronic acid filler",
        "severity": "low",
        "urgency": "routine",
        "base_score": 25,
        "keywords": ["tyndall", "blue discoloration", "bluish under eyes", "superficial filler", "blue-gray discoloration", "tear trough blue"],
        "evidence_key": "tear_trough",
        "summary": "Consistent with superficial HA filler causing bluish or blue-gray discoloration. Not usually an emergency, but ischemia must first be excluded.",
        "steps": [
            {"action": "Confirm there are no ischemic features: pain, blanching, livedo, or delayed capillary refill.", "rationale": "Tyndall must be clearly distinguished from vascular compromise.", "priority": "primary"},
            {"action": "Assess whether superficial HA filler placement is the likely cause.", "rationale": "Management depends on product identity and depth.", "priority": "primary"},
            {"action": "Consider conservative targeted hyaluronidase if ischemia excluded.", "rationale": "Superficial HA filler can often be partially reversed.", "priority": "secondary"},
        ],
        "dose_guidance": [
            {"substance": "Hyaluronidase", "recommendation": "Conservative targeted dosing based on area and desired correction.", "notes": "Avoid overcorrection. Reassess before repeating."},
        ],
        "red_flags": ["Pain", "Blanching", "Livedo or mottling", "Delayed capillary refill"],
        "escalation": ["Escalate immediately if ischemic features are present — do not treat as cosmetic discoloration"],
        "monitoring": ["Monitor cosmetic response and avoid overcorrection"],
        "follow_up_questions": ["Is the discoloration blue-gray rather than pale?", "Was HA filler used?", "Is there pain or blanching?"],
        "limitations": ["Requires confirmation that the product is HA and the finding is superficial placement"],
    },

    "infection_or_biofilm_after_filler": {
        "name": "Suspected infection or biofilm-related complication after filler",
        "severity": "high",
        "urgency": "urgent",
        "base_score": 72,
        "keywords": ["infection after filler", "biofilm after filler", "warm red swelling", "drainage after filler", "abscess after filler", "fever after filler"],
        "evidence_key": "infection",
        "summary": "Raises concern for an infectious or biofilm-related complication. Tenderness, warmth, erythema, fluctuance, drainage, or fever warrant urgent clinical review.",
        "steps": [
            {"action": "Assess for tenderness, warmth, erythema, fluctuance, drainage, fever, and systemic symptoms.", "rationale": "These features raise suspicion for infectious or biofilm complications.", "priority": "primary"},
            {"action": "Do not assume a simple cosmetic irregularity if inflammatory signs are present.", "rationale": "Delayed recognition worsens outcomes.", "priority": "primary"},
            {"action": "Escalate for clinician-led infection assessment and management.", "rationale": "Antibiotic selection and drainage decisions require clinical evaluation.", "priority": "primary"},
        ],
        "dose_guidance": [],
        "red_flags": ["Fever", "Fluctuance", "Drainage", "Rapidly progressive swelling", "Marked tenderness with erythema and warmth"],
        "escalation": ["Urgent in-person clinician review", "Emergency referral if systemic illness or rapidly progressive facial infection is suspected"],
        "monitoring": ["Track swelling, tenderness, temperature, drainage, and systemic symptoms"],
        "follow_up_questions": ["Is there warmth, drainage, or fluctuance?", "Is the patient febrile?", "When did symptoms begin after injection?"],
        "limitations": ["Management requires clinician assessment and depends on local microbiology decisions"],
    },

    "anaphylaxis_allergic_reaction": {
        "name": "Suspected anaphylaxis or severe allergic reaction after aesthetic treatment",
        "severity": "critical",
        "urgency": "immediate",
        "base_score": 95,
        "keywords": ["anaphylaxis", "allergic reaction", "urticaria", "angioedema", "throat swelling", "difficulty breathing", "hypotension", "collapse", "systemic reaction", "wheeze", "stridor"],
        "evidence_key": "anaphylaxis",
        "summary": "This presentation is concerning for anaphylaxis. Immediate recognition and emergency action are required — call emergency services without delay.",
        "steps": [
            {"action": "Stop the procedure immediately and call emergency services.", "rationale": "Anaphylaxis is a medical emergency requiring immediate response.", "priority": "primary"},
            {"action": "Assess airway, breathing, circulation, and mental status.", "rationale": "Rapid ABC assessment guides immediate action.", "priority": "primary"},
            {"action": "Administer intramuscular epinephrine promptly — outer thigh, no delay.", "rationale": "Epinephrine is the only first-line treatment for anaphylaxis.", "priority": "primary"},
            {"action": "Place the patient supine with legs elevated unless breathing difficulty.", "rationale": "Supports circulation and reduces risk of collapse.", "priority": "secondary"},
            {"action": "Repeat epinephrine if symptoms persist or worsen after 5 minutes.", "rationale": "Refractory or biphasic anaphylaxis may require repeated dosing.", "priority": "primary"},
        ],
        "dose_guidance": [
            {"substance": "Epinephrine (adrenaline)", "recommendation": "0.5 mg IM (0.5 mL of 1:1000) into the outer thigh for adults. Repeat after 5 minutes if no improvement.", "notes": "Use auto-injector if available. Do not delay — antihistamines and steroids do not replace epinephrine."},
            {"substance": "Adjunctive medications", "recommendation": "Antihistamines and corticosteroids may be considered as adjuncts only, after epinephrine.", "notes": "Adjuncts do not prevent or treat anaphylaxis shock."},
        ],
        "red_flags": ["Airway swelling or stridor", "Wheeze or respiratory distress", "Hypotension or collapse", "Loss of consciousness"],
        "escalation": ["Call emergency services immediately", "Urgent airway support if swelling or respiratory compromise", "Emergency transfer — observe for biphasic reactions"],
        "monitoring": ["Continuous observation of airway, breathing, and circulation", "Repeat vital signs frequently until emergency team arrives"],
        "follow_up_questions": ["Is there airway swelling or breathing difficulty?", "Is the patient hypotensive or collapsed?", "Have emergency services been called?"],
        "limitations": ["This tool does not replace formal emergency protocols", "Follow local emergency resuscitation and anaphylaxis policy"],
    },

    "botulinum_toxin_ptosis": {
        "name": "Suspected eyelid or brow ptosis after botulinum toxin treatment",
        "severity": "moderate",
        "urgency": "same_day",
        "base_score": 40,
        "keywords": ["ptosis after botox", "droopy eyelid", "eyelid droop", "brow ptosis", "brow heaviness", "botulinum toxin complication", "levator spread", "botox ptosis", "toxin ptosis"],
        "evidence_key": "toxin",
        "summary": "Consistent with toxin diffusion-related eyelid or brow ptosis. Usually temporary, resolving in 4–12 weeks. Visual symptoms or atypical findings require escalation.",
        "steps": [
            {"action": "Confirm recent botulinum toxin treatment and define whether the issue is eyelid ptosis, brow ptosis, or another pattern.", "rationale": "Pattern recognition guides management and escalation.", "priority": "primary"},
            {"action": "Assess for diplopia, visual disturbance, anisocoria, or atypical neurologic signs.", "rationale": "These may indicate an alternative diagnosis requiring urgent escalation.", "priority": "primary"},
            {"action": "Reassure the patient that toxin-related ptosis is temporary.", "rationale": "Most cases resolve within 4–12 weeks as toxin effect naturally wanes.", "priority": "secondary"},
            {"action": "Consider apraclonidine 0.5% eye drops for confirmed eyelid ptosis if no contraindication.", "rationale": "Alpha-agonist stimulates Müller's muscle for mild temporary elevation.", "priority": "secondary"},
        ],
        "dose_guidance": [
            {"substance": "Apraclonidine 0.5% eye drops", "recommendation": "1 drop to the affected eye up to three times daily.", "notes": "Prescription required. Check contraindications. Symptomatic only — ptosis resolves as toxin wanes."},
        ],
        "red_flags": ["Diplopia or double vision", "Visual disturbance", "Atypical or progressive neurologic findings", "Progressive systemic weakness or dysphagia"],
        "escalation": ["Urgent clinician review if diplopia or atypical neurologic symptoms", "Ophthalmology review if visual field significantly affected", "Emergency review if systemic weakness or dysphagia develops"],
        "monitoring": ["Review weekly or fortnightly until resolution", "Document visual function and expected recovery discussion at each review"],
        "follow_up_questions": ["Is the ptosis affecting the eyelid, brow, or both?", "Are there any visual symptoms?", "When did it start relative to the injection?"],
        "limitations": ["Management depends on confirming uncomplicated toxin diffusion", "Most cases resolve without active intervention"],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Drug interaction rules
# ──────────────────────────────────────────────────────────────────────────────

DRUG_RULES: List[Dict[str, Any]] = [
    {"meds": ["warfarin", "acenocoumarol"], "severity": "high",
     "explanation": "Vitamin K antagonists substantially increase bruising and bleeding risk. INR should be checked and within therapeutic range.",
     "action": "Check INR before treatment. Discuss bleeding risk explicitly. Consider timing relative to dose."},
    {"meds": ["apixaban", "rivaroxaban", "dabigatran", "edoxaban"], "severity": "high",
     "explanation": "NOACs significantly increase procedural bleeding risk. No reliable reversal agent is available for all NOACs in aesthetic settings.",
     "action": "Document anticoagulation. Discuss risk. Consider whether timing adjustment is clinically appropriate."},
    {"meds": ["heparin", "enoxaparin", "tinzaparin", "dalteparin"], "severity": "high",
     "explanation": "Injectable anticoagulants significantly increase bleeding and bruising risk.",
     "action": "Discuss timing with prescribing clinician. Do not proceed on same day as therapeutic heparin dose."},
    {"meds": ["aspirin", "clopidogrel", "ticagrelor", "prasugrel"], "severity": "moderate",
     "explanation": "Antiplatelet agents increase bruising risk. Do not stop without prescriber approval.",
     "action": "Do not stop without medical approval. Warn patient about bruising. Document in consent."},
    {"meds": ["ibuprofen", "naproxen", "diclofenac", "celecoxib", "indometacin"], "severity": "moderate",
     "explanation": "NSAIDs inhibit platelet function and increase bruising risk.",
     "action": "Advise stopping 5–7 days before treatment if safe to do so."},
    {"meds": ["sertraline", "fluoxetine", "escitalopram", "citalopram", "paroxetine", "venlafaxine", "duloxetine", "fluvoxamine"], "severity": "moderate",
     "explanation": "SSRIs/SNRIs reduce platelet aggregation and may increase bruising risk.",
     "action": "Warn patient about increased bruising potential. Do not stop without prescriber advice."},
    {"meds": ["vitamin e", "fish oil", "omega 3", "omega-3", "ginkgo", "garlic supplement"], "severity": "low",
     "explanation": "These supplements may mildly increase bruising risk.",
     "action": "Advise stopping 1 week before treatment if possible."},
    {"meds": ["methotrexate", "azathioprine", "ciclosporin", "tacrolimus", "mycophenolate"], "severity": "high",
     "explanation": "Immunosuppressants increase infection risk and may impair healing.",
     "action": "Discuss with prescribing clinician. Ensure infection risk is discussed and documented."},
    {"meds": ["isotretinoin", "roaccutane", "accutane"], "severity": "high",
     "explanation": "Isotretinoin impairs wound healing and is a relative contraindication to ablative procedures.",
     "action": "Defer ablative procedures until 6–12 months after stopping. Discuss specific risk for injectables."},
    {"meds": ["prednisolone", "prednisone", "dexamethasone", "hydrocortisone oral"], "severity": "moderate",
     "explanation": "Long-term steroids impair healing and immune response.",
     "action": "Document steroid use. Be aware of impaired healing and increased infection risk."},
]


# ──────────────────────────────────────────────────────────────────────────────
# Evidence retrieval
# ──────────────────────────────────────────────────────────────────────────────

def retrieve_evidence(procedure: str, region: str, product_type: str) -> List[EvidenceItem]:
    blob = normalize(f"{procedure} {region} {product_type}")
    priority_map = [
        (["vision loss", "ocular", "blindness"], "vision_loss"),
        (["vascular occlusion", "blanching", "mottling", "ischemia", "necrosis", "skin necrosis"], "necrosis"),
        (["nose", "nasal"], "nasal"),
        (["vascular", "blanching", "mottling", "ischemia", "occlusion"], "vascular"),
        (["lip", "labial"], "lip"),
        (["tear trough", "periorbital", "under eye", "tyndall"], "tear_trough"),
        (["glabella", "glabellar", "frown"], "glabella"),
        (["toxin", "botulinum", "botox", "ptosis"], "toxin"),
        (["anaphylaxis", "allergic", "urticaria"], "anaphylaxis"),
        (["infection", "biofilm", "abscess"], "infection"),
        (["nodule", "granuloma", "lump", "bump"], "nodule"),
    ]
    matched_keys: List[str] = []
    for keywords, key in priority_map:
        if any(kw in blob for kw in keywords):
            matched_keys.append(key)
            if len(matched_keys) >= 2:
                break
    results: List[EvidenceItem] = []
    for key in matched_keys:
        results.extend(CURATED_EVIDENCE.get(key, []))
    if not results:
        results = CURATED_EVIDENCE.get("default", [])
    seen: set = set()
    deduped: List[EvidenceItem] = []
    for item in results:
        if item.source_id not in seen:
            seen.add(item.source_id)
            deduped.append(item)
    return deduped[:5]


# ──────────────────────────────────────────────────────────────────────────────
# Rule matching and scoring
# ──────────────────────────────────────────────────────────────────────────────

def match_rule(request: PreProcedureRequest) -> Dict[str, Any]:
    proc_n = normalize(request.procedure)
    region_n = normalize(request.region)
    prod_n = normalize(request.product_type)
    best_rule: Optional[Dict[str, Any]] = None
    best_score = -1
    for rule in PROCEDURE_RULES:
        score = 0
        for alias in rule["procedure_aliases"]:
            if normalize(alias) in proc_n or proc_n in normalize(alias):
                score += 3
                break
        for alias in rule["region_aliases"]:
            if normalize(alias) in region_n or region_n in normalize(alias):
                score += 2
                break
        for alias in rule["product_aliases"]:
            if normalize(alias) in prod_n or prod_n in normalize(alias):
                score += 1
                break
        if score > best_score:
            best_score = score
            best_rule = rule
    if best_rule is None:
        raise HTTPException(status_code=500, detail="No procedure rules configured.")
    return best_rule


def adjust_score(base: int, request: PreProcedureRequest) -> Tuple[int, List[str]]:
    score = base
    flags: List[str] = []
    exp = request.injector_experience_level
    if exp == "junior":
        score += 10
        flags.append("Junior injector — additional supervision and conservative technique recommended.")
    elif exp == "intermediate":
        score += 4
    elif exp == "senior":
        score -= 4
    tech_n = normalize(request.technique or "")
    if "cannula" in tech_n:
        score -= 4
        flags.append("Cannula technique selected — generally lower vascular risk than sharp needle.")
    elif "needle" in tech_n or "sharp" in tech_n:
        score += 6
        flags.append("Sharp needle technique — higher vascular risk than cannula in most regions.")
    pf = request.patient_factors
    if pf:
        if pf.prior_vascular_event:
            score += 10
            flags.append("Prior vascular event — significantly elevated ischemic risk.")
        if pf.active_infection_near_site:
            score += 15
            flags.append("Active infection near site — treatment should be deferred.")
        if pf.allergy_history:
            score += 5
            flags.append("Allergy history — ensure emergency preparedness for allergic reaction.")
        if pf.autoimmune_history:
            score += 4
            flags.append("Autoimmune history — inflammatory complications may be harder to interpret.")
        if pf.anticoagulation:
            score += 5
            flags.append("Anticoagulation — increased bruising and bleeding risk.")
        if pf.nsaid_use:
            score += 3
            flags.append("NSAID use — increased bruising risk.")
        if pf.ssri_use:
            score += 3
            flags.append("SSRI use — increased bruising risk.")
        if pf.smoking:
            score += 4
            flags.append("Smoking — impaired tissue healing and vascular resilience.")
        if pf.prior_filler_in_same_area:
            score += 6
            flags.append("Prior filler in same area — altered anatomy and cumulative volume risk.")
        if pf.pregnancy:
            score += 20
            flags.append("Pregnancy — aesthetic injectable treatment should be deferred.")
        if pf.immunosuppression:
            score += 7
            flags.append("Immunosuppression — infection risk is elevated.")
        if pf.vascular_disease:
            score += 8
            flags.append("Vascular disease — ischemic complications are harder to manage.")
        if pf.glp1_patient:
            score += 6
            flags.append(
                "GLP-1 medication (semaglutide/tirzepatide): rapid facial fat loss alters volume "
                "distribution and may change filler requirements. Standard quantities risk overcorrection. "
                "Facial anatomy may differ from prior assessments. Reassess treatment plan accordingly."
            )
    return clamp(score, 0, 100), flags


def build_top_risks(rule: Dict[str, Any], overall_score: int) -> List[RiskItem]:
    modifier = int((overall_score - rule["base_risk"]) * 0.35)
    risks: List[RiskItem] = []
    for complication, raw_score, why in rule["complications"]:
        final_score = clamp(raw_score + modifier, 0, 100)
        risks.append(RiskItem(
            complication=complication,
            risk_score=final_score,
            risk_level=risk_level_from_score(final_score),
            why_it_matters=why,
        ))
    risks.sort(key=lambda x: x.risk_score, reverse=True)
    return risks


def get_onboarding_hint(procedure: str, region: str) -> OnboardingHint:
    blob = normalize(f"{procedure} {region}")
    if "nose" in blob or "nasal" in blob:
        return ONBOARDING_HINTS.get("nose", ONBOARDING_HINTS["default"])
    if "glabella" in blob or "frown" in blob:
        return ONBOARDING_HINTS.get("glabella", ONBOARDING_HINTS["default"])
    if "lip" in blob or "labial" in blob:
        return ONBOARDING_HINTS.get("lip", ONBOARDING_HINTS["default"])
    if "tear trough" in blob or "periorbital" in blob:
        return ONBOARDING_HINTS.get("tear_trough", ONBOARDING_HINTS["default"])
    return ONBOARDING_HINTS["default"]


# ──────────────────────────────────────────────────────────────────────────────
# Related papers with 6-hour cache
# ──────────────────────────────────────────────────────────────────────────────

def _paper_cache_get(key: str) -> Optional[List[Dict[str, Any]]]:
    with _paper_cache_lock:
        entry = _paper_cache.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > PAPER_CACHE_TTL_SECONDS:
            _paper_cache.pop(key, None)
            return None
        return entry["value"]

def _paper_cache_set(key: str, value: List[Dict[str, Any]]) -> None:
    with _paper_cache_lock:
        _paper_cache[key] = {"ts": time.time(), "value": value}


def fetch_related_papers(procedure: str, region: str) -> List[Dict[str, Any]]:
    cache_key = normalize(f"{procedure}|{region}")
    cached = _paper_cache_get(cache_key)
    if cached is not None:
        return cached
    results: List[Dict[str, Any]] = []
    try:
        import requests
        topic = f"{procedure} {region} aesthetic filler safety"
        params: Dict[str, str] = {
            "db": "pubmed",
            "term": topic,
            "retmax": "3",
            "sort": "pub date",
            "retmode": "json",
            "mindate": "2024/01/01",
            "maxdate": datetime.now().strftime("%Y/%m/%d"),
            "datetype": "pdat",
        }
        ncbi_key = os.environ.get("NCBI_API_KEY", "")
        if ncbi_key:
            params["api_key"] = ncbi_key
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params, timeout=3)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if ids:
            r2 = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                              params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}, timeout=3)
            r2.raise_for_status()
            data = r2.json().get("result", {})
            for pmid in ids:
                entry = data.get(pmid, {})
                if entry and "error" not in entry:
                    results.append({
                        "title": entry.get("title", ""),
                        "journal": entry.get("source", ""),
                        "date": entry.get("pubdate", ""),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    })
    except Exception:
        results = []
    _paper_cache_set(cache_key, results[:3])
    return results[:3]


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard logging
# ──────────────────────────────────────────────────────────────────────────────

def log_safety_to_dashboard(request: PreProcedureRequest, decision: str, risk_score: int, response_time_ms: float) -> None:
    try:
        with db_cursor() as (_, cur):
            cur.execute("""
                INSERT INTO query_logs
                    (id, clinic_id, clinician_id, query_text, answer_type, aci_score, response_time_ms, evidence_level, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_id(),
                request.clinic_id or "unknown",
                request.clinician_id or "unknown",
                f"Pre-procedure check: {request.procedure} / {request.region}",
                "safety_check",
                float(max(0, 10 - (risk_score / 10))),
                response_time_ms,
                decision,
                now_utc_iso(),
            ))
    except Exception:  # nosec B110
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Response builders
# ──────────────────────────────────────────────────────────────────────────────

def build_safety_response(request: PreProcedureRequest, *, include_related_papers: bool = True) -> PreProcedureResponse:
    rule = match_rule(request)
    overall_score, flags = adjust_score(rule["base_risk"], request)
    overall_level = risk_level_from_score(overall_score)
    decision = decision_from_score(overall_score)
    top_risks = build_top_risks(rule, overall_score)
    evidence = retrieve_evidence(request.procedure, request.region, request.product_type)
    hint = get_onboarding_hint(request.procedure, request.region)
    related_papers = fetch_related_papers(request.procedure, request.region) if include_related_papers else []
    rationale_map = {
        "go": "Current setup appears acceptable. Standard safety precautions and emergency preparedness remain essential.",
        "caution": "Proceed only with heightened vigilance, full mitigation steps applied, and immediate readiness to manage complications.",
        "high_risk": "Risk is materially elevated. Reassess technique, timing, and patient factors before proceeding. Consider deferring treatment.",
    }
    return PreProcedureResponse(
        request_id=new_id(),
        generated_at_utc=now_utc_iso(),
        engine_version=ENGINE_VERSION,
        knowledge_revision=KNOWLEDGE_REVISION,
        safety_assessment=SafetyAssessment(
            overall_risk_score=overall_score,
            overall_risk_level=overall_level,
            decision=decision,
            rationale=rationale_map[decision],
        ),
        top_risks=top_risks,
        procedure_insight=ProcedureInsight(
            procedure_name=request.procedure,
            region=request.region,
            likely_plane_or_target=rule["plane"],
            danger_zones=rule["danger_zones"],
            technical_notes=rule["tech_notes"],
            ultrasound_recommended=get_ultrasound_flag(request.region)[0],
            ultrasound_note=get_ultrasound_flag(request.region)[1],
        ),
        mitigation_steps=rule["mitigation"],
        caution_flags=flags,
        evidence=evidence,
        onboarding_hint=hint,
        related_papers=related_papers,
        disclaimer=(
            "This output is pre-procedure safety decision support only. "
            "It does not replace clinician judgment, anatomical expertise, "
            "product knowledge, or local emergency preparedness."
        ),
    )


def run_preprocedure(payload: PreProcedureRequest) -> PreProcedureResponse:
    started = time.perf_counter()
    response = build_safety_response(payload, include_related_papers=True)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    if payload.log_to_dashboard:
        log_safety_to_dashboard(
            request=payload,
            decision=response.safety_assessment.decision,
            risk_score=response.safety_assessment.overall_risk_score,
            response_time_ms=elapsed_ms,
        )
    return response


def summarize_batch(items: List[PreProcedureResponse]) -> Dict[str, Any]:
    decisions = Counter(item.safety_assessment.decision for item in items)
    risk_scores = [item.safety_assessment.overall_risk_score for item in items]
    avg_risk = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0.0
    return {
        "average_risk_score": avg_risk,
        "decision_counts": {"go": decisions.get("go", 0), "caution": decisions.get("caution", 0), "high_risk": decisions.get("high_risk", 0)},
        "highest_risk_cases": sorted(
            [{"request_id": item.request_id, "risk_score": item.safety_assessment.overall_risk_score,
              "decision": item.safety_assessment.decision, "procedure": item.procedure_insight.procedure_name,
              "region": item.procedure_insight.region} for item in items],
            key=lambda x: x["risk_score"], reverse=True,
        )[:5],
    }


def score_and_select_protocol(query: str, region: Optional[str], product_type: Optional[str]) -> Tuple[str, Dict[str, Any], float]:
    blob = normalize(f"{query} {region or ''} {product_type or ''}")
    best_key = None
    best_proto = None
    best_score = -1.0
    for key, proto in COMPLICATION_PROTOCOLS.items():
        score = sum(1.0 for kw in proto["keywords"] if kw in blob)
        if score > best_score:
            best_score = score
            best_key = key
            best_proto = proto
    if not best_key or not best_proto or best_score <= 0:
        raise HTTPException(status_code=404, detail="No matching complication protocol found. Provide more specific clinical details.")
    confidence = min(0.99, round(0.45 + best_score * 0.06, 2))
    return best_key, best_proto, confidence


def build_protocol_response(request: ComplicationProtocolRequest) -> ComplicationProtocolResponse:
    key, proto, confidence = score_and_select_protocol(request.query, request.region, request.product_type)
    base_score = proto["base_score"]
    if request.visual_symptoms and key in ("vascular_occlusion_ha_filler",):
        base_score = min(100, base_score + 8)
    if request.pain_score and request.pain_score >= 8:
        base_score = min(100, base_score + 4)
    if request.time_since_injection_minutes and request.time_since_injection_minutes <= 30:
        base_score = min(100, base_score + 4)
    evidence = retrieve_evidence(request.region or proto["name"], request.region or "", request.product_type or "")
    return ComplicationProtocolResponse(
        request_id=new_id(),
        generated_at_utc=now_utc_iso(),
        engine_version=ENGINE_VERSION,
        matched_protocol_key=key,
        matched_protocol_name=proto["name"],
        confidence=confidence,
        risk_score=base_score,
        severity=proto["severity"],
        urgency=proto["urgency"],
        clinical_summary=proto["summary"],
        immediate_actions=[
            ProtocolStep(step_number=i + 1, action=s["action"], rationale=s["rationale"], priority=s.get("priority", "primary"))
            for i, s in enumerate(proto["steps"])
        ],
        dose_guidance=[
            DoseGuidance(substance=d["substance"], recommendation=d["recommendation"], notes=d["notes"])
            for d in proto["dose_guidance"]
        ],
        red_flags=proto["red_flags"],
        escalation=proto["escalation"],
        monitoring=proto["monitoring"],
        follow_up_questions=proto["follow_up_questions"],
        limitations=proto["limitations"],
        evidence=evidence,
        disclaimer="This protocol is clinical decision support only. It does not replace clinician judgment, emergency training, or local protocols.",
    )


def check_drug_interactions(medications: List[str], planned_products: List[str]) -> DrugCheckResponse:
    interactions: List[DrugInteractionItem] = []
    meds_n = [normalize(m) for m in medications]
    contexts = planned_products or ["injectable aesthetic procedure"]
    for rule in DRUG_RULES:
        for med_n in meds_n:
            matched = any(rule_med in med_n or med_n in rule_med for rule_med in rule["meds"])
            if matched:
                original = next((m for m in medications if normalize(m) == med_n or any(rm in normalize(m) for rm in rule["meds"])), med_n)
                for context in contexts:
                    interactions.append(DrugInteractionItem(
                        medication=original,
                        product_or_context=context,
                        severity=rule["severity"],
                        explanation=rule["explanation"],
                        action=rule["action"],
                    ))
    has_high = any(i.severity == "high" for i in interactions)
    has_moderate = any(i.severity == "moderate" for i in interactions)
    if has_high:
        summary = f"{len(interactions)} interaction(s) found — HIGH severity. Review before proceeding."
    elif has_moderate:
        summary = f"{len(interactions)} interaction(s) found — moderate severity. Document and discuss."
    elif interactions:
        summary = f"{len(interactions)} low-severity interaction(s) found. Note in records."
    else:
        summary = "No significant drug interactions identified."
    return DrugCheckResponse(interactions=interactions, summary=summary, proceed_with_caution=has_high or has_moderate)


# ──────────────────────────────────────────────────────────────────────────────
# PDF export
# ──────────────────────────────────────────────────────────────────────────────

class PDFWriter:
    def __init__(self, path: str) -> None:
        self.c = canvas.Canvas(path, pagesize=A4)
        self.w, self.h = A4
        self.left = 18 * mm
        self.right = self.w - 18 * mm
        self.top = self.h - 18 * mm
        self.bottom = 20 * mm
        self.y = self.top

    def _ensure(self, needed: float) -> None:
        if self.y - needed < self.bottom:
            self.c.showPage()
            self.y = self.top

    def line(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14) -> None:
        self._ensure(leading)
        self.c.setFont(font, size)
        self.c.drawString(self.left, self.y, str(text))
        self.y -= leading

    def wrapped(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14, bullet: str = "") -> None:
        max_w = self.right - self.left
        self.c.setFont(font, size)
        prefix = f"{bullet} " if bullet else ""
        indent = stringWidth(prefix, font, size) if bullet else 0
        usable = max_w - indent
        words = str(text).split()
        cur = ""
        first = True

        def flush(t: str, is_first: bool) -> None:
            self._ensure(leading)
            self.c.setFont(font, size)
            if bullet and is_first:
                self.c.drawString(self.left, self.y, prefix + t)
            elif bullet:
                self.c.drawString(self.left + indent, self.y, t)
            else:
                self.c.drawString(self.left, self.y, t)
            self.y -= leading

        for word in words:
            candidate = word if not cur else f"{cur} {word}"
            if stringWidth(candidate, font, size) <= usable:
                cur = candidate
            else:
                if cur:
                    flush(cur, first)
                    first = False
                cur = word
        if cur:
            flush(cur, first)

    def section(self, title: str) -> None:
        self.y -= 4
        self.line(title, font="Helvetica-Bold", size=12, leading=16)

    def save(self) -> None:
        self.c.save()


def export_safety_pdf(response: PreProcedureResponse) -> str:
    filename = safe_filename("safety_v2", response.request_id)
    path = os.path.join(EXPORT_DIR, filename)
    pdf = PDFWriter(path)
    pdf.line("AesthetiCite Pre-Procedure Safety Check", font="Helvetica-Bold", size=16, leading=20)
    pdf.line(f"Engine v{response.engine_version} · Knowledge {response.knowledge_revision} · {response.generated_at_utc}")
    pdf.line(
        f"Risk: {response.safety_assessment.overall_risk_score}/100 · Level: {response.safety_assessment.overall_risk_level} · Decision: {response.safety_assessment.decision.replace('_', ' ').upper()}",
        font="Helvetica-Bold", size=11, leading=16,
    )
    pdf.section("Safety Rationale")
    pdf.wrapped(response.safety_assessment.rationale)
    if response.caution_flags:
        pdf.section("Caution Flags")
        for flag in response.caution_flags:
            pdf.wrapped(flag, bullet="!")
    pdf.section("Top Complication Risks")
    for risk in response.top_risks:
        pdf.wrapped(f"{risk.complication.title()}: {risk.risk_score}/100 ({risk.risk_level})", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(risk.why_it_matters)
    pdf.section("Danger Zones")
    for zone in response.procedure_insight.danger_zones:
        pdf.wrapped(zone, bullet="⚠")
    pdf.section("Technique Notes")
    for note in response.procedure_insight.technical_notes:
        pdf.wrapped(note, bullet="→")
    pdf.section("Mitigation Steps")
    for i, step in enumerate(response.mitigation_steps, 1):
        pdf.wrapped(f"{i}. {step}")
    pdf.section("Evidence")
    for item in response.evidence:
        pdf.wrapped(f"[{item.source_id}] {item.title}", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(item.note)
        if item.citation_text:
            pdf.wrapped(f'"{item.citation_text}"')
    if response.related_papers:
        pdf.section("Recent Related Papers")
        for paper in response.related_papers:
            pdf.wrapped(f"{paper.get('title', '')} — {paper.get('journal', '')} {paper.get('date', '')}", bullet="•")
            if paper.get("url"):
                pdf.wrapped(paper["url"])
    pdf.section("Disclaimer")
    pdf.wrapped(response.disclaimer)
    pdf.save()
    return path


def export_protocol_pdf(response: ComplicationProtocolResponse) -> str:
    filename = safe_filename("protocol_v2", response.request_id)
    path = os.path.join(EXPORT_DIR, filename)
    pdf = PDFWriter(path)
    pdf.line("AesthetiCite Complication Protocol", font="Helvetica-Bold", size=16, leading=20)
    pdf.line(f"Protocol: {response.matched_protocol_name}", font="Helvetica-Bold", size=11)
    pdf.line(f"Severity: {response.severity.upper()} · Urgency: {response.urgency.upper()} · Risk: {response.risk_score}/100")
    pdf.section("Clinical Summary")
    pdf.wrapped(response.clinical_summary)
    pdf.section("Immediate Actions")
    for step in response.immediate_actions:
        pdf.wrapped(f"Step {step.step_number}: {step.action}", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(f"Rationale: {step.rationale}")
    pdf.section("Dose Guidance")
    for dose in response.dose_guidance:
        pdf.wrapped(f"{dose.substance}: {dose.recommendation}", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(dose.notes)
    pdf.section("Red Flags")
    for flag in response.red_flags:
        pdf.wrapped(flag, bullet="⚠")
    pdf.section("Escalation")
    for step in response.escalation:
        pdf.wrapped(step, bullet="→")
    pdf.section("Evidence")
    for item in response.evidence:
        pdf.wrapped(f"[{item.source_id}] {item.title}", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(item.note)
    pdf.section("Disclaimer")
    pdf.wrapped(response.disclaimer)
    pdf.save()
    return path


# ──────────────────────────────────────────────────────────────────────────────
# V2 Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/safety/v2/preprocedure-check", response_model=PreProcedureResponse)
def preprocedure_check_v2(payload: PreProcedureRequest) -> PreProcedureResponse:
    return run_preprocedure(payload)


@router.post("/api/safety/v2/preprocedure-check/export-pdf", response_model=ExportPDFResponse)
def preprocedure_check_pdf_v2(payload: PreProcedureRequest) -> ExportPDFResponse:
    response = run_preprocedure(payload)
    path = export_safety_pdf(response)
    return ExportPDFResponse(request_id=response.request_id, filename=os.path.basename(path), pdf_path=path)


@router.post("/api/safety/v2/preprocedure-check/batch", response_model=BatchPreProcedureResponse)
def preprocedure_check_batch_v2(payload: BatchPreProcedureRequest) -> BatchPreProcedureResponse:
    results = [run_preprocedure(item) for item in payload.items]
    return BatchPreProcedureResponse(
        batch_id=new_id(),
        generated_at_utc=now_utc_iso(),
        engine_version=ENGINE_VERSION,
        total=len(results),
        items=results,
        summary=summarize_batch(results),
    )


@router.get("/api/safety/v2/workspace-bootstrap", response_model=WorkspaceBootstrapResponse)
def workspace_bootstrap_v2() -> WorkspaceBootstrapResponse:
    return WorkspaceBootstrapResponse(
        engine_version=ENGINE_VERSION,
        knowledge_revision=KNOWLEDGE_REVISION,
        default_session_title="Session Safety Report",
        supported_experience_levels=["junior", "intermediate", "senior"],
        available_protocol_count=len(COMPLICATION_PROTOCOLS),
        ui_labels={
            "preprocedure_check": "AesthetiCite Pre-Procedure Safety Check",
            "session_report": "Session Safety Report",
            "complication_protocol": "Complication Protocol",
            "evidence": "Clinical Evidence",
            "danger_zones": "Danger Zones",
            "mitigation_steps": "Mitigation Steps",
        },
        feature_flags={
            "preprocedure_pdf_export": True,
            "protocol_pdf_export": True,
            "batch_preprocedure": True,
            "drug_checker": True,
            "case_logging": True,
            "paper_digest": True,
        },
    )


@router.post("/api/safety/v2/complications/protocol", response_model=ComplicationProtocolResponse)
def complication_protocol_v2(payload: ComplicationProtocolRequest) -> ComplicationProtocolResponse:
    return build_protocol_response(payload)


@router.get("/api/safety/v2/complications/protocols")
def list_complication_protocols_v2() -> List[Dict[str, Any]]:
    return [
        {"key": key, "name": proto["name"], "severity": proto["severity"],
         "urgency": proto["urgency"], "base_score": proto["base_score"],
         "keyword_count": len(proto["keywords"])}
        for key, proto in COMPLICATION_PROTOCOLS.items()
    ]


@router.post("/api/safety/v2/complications/export-pdf", response_model=ExportPDFResponse)
def complication_protocol_pdf_v2(payload: ComplicationProtocolRequest) -> ExportPDFResponse:
    response = build_protocol_response(payload)
    path = export_protocol_pdf(response)
    return ExportPDFResponse(request_id=response.request_id, filename=os.path.basename(path), pdf_path=path)


@router.post("/api/safety/v2/drug-check", response_model=DrugCheckResponse)
def drug_check_v2(payload: DrugCheckRequest) -> DrugCheckResponse:
    return check_drug_interactions(payload.medications, payload.planned_products)


@router.post("/api/safety/v2/log-case", response_model=CaseLogResponse)
def log_case_v2(payload: CaseLogRequest) -> CaseLogResponse:
    case_id = new_id()
    with db_cursor() as (_, cur):
        cur.execute("""
            INSERT INTO safety_cases
                (id, clinic_id, clinician_id, procedure, region, product_type,
                 technique, decision, risk_score, patient_factors_json, outcome, notes, created_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case_id, payload.clinic_id, payload.clinician_id, payload.procedure, payload.region,
            payload.product_type, payload.technique, payload.decision, payload.risk_score,
            json.dumps(payload.patient_factors.model_dump() if payload.patient_factors else {}),
            payload.outcome, payload.notes, now_utc_iso(),
        ))
    return CaseLogResponse(status="ok", case_id=case_id)


@router.get("/api/safety/v2/case-log")
def get_case_log_v2(clinic_id: Optional[str] = None, limit: int = Query(default=50, ge=1, le=500)) -> Dict[str, Any]:
    with db_cursor() as (_, cur):
        if clinic_id:
            cur.execute("SELECT * FROM safety_cases WHERE clinic_id = ? ORDER BY created_at_utc DESC LIMIT ?", (clinic_id, limit))
        else:
            cur.execute("SELECT * FROM safety_cases ORDER BY created_at_utc DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
    cases = [{k: row[k] for k in row.keys()} for row in rows]
    return {
        "total": len(cases),
        "cases": cases,
        "stats": {
            "by_procedure": dict(Counter(c["procedure"] for c in cases if c["procedure"])),
            "by_decision": dict(Counter(c["decision"] for c in cases if c["decision"])),
        },
    }


@router.get("/api/safety/v2/onboarding-hint", response_model=OnboardingHint)
def onboarding_hint_v2(procedure: str = "", region: str = "") -> OnboardingHint:
    return get_onboarding_hint(procedure, region)


@router.get("/api/safety/v2/paper-digest/{topic}")
def paper_digest_v2(topic: str) -> Dict[str, Any]:
    papers = fetch_related_papers(topic, "")
    return {"topic": topic, "papers": papers, "fetched_at_utc": now_utc_iso()}


# ══════════════════════════════════════════════════════════════════════════════
#  Complication Differential Endpoint  POST /api/safety/differential
# ══════════════════════════════════════════════════════════════════════════════

class DifferentialSymptoms(BaseModel):
    onset: str = Field(..., description="e.g. 'immediate', 'hours after', 'weeks after'")
    appearance: str = Field(..., description="e.g. 'pale/blanching', 'lump/nodule', 'erythema'")
    pain: str = Field(..., description="e.g. 'severe burning', 'mild tender', 'none'")
    location: str = Field(..., description="e.g. 'nose tip', 'tear trough', 'lip'")
    product_used: Optional[str] = None
    time_since_injection: Optional[str] = None


class DifferentialItem(BaseModel):
    rank: int
    diagnosis: str
    probability: Literal["high", "moderate", "low"]
    key_clues: List[str]
    immediate_actions: List[str]
    rule_out: List[str]
    escalation_note: Optional[str] = None


class DifferentialResponse(BaseModel):
    request_id: str
    generated_at_utc: str
    differentials: List[DifferentialItem]
    clinical_reminder: str


def _score_differential(symptoms: DifferentialSymptoms) -> List[DifferentialItem]:
    results: List[DifferentialItem] = []
    a = symptoms.appearance.lower()
    p = symptoms.pain.lower()
    o = symptoms.onset.lower()
    t = (symptoms.time_since_injection or "").lower()

    vo_score = (
        (3 if any(x in a for x in ["pale", "blanch", "white", "mottl", "livedo"]) else 0) +
        (2 if any(x in p for x in ["severe", "intense", "burning"]) else 0) +
        (2 if any(x in o for x in ["immediate", "during", "minutes"]) else 0)
    )
    if vo_score >= 2:
        results.append(DifferentialItem(
            rank=0, diagnosis="Vascular Occlusion (VO)",
            probability="high" if vo_score >= 5 else "moderate",
            key_clues=["Blanching, pallor, or mottled/livedo pattern", "Severe or burning pain", "Immediate or rapid onset", "Well-demarcated ischaemic zone"],
            immediate_actions=["STOP injection immediately — do not inject further", "Apply warm compress to affected area", "Inject hyaluronidase NOW if HA filler — do not wait", "Initiate vascular occlusion protocol", "Escalate if no improvement within 30–60 min"],
            rule_out=["Bruising (purplish, non-demarcated, resolves over days)", "Normal post-procedure erythema (diffuse, warm)", "Delayed-onset nodule (palpable, weeks later, no blanching)"],
            escalation_note="If visual symptoms develop — immediate ophthalmology emergency referral.",
        ))

    don_score = (
        (3 if any(x in a for x in ["lump", "nodule", "hard", "firm"]) else 0) +
        (2 if any(x in t for x in ["week", "month"]) else 0) +
        (1 if any(x in p for x in ["mild", "tender"]) else 0)
    )
    if don_score >= 2:
        results.append(DifferentialItem(
            rank=0, diagnosis="Delayed-Onset Nodule (DON)",
            probability="high" if don_score >= 4 else "moderate",
            key_clues=["Palpable firm nodule (days to months post-procedure)", "May be tender or asymptomatic", "Non-blanching", "Delayed onset"],
            immediate_actions=["Assess if filler-related vs inflammatory vs infected", "Use ultrasound if available to differentiate filler mass from abscess", "If HA filler: trial hyaluronidase", "If infected: culture, antibiotics, do not inject further"],
            rule_out=["Vascular occlusion (no blanching, no acute onset)", "Granuloma (late onset, inflammatory)", "Infection (warm, erythematous, fever)"],
            escalation_note=None,
        ))

    inf_score = (
        (2 if any(x in a for x in ["red", "erythema", "warm"]) else 0) +
        (3 if any(x in a for x in ["pus", "discharge"]) else 0) +
        (1 if any(x in t for x in ["week", "month"]) else 0) +
        (1 if "throb" in p else 0)
    )
    if inf_score >= 2:
        results.append(DifferentialItem(
            rank=0, diagnosis="Infection / Biofilm",
            probability="high" if inf_score >= 4 else "moderate",
            key_clues=["Erythema, warmth, swelling, tenderness", "Possible pus or discharge", "Onset days to weeks post-procedure", "Throbbing pain may suggest abscess"],
            immediate_actions=["Do NOT inject more filler", "Swab for culture if discharge present", "Start broad-spectrum antibiotics empirically", "Consider hyaluronidase if firm HA nodule", "Refer if no improvement in 48 hours"],
            rule_out=["Hypersensitivity (urticarial, rapid onset, no pus)", "Normal post-procedure swelling (resolves 24–48h)"],
            escalation_note="Biofilm may require prolonged antibiotics and product dissolution.",
        ))

    hs_score = (
        (3 if any(x in a for x in ["itch", "urtic", "hive", "rash"]) else 0) +
        (2 if any(x in o for x in ["immediate", "minutes"]) else 0) +
        (1 if "widespread" in symptoms.location.lower() else 0)
    )
    if hs_score >= 2:
        results.append(DifferentialItem(
            rank=0, diagnosis="Hypersensitivity / Anaphylaxis",
            probability="high" if hs_score >= 4 else "moderate",
            key_clues=["Urticaria, pruritus, or generalised erythema", "Rapid onset (minutes)", "May be widespread", "Throat tightness suggests anaphylaxis"],
            immediate_actions=["ASSESS airway, breathing, circulation FIRST", "If anaphylaxis: adrenaline 0.5mg IM IMMEDIATELY", "Call emergency services if systemic signs", "Antihistamine and corticosteroid as adjuncts", "Do not leave patient unattended"],
            rule_out=["Normal localised post-procedure erythema", "Vascular occlusion (ischaemic pattern, not urticarial)"],
            escalation_note="Anaphylaxis is an emergency — do not delay epinephrine.",
        ))

    tyndall_score = (
        (3 if any(x in a for x in ["blue", "grey", "gray", "discolour", "discolor"]) else 0) +
        (2 if any(x in symptoms.location.lower() for x in ["tear", "eye", "periorbital", "under"]) else 0) +
        (1 if any(x in t for x in ["week", "month"]) else 0)
    )
    if tyndall_score >= 2:
        results.append(DifferentialItem(
            rank=0, diagnosis="Tyndall Effect",
            probability="high" if tyndall_score >= 4 else "moderate",
            key_clues=["Blue-grey discolouration under the skin", "Periorbital or superficial injection site", "Gradual onset (not immediate)", "Typically painless"],
            immediate_actions=["Confirm clinically — Wood's lamp may help", "Plan hyaluronidase treatment for HA dissolution", "Counsel patient: may require multiple sessions", "Photograph and document"],
            rule_out=["Bruising (purple, resolves over days)", "Infection (warm, erythematous, painful)"],
            escalation_note=None,
        ))

    if not results:
        results.append(DifferentialItem(
            rank=1, diagnosis="Insufficient symptom data — further assessment required",
            probability="low",
            key_clues=["Symptom pattern does not match standard complication profiles"],
            immediate_actions=["Full clinical assessment", "Use ultrasound if available", "Consult an experienced colleague", "Treat as vascular occlusion if any blanching present"],
            rule_out=["Consider vascular occlusion in any post-filler concern with colour change or pain"],
            escalation_note=None,
        ))
        return results

    order = {"high": 0, "moderate": 1, "low": 2}
    results.sort(key=lambda r: order[r.probability])
    for i, r in enumerate(results):
        r.rank = i + 1
    return results


@router.post("/api/safety/differential", response_model=DifferentialResponse)
def complication_differential(payload: DifferentialSymptoms) -> DifferentialResponse:
    """
    POST /api/safety/differential
    Ranked complication differential from structured symptom input.
    Based on the CMAC 2025 complication framework.
    """
    diffs = _score_differential(payload)
    return DifferentialResponse(
        request_id=str(uuid.uuid4()),
        generated_at_utc=now_utc_iso(),
        differentials=diffs,
        clinical_reminder=(
            "This differential is clinical decision support only. "
            "In any post-filler concern with blanching, pallor, or ischaemic signs, "
            "treat as vascular occlusion until proven otherwise and act immediately."
        ),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Legacy-compatible aliases (backward compat for existing pages)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/safety/preprocedure-check", response_model=PreProcedureResponse)
def preprocedure_check_legacy(payload: PreProcedureRequest) -> PreProcedureResponse:
    return run_preprocedure(payload)


@router.post("/api/safety/preprocedure-check/export-pdf")
def preprocedure_check_pdf_legacy(payload: PreProcedureRequest):
    response = run_preprocedure(payload)
    path = export_safety_pdf(response)
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


@router.get("/api/safety/onboarding-hint", response_model=OnboardingHint)
def onboarding_hint_legacy(procedure: str = "", region: str = "") -> OnboardingHint:
    return get_onboarding_hint(procedure, region)


@router.post("/api/safety/complications/protocol", response_model=ComplicationProtocolResponse)
def complication_protocol_legacy(payload: ComplicationProtocolRequest) -> ComplicationProtocolResponse:
    return build_protocol_response(payload)


@router.post("/api/safety/drug-check", response_model=DrugCheckResponse)
def drug_check_legacy(payload: DrugCheckRequest) -> DrugCheckResponse:
    return check_drug_interactions(payload.medications, payload.planned_products)
