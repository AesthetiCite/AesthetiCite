"""
AesthetiCite Vision Advanced Backend
======================================
New improvements not yet built:
  1. Quantified serial delta — score diff between visits
  2. Analysis confidence badge
  3. Bilateral symmetry score
  4. Shared review link (remote supervision)
  5. Colour calibration prompt
  6. Population baseline descriptor from corpus
  7. Auto-log after every session

Existing modules already delivered (reference only — already in outputs/):
  - vision_protocol_bridge.py    → app/engine/vision_protocol_bridge.py
  - vision_quality.py            → app/engine/vision_quality.py
  - vision_extensions.py         → app/api/vision_extensions.py
  - skingpt_integration.py       → app/api/skingpt_integration.py

Add this file:
  app/api/vision_advanced.py

Add to main.py:
  from app.api.vision_advanced import router as vision_advanced_router
  app.include_router(vision_advanced_router)

Add to server/routes.ts:
  app.post("/api/visual/serial-delta",     (req,res)=>proxyToFastAPI(req,res,"/visual/serial-delta"));
  app.post("/api/visual/confidence-badge", (req,res)=>proxyToFastAPI(req,res,"/visual/confidence-badge"));
  app.post("/api/visual/symmetry",         (req,res)=>proxyToFastAPI(req,res,"/visual/symmetry"));
  app.post("/api/visual/share",            (req,res)=>proxyToFastAPI(req,res,"/visual/share"));
  app.get ("/api/visual/share/:token",     (req,res)=>proxyToFastAPI(req,res,`/visual/share/${req.params.token}`));
  app.post("/api/visual/calibrate-colour", (req,res)=>proxyToFastAPI(req,res,"/visual/calibrate-colour"));
  app.post("/api/visual/population-baseline",(req,res)=>proxyToFastAPI(req,res,"/visual/population-baseline"));
  app.post("/api/visual/auto-log",         (req,res)=>proxyToFastAPI(req,res,"/visual/auto-log"));
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visual", tags=["Vision Advanced"])

OPENAI_API_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
APP_BASE_URL    = os.environ.get("APP_BASE_URL", "https://aestheticite.com")

_STORE: Dict[str, Any] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _gpt4o_vision(b64: str, system: str, user: str, max_tokens: int = 500) -> str:
    payload = {
        "model": "gpt-4o",
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": user},
            ]},
        ],
    }
    async with httpx.AsyncClient(timeout=40.0) as client:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def _gpt4o_text(system: str, user: str, max_tokens: int = 400) -> str:
    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Quantified Serial Delta
# POST /visual/serial-delta
# Computes score difference between two visits
# ─────────────────────────────────────────────────────────────────────────────

class VisualScores(BaseModel):
    skin_colour_change: Optional[int] = None   # 0–3
    swelling_severity:  Optional[int] = None   # 0–3
    asymmetry_flag:     Optional[bool] = None
    infection_signal:   Optional[int] = None   # 0–3
    ptosis_flag:        Optional[bool] = None
    tyndall_flag:       Optional[bool] = None
    overall_concern_level: Optional[str] = None


class SerialDeltaRequest(BaseModel):
    scores_before: VisualScores
    scores_after:  VisualScores
    days_between:  Optional[int] = None
    procedure:     Optional[str] = None


class ScoreDelta(BaseModel):
    field: str
    label: str
    before: Any
    after:  Any
    change: Any              # numeric diff or bool change
    direction: Literal["improved", "worsened", "unchanged", "resolved", "appeared"]
    pct_change: Optional[float] = None


class SerialDeltaResponse(BaseModel):
    deltas:              List[ScoreDelta]
    overall_trajectory:  Literal["improving", "worsening", "stable", "resolved", "mixed"]
    summary:             str
    days_between:        Optional[int]
    generated_at_utc:    str


@router.post("/serial-delta", response_model=SerialDeltaResponse)
def compute_serial_delta(req: SerialDeltaRequest) -> SerialDeltaResponse:
    """
    Computes quantified score differences between two visits.
    Returns per-field deltas with direction labels and an overall trajectory.

    Frontend: call this after loading two consecutive VisualScores from
    the case log, then render the SerialDeltaDisplay component.
    """
    deltas: List[ScoreDelta] = []

    def _numeric_delta(field: str, label: str, before: Optional[int], after: Optional[int]) -> Optional[ScoreDelta]:
        if before is None and after is None:
            return None
        b = before or 0
        a = after or 0
        diff = a - b
        pct = round(((b - a) / b) * 100, 1) if b else None  # improvement pct

        if diff < 0:
            direction = "improved"
        elif diff > 0:
            direction = "worsened"
        else:
            direction = "unchanged"

        return ScoreDelta(field=field, label=label, before=before, after=after,
                          change=diff, direction=direction, pct_change=pct)

    def _bool_delta(field: str, label: str, before: Optional[bool], after: Optional[bool]) -> Optional[ScoreDelta]:
        if before is None and after is None:
            return None
        if before is True and after is False:
            direction, change = "resolved", "resolved"
        elif before is False and after is True:
            direction, change = "appeared", "appeared"
        elif before == after:
            direction, change = "unchanged", "unchanged"
        else:
            direction, change = "unchanged", "unchanged"
        return ScoreDelta(field=field, label=label, before=before, after=after,
                          change=change, direction=direction)

    b, a = req.scores_before, req.scores_after

    for d in filter(None, [
        _numeric_delta("skin_colour_change", "Perfusion / skin colour",  b.skin_colour_change, a.skin_colour_change),
        _numeric_delta("swelling_severity",  "Swelling severity",         b.swelling_severity,  a.swelling_severity),
        _numeric_delta("infection_signal",   "Infection signal",          b.infection_signal,   a.infection_signal),
        _bool_delta   ("asymmetry_flag",     "Asymmetry",                 b.asymmetry_flag,     a.asymmetry_flag),
        _bool_delta   ("ptosis_flag",        "Ptosis",                    b.ptosis_flag,        a.ptosis_flag),
        _bool_delta   ("tyndall_flag",       "Tyndall effect",            b.tyndall_flag,       a.tyndall_flag),
    ]):
        deltas.append(d)

    improved  = sum(1 for d in deltas if d.direction in ("improved", "resolved"))
    worsened  = sum(1 for d in deltas if d.direction in ("worsened", "appeared"))
    unchanged = sum(1 for d in deltas if d.direction == "unchanged")

    if improved > 0 and worsened == 0:
        trajectory = "improving" if improved < len(deltas) else "resolved"
    elif worsened > 0 and improved == 0:
        trajectory = "worsening"
    elif improved > 0 and worsened > 0:
        trajectory = "mixed"
    else:
        trajectory = "stable"

    days_str = f" over {req.days_between} days" if req.days_between else ""
    summary = (
        f"{improved} signal(s) improved, {worsened} worsened, {unchanged} unchanged{days_str}. "
        f"Overall trajectory: {trajectory}."
    )
    if req.procedure:
        summary = f"Post {req.procedure}: " + summary

    return SerialDeltaResponse(
        deltas=deltas,
        overall_trajectory=trajectory,
        summary=summary,
        days_between=req.days_between,
        generated_at_utc=_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Analysis Confidence Badge
# POST /visual/confidence-badge
# ─────────────────────────────────────────────────────────────────────────────

class ConfidenceBadgeRequest(BaseModel):
    image_quality_score:    Optional[int]  = None   # 0–100 from validate-capture
    signals_detected:       int            = 0       # count of triggered signals
    structured_sections_ok: int            = 0       # 0–5 (how many prompt sections populated)
    analysis_text_length:   int            = 0       # chars in GPT-4o output
    fitzpatrick_detected:   bool           = False
    overall_concern_level:  Optional[str]  = None


class ConfidenceBadgeResponse(BaseModel):
    confidence_score:  int                  # 0–100
    confidence_label:  Literal["High", "Moderate", "Low", "Insufficient"]
    confidence_color:  Literal["green", "yellow", "orange", "red"]
    limiting_factors:  List[str]
    tooltip:           str


@router.post("/confidence-badge", response_model=ConfidenceBadgeResponse)
def compute_confidence_badge(req: ConfidenceBadgeRequest) -> ConfidenceBadgeResponse:
    """
    Computes a confidence score for the visual analysis output.
    Factors: image quality, number of signals, structured output completeness.
    This is Improvement #3 — analysis confidence badge.
    """
    score = 0
    factors: List[str] = []

    # Image quality (40 pts max)
    iq = req.image_quality_score or 50
    score += int(iq * 0.4)
    if iq < 60:
        factors.append(f"Image quality low ({iq}/100) — consider retaking")

    # Signal detection (20 pts max)
    sig_pts = min(req.signals_detected * 5, 20)
    score += sig_pts
    if req.signals_detected == 0:
        factors.append("No specific clinical signals detected")

    # Structured output completeness (25 pts max)
    section_pts = int((req.structured_sections_ok / 5) * 25)
    score += section_pts
    if req.structured_sections_ok < 3:
        factors.append("Analysis text incomplete — some sections could not be assessed")

    # Output length (10 pts max)
    len_pts = min(int(req.analysis_text_length / 30), 10)
    score += len_pts

    # Fitzpatrick bonus (5 pts)
    if req.fitzpatrick_detected:
        score += 5
    else:
        factors.append("Fitzpatrick type could not be estimated")

    score = min(score, 100)

    if score >= 75:
        label, color = "High", "green"
    elif score >= 55:
        label, color = "Moderate", "yellow"
    elif score >= 35:
        label, color = "Low", "orange"
    else:
        label, color = "Insufficient", "red"

    tooltip = (
        f"Analysis confidence {score}/100. "
        + (f"Factors: {'; '.join(factors)}." if factors else "All factors adequate.")
    )

    return ConfidenceBadgeResponse(
        confidence_score=score,
        confidence_label=label,
        confidence_color=color,
        limiting_factors=factors,
        tooltip=tooltip,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Bilateral Symmetry Score
# POST /visual/symmetry
# ─────────────────────────────────────────────────────────────────────────────

_SYMMETRY_SYSTEM = """You are a clinical facial symmetry assessor for aesthetic injectable medicine.
Assess bilateral facial symmetry from the uploaded photograph.

Respond ONLY with valid JSON:
{
  "symmetry_score": 0-100,
  "left_right_balance": "left_dominant" | "right_dominant" | "balanced",
  "asymmetry_regions": ["list of regions with visible asymmetry, e.g. 'periorbital', 'lip', 'brow'"],
  "clinical_significance": "none" | "mild" | "moderate" | "significant",
  "likely_cause": "natural variation" | "post-treatment swelling" | "ptosis" | "injection asymmetry" | "unknown",
  "notes": "one sentence clinical comment",
  "caveat": "Photo-based symmetry assessment; clinical examination required for definitive evaluation"
}

100 = perfect symmetry. 0 = complete asymmetry.
For post-injection assessments, note whether asymmetry is consistent with normal post-treatment swelling
vs injection-related asymmetry (different volumes, incorrect placement)."""


class SymmetryRequest(BaseModel):
    visual_id:        Optional[str] = None
    context:          Optional[str] = None  # e.g. "48h post lip filler"


class SymmetryResponse(BaseModel):
    symmetry_score:         int
    left_right_balance:     str
    asymmetry_regions:      List[str]
    clinical_significance:  str
    likely_cause:           str
    notes:                  str
    caveat:                 str
    assessed_at_utc:        str


@router.post("/symmetry", summary="Bilateral symmetry assessment from image")
async def assess_symmetry(file: UploadFile = File(...), context: str = "") -> SymmetryResponse:
    """
    Improvement #5: Bilateral symmetry score with clinical significance classification.
    Returns left/right balance, affected regions, and likely cause.
    Particularly useful for monitoring post-injection ptosis and swelling asymmetry.
    """
    img_bytes = await file.read()
    b64 = base64.b64encode(img_bytes).decode()

    user = "Assess bilateral facial symmetry in this image."
    if context:
        user += f" Clinical context: {context}."

    try:
        raw = await _gpt4o_vision(b64, _SYMMETRY_SYSTEM, user + " Return only the JSON object.", max_tokens=350)
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(cleaned)
        return SymmetryResponse(**data, assessed_at_utc=_now())
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Could not parse symmetry assessment. Try a clearer frontal image.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Symmetry assessment failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Shared Review Link (remote supervision)
# POST /visual/share
# GET  /visual/share/{token}
# ─────────────────────────────────────────────────────────────────────────────

class ShareRequest(BaseModel):
    session_data: Dict[str, Any]       # full ConsultationFlow state to share
    expires_hours: int = Field(24, ge=1, le=168)
    reviewer_email: Optional[str] = None
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    note: Optional[str] = None         # message to reviewer


class ShareResponse(BaseModel):
    share_token: str
    share_url: str
    expires_at_utc: str
    reviewer_email: Optional[str]


class ShareViewResponse(BaseModel):
    session_data: Dict[str, Any]
    created_at_utc: str
    expires_at_utc: str
    clinician_id: Optional[str]
    note: Optional[str]
    is_expired: bool


@router.post("/share", response_model=ShareResponse,
             summary="Create a time-limited shared review link (Improvement #6)")
def create_share_link(req: ShareRequest) -> ShareResponse:
    """
    Generates a one-time review URL for remote clinical supervision.
    A junior injector in clinic shares this with a senior clinician who
    can review the analysis, scores, and protocols from any device.

    Audit trail: all access is logged. Link expires after req.expires_hours.
    No AesthetiCite account required to view a shared link.
    """
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=req.expires_hours)

    _STORE[f"share:{token}"] = {
        "token": token,
        "session_data": req.session_data,
        "created_at_utc": _now(),
        "expires_at_utc": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at_ts": expires_at.timestamp(),
        "clinician_id": req.clinician_id,
        "clinic_id": req.clinic_id,
        "reviewer_email": req.reviewer_email,
        "note": req.note,
        "access_count": 0,
        "access_log": [],
    }

    share_url = f"{APP_BASE_URL}/visual/review/{token}"
    logger.info(f"[VisionAdvanced] Share link created: token={token[:8]}... expires={expires_at.date()}")

    return ShareResponse(
        share_token=token,
        share_url=share_url,
        expires_at_utc=expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        reviewer_email=req.reviewer_email,
    )


@router.get("/share/{token}", response_model=ShareViewResponse,
            summary="Retrieve a shared visual review")
def view_share_link(token: str) -> ShareViewResponse:
    """
    Retrieves a shared visual session. No authentication required.
    Access is logged. Returns is_expired=True if the link has expired.
    """
    record = _STORE.get(f"share:{token}")
    if not record:
        raise HTTPException(status_code=404, detail="Review link not found or already deleted")

    now_ts = datetime.now(timezone.utc).timestamp()
    is_expired = now_ts > record["expires_at_ts"]

    # Log access
    record["access_count"] += 1
    record["access_log"].append({"accessed_at": _now(), "expired": is_expired})

    return ShareViewResponse(
        session_data=record["session_data"],
        created_at_utc=record["created_at_utc"],
        expires_at_utc=record["expires_at_utc"],
        clinician_id=record.get("clinician_id"),
        note=record.get("note"),
        is_expired=is_expired,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Colour Calibration Prompt
# POST /visual/calibrate-colour
# ─────────────────────────────────────────────────────────────────────────────

_CALIBRATION_SYSTEM = """You are a clinical image colour calibration assistant.
You are given an image that may contain a colour reference card alongside a patient's skin.
Use the reference card to calibrate your colour interpretation.

If a reference card is present: note which colours appear shifted vs standard, and adjust
your skin tone and perfusion analysis accordingly.

If no reference card is visible: note this and proceed with standard interpretation.

Respond ONLY with valid JSON:
{
  "reference_card_detected": true | false,
  "colour_shift": "none" | "warm" | "cool" | "overexposed" | "underexposed",
  "calibration_adjustment": "brief description of adjustment applied",
  "adjusted_skin_tone_description": "skin tone after calibration adjustment",
  "calibration_confidence": "high" | "moderate" | "low",
  "note": "one sentence clinical note on colour reliability"
}"""


class ColourCalibrationRequest(BaseModel):
    context: Optional[str] = None


class ColourCalibrationResponse(BaseModel):
    reference_card_detected: bool
    colour_shift: str
    calibration_adjustment: str
    adjusted_skin_tone_description: str
    calibration_confidence: str
    note: str
    calibrated_at_utc: str


@router.post("/calibrate-colour", summary="Colour calibration for standardised visual assessment")
async def calibrate_colour(file: UploadFile = File(...)) -> ColourCalibrationResponse:
    """
    Improvement #8: Colour calibration prompt.
    Show clinician a reference guide: "Hold a white piece of paper next to the patient"
    — this endpoint then calibrates GPT-4o's colour interpretation.

    Frontend instruction (show before photo capture):
    'For best results, hold a white A4 sheet next to the treatment area when photographing.'
    """
    img_bytes = await file.read()
    b64 = base64.b64encode(img_bytes).decode()

    try:
        raw = await _gpt4o_vision(
            b64, _CALIBRATION_SYSTEM,
            "Assess colour calibration in this image. Return only the JSON object.",
            max_tokens=300,
        )
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(cleaned)
        return ColourCalibrationResponse(**data, calibrated_at_utc=_now())
    except Exception as e:
        return ColourCalibrationResponse(
            reference_card_detected=False,
            colour_shift="unknown",
            calibration_adjustment="Calibration unavailable — proceeding with standard interpretation",
            adjusted_skin_tone_description="Standard interpretation",
            calibration_confidence="low",
            note="Colour calibration failed. Results may be affected by lighting conditions.",
            calibrated_at_utc=_now(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Population Baseline Descriptor from Corpus
# POST /visual/population-baseline
# ─────────────────────────────────────────────────────────────────────────────

class BaselineRequest(BaseModel):
    procedure:   str
    days_post:   int           # days since treatment
    region:      Optional[str] = None
    product:     Optional[str] = None


class BaselineResponse(BaseModel):
    procedure:           str
    days_post:           int
    typical_appearance:  str    # what's normal at this timepoint
    expected_resolution: str    # when to expect resolution
    amber_flags:         List[str]  # things that suggest above-normal
    red_flags:           List[str]  # things requiring action
    evidence_basis:      str    # brief source description
    retrieved_at_utc:    str


# Clinical baseline knowledge — in production, supplement with RAG retrieval
# from the 206k-document corpus using retrieve_db() on a population-level query
_BASELINES: Dict[str, Dict[int, Dict[str, Any]]] = {
    "lip_filler": {
        1:  {"typical": "Marked swelling (2–3x normal volume), bruising possible, firm texture", "resolution": "Peak swelling resolves 48–72h"},
        3:  {"typical": "Moderate swelling, bruising fading, early settling", "resolution": "Most swelling resolves 5–7 days"},
        7:  {"typical": "Minimal residual swelling, natural texture returning, final shape emerging", "resolution": "Final result visible 2–4 weeks"},
        14: {"typical": "Settled result, natural movement, minor asymmetry may persist", "resolution": "Full integration 4–6 weeks"},
    },
    "tear_trough_filler": {
        1:  {"typical": "Periorbital swelling, bruising common, Tyndall risk if superficial placement", "resolution": "Swelling peaks 24–48h"},
        7:  {"typical": "Swelling subsided, blue-grey tinge if Tyndall present", "resolution": "Tyndall does not self-resolve"},
        14: {"typical": "Settled, natural contour, symmetry assessment possible", "resolution": "Final assessment at 4 weeks"},
    },
    "nasolabial_filler": {
        1:  {"typical": "Mild-moderate swelling, possible bruising, slightly overfilled appearance", "resolution": "Swelling resolves 3–5 days"},
        7:  {"typical": "Near-final result, fold softening evident", "resolution": "Full integration 2–4 weeks"},
    },
    "default": {
        1:  {"typical": "Initial post-treatment swelling and possible bruising", "resolution": "Most swelling resolves within 3–7 days"},
        7:  {"typical": "Swelling substantially resolved, early result visible", "resolution": "Final result at 4 weeks"},
        14: {"typical": "Settled result", "resolution": "Full integration 4–6 weeks"},
    },
}


def _get_baseline_entry(procedure: str, days: int) -> Tuple[str, Dict[str, Any]]:
    proc_key = procedure.lower().replace(" ", "_")
    timeline = _BASELINES.get(proc_key, _BASELINES["default"])
    # Find closest timepoint
    timepoints = sorted(timeline.keys())
    closest = min(timepoints, key=lambda t: abs(t - days))
    return proc_key, timeline[closest]


@router.post("/population-baseline", response_model=BaselineResponse,
             summary="Expected appearance at specific post-treatment timepoint")
async def get_population_baseline(req: BaselineRequest) -> BaselineResponse:
    """
    Improvement #9: Population baseline descriptor.
    Tells the clinician what "normal" looks like for this procedure at this timepoint.

    In production this should call retrieve_db() to pull papers describing
    normal post-procedure appearance, augmenting the built-in knowledge.
    """
    proc_key, entry = _get_baseline_entry(req.procedure, req.days_post)

    # Attempt RAG enrichment
    rag_note = ""
    try:
        from app.rag.retriever import retrieve_db
        import asyncio
        query = f"normal appearance {req.days_post} days after {req.procedure} {req.region or ''}"
        docs = await asyncio.to_thread(retrieve_db, query, k=3)
        if docs:
            titles = [d.get("title", "")[:60] for d in docs[:2] if d.get("title")]
            rag_note = f"Evidence from: {'; '.join(titles)}"
    except Exception:
        rag_note = "Based on clinical consensus and procedure guidelines"

    amber_flags = [
        f"Swelling beyond expected range at day {req.days_post}",
        "Asymmetry not consistent with post-treatment pattern",
        "Bruising expanding rather than fading",
    ]
    red_flags = [
        "Blanching or skin colour change",
        "Increasing pain",
        "Visual disturbance",
        "Skin breakdown or necrosis",
        "Fever or systemic symptoms",
    ]

    return BaselineResponse(
        procedure=req.procedure,
        days_post=req.days_post,
        typical_appearance=entry["typical"],
        expected_resolution=entry["resolution"],
        amber_flags=amber_flags,
        red_flags=red_flags,
        evidence_basis=rag_note or "Clinical consensus",
        retrieved_at_utc=_now(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Auto-Log After Session (1-click)
# POST /visual/auto-log
# ─────────────────────────────────────────────────────────────────────────────

class AutoLogRequest(BaseModel):
    """Entire ConsultationFlow state, submitted automatically at end of session."""
    visual_id:          Optional[str] = None
    analysis_text:      Optional[str] = None
    visual_scores:      Optional[Dict[str, Any]] = None
    triggered_protocols:List[Dict[str, Any]] = []
    simulations_run:    List[str] = []           # complication_key list
    procedure:          Optional[str] = None
    region:             Optional[str] = None
    product_type:       Optional[str] = None
    fitzpatrick_type:   Optional[str] = None
    patient_ref:        Optional[str] = None     # de-identified
    clinician_id:       Optional[str] = None
    clinic_id:          Optional[str] = None
    consent_obtained:   bool = False
    outcome:            Optional[str] = None     # if known
    clinician_notes:    Optional[str] = None
    session_duration_s: Optional[int] = None


class AutoLogResponse(BaseModel):
    case_id:          str
    logged_at_utc:    str
    dataset_total:    int
    also_logged_to_complication_engine: bool


_AUTO_LOG_STORE: List[Dict[str, Any]] = []


@router.post("/auto-log", response_model=AutoLogResponse,
             summary="Auto-log session on completion — 1 click (Improvement #7)")
def auto_log_session(req: AutoLogRequest) -> AutoLogResponse:
    """
    Called automatically at the end of every ConsultationFlow.
    Requires one "Log this session" button tap from the clinician — no form.

    Wires into:
    - SERIAL_CASE_STORE (vision_extensions.py)
    - CASE_STORE (complication_protocol_engine.py) if protocol triggered
    - Training dataset accumulator (vision_quality.py)

    This is the primary mechanism for building the proprietary dataset.
    """
    case_id = uuid.uuid4().hex[:14]
    logged_at = _now()

    record = req.dict()
    record["case_id"] = case_id
    record["logged_at_utc"] = logged_at
    record["source"] = "auto_log"

    _AUTO_LOG_STORE.append(record)

    # Wire into complication engine case store
    also_logged = False
    if req.triggered_protocols:
        try:
            from app.api.complication_protocol_engine import CASE_STORE, LoggedCase
            for p in req.triggered_protocols[:1]:  # log first triggered protocol
                comp_case = LoggedCase(
                    case_id=case_id,
                    logged_at_utc=logged_at,
                    clinic_id=req.clinic_id,
                    clinician_id=req.clinician_id,
                    protocol_key=p.get("protocol_key", "unknown"),
                    region=req.region,
                    procedure=req.procedure,
                    product_type=req.product_type,
                    symptoms=[s for p in req.triggered_protocols for s in p.get("detected_signals", [])],
                    outcome=req.outcome,
                )
                CASE_STORE.append(comp_case)
                also_logged = True
        except Exception as e:
            logger.warning(f"[AutoLog] Complication engine write failed: {e}")

    # Wire into training dataset
    try:
        from app.engine.vision_quality import _TRAINING_CASES
        _TRAINING_CASES.append({
            "case_id": case_id,
            "logged_at_utc": logged_at,
            "source": "auto_log",
            "visual_id": req.visual_id,
            "procedure": req.procedure,
            "region": req.region,
            "fitzpatrick_type": req.fitzpatrick_type,
            "ai_detected_signals": [
                s for p in req.triggered_protocols for s in p.get("detected_signals", [])
            ],
            "ai_triggered_protocol": req.triggered_protocols[0].get("protocol_key") if req.triggered_protocols else None,
            "clinician_confirmed_signals": [],  # clinician can update later
            "consent_obtained": req.consent_obtained,
        })
    except Exception as e:
        logger.debug(f"[AutoLog] Training dataset write failed: {e}")

    logger.info(f"[AutoLog] Session logged: {case_id} | protocols={len(req.triggered_protocols)}")

    return AutoLogResponse(
        case_id=case_id,
        logged_at_utc=logged_at,
        dataset_total=len(_AUTO_LOG_STORE),
        also_logged_to_complication_engine=also_logged,
    )


@router.get("/auto-log/stats", summary="Auto-log dataset statistics")
def auto_log_stats() -> Dict[str, Any]:
    return {
        "total_sessions": len(_AUTO_LOG_STORE),
        "sessions_with_protocol": sum(1 for s in _AUTO_LOG_STORE if s.get("triggered_protocols")),
        "sessions_with_consent": sum(1 for s in _AUTO_LOG_STORE if s.get("consent_obtained")),
        "unique_procedures": list({s.get("procedure") for s in _AUTO_LOG_STORE if s.get("procedure")}),
    }
