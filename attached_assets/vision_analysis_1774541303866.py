"""
AesthetiCite Complication Vision Engine v1.0
============================================
POST /api/vision/analyse

Structured visual assessment of post-procedure clinical photos.
Positioned as: "AI highlights visual patterns that may indicate
complications and guides next steps" — NOT diagnosis.

Output:
  - Visual feature extraction (swelling, asymmetry, redness, contour)
  - Risk classification (low / moderate / high suspicion)
  - Suggested causes with confidence
  - Clinical action recommendation
  - Evidence layer with citations
  - Protocol links

Also provides:
  POST /api/vision/serial-compare  — compare two photos for healing progress
  GET  /api/vision/feature-glossary — glossary of visual features for clinicians

Mount in main.py:
    from app.api.vision_analysis import router as vision_router
    app.include_router(vision_router, prefix="/api/vision")

Express proxy (routes.ts):
    app.post("/api/vision/analyse",          (req, res) => proxyToFastAPI(req, res, "/api/vision/analyse"));
    app.post("/api/vision/serial-compare",   (req, res) => proxyToFastAPI(req, res, "/api/vision/serial-compare"));
    app.get ("/api/vision/feature-glossary", (req, res) => proxyToFastAPI(req, res, "/api/vision/feature-glossary"));
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from openai import OpenAI

logger = logging.getLogger(__name__)
router = APIRouter()

VISION_MODEL   = "gpt-4o"
COMPOSE_MODEL  = os.environ.get("COMPOSE_MODEL", "gpt-4o-mini")


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )


# ─────────────────────────────────────────────────────────────────
# Image store (shared with visual_differential.py)
# ─────────────────────────────────────────────────────────────────

_VISUAL_STORE: Dict[str, bytes] = {}

def register_visual(visual_id: str, image_bytes: bytes) -> None:
    _VISUAL_STORE[visual_id] = image_bytes

def _load_image(visual_id: str) -> Optional[bytes]:
    if visual_id in _VISUAL_STORE:
        return _VISUAL_STORE[visual_id]
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join("uploads", f"{visual_id}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
    return None

def _b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


# ─────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────

class VisionAnalysisRequest(BaseModel):
    visual_id: str
    procedure_type: Optional[str] = Field(None, description="e.g. lip filler, rhinoplasty, breast augmentation")
    days_post_procedure: Optional[int] = None
    injected_region: Optional[str] = None
    product_type: Optional[str] = None
    patient_symptoms: Optional[List[str]] = Field(default_factory=list)
    clinical_notes: Optional[str] = None
    ephemeral: bool = Field(False, description="Delete image after analysis")


class VisualFeature(BaseModel):
    feature: str          # e.g. "asymmetry", "erythema", "oedema"
    severity: str         # "absent" | "mild" | "moderate" | "marked"
    severity_score: int   # 0–10
    location: str         # anatomical location
    clinical_note: str    # what this feature means clinically
    flag: bool            # True if this feature alone is clinically significant


class RiskClassification(BaseModel):
    level: str            # "low" | "moderate" | "high"
    score: int            # 0–100
    label: str            # "Low suspicion" etc.
    rationale: str        # why this level
    colour: str           # "green" | "amber" | "red"


class SuggestedCause(BaseModel):
    rank: int
    cause: str
    category: str         # "vascular" | "infectious" | "inflammatory" | "mechanical" | "normal_healing"
    confidence: int       # 0–100
    confidence_label: str
    supporting_features: List[str]
    timeline_fit: str     # how the timing fits
    protocol_key: Optional[str] = None
    protocol_url: Optional[str] = None


class ClinicalAction(BaseModel):
    priority: str         # "immediate" | "urgent" | "review" | "monitor" | "reassure"
    action: str
    rationale: str
    timeframe: str        # e.g. "within 30 minutes", "today", "next 48 hours"
    escalation_trigger: Optional[str] = None


class EvidenceItem(BaseModel):
    source_id: str
    title: str
    note: str
    relevance: str        # "direct" | "supporting" | "contextual"
    source_type: str


class SerialCompareResult(BaseModel):
    change_summary: str
    improving_features: List[str]
    worsening_features: List[str]
    stable_features: List[str]
    overall_trajectory: str   # "improving" | "stable" | "worsening" | "mixed"
    clinical_interpretation: str
    recommended_action: str


class VisionAnalysisResponse(BaseModel):
    request_id: str
    visual_id: str
    generated_at_utc: str
    processing_ms: int
    image_quality: str        # "good" | "acceptable" | "poor"
    image_quality_note: str
    visual_features: List[VisualFeature]
    risk_classification: RiskClassification
    suggested_causes: List[SuggestedCause]
    primary_action: ClinicalAction
    secondary_actions: List[ClinicalAction]
    evidence: List[EvidenceItem]
    red_flags_present: List[str]
    reassuring_signs: List[str]
    next_review_recommendation: str
    imaging_indicated: bool
    imaging_rationale: Optional[str]
    disclaimer: str
    limitations: List[str]


# ─────────────────────────────────────────────────────────────────
# Protocol routing
# ─────────────────────────────────────────────────────────────────

PROTOCOL_MAP = {
    "vascular_occlusion_ha_filler":                   "/emergency?protocol=vascular_occlusion_ha_filler",
    "anaphylaxis_in_clinic":                           "/emergency?protocol=anaphylaxis_in_clinic",
    "tyndall_effect_ha_filler":                        "/complications?protocol=tyndall_effect_ha_filler",
    "botulinum_toxin_ptosis":                          "/complications?protocol=botulinum_toxin_ptosis",
    "infection_or_biofilm_after_filler":               "/complications?protocol=infection_or_biofilm_after_filler",
    "filler_nodules_inflammatory_or_noninflammatory":  "/complications?protocol=filler_nodules_inflammatory_or_noninflammatory",
}

CAUSE_CATEGORIES = {
    "vascular":      {"colour": "red",    "urgency": "immediate"},
    "infectious":    {"colour": "red",    "urgency": "urgent"},
    "inflammatory":  {"colour": "amber",  "urgency": "review"},
    "mechanical":    {"colour": "amber",  "urgency": "review"},
    "normal_healing":{"colour": "green",  "urgency": "monitor"},
}


# ─────────────────────────────────────────────────────────────────
# Vision prompt
# ─────────────────────────────────────────────────────────────────

VISION_SYSTEM = """You are AesthetiCite, a clinical safety AI for aesthetic medicine.

You are performing structured visual assessment of a clinical photograph
to identify patterns that may indicate post-procedure complications.

CRITICAL POSITIONING:
You are NOT diagnosing. You are:
- Extracting observable visual features
- Classifying risk level based on those features
- Suggesting possible causes that match the pattern
- Recommending clinical actions

SAFETY RULES:
1. Any blanching, pallor, mottling, or livedo → risk MUST be "high", cause must include vascular
2. Any signs of airway involvement (angioedema, tongue swelling) → immediate escalation
3. Erythema + warmth + swelling → include infection/biofilm in causes
4. Asymmetric ptosis → include botulinum toxin ptosis
5. Blue-grey discolouration → Tyndall effect must be in causes
6. Never say "diagnosed with" — say "pattern consistent with" or "features suggesting"
7. Always include reassuring signs if present
8. Return ONLY valid JSON. No prose before or after.

FEATURE SEVERITY SCALE:
0-2 = absent, 3-4 = mild, 5-6 = moderate, 7-10 = marked

PROTOCOL KEYS (use exactly):
vascular_occlusion_ha_filler | anaphylaxis_in_clinic | tyndall_effect_ha_filler
botulinum_toxin_ptosis | infection_or_biofilm_after_filler | filler_nodules_inflammatory_or_noninflammatory
"""

def _vision_prompt(req: VisionAnalysisRequest) -> str:
    ctx = []
    if req.procedure_type:          ctx.append(f"Procedure: {req.procedure_type}")
    if req.injected_region:         ctx.append(f"Region: {req.injected_region}")
    if req.product_type:            ctx.append(f"Product: {req.product_type}")
    if req.days_post_procedure is not None:
                                    ctx.append(f"Days post-procedure: {req.days_post_procedure}")
    if req.patient_symptoms:        ctx.append(f"Patient symptoms: {', '.join(req.patient_symptoms)}")
    if req.clinical_notes:          ctx.append(f"Notes: {req.clinical_notes}")

    ctx_block = "\n".join(ctx) if ctx else "No additional context provided."

    return f"""Perform a structured visual assessment of this clinical photograph.

Context:
{ctx_block}

Return JSON in EXACTLY this structure:
{{
  "image_quality": "good|acceptable|poor",
  "image_quality_note": "brief note on photo quality and any limitations",
  "visual_features": [
    {{
      "feature": "feature name (e.g. erythema, oedema, asymmetry, bruising, blanching, livedo, tyndall, ptosis, nodule, contour_irregularity)",
      "severity": "absent|mild|moderate|marked",
      "severity_score": 0,
      "location": "anatomical location",
      "clinical_note": "what this means clinically in 1 sentence",
      "flag": false
    }}
  ],
  "risk_classification": {{
    "level": "low|moderate|high",
    "score": 0,
    "label": "Low suspicion|Moderate suspicion|High suspicion — act now",
    "rationale": "1-2 sentences explaining why this risk level",
    "colour": "green|amber|red"
  }},
  "suggested_causes": [
    {{
      "rank": 1,
      "cause": "cause name",
      "category": "vascular|infectious|inflammatory|mechanical|normal_healing",
      "confidence": 0,
      "confidence_label": "High|Moderate|Low",
      "supporting_features": ["feature 1", "feature 2"],
      "timeline_fit": "how timing fits this cause",
      "protocol_key": "protocol_key or null"
    }}
  ],
  "primary_action": {{
    "priority": "immediate|urgent|review|monitor|reassure",
    "action": "specific action to take",
    "rationale": "why",
    "timeframe": "within X minutes/hours/days",
    "escalation_trigger": "what would change this to immediate (or null)"
  }},
  "secondary_actions": [
    {{
      "priority": "review|monitor",
      "action": "secondary action",
      "rationale": "why",
      "timeframe": "timeframe",
      "escalation_trigger": null
    }}
  ],
  "evidence": [
    {{
      "source_id": "S1",
      "title": "evidence title",
      "note": "relevance to findings",
      "relevance": "direct|supporting|contextual",
      "source_type": "guideline|review|consensus"
    }}
  ],
  "red_flags_present": ["list of concerning findings visible"],
  "reassuring_signs": ["list of reassuring findings visible"],
  "next_review_recommendation": "when to review this patient",
  "imaging_indicated": false,
  "imaging_rationale": "why imaging is or is not indicated (null if not indicated)"
}}

Include 4-6 visual features. List causes in descending likelihood. Always include at least one reassuring sign if present.
"""


# ─────────────────────────────────────────────────────────────────
# Response builder
# ─────────────────────────────────────────────────────────────────

def _confidence_label(score: int) -> str:
    return "High" if score >= 70 else "Moderate" if score >= 40 else "Low"

def _build_response(raw: Dict[str, Any], visual_id: str, request_id: str, ms: int) -> VisionAnalysisResponse:
    features = [
        VisualFeature(
            feature=f.get("feature", ""),
            severity=f.get("severity", "absent"),
            severity_score=int(f.get("severity_score", 0)),
            location=f.get("location", ""),
            clinical_note=f.get("clinical_note", ""),
            flag=bool(f.get("flag", False)),
        )
        for f in raw.get("visual_features", [])
    ]

    rc = raw.get("risk_classification", {})
    risk = RiskClassification(
        level=rc.get("level", "low"),
        score=int(rc.get("score", 0)),
        label=rc.get("label", "Low suspicion"),
        rationale=rc.get("rationale", ""),
        colour=rc.get("colour", "green"),
    )

    causes = []
    for c in raw.get("suggested_causes", []):
        pk = c.get("protocol_key") or None
        if pk and pk not in PROTOCOL_MAP:
            pk = None
        score = int(c.get("confidence", 50))
        causes.append(SuggestedCause(
            rank=int(c.get("rank", len(causes)+1)),
            cause=c.get("cause", ""),
            category=c.get("category", "inflammatory"),
            confidence=score,
            confidence_label=_confidence_label(score),
            supporting_features=c.get("supporting_features", []),
            timeline_fit=c.get("timeline_fit", ""),
            protocol_key=pk,
            protocol_url=PROTOCOL_MAP.get(pk) if pk else None,
        ))

    def _action(d: Dict) -> ClinicalAction:
        return ClinicalAction(
            priority=d.get("priority", "monitor"),
            action=d.get("action", ""),
            rationale=d.get("rationale", ""),
            timeframe=d.get("timeframe", ""),
            escalation_trigger=d.get("escalation_trigger") or None,
        )

    pa_raw = raw.get("primary_action", {})
    primary_action = _action(pa_raw)
    secondary_actions = [_action(a) for a in raw.get("secondary_actions", [])]

    evidence = [
        EvidenceItem(
            source_id=e.get("source_id", f"S{i+1}"),
            title=e.get("title", ""),
            note=e.get("note", ""),
            relevance=e.get("relevance", "supporting"),
            source_type=e.get("source_type", "review"),
        )
        for i, e in enumerate(raw.get("evidence", []))
    ]

    return VisionAnalysisResponse(
        request_id=request_id,
        visual_id=visual_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        processing_ms=ms,
        image_quality=raw.get("image_quality", "acceptable"),
        image_quality_note=raw.get("image_quality_note", ""),
        visual_features=features,
        risk_classification=risk,
        suggested_causes=causes,
        primary_action=primary_action,
        secondary_actions=secondary_actions,
        evidence=evidence,
        red_flags_present=raw.get("red_flags_present", []),
        reassuring_signs=raw.get("reassuring_signs", []),
        next_review_recommendation=raw.get("next_review_recommendation", ""),
        imaging_indicated=bool(raw.get("imaging_indicated", False)),
        imaging_rationale=raw.get("imaging_rationale") or None,
        disclaimer=(
            "AesthetiCite Vision highlights visual patterns that may indicate complications "
            "and guides next steps. It does not diagnose. All findings require clinician review. "
            "Escalate immediately for visual symptoms, signs of vascular compromise, or airway involvement."
        ),
        limitations=raw.get("limitations", [
            "Photo-based assessment cannot replace in-person clinical examination",
            "Image quality, lighting, and angle affect accuracy",
            "Clinical context not visible in the photograph may be relevant",
        ]),
    )


# ─────────────────────────────────────────────────────────────────
# Main endpoint
# ─────────────────────────────────────────────────────────────────

@router.post("/analyse", response_model=VisionAnalysisResponse)
def vision_analyse(req: VisionAnalysisRequest) -> VisionAnalysisResponse:
    start = time.time()
    request_id = str(uuid.uuid4())

    image_bytes = _load_image(req.visual_id)
    if not image_bytes:
        raise HTTPException(404, detail=f"Visual ID '{req.visual_id}' not found.")

    b64 = _b64(image_bytes)
    user_prompt = _vision_prompt(req)

    try:
        resp = _client().chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": VISION_SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                    {"type": "text", "text": user_prompt},
                ]},
            ],
            max_tokens=2500,
            temperature=0.1,
        )
    except Exception as e:
        logger.error(f"[VisionEngine] Model error: {e}")
        raise HTTPException(502, detail=f"Vision model unavailable: {str(e)[:120]}")

    raw_text = re.sub(r"```json|```", "", resp.choices[0].message.content or "").strip()

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"[VisionEngine] JSON parse error: {e}\nRaw: {raw_text[:400]}")
        raise HTTPException(500, detail="Model returned malformed JSON. Please retry.")

    ms = int((time.time() - start) * 1000)
    result = _build_response(raw, req.visual_id, request_id, ms)

    # Ephemeral delete
    if req.ephemeral:
        _VISUAL_STORE.pop(req.visual_id, None)
        for ext in ("jpg","jpeg","png","webp"):
            path = os.path.join("uploads", f"{req.visual_id}.{ext}")
            if os.path.exists(path):
                try: os.remove(path)
                except: pass

    return result


# ─────────────────────────────────────────────────────────────────
# Serial comparison endpoint
# ─────────────────────────────────────────────────────────────────

class SerialCompareRequest(BaseModel):
    visual_id_before: str
    visual_id_after: str
    days_between: Optional[int] = None
    procedure_type: Optional[str] = None
    clinical_notes: Optional[str] = None


@router.post("/serial-compare", response_model=SerialCompareResult)
def serial_compare(req: SerialCompareRequest) -> SerialCompareResult:
    before = _load_image(req.visual_id_before)
    after  = _load_image(req.visual_id_after)
    if not before:
        raise HTTPException(404, detail=f"Before image '{req.visual_id_before}' not found.")
    if not after:
        raise HTTPException(404, detail=f"After image '{req.visual_id_after}' not found.")

    ctx_parts = []
    if req.procedure_type:   ctx_parts.append(f"Procedure: {req.procedure_type}")
    if req.days_between:     ctx_parts.append(f"Days between photos: {req.days_between}")
    if req.clinical_notes:   ctx_parts.append(f"Notes: {req.clinical_notes}")
    ctx_block = "\n".join(ctx_parts) or "No context provided."

    prompt = f"""Compare these two clinical photographs: BEFORE (left/first) and AFTER (right/second).
Context: {ctx_block}

Assess:
1. Swelling change
2. Erythema change
3. Asymmetry change
4. Bruising/haematoma change
5. Overall healing trajectory

Return JSON:
{{
  "change_summary": "2-3 sentence summary of what changed",
  "improving_features": ["feature 1", ...],
  "worsening_features": ["feature 1", ...],
  "stable_features": ["feature 1", ...],
  "overall_trajectory": "improving|stable|worsening|mixed",
  "clinical_interpretation": "what this trajectory means clinically",
  "recommended_action": "concrete recommendation based on trajectory"
}}"""

    try:
        resp = _client().chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(before)}", "detail": "low"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(after)}",  "detail": "low"}},
                {"type": "text", "text": prompt},
            ]}],
            max_tokens=800,
            temperature=0.2,
        )
    except Exception as e:
        raise HTTPException(502, detail=f"Model unavailable: {str(e)[:120]}")

    raw = re.sub(r"```json|```", "", resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except:
        raise HTTPException(500, detail="Model returned malformed JSON.")

    return SerialCompareResult(
        change_summary=data.get("change_summary",""),
        improving_features=data.get("improving_features",[]),
        worsening_features=data.get("worsening_features",[]),
        stable_features=data.get("stable_features",[]),
        overall_trajectory=data.get("overall_trajectory","stable"),
        clinical_interpretation=data.get("clinical_interpretation",""),
        recommended_action=data.get("recommended_action",""),
    )


# ─────────────────────────────────────────────────────────────────
# Feature glossary
# ─────────────────────────────────────────────────────────────────

GLOSSARY = {
    "blanching":           {"definition": "Whitening of skin due to reduced blood flow. In the post-filler context, blanching is a red flag for vascular compromise.", "urgency": "immediate"},
    "livedo_reticularis":  {"definition": "Mottled, net-like reddish-blue discolouration indicating disrupted microcirculation. Associated with vascular occlusion.", "urgency": "immediate"},
    "erythema":            {"definition": "Redness of the skin. Localised post-procedure erythema is common; spreading or worsening erythema suggests infection.", "urgency": "context-dependent"},
    "oedema":              {"definition": "Swelling due to fluid accumulation. Expected early post-procedure; asymmetric or expanding oedema warrants review.", "urgency": "context-dependent"},
    "ecchymosis":          {"definition": "Bruising. Common post-injection; extensive bruising or haematoma requires assessment.", "urgency": "monitor"},
    "tyndall_effect":      {"definition": "Blue-grey discolouration from superficial HA filler placement scattering light. Not a vascular sign.", "urgency": "routine"},
    "asymmetry":           {"definition": "Unequal appearance between sides. Post-procedure swelling causes temporary asymmetry; persistent asymmetry needs review.", "urgency": "context-dependent"},
    "induration":          {"definition": "Hardening or firmness of tissue. May indicate fibrosis, biofilm, or granuloma formation.", "urgency": "same-day"},
    "fluctuance":          {"definition": "Fluid-filled swelling that compresses and rebounds. Suggests abscess or haematoma.", "urgency": "urgent"},
    "ptosis":              {"definition": "Drooping of the eyelid or brow. Post-toxin ptosis usually resolves; new onset ptosis requires assessment.", "urgency": "same-day"},
    "contour_irregularity":{"definition": "Uneven surface contour. Can indicate product migration, nodule formation, or uneven resorption.", "urgency": "routine"},
    "nodule":              {"definition": "Palpable lump. Can be inflammatory, infectious, or non-inflammatory filler deposition.", "urgency": "same-day"},
}

@router.get("/feature-glossary")
def feature_glossary():
    return {"features": GLOSSARY, "total": len(GLOSSARY)}
