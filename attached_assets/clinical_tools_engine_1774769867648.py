"""
app/api/clinical_tools_engine.py
=================================
AI-powered clinical tools engine for AesthetiCite.
Handles tools that require LLM reasoning beyond pure calculation.

Endpoints:
  POST /api/tools/glp1-assessment       — GLP-1 patient aesthetic impact
  POST /api/tools/vascular-risk         — Vascular occlusion risk scorer
  POST /api/tools/consent-checklist     — Treatment-specific consent generator
  POST /api/tools/aftercare             — Post-procedure aftercare generator
  POST /api/tools/toxin-dosing          — Region-specific toxin dosing guide

Mount in main.py:
    from app.api.clinical_tools_engine import router as tools_engine_router
    app.include_router(tools_engine_router)

Express proxy (server/routes.ts) — add these 5 routes:
    app.post("/api/tools/glp1-assessment",   (req,res) => proxyToFastAPI(req,res,"/api/tools/glp1-assessment"));
    app.post("/api/tools/vascular-risk",     (req,res) => proxyToFastAPI(req,res,"/api/tools/vascular-risk"));
    app.post("/api/tools/consent-checklist", (req,res) => proxyToFastAPI(req,res,"/api/tools/consent-checklist"));
    app.post("/api/tools/aftercare",         (req,res) => proxyToFastAPI(req,res,"/api/tools/aftercare"));
    app.post("/api/tools/toxin-dosing",      (req,res) => proxyToFastAPI(req,res,"/api/tools/toxin-dosing"));
"""

from __future__ import annotations
import json, logging, os, re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tools", tags=["Clinical Tools Engine"])
MODEL = "gpt-4o-mini"


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )


def _ask(system: str, user: str, max_tokens: int = 1000) -> Dict:
    try:
        r = _client().chat.completions.create(
            model=MODEL,
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            max_tokens=max_tokens, temperature=0.1,
        )
        raw = re.sub(r"```json|```","", r.choices[0].message.content or "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(500, detail=f"Model returned malformed JSON: {e}")
    except Exception as e:
        raise HTTPException(502, detail=f"Model unavailable: {str(e)[:120]}")


# ─────────────────────────────────────────────────────────────────
# 1. GLP-1 Patient Aesthetic Impact Assessment
# ─────────────────────────────────────────────────────────────────

class GLP1Request(BaseModel):
    drug_name: str                    # semaglutide, liraglutide, tirzepatide, dulaglutide
    duration_months: int              # how long on GLP-1
    weight_loss_kg: Optional[float]   # kg lost
    planned_treatment: str            # lip filler, cheek filler, full face, etc.
    sedation_planned: bool = False
    current_dose: Optional[str] = None

@router.post("/glp1-assessment")
def glp1_assessment(req: GLP1Request):
    system = """You are AesthetiCite, a clinical safety AI for aesthetic medicine.
    Return ONLY valid JSON. No prose. Be clinically precise."""
    user = f"""Assess aesthetic treatment implications for a patient on {req.drug_name}
for {req.duration_months} months, weight loss {req.weight_loss_kg or 'unknown'} kg.
Planned: {req.planned_treatment}. Sedation: {req.sedation_planned}.

Return JSON:
{{
  "risk_level": "standard|caution|high",
  "volume_change_assessment": "string — how GLP-1 affects treatment planning",
  "filler_recommendation": "HA|biostimulator|both|defer",
  "filler_rationale": "string",
  "sedation_guidance": "string or null",
  "fasting_protocol": "string — ASA 2023 guidance if sedation planned or null",
  "timing_recommendation": "string — when to treat relative to drug cycle",
  "key_considerations": ["list of 3-5 clinical points"],
  "contraindications": ["list or empty"],
  "follow_up": "string"
}}"""
    return _ask(system, user)


# ─────────────────────────────────────────────────────────────────
# 2. Vascular Occlusion Risk Scorer
# ─────────────────────────────────────────────────────────────────

class VascularRiskRequest(BaseModel):
    region: str           # e.g. glabella, nose, nasolabial fold, tear trough, lip
    product: str          # HA, CaHA, PLLA, collagen stimulator
    technique: str        # needle, cannula, bolus, linear threading, fanning
    layer: str            # subcutaneous, supraperiosteal, subdermal, intramuscular
    injector_level: str   # novice, intermediate, advanced, expert
    prior_treatment: bool = False

@router.post("/vascular-risk")
def vascular_risk(req: VascularRiskRequest):
    system = """You are AesthetiCite, a clinical safety AI.
    Return ONLY valid JSON. Be evidence-based and specific to anatomy."""
    user = f"""Score vascular occlusion risk for:
Region: {req.region} | Product: {req.product} | Technique: {req.technique}
Layer: {req.layer} | Injector level: {req.injector_level} | Prior treatment: {req.prior_treatment}

Return JSON:
{{
  "risk_score": 0-100,
  "risk_level": "low|moderate|high|critical",
  "risk_label": "string e.g. High risk — danger zone anatomy",
  "named_vessels_at_risk": ["specific vessel names"],
  "danger_zone": true/false,
  "danger_zone_description": "string or null",
  "technique_recommendation": "needle|cannula|either",
  "technique_rationale": "string",
  "layer_safety": "safe|caution|avoid",
  "layer_note": "string",
  "mitigation_steps": ["list of 3-5 specific steps"],
  "aspiration_recommended": true/false,
  "aspiration_note": "string",
  "red_flags_to_watch": ["list"],
  "evidence_note": "string — key reference"
}}"""
    return _ask(system, user)


# ─────────────────────────────────────────────────────────────────
# 3. Consent Checklist Generator
# ─────────────────────────────────────────────────────────────────

class ConsentRequest(BaseModel):
    treatment: str          # lip filler, toxin forehead, cheek augmentation, etc.
    patient_factors: Optional[List[str]] = None
    jurisdiction: str = "UK"

@router.post("/consent-checklist")
def consent_checklist(req: ConsentRequest):
    system = """You are AesthetiCite, a clinical safety AI for aesthetic medicine.
    Generate a UK-compliant consent checklist. Return ONLY valid JSON."""
    user = f"""Generate a treatment-specific consent checklist for: {req.treatment}
Patient factors: {req.patient_factors or 'none specified'}
Jurisdiction: {req.jurisdiction}

Return JSON:
{{
  "treatment": "{req.treatment}",
  "risks_common": ["list of common risks >1% — be specific"],
  "risks_uncommon": ["list of uncommon risks 0.1-1%"],
  "risks_rare_serious": ["list of rare but serious risks <0.1%"],
  "alternatives_discussed": ["list of alternatives to document"],
  "limitations": ["list of treatment limitations to discuss"],
  "post_care_summary": ["list of key aftercare points"],
  "when_to_seek_help": ["list of red flags to tell patient"],
  "cooling_off_note": "string — UK cooling off guidance",
  "documentation_checklist": ["list of items that must be documented"],
  "jccp_note": "string — JCCP/CQC specific note for UK practitioners"
}}"""
    return _ask(system, user, max_tokens=1500)


# ─────────────────────────────────────────────────────────────────
# 4. Post-Procedure Aftercare Generator
# ─────────────────────────────────────────────────────────────────

class AftercareRequest(BaseModel):
    treatment: str
    region: Optional[str] = None
    patient_factors: Optional[List[str]] = None

@router.post("/aftercare")
def aftercare_sheet(req: AftercareRequest):
    system = """You are AesthetiCite, a clinical safety AI.
    Generate patient-readable aftercare. Plain language. Return ONLY valid JSON."""
    user = f"""Generate aftercare instructions for: {req.treatment}
Region: {req.region or 'not specified'}
Patient factors: {req.patient_factors or 'none'}

Return JSON:
{{
  "treatment": "{req.treatment}",
  "what_to_expect": ["list — normal expected symptoms with timeline"],
  "first_24_hours": ["list of specific instructions"],
  "first_week": ["list of instructions"],
  "avoid": ["list of things to avoid and for how long"],
  "when_to_call_clinic": ["list of symptoms that need same-day contact"],
  "when_emergency": ["list of symptoms requiring 999/A&E"],
  "follow_up": "string — when to return",
  "results_timeline": "string — when to expect results",
  "patient_note": "string — one reassuring sentence for the patient"
}}"""
    return _ask(system, user)


# ─────────────────────────────────────────────────────────────────
# 5. Region-Specific Toxin Dosing Guide
# ─────────────────────────────────────────────────────────────────

class ToxinDosingRequest(BaseModel):
    region: str          # glabella, forehead, crow's feet, etc.
    product: str         # Botox, Dysport, Xeomin, Bocouture, Letybo, Azzalure
    patient_type: str    # average, strong muscles, first treatment, male, fine lines

@router.post("/toxin-dosing")
def toxin_dosing(req: ToxinDosingRequest):
    system = """You are AesthetiCite, a clinical safety AI for aesthetic injectables.
    Provide evidence-based dosing guidance. Return ONLY valid JSON."""
    user = f"""Provide dosing guidance for:
Region: {req.region} | Product: {req.product} | Patient: {req.patient_type}

Return JSON:
{{
  "region": "{req.region}",
  "product": "{req.product}",
  "total_dose_range_units": "string e.g. 20-40U",
  "injection_points": 0,
  "dose_per_point_units": "string",
  "manufacturer_approved": true/false,
  "manufacturer_dose": "string or null",
  "recommended_dilution_ml": "string",
  "concentration_units_per_ml": "string",
  "depth": "intradermal|subcutaneous|intramuscular",
  "technique_notes": ["list of technique points"],
  "onset_days": "string e.g. 3-5 days",
  "peak_days": "string",
  "duration_months": "string",
  "patient_type_adjustment": "string — how to modify for this patient type",
  "warnings": ["list of specific warnings for this region"],
  "contraindications": ["list or empty"],
  "evidence_note": "string"
}}"""
    return _ask(system, user)
