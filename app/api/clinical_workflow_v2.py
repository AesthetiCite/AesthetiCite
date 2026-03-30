"""
AesthetiCite Clinical Workflow v2
===================================
Implements improvements #5, #6, #7, #13:
  #5  — Ambient voice → structured consultation note
  #6  — Digital consent with audit trail tied to pre-procedure check
  #7  — Red flag pre-appointment questionnaire
  #13 — OpenMed NER for richer chunk tagging (inline, no external model required)

Add to main.py:
    from app.api.clinical_workflow_v2 import router as clinical_workflow_v2_router
    app.include_router(clinical_workflow_v2_router)

Add to server/routes.ts:
    app.post("/api/workflow/consultation-note", (req, res) => proxyToFastAPI(req, res, "/workflow/consultation-note"));
    app.post("/api/workflow/consent",           (req, res) => proxyToFastAPI(req, res, "/workflow/consent"));
    app.get ("/api/workflow/consent/:id",       (req, res) => proxyToFastAPI(req, res, `/workflow/consent/${req.params.id}`));
    app.post("/api/workflow/preflight",         (req, res) => proxyToFastAPI(req, res, "/workflow/preflight"));
    app.post("/api/workflow/tag-chunk",         (req, res) => proxyToFastAPI(req, res, "/workflow/tag-chunk"));
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflow", tags=["Clinical Workflow v2"])

OPENAI_API_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")

_STORE: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# Improvement #5 — Voice → Structured Consultation Note
# POST /workflow/consultation-note
# ─────────────────────────────────────────────────────────────────────────────

_NOTE_SYSTEM = """You are a medical scribe specialising in aesthetic injectable medicine.
Convert the clinician's spoken consultation summary into a structured clinical note.
The note must include ALL of the following sections, even if the spoken text is brief.

Output as valid JSON only. No prose, no markdown fences.

JSON schema:
{
  "patient_ref": "de-identified reference or 'Not provided'",
  "consultation_date": "YYYY-MM-DD or 'Not stated'",
  "procedure_intended": "procedure name",
  "region": "anatomical region",
  "product_type": "e.g. HA filler, botulinum toxin",
  "risk_score": null,
  "decision": null,
  "risk_factors_mentioned": ["list of any risk factors spoken by clinician"],
  "clinical_findings": "summary of relevant clinical findings",
  "plan": "treatment plan as discussed",
  "consent_obtained": true | false | null,
  "complications_discussed": ["list of complications discussed with patient"],
  "follow_up": "follow-up plan or 'Not stated'",
  "clinician_notes": "any additional notes",
  "ai_scribe_confidence": 0.0-1.0
}

Rules:
- Extract only what was explicitly said. Do not invent information.
- If the spoken text mentions a risk score, decision (go/caution/high_risk), extract it.
- Set ai_scribe_confidence based on how much of the schema you could reliably fill."""


class ConsultationNoteRequest(BaseModel):
    transcript: str = Field(..., min_length=10, description="Spoken consultation text or voice transcript")
    pre_procedure_result: Optional[Dict[str, Any]] = Field(
        None, description="Pre-procedure safety check result to merge in"
    )
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None


class ConsultationNoteResponse(BaseModel):
    note_id: str
    structured_note: Dict[str, Any]
    generated_at_utc: str
    model_used: str


@router.post(
    "/consultation-note",
    response_model=ConsultationNoteResponse,
    summary="Convert voice transcript to structured clinical note (Improvement #5)",
)
async def generate_consultation_note(req: ConsultationNoteRequest) -> ConsultationNoteResponse:
    """
    Takes a voice transcript (from /api/voice/transcribe or /api/transcribe)
    and returns a structured clinical note in JSON.
    If pre_procedure_result is provided, the risk score and decision are
    automatically merged from the safety check into the note.
    """
    extra_context = ""
    if req.pre_procedure_result:
        sa = req.pre_procedure_result.get("safety_assessment", {})
        extra_context = (
            f"\n\nPre-procedure check result (already computed):\n"
            f"  Risk score: {sa.get('overall_risk_score', 'N/A')}/100\n"
            f"  Decision: {sa.get('decision', 'N/A')}\n"
            f"  Procedure: {req.pre_procedure_result.get('procedure_insight', {}).get('procedure_name', 'N/A')}\n"
        )

    user_prompt = f"Clinician consultation transcript:\n{req.transcript}{extra_context}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                    "max_tokens": 800,
                    "messages": [
                        {"role": "system", "content": _NOTE_SYSTEM},
                        {"role": "user",   "content": user_prompt},
                    ],
                },
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                         "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            note_data = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Could not parse structured note from transcript.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Note generation failed: {e}")

    if req.pre_procedure_result:
        sa = req.pre_procedure_result.get("safety_assessment", {})
        note_data["risk_score"] = sa.get("overall_risk_score")
        note_data["decision"]   = sa.get("decision")

    note_id = uuid.uuid4().hex[:12]
    _STORE[f"note:{note_id}"] = {
        "note_id": note_id,
        "clinician_id": req.clinician_id,
        "clinic_id": req.clinic_id,
        "structured_note": note_data,
        "created_at": _now(),
    }

    return ConsultationNoteResponse(
        note_id=note_id,
        structured_note=note_data,
        generated_at_utc=_now(),
        model_used="gpt-4o-mini",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Improvement #6 — Digital Consent with Audit Trail
# POST /workflow/consent
# GET  /workflow/consent/{consent_id}
# ─────────────────────────────────────────────────────────────────────────────

class ConsentRequest(BaseModel):
    procedure: str
    region: str
    product_type: str
    risk_score: Optional[int] = None
    decision: Optional[str] = None
    top_risks: List[str] = []
    danger_zones: List[str] = []
    mitigation_steps: List[str] = []
    complications_discussed: List[str] = []
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    patient_ref: Optional[str] = None
    patient_signature_b64: Optional[str] = None
    patient_agreed: bool = False
    clinician_agreed: bool = False


class ConsentResponse(BaseModel):
    consent_id: str
    status: Literal["draft", "signed", "unsigned"]
    audit_hash: str
    generated_at_utc: str
    consent_text: str


def _build_consent_text(req: ConsentRequest) -> str:
    risks_str = "\n".join(f"  - {r}" for r in (req.top_risks or req.complications_discussed)[:8])
    danger_str = "\n".join(f"  - {z}" for z in req.danger_zones[:5])
    mitigation_str = "\n".join(f"  - {m}" for m in req.mitigation_steps[:6])

    decision_label = {
        "go": "Acceptable risk — standard precautions apply",
        "caution": "Elevated risk — enhanced precautions required",
        "high_risk": "High risk — clinician review strongly recommended before proceeding",
    }.get(req.decision or "", "Risk assessment not completed")

    score_str = f"{req.risk_score}/100" if req.risk_score is not None else "Not assessed"

    return f"""AESTHETIC INJECTABLE TREATMENT CONSENT FORM
Generated by AesthetiCite Clinical Safety Platform
Date: {_now()[:10]}

TREATMENT DETAILS
Procedure:    {req.procedure}
Region:       {req.region}
Product:      {req.product_type}
Risk Score:   {score_str} — {decision_label}

RISKS AND COMPLICATIONS
The following complications were discussed with the patient:
{risks_str if risks_str else "  - Standard injection risks (bruising, swelling, tenderness)"}

ANATOMICAL DANGER ZONES
The following high-risk anatomical areas are relevant to this treatment:
{danger_str if danger_str else "  - None specific to this procedure"}

SAFETY MEASURES
The following precautions will be taken:
{mitigation_str if mitigation_str else "  - Standard safe injection protocols"}

PATIENT ACKNOWLEDGEMENT
I confirm that:
1. The procedure, risks, and alternatives have been explained to me.
2. I have had the opportunity to ask questions.
3. I understand that complications can occur even with correct technique.
4. I consent to the treatment described above.
5. I understand this is clinical decision support, not a medical device diagnosis.

IMPORTANT: This consent was generated by AesthetiCite using AI-assisted risk assessment.
Clinical judgement supersedes all automated outputs.

DISCLAIMER: AesthetiCite is clinical decision support software. It does not replace
clinician training, anatomical knowledge, or emergency preparedness.
"""


@router.post(
    "/consent",
    response_model=ConsentResponse,
    summary="Generate and store digital consent form (Improvement #6)",
)
def create_consent(req: ConsentRequest) -> ConsentResponse:
    consent_text = _build_consent_text(req)
    audit_hash = hashlib.sha256(consent_text.encode()).hexdigest()
    consent_id = uuid.uuid4().hex[:14]

    status: Literal["draft", "signed", "unsigned"] = (
        "signed" if req.patient_agreed and req.clinician_agreed else
        "draft"  if not req.patient_agreed and not req.clinician_agreed else
        "unsigned"
    )

    record = {
        "consent_id": consent_id,
        "status": status,
        "audit_hash": audit_hash,
        "consent_text": consent_text,
        "procedure": req.procedure,
        "region": req.region,
        "risk_score": req.risk_score,
        "decision": req.decision,
        "patient_ref": req.patient_ref,
        "clinician_id": req.clinician_id,
        "clinic_id": req.clinic_id,
        "patient_agreed": req.patient_agreed,
        "clinician_agreed": req.clinician_agreed,
        "signature_present": bool(req.patient_signature_b64),
        "created_at": _now(),
    }
    _STORE[f"consent:{consent_id}"] = record

    return ConsentResponse(
        consent_id=consent_id,
        status=status,
        audit_hash=audit_hash,
        generated_at_utc=_now(),
        consent_text=consent_text,
    )


@router.get(
    "/consent/{consent_id}",
    summary="Retrieve a stored consent record",
)
def get_consent(consent_id: str) -> Dict[str, Any]:
    record = _STORE.get(f"consent:{consent_id}")
    if not record:
        raise HTTPException(status_code=404, detail=f"Consent {consent_id} not found")
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Improvement #7 — Red Flag Pre-Appointment Questionnaire
# POST /workflow/preflight
# ─────────────────────────────────────────────────────────────────────────────

RED_FLAG_RULES = [
    {
        "field":    "prior_vascular_event",
        "value":    True,
        "severity": "critical",
        "flag":     "History of prior vascular occlusion — highest risk factor for repeat event",
        "protocol": "vascular_occlusion",
    },
    {
        "field":    "active_infection_near_site",
        "value":    True,
        "severity": "critical",
        "flag":     "Active infection near treatment site — treatment should be deferred",
        "protocol": "infection_biofilm",
    },
    {
        "field":    "on_anticoagulants",
        "value":    True,
        "severity": "high",
        "flag":     "Anticoagulation — increased bruising and haematoma risk; review necessity",
        "protocol": None,
    },
    {
        "field":    "herpes_history_near_site",
        "value":    True,
        "severity": "high",
        "flag":     "Herpes simplex history near treatment site — consider prophylactic antiviral",
        "protocol": None,
    },
    {
        "field":    "autoimmune_condition",
        "value":    True,
        "severity": "moderate",
        "flag":     "Autoimmune history — may affect healing and complicate inflammatory interpretation",
        "protocol": None,
    },
    {
        "field":    "keloid_history",
        "value":    True,
        "severity": "moderate",
        "flag":     "Keloid history — may affect scar/nodule formation at injection sites",
        "protocol": None,
    },
    {
        "field":    "pregnant_or_breastfeeding",
        "value":    True,
        "severity": "critical",
        "flag":     "Pregnancy or breastfeeding — most injectable treatments are contraindicated",
        "protocol": None,
    },
    {
        "field":    "allergy_to_product_components",
        "value":    True,
        "severity": "critical",
        "flag":     "Known allergy to product components — treatment contraindicated",
        "protocol": "anaphylaxis",
    },
]


class PreflightQuestionnaire(BaseModel):
    prior_vascular_event:          bool = False
    active_infection_near_site:    bool = False
    on_anticoagulants:             bool = False
    herpes_history_near_site:      bool = False
    autoimmune_condition:          bool = False
    keloid_history:                bool = False
    pregnant_or_breastfeeding:     bool = False
    allergy_to_product_components: bool = False
    current_medications:           List[str] = []
    other_medical_conditions:      str = ""
    previous_aesthetic_treatments: str = ""
    patient_ref:                   Optional[str] = None
    intended_procedure:            Optional[str] = None
    clinician_id:                  Optional[str] = None


class PreflightResult(BaseModel):
    questionnaire_id: str
    red_flags: List[Dict[str, Any]]
    has_critical: bool
    has_high: bool
    risk_score_modifier: int
    triggered_protocols: List[str]
    recommended_action: str
    generated_at_utc: str


@router.post(
    "/preflight",
    response_model=PreflightResult,
    summary="Red flag pre-appointment questionnaire (Improvement #7)",
)
def evaluate_preflight(req: PreflightQuestionnaire) -> PreflightResult:
    """
    Patient fills this in before arrival. AesthetiCite evaluates it and:
    1. Surfaces critical/high red flags immediately to the clinician
    2. Computes a risk score modifier for the pre-procedure check
    3. Identifies protocols that should be pre-loaded for the appointment
    """
    flags: List[Dict[str, Any]] = []
    protocols: set = set()
    score_modifier = 0

    for rule in RED_FLAG_RULES:
        field_val = getattr(req, rule["field"], False)
        if field_val == rule["value"]:
            flags.append({
                "severity": rule["severity"],
                "flag":     rule["flag"],
                "field":    rule["field"],
                "protocol": rule["protocol"],
            })
            if rule["protocol"]:
                protocols.add(rule["protocol"])
            if rule["severity"] == "critical":
                score_modifier += 15
            elif rule["severity"] == "high":
                score_modifier += 8
            elif rule["severity"] == "moderate":
                score_modifier += 4

    dangerous_meds = [
        "warfarin", "apixaban", "rivaroxaban", "dabigatran", "clopidogrel",
        "aspirin", "ibuprofen", "naproxen", "methotrexate", "isotretinoin",
    ]
    for med in req.current_medications:
        for dm in dangerous_meds:
            if dm in med.lower():
                flags.append({
                    "severity": "high",
                    "flag": f"Medication flagged: {med} — review interaction with planned treatment",
                    "field": "current_medications",
                    "protocol": None,
                })
                score_modifier += 5
                break

    has_critical = any(f["severity"] == "critical" for f in flags)
    has_high     = any(f["severity"] == "high"     for f in flags)

    if has_critical:
        recommended_action = "DEFER treatment — discuss critical flags with clinician before any procedure"
    elif has_high:
        recommended_action = "CAUTION — review all flagged conditions before proceeding; consider deferral"
    elif flags:
        recommended_action = "REVIEW flagged items in consultation before commencing treatment"
    else:
        recommended_action = "No pre-appointment red flags detected — standard safety precautions apply"

    qid = uuid.uuid4().hex[:10]
    result = PreflightResult(
        questionnaire_id=qid,
        red_flags=flags,
        has_critical=has_critical,
        has_high=has_high,
        risk_score_modifier=min(score_modifier, 40),
        triggered_protocols=list(protocols),
        recommended_action=recommended_action,
        generated_at_utc=_now(),
    )
    _STORE[f"preflight:{qid}"] = {
        **result.dict(),
        "patient_ref": req.patient_ref,
        "intended_procedure": req.intended_procedure,
        "clinician_id": req.clinician_id,
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Improvement #13 — OpenMed-style NER for chunk tagging
# POST /workflow/tag-chunk  (also callable as a Python function)
# ─────────────────────────────────────────────────────────────────────────────

_NER_PATTERNS: Dict[str, List[str]] = {
    "product": [
        "juvederm", "restylane", "belotero", "teosyal", "sculptra", "radiesse",
        "botox", "dysport", "xeomin", "bocouture", "azzalure", "letybo",
        "hyaluronic acid", "HA filler", "PLLA", "CaHA", "polynucleotides",
        "hyaluronidase", "hyalase",
    ],
    "complication": [
        "vascular occlusion", "blanching", "skin necrosis", "necrosis",
        "Tyndall effect", "ptosis", "anaphylaxis", "infection", "biofilm",
        "nodule", "granuloma", "bruising", "haematoma", "mottling",
        "vision loss", "blindness", "diplopia", "embolism",
    ],
    "procedure": [
        "lip filler", "tear trough", "nasolabial fold", "rhinoplasty",
        "jawline", "chin filler", "temple", "forehead filler",
        "glabellar", "brow lift", "cheek augmentation", "non-surgical",
    ],
    "anatomical": [
        "angular artery", "facial artery", "supratrochlear", "supraorbital",
        "infraorbital", "dorsal nasal artery", "labial artery",
        "danger zone", "high risk zone", "periorbital", "glabella",
    ],
    "drug_class": [
        "anticoagulant", "NSAID", "SSRI", "corticosteroid", "retinoid",
        "isotretinoin", "warfarin", "aspirin", "immunosuppressant",
    ],
    "evidence_type": [
        "systematic review", "meta-analysis", "randomised controlled trial",
        "RCT", "cohort study", "case series", "case report", "expert consensus",
        "guideline", "IFU", "MHRA", "FDA", "CE mark",
    ],
}


def tag_chunk_ner(text: str, title: str = "") -> Dict[str, Any]:
    """
    Improvement #13: Run lightweight NER on a document chunk.
    Returns structured tag dict suitable for enriching chunk metadata.

    Call during document ingestion or at retrieval time:
        from app.api.clinical_workflow_v2 import tag_chunk_ner
        chunk["ner_tags"] = tag_chunk_ner(chunk["text"], chunk.get("title", ""))
    """
    combined = (f"{title} {text}").lower()
    tags: Dict[str, List[str]] = {}

    for category, patterns in _NER_PATTERNS.items():
        found = [p for p in patterns if p.lower() in combined]
        if found:
            tags[category] = found

    is_safety_critical = bool(tags.get("complication") or tags.get("anatomical"))
    has_product        = bool(tags.get("product"))
    evidence_strength  = (
        "strong" if any(t in tags.get("evidence_type", []) for t in
                        ["systematic review", "meta-analysis", "RCT", "randomised controlled trial"])
        else "moderate" if tags.get("evidence_type") else "weak"
    )

    return {
        "ner_tags":           tags,
        "is_safety_critical": is_safety_critical,
        "has_product":        has_product,
        "evidence_strength":  evidence_strength,
        "tag_count":          sum(len(v) for v in tags.values()),
    }


class TagChunkRequest(BaseModel):
    text: str
    title: str = ""


@router.post("/tag-chunk", summary="NER tagging for document chunk (Improvement #13)")
def tag_chunk_endpoint(req: TagChunkRequest) -> Dict[str, Any]:
    return tag_chunk_ner(req.text, req.title)
