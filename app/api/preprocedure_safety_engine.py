"""
AesthetiCite Pre-Procedure Safety Engine v1.0.0
================================================
Predicts risk before treatment, identifies likely complications,
shows anatomical danger zones, suggests mitigation steps, and returns
a structured go / caution / high_risk decision with evidence hook and
one-click PDF export.

Endpoints
---------
POST /api/safety/preprocedure-check
POST /api/safety/preprocedure-check/export-pdf
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

router = APIRouter(prefix="/api/safety", tags=["AesthetiCite Pre-Procedure Safety"])

ENGINE_VERSION = "2.0.0"
KNOWLEDGE_REVISION = "2026-03-19"
EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

RiskLevel = Literal["low", "moderate", "high", "very_high"]
DecisionLevel = Literal["go", "caution", "high_risk"]
EvidenceStrength = Literal["limited", "moderate", "strong"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PatientFactors(BaseModel):
    prior_filler_in_same_area: Optional[bool] = None
    prior_vascular_event: Optional[bool] = None
    autoimmune_history: Optional[bool] = None
    allergy_history: Optional[bool] = None
    active_infection_near_site: Optional[bool] = None
    anticoagulation: Optional[bool] = None
    vascular_disease: Optional[bool] = None
    smoking: Optional[bool] = None
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


class EvidenceItem(BaseModel):
    source_id: str
    title: str
    note: str
    citation_text: Optional[str] = None
    source_type: Optional[str] = None
    relevance_score: Optional[float] = None


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


# ─── Ultrasound flag logic ────────────────────────────────────────────────────

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
    disclaimer: str


class ExportPDFResponse(BaseModel):
    request_id: str
    filename: str
    pdf_path: str


PROCEDURE_RULES: List[Dict[str, Any]] = [
    {
        "procedure_aliases": ["nasolabial fold filler", "nlf filler", "ha filler"],
        "region_aliases": ["nasolabial fold", "nlf"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 42,
        "complications": [
            ("vascular occlusion", 58, "This region is associated with important arterial territory and ischemic risk."),
            ("skin necrosis", 40, "Untreated vascular compromise can progress to tissue injury."),
            ("bruising", 28, "Vascular trauma risk is procedure- and technique-dependent."),
        ],
        "danger_zones": ["Angular artery territory", "Facial artery branches"],
        "plane": "Technique varies by anatomy and product; vascular awareness is critical.",
        "tech_notes": [
            "Small aliquots reduce catastrophic bolus risk.",
            "High suspicion is required for pain, blanching, or mottling.",
        ],
        "mitigation": [
            "Consider cannula when appropriate to reduce vessel penetration risk.",
            "Use small aliquots and avoid high-pressure injection.",
            "Inject slowly and reassess continuously.",
            "Have hyaluronidase immediately available if HA filler is used.",
        ],
        "evidence_strength": "moderate",
    },
    {
        "procedure_aliases": ["tear trough filler", "under eye filler"],
        "region_aliases": ["tear trough", "under eye", "infraorbital"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 48,
        "complications": [
            ("vascular occlusion", 52, "Periorbital anatomy makes vascular complications especially sensitive."),
            ("tyndall effect", 54, "Superficial HA placement can produce blue-gray discoloration."),
            ("edema", 45, "This area is prone to persistent swelling."),
        ],
        "danger_zones": ["Periorbital vascular territory", "Infraorbital region"],
        "plane": "Usually deeper, controlled placement is preferred; superficial placement increases Tyndall risk.",
        "tech_notes": [
            "Avoid superficial deposition.",
            "Product selection and volume discipline are critical.",
        ],
        "mitigation": [
            "Avoid superficial placement.",
            "Use conservative volume.",
            "Reassess symmetry before further product placement.",
            "Escalate immediately for pain, blanching, or visual symptoms.",
        ],
        "evidence_strength": "moderate",
    },
    {
        "procedure_aliases": ["lip filler", "lip augmentation"],
        "region_aliases": ["lip", "lips"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 38,
        "complications": [
            ("vascular occlusion", 47, "Lip vascularity requires careful injection planning."),
            ("swelling", 44, "Post-procedure swelling is common and can be significant."),
            ("bruising", 34, "The lip is highly vascular."),
        ],
        "danger_zones": ["Labial vascular territory"],
        "plane": "Technique varies by lip subunit and aesthetic objective.",
        "tech_notes": [
            "Avoid large bolus deposition.",
            "Careful reassessment helps avoid overcorrection.",
        ],
        "mitigation": [
            "Use controlled volume and slow injection.",
            "Avoid large boluses.",
            "Monitor for disproportionate pain or blanching.",
        ],
        "evidence_strength": "moderate",
    },
    {
        "procedure_aliases": ["glabellar toxin", "frown line botox", "glabella botox", "glabellar botox"],
        "region_aliases": ["glabella", "frown lines", "glabellar"],
        "product_aliases": ["botulinum toxin", "toxin", "botox", "dysport", "xeomin"],
        "base_risk": 24,
        "complications": [
            ("ptosis", 46, "Unwanted toxin diffusion can affect eyelid or brow function."),
            ("asymmetry", 32, "Uneven muscle effect may alter brow balance."),
            ("headache", 18, "Transient treatment-related symptoms can occur."),
        ],
        "danger_zones": ["Unwanted diffusion toward eyelid elevators"],
        "plane": "Target muscles and dose pattern vary by anatomy and facial dynamics.",
        "tech_notes": [
            "Differentiate brow heaviness from true eyelid ptosis.",
            "Precise placement matters more than total dose alone.",
        ],
        "mitigation": [
            "Respect diffusion risk near structures affecting eyelid position.",
            "Use conservative placement strategy in higher-risk anatomy.",
            "Document exact injection points and dose.",
        ],
        "evidence_strength": "moderate",
    },
    {
        "procedure_aliases": ["jawline filler", "chin filler", "cheek filler"],
        "region_aliases": ["jawline", "chin", "cheek"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "calcium hydroxylapatite", "filler"],
        "base_risk": 34,
        "complications": [
            ("vascular occlusion", 36, "Deep structural injection still requires vascular awareness."),
            ("asymmetry", 29, "Volumetric imbalance can become apparent after swelling settles."),
            ("nodules", 24, "Product placement and tissue plane influence palpability."),
        ],
        "danger_zones": ["Regional arterial branches vary by area"],
        "plane": "Plane depends on aesthetic goal, product, and anatomy.",
        "tech_notes": [
            "Respect regional anatomy and product rheology.",
            "Reassess after each increment.",
        ],
        "mitigation": [
            "Inject incrementally.",
            "Use anatomy-driven technique selection.",
            "Reassess projection and symmetry before additional product.",
        ],
        "evidence_strength": "limited",
    },
    {
        "procedure_aliases": ["forehead filler", "temple filler", "forehead botox", "temple botox"],
        "region_aliases": ["forehead", "temple", "frontal"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler", "botulinum toxin", "toxin", "botox"],
        "base_risk": 45,
        "complications": [
            ("vascular occlusion", 55, "Temple and forehead carry significant vascular density and anastomotic connections."),
            ("intracranial embolism", 30, "Superficial temporal and supratrochlear vessels have central connections."),
            ("skin necrosis", 28, "Ischemic injury in this territory can be vision- or life-threatening."),
        ],
        "danger_zones": ["Superficial temporal artery", "Supratrochlear artery", "Supraorbital artery"],
        "plane": "Requires deep periosteal plane for fillers; toxin targets frontalis and corrugators specifically.",
        "tech_notes": [
            "High-risk vascular territory — treat with same vigilance as glabella.",
            "Avoid injection over palpable vessels.",
        ],
        "mitigation": [
            "Deep periosteal placement preferred for fillers in this region.",
            "Avoid injection directly over palpable temporal vessels.",
            "Have full emergency protocol ready before starting.",
            "Use very small volumes per pass.",
        ],
        "evidence_strength": "moderate",
    },
    {
        "procedure_aliases": ["nose filler", "rhinoplasty filler", "nose reshaping filler", "non-surgical rhinoplasty"],
        "region_aliases": ["nose", "nasal", "nasal tip", "nasal bridge", "dorsum"],
        "product_aliases": ["hyaluronic acid filler", "ha filler", "filler"],
        "base_risk": 72,
        "complications": [
            ("vascular occlusion", 82, "The nasal dorsum and tip are among the highest-risk zones for ischemic events."),
            ("skin necrosis", 70, "Thin overlying skin and limited collateral supply make necrosis a real risk."),
            ("visual loss", 35, "Dorsal nasal vessels communicate with ophthalmic territory."),
        ],
        "danger_zones": ["Dorsal nasal artery", "Angular artery", "Ophthalmic territory connections"],
        "plane": "Supraperiosteal or deep subcutaneous preferred; superficial placement dramatically increases risk.",
        "tech_notes": [
            "This is one of the highest-risk aesthetic filler zones.",
            "Blanching at any stage = stop immediately.",
            "Expertise level matters significantly in this region.",
        ],
        "mitigation": [
            "Ensure hyaluronidase is immediately available at the start.",
            "Use smallest possible volumes and linear threading.",
            "Stop on any blanching or patient-reported pain change.",
            "Have ophthalmology emergency contact confirmed before starting.",
        ],
        "evidence_strength": "moderate",
    },
]


class EvidenceRetriever:
    def retrieve(self, request: PreProcedureRequest, matched_rule: Dict[str, Any]) -> List[EvidenceItem]:
        raise NotImplementedError


class DummyEvidenceRetriever(EvidenceRetriever):
    def retrieve(self, request: PreProcedureRequest, matched_rule: Dict[str, Any]) -> List[EvidenceItem]:
        proc = normalize(request.procedure)
        region = normalize(request.region)
        product = normalize(request.product_type)

        if "toxin" in product or "botox" in proc or "botox" in product:
            return [EvidenceItem(
                source_id="S30",
                title="Botulinum toxin adverse effects and ptosis management",
                note="Supports awareness of diffusion-related eyelid or brow effects.",
                citation_text="Ptosis after botulinum toxin is usually related to diffusion and is often temporary.",
                source_type="review",
                relevance_score=0.91,
            )]
        if "tear trough" in region or "infraorbital" in region:
            return [EvidenceItem(
                source_id="S20",
                title="Superficial HA filler placement and Tyndall effect",
                note="Supports caution about superficial placement in the tear trough.",
                citation_text="Superficial HA placement in the tear trough may produce blue-gray discoloration.",
                source_type="review",
                relevance_score=0.90,
            )]
        if "nose" in region or "nasal" in region:
            return [EvidenceItem(
                source_id="S42",
                title="Vascular complications of nasal filler — case series and management",
                note="Nasal filler carries the highest per-procedure risk of vision-threatening events.",
                citation_text="Nasal filler is associated with a disproportionately high rate of severe vascular complications.",
                source_type="case_series",
                relevance_score=0.97,
            )]
        return [EvidenceItem(
            source_id="S1",
            title="Expert consensus on vascular occlusion after HA filler",
            note="Supports strong preparation for ischemic complications in higher-risk filler regions.",
            citation_text="Rapid recognition and access to hyaluronidase are central to HA filler safety.",
            source_type="consensus_review",
            relevance_score=0.96,
        )]


def _build_default_retriever() -> EvidenceRetriever:
    if os.environ.get("AESTHETICITE_PGVECTOR_ENABLED", "0") == "1":
        try:
            from app.api.operational import _LiveEvidenceRetriever
            return _LiveEvidenceRetriever()
        except Exception:  # nosec B110
            pass
    return DummyEvidenceRetriever()


evidence_retriever: EvidenceRetriever = _build_default_retriever()


def alias_match(value: str, aliases: List[str]) -> bool:
    v = normalize(value)
    return any(a in v for a in aliases)


def match_rule(request: PreProcedureRequest) -> Dict[str, Any]:
    procedure = request.procedure
    region = request.region
    product = request.product_type

    best_rule: Optional[Dict[str, Any]] = None
    best_score = -1

    for rule in PROCEDURE_RULES:
        score = 0
        if alias_match(procedure, rule["procedure_aliases"]):
            score += 2
        if alias_match(region, rule["region_aliases"]):
            score += 2
        if alias_match(product, rule["product_aliases"]):
            score += 2
        if score > best_score:
            best_score = score
            best_rule = rule

    if not best_rule or best_score <= 0:
        raise HTTPException(status_code=404, detail="No matching pre-procedure rule found for this combination.")

    return best_rule


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def risk_level_from_score(score: int) -> RiskLevel:
    if score >= 75:
        return "very_high"
    if score >= 50:
        return "high"
    if score >= 25:
        return "moderate"
    return "low"


def decision_from_score(score: int) -> DecisionLevel:
    if score >= 70:
        return "high_risk"
    if score >= 35:
        return "caution"
    return "go"


def adjust_score(base: int, request: PreProcedureRequest) -> Tuple[int, List[str]]:
    """
    Adjust base risk score with patient-factor and technique modifiers.
    Returns (adjusted_score: int, caution_flags: List[str])
    """
    score = base
    flags: List[str] = []

    pf = request.patient_factors
    if pf:
        if pf.prior_vascular_event:
            score += 12
            flags.append("Prior vascular event significantly increases ischemic risk in this region.")
        if pf.active_infection_near_site:
            score += 15
            flags.append("Active infection near the injection site is a contraindication to proceeding.")
        if pf.anticoagulation:
            score += 8
            flags.append("Anticoagulation increases bruising and haematoma risk.")
        if pf.autoimmune_history:
            score += 5
            flags.append("Autoimmune history may increase inflammatory and nodule risk.")
        if pf.allergy_history:
            score += 4
            flags.append("Allergy history — confirm no known reaction to the planned product or its components.")
        if pf.vascular_disease:
            score += 8
            flags.append("Vascular disease increases occlusion risk and reduces tissue tolerance of ischaemia.")
        if pf.smoking:
            score += 5
            flags.append("Smoking impairs wound healing and increases vascular complication risk.")
        if pf.prior_filler_in_same_area:
            score += 3
            flags.append("Prior filler in same area: assess for residual product and altered anatomy.")
        if pf.glp1_patient:
            score += 6
            flags.append(
                "GLP-1 medication (semaglutide/tirzepatide): rapid facial fat loss alters volume "
                "distribution and may change filler requirements. Standard quantities risk overcorrection. "
                "Facial anatomy may differ from prior assessments. Reassess treatment plan accordingly."
            )

    tech = (request.technique or "").lower()
    if "needle" in tech:
        score += 6
    elif "cannula" in tech:
        score -= 4

    exp = request.injector_experience_level
    if exp == "junior":
        score += 8
        flags.append("Junior injector: strict supervision and emergency protocol preparedness is required.")
    elif exp == "senior":
        score -= 4

    return clamp(score, 0, 100), flags


def build_top_risks(rule: Dict[str, Any], overall_score: int) -> List[RiskItem]:
    items: List[RiskItem] = []
    modifier = int((overall_score - rule["base_risk"]) * 0.35)
    for comp, comp_score, why in rule["complications"]:
        final_score = clamp(comp_score + modifier, 0, 100)
        items.append(RiskItem(
            complication=comp,
            risk_score=final_score,
            risk_level=risk_level_from_score(final_score),
            why_it_matters=why,
        ))
    items.sort(key=lambda x: x.risk_score, reverse=True)
    return items


def build_response(request: PreProcedureRequest) -> PreProcedureResponse:
    """Build a full PreProcedureResponse for the given request."""
    rule = match_rule(request)
    score, flags = adjust_score(rule["base_risk"], request)

    if score < 35:
        level: RiskLevel = "low"
        decision: DecisionLevel = "go"
        rationale = (
            "Risk factors are within acceptable parameters for a competent injector with "
            "standard precautions and an emergency protocol in place."
        )
    elif score < 55:
        level = "moderate"
        decision = "caution"
        rationale = (
            "Moderate overall risk identified. Proceed with enhanced vigilance, conservative "
            "volume strategy, and active complication monitoring throughout the procedure."
        )
    elif score < 72:
        level = "high"
        decision = "high_risk"
        rationale = (
            "High risk profile. Ensure full emergency preparedness, confirm hyaluronidase "
            "availability, consider technique modification, and reassess whether to proceed today."
        )
    else:
        level = "very_high"
        decision = "high_risk"
        rationale = (
            "Very high risk. Strongly consider deferring or referring this procedure. "
            "If proceeding, maximum precaution, senior supervision, and immediate emergency "
            "access are essential."
        )

    top_risks = []
    for comp_name, comp_score, comp_why in rule["complications"]:
        adjusted_comp = min(100, comp_score + max(0, score - rule["base_risk"]))
        if adjusted_comp < 25:
            risk_level: RiskLevel = "low"
        elif adjusted_comp < 50:
            risk_level = "moderate"
        elif adjusted_comp < 70:
            risk_level = "high"
        else:
            risk_level = "very_high"
        top_risks.append(
            RiskItem(
                complication=comp_name,
                risk_score=adjusted_comp,
                risk_level=risk_level,
                why_it_matters=comp_why,
            )
        )
    top_risks.sort(key=lambda r: r.risk_score, reverse=True)

    us_recommended, us_note = get_ultrasound_flag(request.region)
    evidence = evidence_retriever.retrieve(request, rule)

    return PreProcedureResponse(
        request_id=str(uuid.uuid4()),
        generated_at_utc=now_utc_iso(),
        engine_version=ENGINE_VERSION,
        knowledge_revision=KNOWLEDGE_REVISION,
        safety_assessment=SafetyAssessment(
            overall_risk_score=score,
            overall_risk_level=level,
            decision=decision,
            rationale=rationale,
        ),
        top_risks=top_risks,
        procedure_insight=ProcedureInsight(
            procedure_name=rule.get("procedure_aliases", [request.procedure])[0],
            region=request.region,
            likely_plane_or_target=rule.get("plane"),
            danger_zones=rule.get("danger_zones", []),
            technical_notes=rule.get("tech_notes", []),
            ultrasound_recommended=us_recommended,
            ultrasound_note=us_note,
        ),
        mitigation_steps=rule["mitigation"],
        caution_flags=flags,
        evidence=evidence,
        disclaimer=(
            "This output is pre-procedure safety decision support, not a substitute for "
            "clinician judgment, anatomical expertise, product knowledge, or local emergency "
            "preparedness."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Complication Differential Endpoint
#  POST /api/safety/differential
# ═══════════════════════════════════════════════════════════════════════════════

class DifferentialSymptoms(BaseModel):
    """Structured symptom input for complication differential."""
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
    """
    Score differential diagnoses from symptom input.
    Based on the structured complication framework from CMAC 2025.
    """
    results: List[DifferentialItem] = []
    a = symptoms.appearance.lower()
    p = symptoms.pain.lower()
    o = symptoms.onset.lower()
    t = (symptoms.time_since_injection or "").lower()

    # ── Vascular Occlusion ─────────────────────────────────────────────────
    vo_score = (
        (3 if any(x in a for x in ["pale", "blanch", "white", "mottl", "livedo"]) else 0) +
        (2 if any(x in p for x in ["severe", "intense", "burning"]) else 0) +
        (2 if any(x in o for x in ["immediate", "during", "minutes"]) else 0)
    )
    if vo_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Vascular Occlusion (VO)",
            probability="high" if vo_score >= 5 else "moderate",
            key_clues=[
                "Blanching, pallor, or mottled/livedo pattern",
                "Severe or burning pain at/near injection site",
                "Immediate or rapid onset (during or minutes after injection)",
                "Well-demarcated ischaemic zone",
            ],
            immediate_actions=[
                "STOP injection immediately — do not inject further",
                "Apply warm compress to affected area",
                "Inject hyaluronidase NOW if HA filler — do not wait for confirmation",
                "Initiate vascular occlusion protocol (high-dose, repeated hyaluronidase)",
                "Escalate if blanching, pain, or mottling does not resolve within 30–60 min",
                "Have emergency ophthalmology contact if periorbital or nasal region",
            ],
            rule_out=[
                "Bruising (purplish, non-demarcated, resolves over days)",
                "Normal post-procedure erythema (diffuse, warm, resolves in hours)",
                "Delayed-onset nodule (palpable, weeks later, no blanching)",
            ],
            escalation_note=(
                "If visual symptoms develop (blurred vision, loss of visual field) — "
                "immediate ophthalmology emergency referral. This is a sight-threatening emergency."
            ),
        ))

    # ── Delayed-Onset Nodule ───────────────────────────────────────────────
    don_score = (
        (3 if any(x in a for x in ["lump", "nodule", "hard", "firm"]) else 0) +
        (2 if any(x in t for x in ["week", "month"]) else 0) +
        (1 if any(x in p for x in ["mild", "tender"]) else 0)
    )
    if don_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Delayed-Onset Nodule (DON)",
            probability="high" if don_score >= 4 else "moderate",
            key_clues=[
                "Palpable firm nodule (days to months post-procedure)",
                "May be tender or asymptomatic",
                "Non-blanching",
                "Delayed onset (not immediate)",
            ],
            immediate_actions=[
                "Assess if filler-related nodule vs inflammatory vs infected",
                "Use ultrasound if available to differentiate filler mass from abscess",
                "If HA filler: trial hyaluronidase injection",
                "If signs of infection: culture, antibiotics, do not inject further",
                "Photograph and document for follow-up tracking",
            ],
            rule_out=[
                "Vascular occlusion (no blanching, no acute onset in DON)",
                "Granuloma (typically late onset, inflammatory, firm — may need biopsy)",
                "Infection (warm, erythematous, fever possible)",
            ],
            escalation_note=None,
        ))

    # ── Infection / Biofilm ────────────────────────────────────────────────
    inf_score = (
        (2 if any(x in a for x in ["red", "erythema", "warm"]) else 0) +
        (3 if any(x in a for x in ["pus", "discharge"]) else 0) +
        (1 if any(x in t for x in ["week", "month"]) else 0) +
        (1 if "throb" in p else 0)
    )
    if inf_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Infection / Biofilm",
            probability="high" if inf_score >= 4 else "moderate",
            key_clues=[
                "Erythema, warmth, swelling, tenderness",
                "Possible pus or discharge",
                "Onset typically days to weeks post-procedure",
                "Throbbing pain may suggest abscess",
            ],
            immediate_actions=[
                "Do NOT inject more filler into or near the area",
                "Swab for culture if discharge present",
                "Start broad-spectrum antibiotics empirically",
                "Consider hyaluronidase if firm HA nodule with signs of infection",
                "Refer to appropriate specialist if no improvement in 48 hours",
                "Consider imaging (ultrasound) to assess for abscess",
            ],
            rule_out=[
                "Hypersensitivity (more urticarial, no pus, rapid onset)",
                "Normal post-procedure swelling (resolves within 24–48h, no erythema or warmth)",
                "Delayed-onset inflammatory nodule (no systemic signs, no fever)",
            ],
            escalation_note=(
                "Biofilm infections may require prolonged antibiotic courses and product dissolution. "
                "Multidrug resistance is possible with delayed-presentation biofilm."
            ),
        ))

    # ── Hypersensitivity / Anaphylaxis ─────────────────────────────────────
    hs_score = (
        (3 if any(x in a for x in ["itch", "urtic", "hive", "rash"]) else 0) +
        (2 if any(x in o for x in ["immediate", "minutes"]) else 0) +
        (1 if "widespread" in symptoms.location.lower() else 0)
    )
    if hs_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Hypersensitivity / Anaphylaxis",
            probability="high" if hs_score >= 4 else "moderate",
            key_clues=[
                "Urticaria, pruritus, or generalised erythema",
                "Rapid onset (typically within minutes)",
                "May be widespread or involve distant sites",
                "Throat tightness, wheeze, or hypotension suggest anaphylaxis",
            ],
            immediate_actions=[
                "ASSESS airway, breathing, circulation FIRST",
                "If anaphylaxis: adrenaline (epinephrine) 0.5mg IM (lateral thigh) IMMEDIATELY",
                "Call emergency services if systemic signs present",
                "Antihistamine and corticosteroid as adjunct (not primary treatment)",
                "Position patient supine with legs raised",
                "Do not leave patient unattended",
            ],
            rule_out=[
                "Normal post-procedure localised erythema (limited to injection site, not urticarial)",
                "Vascular occlusion (ischaemic pattern, not urticarial or widespread)",
            ],
            escalation_note=(
                "Anaphylaxis is an emergency — do not delay epinephrine. "
                "Have adrenaline auto-injector (EpiPen) in clinic at all times."
            ),
        ))

    # ── Tyndall Effect ─────────────────────────────────────────────────────
    tyndall_score = (
        (3 if any(x in a for x in ["blue", "grey", "gray", "discolour", "discolor"]) else 0) +
        (2 if any(x in symptoms.location.lower() for x in ["tear", "eye", "periorbital", "under"]) else 0) +
        (1 if any(x in t for x in ["week", "month"]) else 0)
    )
    if tyndall_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Tyndall Effect",
            probability="high" if tyndall_score >= 4 else "moderate",
            key_clues=[
                "Blue-grey discolouration under the skin",
                "Periorbital or superficial injection site",
                "Gradual onset (not immediate)",
                "Typically painless",
            ],
            immediate_actions=[
                "Confirm clinically — Wood's lamp may help",
                "Plan hyaluronidase treatment for HA filler dissolution",
                "Counsel patient: may require multiple treatment sessions",
                "Photograph and document",
                "Reassess depth and product selection for future treatments",
            ],
            rule_out=[
                "Bruising (purple, resolves over days, not persistent blue-grey)",
                "Infection (warm, erythematous, painful)",
            ],
            escalation_note=None,
        ))

    # ── Fallback ───────────────────────────────────────────────────────────
    if not results:
        results.append(DifferentialItem(
            rank=1,
            diagnosis="Insufficient symptom data — further assessment required",
            probability="low",
            key_clues=["Symptom pattern does not clearly match standard complication profiles"],
            immediate_actions=[
                "Perform a full clinical assessment",
                "Use ultrasound if available to assess local anatomy and filler position",
                "Consult an experienced colleague",
                "Treat as vascular occlusion until proven otherwise if any blanching is present",
            ],
            rule_out=["Consider vascular occlusion in any post-filler concern with colour change or pain"],
            escalation_note=None,
        ))
        return results

    order = {"high": 0, "moderate": 1, "low": 2}
    results.sort(key=lambda r: order[r.probability])
    for i, r in enumerate(results):
        r.rank = i + 1

    return results


@router.post("/differential", response_model=DifferentialResponse)
def complication_differential(payload: DifferentialSymptoms) -> DifferentialResponse:
    """
    POST /api/safety/differential
    Accepts a structured symptom description and returns a ranked
    complication differential with immediate action steps.
    Based on the structured complication framework from CMAC 2025.
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


class PDFWriter:
    def __init__(self, path: str) -> None:
        self.path = path
        self.c = canvas.Canvas(path, pagesize=A4)
        self.width, self.height = A4
        self.left = 18 * mm
        self.right = self.width - 18 * mm
        self.top = self.height - 18 * mm
        self.bottom = 18 * mm
        self.y = self.top

    def new_page(self) -> None:
        self.c.showPage()
        self.y = self.top

    def ensure_space(self, needed: float) -> None:
        if self.y - needed < self.bottom:
            self.new_page()

    def line(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14) -> None:
        self.ensure_space(leading)
        self.c.setFont(font, size)
        self.c.drawString(self.left, self.y, text)
        self.y -= leading

    def wrapped(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14, bullet: Optional[str] = None) -> None:
        max_width = self.right - self.left
        self.c.setFont(font, size)
        prefix = f"{bullet} " if bullet else ""
        indent_width = stringWidth(prefix, font, size) if bullet else 0
        usable_width = max_width - indent_width
        words = text.split()
        current = ""
        first = True

        def flush(line_text: str, is_first: bool) -> None:
            self.ensure_space(leading)
            self.c.setFont(font, size)
            if bullet:
                if is_first:
                    self.c.drawString(self.left, self.y, prefix + line_text)
                else:
                    self.c.drawString(self.left + indent_width, self.y, line_text)
            else:
                self.c.drawString(self.left, self.y, line_text)
            self.y -= leading

        for word in words:
            candidate = word if not current else f"{current} {word}"
            if stringWidth(candidate, font, size) <= usable_width:
                current = candidate
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


def export_pdf(response: PreProcedureResponse) -> str:
    filename = f"preprocedure_safety_{response.request_id}.pdf"
    path = os.path.join(EXPORT_DIR, filename)
    pdf = PDFWriter(path)

    pdf.line("AesthetiCite Pre-Procedure Safety Check", font="Helvetica-Bold", size=16, leading=20)
    pdf.line(f"Request ID: {response.request_id}")
    pdf.line(f"Generated: {response.generated_at_utc}")
    pdf.line(f"Engine v{response.engine_version}  |  Knowledge revision: {response.knowledge_revision}")
    decision_upper = response.safety_assessment.decision.replace("_", " ").upper()
    pdf.line(
        f"Overall Risk: {response.safety_assessment.overall_risk_score}/100  "
        f"Level: {response.safety_assessment.overall_risk_level}  "
        f"Decision: {decision_upper}"
    )

    pdf.section("Safety Assessment")
    pdf.wrapped(response.safety_assessment.rationale)

    if response.caution_flags:
        pdf.section("Caution Flags")
        for flag in response.caution_flags:
            pdf.wrapped(flag, bullet="!")

    pdf.section("Top Risks")
    for item in response.top_risks:
        pdf.wrapped(
            f"{item.complication.title()}: {item.risk_score}/100 ({item.risk_level})",
            font="Helvetica-Bold", bullet="•"
        )
        pdf.wrapped(item.why_it_matters, bullet=" ")

    pdf.section("Procedure Insight")
    pdf.wrapped(f"Procedure: {response.procedure_insight.procedure_name}", font="Helvetica-Bold")
    pdf.wrapped(f"Region: {response.procedure_insight.region}", bullet="•")
    if response.procedure_insight.likely_plane_or_target:
        pdf.wrapped(f"Plane/target: {response.procedure_insight.likely_plane_or_target}", bullet="•")
    for dz in response.procedure_insight.danger_zones:
        pdf.wrapped(f"Danger zone: {dz}", bullet="⚠")
    for note in response.procedure_insight.technical_notes:
        pdf.wrapped(note, bullet="→")

    pdf.section("Mitigation Steps")
    for step in response.mitigation_steps:
        pdf.wrapped(step, bullet="•")

    pdf.section("Evidence")
    for ev in response.evidence:
        pdf.wrapped(f"[{ev.source_id}] {ev.title}", font="Helvetica-Bold", bullet="•")
        pdf.wrapped(ev.note, bullet=" ")
        if ev.citation_text:
            pdf.wrapped(f'"{ev.citation_text}"', bullet=" ")

    pdf.section("Disclaimer")
    pdf.wrapped(response.disclaimer)

    pdf.save()
    return path


@router.post("/preprocedure-check", response_model=PreProcedureResponse)
def preprocedure_check(payload: PreProcedureRequest) -> PreProcedureResponse:
    return build_response(payload)


@router.post("/preprocedure-check/export-pdf", response_model=ExportPDFResponse)
def preprocedure_check_export_pdf(payload: PreProcedureRequest) -> ExportPDFResponse:
    response = build_response(payload)
    pdf_path = export_pdf(response)
    return ExportPDFResponse(
        request_id=response.request_id,
        filename=os.path.basename(pdf_path),
        pdf_path=pdf_path,
    )
