"""
AesthetiCite Vision Quality Engine
=====================================
Five improvements to the Vision Engine, in one additive module.

Improvement 1 — Image capture guidance (frontend companion: CaptureGuide.tsx)
  POST /visual/validate-capture   — scores image quality before GPT-4o analysis

Improvement 2 — Structured numeric output
  Extracts 7 trackable clinical scores from GPT-4o free text — no second LLM call.
  Call: extract_visual_scores(analysis_text) → VisualScores

Improvement 3 — Hardened injectable safety prompt
  Replaces the generic GPT-4o vision prompt.
  Call: build_injectable_safety_prompt(question, context_hint)

Improvement 4 — Fitzpatrick skin type detection
  POST /visual/fitzpatrick   — detects Fitzpatrick type I–VI from uploaded image

Improvement 5 — Fine-tune dataset accumulation
  POST /visual/training-case  — logs structured case for future model fine-tuning
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visual", tags=["Vision Quality Engine"])

EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _gpt4o_vision(
    base64_image: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 600,
    temperature: float = 0.1,
) -> str:
    """Single GPT-4o vision call. Returns the text response."""
    import httpx

    payload = {
        "model": "gpt-4o",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────────────────────────────────────
# IMPROVEMENT 3 — Hardened injectable safety prompt
# ─────────────────────────────────────────────────────────────────────────────

INJECTABLE_SAFETY_SYSTEM = """You are a clinical visual assessment assistant for aesthetic injectable medicine.

YOUR TASK: Describe only what is visually observable in this photograph. Do not diagnose. Do not infer causes. Do not speculate beyond what is directly visible.

FOCUS EXCLUSIVELY on these clinical signals relevant to injectable complications:

SKIN COLOUR & PERFUSION
- Blanching (white/pale areas suggesting absent blood flow)
- Mottling or livedo reticularis (irregular net-like discolouration)
- Dusky, violaceous, or cyanotic patches
- Erythema (redness, inflammation)
- Blue-grey discolouration (possible Tyndall effect from superficial HA filler)

TISSUE CHANGES
- Swelling or oedema (localised vs diffuse, pitting vs non-pitting appearance)
- Nodules, lumps, or firmness visible through skin contour change
- Signs of skin breakdown, eschar, or tissue loss
- Asymmetry compared to contralateral side

OCULAR / PERIOCULAR
- Eyelid position (ptosis, asymmetric lid height)
- Brow position and symmetry
- Periorbital swelling

SIGNS OF INFECTION
- Localised warmth indicated by skin changes
- Fluctuance or pointing (fluid collection visible)
- Purulent material

FITZPATRICK TYPE (estimate only)
- Estimate Fitzpatrick skin type I–VI based on visible skin tone.

FORMAT YOUR RESPONSE AS FOLLOWS — use exactly these section headers:

PERFUSION & COLOUR: [describe or "No abnormality observed"]
TISSUE CHANGES: [describe or "No abnormality observed"]
OCULAR/PERIOCULAR: [describe or "Not visible / No abnormality"]
INFECTION SIGNS: [describe or "No signs observed"]
FITZPATRICK ESTIMATE: [I / II / III / IV / V / VI — with brief rationale]
OVERALL OBSERVATION: [2–3 sentence clinical summary of visible findings]

HARD RULES:
- Do not use words: diagnose, diagnosis, confirmed, definitive, recommend treatment
- Do not name specific conditions unless you use the phrase "appearance consistent with"
- Do not advise on treatment
- If image quality is too poor to assess, say: IMAGE QUALITY: Insufficient for assessment
"""


def build_injectable_safety_prompt(
    question: str,
    context_hint: Optional[str] = None,
) -> str:
    """
    Build the user-turn prompt for GPT-4o vision analysis.
    context_hint: optional procedure context e.g. "48h post lip filler with HA"

    Usage in visual_counseling.py:
        from app.engine.vision_quality import build_injectable_safety_prompt, INJECTABLE_SAFETY_SYSTEM
        system = INJECTABLE_SAFETY_SYSTEM
        user   = build_injectable_safety_prompt(question, context_hint=procedure_context)
    """
    parts = []
    if context_hint:
        parts.append(f"Clinical context provided by clinician: {context_hint}")
    if question:
        parts.append(f"Clinician question: {question}")
    parts.append(
        "Please assess this image following the structured format in your instructions. "
        "Describe only what is visually observable."
    )
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# IMPROVEMENT 2 — Structured numeric output
# ─────────────────────────────────────────────────────────────────────────────

class VisualScores(BaseModel):
    skin_colour_change: Optional[int] = Field(
        None, ge=0, le=3,
        description="0=normal, 1=mild erythema, 2=mottling/dusky, 3=blanching/cyanosis"
    )
    swelling_severity: Optional[int] = Field(
        None, ge=0, le=3,
        description="0=none, 1=mild, 2=moderate, 3=severe/angioedema"
    )
    asymmetry_flag: Optional[bool] = Field(None, description="True if visible asymmetry noted")
    infection_signal: Optional[int] = Field(
        None, ge=0, le=3,
        description="0=none, 1=erythema only, 2=swelling+erythema, 3=fluctuance/purulent"
    )
    ptosis_flag: Optional[bool] = Field(None, description="True if eyelid/brow ptosis noted")
    fitzpatrick_type: Optional[str] = Field(None, description="I, II, III, IV, V, or VI")
    tyndall_flag: Optional[bool] = Field(None, description="True if blue-grey discolouration suggesting Tyndall effect noted")
    overall_concern_level: Literal["none", "low", "moderate", "high", "critical"] = Field(
        "none", description="Derived from all signals combined"
    )
    assessed_at_utc: str = Field(default_factory=_now)


def extract_visual_scores(analysis_text: str) -> VisualScores:
    """
    Extracts VisualScores from the structured output of the hardened prompt.
    Called immediately after GPT-4o returns its analysis text.
    Zero extra LLM calls — pure regex/keyword extraction.
    """
    if not analysis_text:
        return VisualScores()

    t = analysis_text.lower()

    # ── Skin colour / perfusion ──────────────────────────────────────────────
    colour_score: Optional[int] = None
    if any(w in t for w in ["blanching", "blanch", "pallor", "white area", "absent blood"]):
        colour_score = 3
    elif any(w in t for w in ["mottling", "livedo", "dusky", "violaceous", "cyanotic", "blue-grey", "blue-gray"]):
        colour_score = 2
    elif any(w in t for w in ["erythema", "redness", "red area", "inflamed"]):
        colour_score = 1
    elif "no abnormality" in t and "perfusion" in t:
        colour_score = 0

    # ── Swelling ─────────────────────────────────────────────────────────────
    swelling: Optional[int] = None
    if any(w in t for w in ["angioedema", "severe swelling", "significant oedema", "marked swelling"]):
        swelling = 3
    elif any(w in t for w in ["moderate swelling", "moderate oedema", "notable swelling"]):
        swelling = 2
    elif any(w in t for w in ["mild swelling", "mild oedema", "slight swelling", "slight puffiness"]):
        swelling = 1
    elif any(w in t for w in ["no swelling", "no oedema", "no abnormality"]):
        swelling = 0

    # ── Asymmetry ────────────────────────────────────────────────────────────
    asymmetry: Optional[bool] = None
    if any(w in t for w in ["asymmetr", "uneven", "unequal", "contralateral difference"]):
        asymmetry = True
    elif "no asymmetry" in t or "symmetrical" in t:
        asymmetry = False

    # ── Infection ────────────────────────────────────────────────────────────
    infection: Optional[int] = None
    if any(w in t for w in ["fluctuance", "purulent", "abscess", "pointing", "pus"]):
        infection = 3
    elif any(w in t for w in ["swelling and redness", "erythema and swelling", "inflammatory signs"]):
        infection = 2
    elif any(w in t for w in ["erythema", "redness"]) and "infection" not in t:
        infection = 1
    elif "no signs" in t and "infection" in t:
        infection = 0

    # ── Ptosis ───────────────────────────────────────────────────────────────
    ptosis: Optional[bool] = None
    if any(w in t for w in ["ptosis", "drooping eyelid", "lid droop", "eyelid droop", "brow ptosis", "brow drop", "asymmetric lid"]):
        ptosis = True
    elif any(w in t for w in ["normal eyelid", "no ptosis", "symmetric lid", "no abnormality observed"]):
        ptosis = False

    # ── Fitzpatrick ───────────────────────────────────────────────────────────
    fitzpatrick: Optional[str] = None
    fitz_match = re.search(
        r"fitzpatrick[^:]*:\s*(type\s*)?([ivIV]{1,3}|\d)",
        analysis_text,
        re.IGNORECASE,
    )
    if fitz_match:
        raw = fitz_match.group(2).upper().strip()
        digit_map = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}
        fitzpatrick = digit_map.get(raw, raw if raw in ("I", "II", "III", "IV", "V", "VI") else None)

    # ── Tyndall ───────────────────────────────────────────────────────────────
    tyndall: Optional[bool] = None
    if any(w in t for w in ["tyndall", "blue-grey", "blue-gray", "bluish discolouration", "blue discoloration"]):
        tyndall = True
    elif "no blue" in t or "no tyndall" in t:
        tyndall = False

    # ── Derive overall concern level ──────────────────────────────────────────
    concern: Literal["none", "low", "moderate", "high", "critical"] = "none"
    if colour_score == 3 or infection == 3:
        concern = "critical"
    elif colour_score == 2 or swelling == 3 or infection == 2 or ptosis is True:
        concern = "high"
    elif colour_score == 1 or swelling in (1, 2) or infection == 1 or tyndall is True or asymmetry is True:
        concern = "moderate"
    elif colour_score == 0 and swelling == 0 and infection == 0:
        concern = "none"
    else:
        concern = "low"

    return VisualScores(
        skin_colour_change=colour_score,
        swelling_severity=swelling,
        asymmetry_flag=asymmetry,
        infection_signal=infection,
        ptosis_flag=ptosis,
        fitzpatrick_type=fitzpatrick,
        tyndall_flag=tyndall,
        overall_concern_level=concern,
    )


# ─────────────────────────────────────────────────────────────────────────────
# IMPROVEMENT 1 — Image capture quality validation
# POST /visual/validate-capture
# ─────────────────────────────────────────────────────────────────────────────

_CAPTURE_SYSTEM = """You are a clinical image quality assessor for aesthetic medicine.
Evaluate the uploaded photograph for suitability as a clinical reference image.
Respond ONLY with valid JSON — no prose, no markdown fences.

JSON schema:
{
  "usable": true | false,
  "quality_score": 0-100,
  "issues": ["list of specific issues, empty if none"],
  "suggestions": ["list of actionable improvements, empty if none"],
  "lighting": "adequate | too_dark | too_bright | uneven",
  "focus": "sharp | slightly_blurred | blurred",
  "angle": "frontal | three_quarter | profile | oblique | unclear",
  "face_visible": true | false,
  "treatment_area_visible": true | false
}

Assess: lighting quality, focus/sharpness, angle consistency, face visibility,
treatment area visibility, background interference, filters/editing artefacts.
A usable image scores 60+. Be concise. No explanations outside the JSON."""


class CaptureValidationResponse(BaseModel):
    usable: bool
    quality_score: int = Field(..., ge=0, le=100)
    issues: List[str] = []
    suggestions: List[str] = []
    lighting: str
    focus: str
    angle: str
    face_visible: bool
    treatment_area_visible: bool
    validated_at_utc: str = Field(default_factory=_now)


@router.post(
    "/validate-capture",
    response_model=CaptureValidationResponse,
    summary="Score image quality before analysis — fast pre-flight check",
)
async def validate_capture(file: UploadFile = File(...)) -> CaptureValidationResponse:
    img_bytes = await file.read()
    if len(img_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 20MB)")

    b64 = base64.b64encode(img_bytes).decode()

    try:
        raw = await _gpt4o_vision(
            base64_image=b64,
            system_prompt=_CAPTURE_SYSTEM,
            user_prompt="Assess this image for clinical suitability. Return only the JSON object.",
            max_tokens=400,
            temperature=0.0,
        )
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(cleaned)
        return CaptureValidationResponse(**data, validated_at_utc=_now())

    except json.JSONDecodeError:
        logger.warning(f"[VisionQuality] Capture validation JSON parse failed: {raw[:200]}")
        return CaptureValidationResponse(
            usable=True,
            quality_score=50,
            issues=["Automatic quality assessment unavailable"],
            suggestions=["Ensure good lighting, sharp focus, and frontal angle"],
            lighting="adequate",
            focus="sharp",
            angle="frontal",
            face_visible=True,
            treatment_area_visible=True,
        )
    except Exception as e:
        logger.error(f"[VisionQuality] Capture validation failed: {e}")
        raise HTTPException(status_code=502, detail="Image quality check failed")


# ─────────────────────────────────────────────────────────────────────────────
# IMPROVEMENT 4 — Fitzpatrick skin type detection
# POST /visual/fitzpatrick
# ─────────────────────────────────────────────────────────────────────────────

_FITZPATRICK_SYSTEM = """You are a clinical skin type assessor for aesthetic medicine.
Estimate the Fitzpatrick skin phototype from this photograph.

Respond ONLY with valid JSON — no prose, no markdown fences.

JSON schema:
{
  "fitzpatrick_type": "I" | "II" | "III" | "IV" | "V" | "VI",
  "confidence": "high" | "moderate" | "low",
  "description": "one sentence skin tone description",
  "clinical_implications": {
    "laser_energy_device_risk": "low | moderate | high",
    "pih_risk": "low | moderate | high",
    "keloid_risk": "low | moderate | high",
    "notes": "one sentence clinical note relevant to aesthetic injectable medicine"
  },
  "caveat": "standard disclaimer about photo-based estimation limitations"
}

Fitzpatrick scale reference:
I   = Very fair, always burns, never tans
II  = Fair, usually burns, sometimes tans
III = Medium, sometimes burns, usually tans
IV  = Olive/light brown, rarely burns, always tans
V   = Brown, very rarely burns
VI  = Dark brown/black, never burns

Be conservative. Photo lighting, colour temperature, and filters significantly affect apparent skin tone.
Always include the caveat."""


class FitzpatrickResponse(BaseModel):
    fitzpatrick_type: Literal["I", "II", "III", "IV", "V", "VI"]
    confidence: Literal["high", "moderate", "low"]
    description: str
    clinical_implications: Dict[str, Any]
    caveat: str
    assessed_at_utc: str = Field(default_factory=_now)


@router.post(
    "/fitzpatrick",
    response_model=FitzpatrickResponse,
    summary="Estimate Fitzpatrick skin type with clinical implications",
)
async def detect_fitzpatrick(file: UploadFile = File(...)) -> FitzpatrickResponse:
    img_bytes = await file.read()
    b64 = base64.b64encode(img_bytes).decode()

    try:
        raw = await _gpt4o_vision(
            base64_image=b64,
            system_prompt=_FITZPATRICK_SYSTEM,
            user_prompt="Estimate the Fitzpatrick skin type. Return only the JSON object.",
            max_tokens=350,
            temperature=0.0,
        )
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(cleaned)
        return FitzpatrickResponse(**data, assessed_at_utc=_now())

    except json.JSONDecodeError:
        logger.warning(f"[VisionQuality] Fitzpatrick JSON parse failed: {raw[:200]}")
        raise HTTPException(
            status_code=422,
            detail="Fitzpatrick assessment returned unparseable response. Try a clearer image.",
        )
    except Exception as e:
        logger.error(f"[VisionQuality] Fitzpatrick detection failed: {e}")
        raise HTTPException(status_code=502, detail="Fitzpatrick assessment failed")


# ─────────────────────────────────────────────────────────────────────────────
# IMPROVEMENT 5 — Fine-tune dataset accumulation
# POST /visual/training-case + GET /visual/training-dataset/stats
# ─────────────────────────────────────────────────────────────────────────────

class TrainingCaseRequest(BaseModel):
    visual_id: Optional[str] = None
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_type: Optional[str] = None
    days_post_treatment: Optional[int] = None
    fitzpatrick_type: Optional[str] = None
    ai_detected_signals: List[str] = []
    ai_triggered_protocol: Optional[str] = None
    ai_concern_level: Optional[str] = None
    clinician_confirmed_signals: List[str] = Field(
        ..., description="What the clinician confirms is actually present in the image"
    )
    clinician_diagnosis: Optional[str] = Field(
        None, description="e.g. 'vascular occlusion', 'Tyndall effect', 'normal post-procedure swelling'"
    )
    clinician_corrected_protocol: Optional[str] = Field(
        None, description="If AI triggered wrong protocol, what should it have been"
    )
    outcome: Optional[Literal["resolved", "improving", "stable", "worsening", "referred", "unknown"]] = None
    ai_assessment_correct: Optional[bool] = Field(
        None, description="True if AI signals matched clinician ground truth"
    )
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    consent_obtained: bool = Field(
        ..., description="Clinician confirms patient consent for educational/research use of de-identified image data"
    )


class TrainingCaseResponse(BaseModel):
    status: str
    case_id: str
    logged_at_utc: str
    dataset_total: int


_TRAINING_CASES: List[Dict[str, Any]] = []
_LABEL_COUNTS: Dict[str, int] = {}


@router.post(
    "/training-case",
    response_model=TrainingCaseResponse,
    summary="Log a labelled visual case for fine-tune dataset accumulation",
)
def log_training_case(req: TrainingCaseRequest) -> TrainingCaseResponse:
    if not req.consent_obtained:
        raise HTTPException(
            status_code=400,
            detail="Patient consent must be confirmed before logging a training case.",
        )

    case_id = str(uuid.uuid4())
    logged_at = _now()

    record = req.dict()
    record["case_id"] = case_id
    record["logged_at_utc"] = logged_at

    _TRAINING_CASES.append(record)

    for signal in req.clinician_confirmed_signals:
        _LABEL_COUNTS[signal] = _LABEL_COUNTS.get(signal, 0) + 1
    if req.clinician_diagnosis:
        _LABEL_COUNTS[req.clinician_diagnosis] = _LABEL_COUNTS.get(req.clinician_diagnosis, 0) + 1

    logger.info(
        f"[VisionQuality] Training case logged: {case_id} | "
        f"diagnosis={req.clinician_diagnosis} | ai_correct={req.ai_assessment_correct} | "
        f"total={len(_TRAINING_CASES)}"
    )

    return TrainingCaseResponse(
        status="ok",
        case_id=case_id,
        logged_at_utc=logged_at,
        dataset_total=len(_TRAINING_CASES),
    )


@router.get(
    "/training-dataset/stats",
    summary="Dataset accumulation statistics — model readiness tracker",
)
def training_dataset_stats() -> Dict[str, Any]:
    total = len(_TRAINING_CASES)
    if total == 0:
        return {"total_cases": 0, "message": "No cases logged yet."}

    correct = sum(1 for c in _TRAINING_CASES if c.get("ai_assessment_correct") is True)
    assessed = sum(1 for c in _TRAINING_CASES if c.get("ai_assessment_correct") is not None)
    ai_accuracy = round(correct / assessed, 3) if assessed > 0 else None

    diagnosis_dist: Dict[str, int] = {}
    for c in _TRAINING_CASES:
        diag = c.get("clinician_diagnosis")
        if diag:
            diagnosis_dist[diag] = diagnosis_dist.get(diag, 0) + 1

    min_class_count = min(diagnosis_dist.values()) if diagnosis_dist else 0

    readiness = "not_ready"
    if min_class_count >= 500:
        readiness = "fine_tune_ready"
    elif min_class_count >= 100:
        readiness = "prompt_optimisation_ready"
    elif total >= 50:
        readiness = "early_accumulation"

    return {
        "total_cases": total,
        "ai_accuracy_rate": ai_accuracy,
        "cases_with_ai_assessment": assessed,
        "diagnosis_distribution": diagnosis_dist,
        "signal_label_counts": _LABEL_COUNTS,
        "fine_tune_readiness": readiness,
        "min_class_count": min_class_count,
        "target_per_class": 500,
        "progress_to_fine_tune": f"{min(round(min_class_count / 500 * 100), 100)}%",
    }
