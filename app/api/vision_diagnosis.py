"""
AesthetiCite Vision — Complication Diagnosis Engine  (VisualDX-inspired)
=========================================================================
Provides structured complication recognition from a single image.

This is distinct from the existing visual endpoints:
  /visual/upload + /ask/visual/stream  →  free-text evidence counseling
  /vision-followup                     →  serial comparison of two images

This module adds:
  POST /api/vision/diagnose            →  ranked complication differential from ONE image
  POST /api/vision/diagnose-compare    →  ranked differential from a BEFORE/AFTER pair
  GET  /api/vision/complication-signs  →  dictionary of visual signs per complication

Output structure (VisualDX-style ranked differential):
  {
    "primary":     { "complication": str, "confidence": float, "urgency": str,
                     "visual_evidence": [str], "action": str },
    "differentials": [{ same structure }],
    "visual_signs_detected": [str],
    "safe_to_proceed": bool,
    "trigger_protocol": str | null,
    "risk_level": "critical"|"high"|"moderate"|"low",
    "image_quality": "good"|"acceptable"|"poor",
    "disclaimer": str,
    "latency_ms": float
  }
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/vision", tags=["Vision Diagnosis"])
logger = logging.getLogger(__name__)

_AI_BASE = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
_AI_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ===========================================================================
# COMPLICATION VISUAL SIGN DICTIONARY
# ===========================================================================

COMPLICATION_SIGNS: Dict[str, Dict[str, Any]] = {
    "vascular_occlusion": {
        "display": "Vascular Occlusion",
        "urgency": "immediate",
        "risk_level": "critical",
        "visual_signs": [
            "Blanching (white/pale area at injection site)",
            "Livedo reticularis (mottled, net-like discolouration)",
            "Skin discolouration — dusky, violaceous, or cyanotic",
            "Demarcated border matching vascular territory",
            "Unilateral or focal loss of normal skin colour",
        ],
        "trigger_protocol": "vascular_occlusion",
        "action": "Immediate: Stop injection. Hyaluronidase 1500 IU now. Call 999 if visual symptoms.",
        "safe_to_proceed": False,
    },
    "skin_necrosis": {
        "display": "Skin Necrosis",
        "urgency": "immediate",
        "risk_level": "critical",
        "visual_signs": [
            "Dark purple or black skin discolouration",
            "Eschar or crusting tissue",
            "Sharply demarcated zone of tissue death",
            "Surrounding erythema or inflammation",
            "Loss of normal skin texture in affected zone",
        ],
        "trigger_protocol": "necrosis",
        "action": "Urgent: Photograph, start vascular occlusion protocol, same-day plastic surgery referral.",
        "safe_to_proceed": False,
    },
    "infection_cellulitis": {
        "display": "Infection / Cellulitis",
        "urgency": "urgent",
        "risk_level": "high",
        "visual_signs": [
            "Diffuse erythema spreading beyond injection site",
            "Warmth and swelling (often described as skin-coloured or red)",
            "Induration of surrounding tissue",
            "Potential crusting or oozing at entry points",
            "Asymmetric, unilateral distribution",
        ],
        "trigger_protocol": "infection",
        "action": "Start antibiotics within hours. Swab if discharge present. Refer if spreading or systemic.",
        "safe_to_proceed": False,
    },
    "tyndall_effect": {
        "display": "Tyndall Effect",
        "urgency": "routine",
        "risk_level": "low",
        "visual_signs": [
            "Blue-grey discolouration visible through thin skin",
            "Superficial, translucent appearance",
            "Most visible in periorbital, nasolabial, or lip area",
            "No erythema or warmth",
            "Present at rest without pressure",
        ],
        "trigger_protocol": "tyndall",
        "action": "Dissolve with hyaluronidase 15–75 IU intradermal. Conservative dosing.",
        "safe_to_proceed": True,
    },
    "inflammatory_nodule": {
        "display": "Inflammatory Nodule / Granuloma",
        "urgency": "same_day",
        "risk_level": "moderate",
        "visual_signs": [
            "Visible raised lump or nodule at or near injection site",
            "Erythema over or surrounding the lump",
            "Possible skin surface irregularity",
            "Firmness visible as surface contour change",
            "May show mild surrounding oedema",
        ],
        "trigger_protocol": "nodule",
        "action": "Assess inflammatory vs non-inflammatory. Consider hyaluronidase or intralesional 5-FU/steroid.",
        "safe_to_proceed": True,
    },
    "severe_oedema": {
        "display": "Severe Oedema / Angioedema",
        "urgency": "urgent",
        "risk_level": "high",
        "visual_signs": [
            "Diffuse, bilateral, non-pitting swelling",
            "Marked volume increase disproportionate to procedure",
            "Periorbital or lip swelling most common",
            "Skin surface appears smooth and tight",
            "May extend beyond treated area",
        ],
        "trigger_protocol": "dir",
        "action": "Antihistamine stat. If airway involved: 999 immediately. Monitor for anaphylaxis.",
        "safe_to_proceed": False,
    },
    "haematoma_bruising": {
        "display": "Haematoma / Ecchymosis",
        "urgency": "routine",
        "risk_level": "low",
        "visual_signs": [
            "Purple, red, or yellow-green discolouration",
            "No blanching on pressure",
            "Soft tissue swelling with discolouration",
            "Diffuse spread not following vascular territory",
            "Improving in colour spectrum (purple → yellow as resolves)",
        ],
        "trigger_protocol": None,
        "action": "Topical arnica, cold compress. Reassure — usually resolves 1–2 weeks.",
        "safe_to_proceed": True,
    },
    "asymmetry": {
        "display": "Post-Procedure Asymmetry",
        "urgency": "routine",
        "risk_level": "low",
        "visual_signs": [
            "Visible difference in volume between treated sides",
            "Uneven contour compared to pre-treatment baseline",
            "One side more elevated or projected",
            "Difference in skin fold or shadow pattern",
        ],
        "trigger_protocol": None,
        "action": "Review at 2 weeks (allow settling). Touch-up or dissolving may be appropriate.",
        "safe_to_proceed": True,
    },
    "normal_post_procedure": {
        "display": "Normal Post-Procedure Appearance",
        "urgency": "routine",
        "risk_level": "low",
        "visual_signs": [
            "Expected mild erythema at injection points",
            "Normal oedema consistent with procedure volume",
            "Pinpoint bruising at needle/cannula entry sites",
            "Mild asymmetry within expected range",
        ],
        "trigger_protocol": None,
        "action": "Standard aftercare. Review at 2 weeks if requested.",
        "safe_to_proceed": True,
    },
}


# ===========================================================================
# SYSTEM PROMPTS
# ===========================================================================

_SINGLE_IMAGE_SYSTEM = """You are AesthetiCite Vision, a specialist AI for aesthetic medicine complication recognition.
You have been given a clinical photograph taken after an aesthetic procedure.

Your task: Analyse the image and return a structured complication differential diagnosis.

CRITICAL RULES:
1. Return ONLY valid JSON — no markdown, no preamble.
2. Be specific about visual signs you actually observe in the image.
3. Do NOT hallucinate findings not visible in the image.
4. If image quality prevents reliable assessment, set image_quality to "poor" and reduce confidence.
5. If you observe signs consistent with vascular occlusion or necrosis, set urgency to "immediate".
6. Your primary diagnosis must be the most likely complication based on observable visual signs.
7. Always include "normal_post_procedure" as a differential if signs are mild or ambiguous.

Complications to consider:
- vascular_occlusion: blanching, livedo reticularis, dusky discolouration, vascular territory pattern
- skin_necrosis: dark purple/black, eschar, sharply demarcated tissue death
- infection_cellulitis: spreading erythema, warmth-consistent redness, induration pattern
- tyndall_effect: blue-grey translucent discolouration in thin skin
- inflammatory_nodule: visible raised lump, surface erythema
- severe_oedema: diffuse bilateral swelling, smooth tight skin
- haematoma_bruising: purple/yellow-green discolouration, non-blanching
- asymmetry: volume difference between sides
- normal_post_procedure: mild erythema, expected swelling

Return this exact JSON:
{
  "image_quality": "good|acceptable|poor",
  "visual_signs_detected": ["specific sign observed 1", "specific sign observed 2"],
  "primary": {
    "complication": "complication_key from list above",
    "display_name": "Human-readable name",
    "confidence": 0.0-1.0,
    "confidence_label": "low|medium|high",
    "urgency": "immediate|urgent|same_day|routine",
    "visual_evidence": ["specific visual finding that supports this diagnosis"],
    "risk_level": "critical|high|moderate|low"
  },
  "differentials": [
    {
      "complication": "complication_key",
      "display_name": "Human-readable name",
      "confidence": 0.0-1.0,
      "confidence_label": "low|medium|high",
      "urgency": "immediate|urgent|same_day|routine",
      "visual_evidence": ["finding that could support this"],
      "exclude_reason": "Why this is less likely than the primary"
    }
  ],
  "safe_to_proceed": true|false,
  "trigger_protocol": "complication_key or null",
  "overall_risk_level": "critical|high|moderate|low",
  "clinical_note": "One sentence of the most important clinical point"
}"""

_COMPARE_IMAGE_SYSTEM = """You are AesthetiCite Vision, a specialist AI for aesthetic medicine serial image analysis.
You have been given TWO clinical photographs: a BEFORE (baseline/day 0) and AFTER image.

Your task: Compare the images and identify any new or worsening complications since baseline.

CRITICAL RULES:
1. Return ONLY valid JSON.
2. Focus on CHANGES between the two images — not static baseline findings.
3. Flag any new erythema, swelling, discolouration, asymmetry, or signs of vascular compromise.
4. Estimate degree of change: "improved" | "stable" | "mildly_worsened" | "significantly_worsened".
5. If you see new blanching or livedo not present at baseline: urgency = "immediate".

Return this exact JSON:
{
  "change_status": "improved|stable|mildly_worsened|significantly_worsened",
  "image_quality": "good|acceptable|poor",
  "new_signs_detected": ["new finding in after vs before"],
  "resolved_signs": ["signs present in before, resolved in after"],
  "persistent_signs": ["unchanged signs"],
  "primary_concern": {
    "complication": "complication_key",
    "display_name": "Human-readable name",
    "is_new_since_baseline": true|false,
    "confidence": 0.0-1.0,
    "urgency": "immediate|urgent|same_day|routine",
    "visual_evidence": ["specific change observed"],
    "risk_level": "critical|high|moderate|low"
  },
  "additional_concerns": [],
  "clinical_changes": {
    "asymmetry": "improved|stable|worsened|not_applicable",
    "erythema": "improved|stable|worsened|not_applicable",
    "swelling": "improved|stable|worsened|not_applicable",
    "discolouration": "improved|stable|worsened|not_applicable",
    "blanching": "present|absent|not_applicable"
  },
  "safe_to_continue_monitoring": true|false,
  "trigger_protocol": "complication_key or null",
  "clinical_note": "One sentence summary of the most important change"
}"""


# ===========================================================================
# LLM VISION CALL
# ===========================================================================

async def _call_vision_llm(
    system: str,
    images_b64: List[Tuple[str, str]],
    context_text: str = "",
) -> Dict[str, Any]:
    """
    Call GPT-4o with one or two images. Returns parsed JSON dict.
    """
    import httpx

    content: List[Dict] = []

    if context_text:
        content.append({"type": "text", "text": context_text})

    for b64, media_type in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{b64}",
                "detail": "high",
            },
        })

    content.append({
        "type": "text",
        "text": "Analyse the image(s) and return the structured JSON diagnosis. No markdown, no preamble.",
    })

    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": content},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {_AI_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_AI_BASE.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            clean = re.sub(r"```(?:json)?", "", raw).strip()
            return json.loads(clean)
    except json.JSONDecodeError as e:
        logger.warning(f"Vision LLM JSON parse error: {e}")
        return {"_parse_error": True, "raw": raw[:300] if "raw" in dir() else ""}
    except Exception as e:
        logger.error(f"Vision LLM call failed: {e}")
        raise HTTPException(502, f"Vision engine unavailable: {str(e)[:100]}")


def _enrich_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich the LLM result with our complication sign dictionary data.
    Adds action text, trigger_protocol, safe_to_proceed from COMPLICATION_SIGNS.
    """
    primary = raw.get("primary", {})
    comp_key = primary.get("complication", "")
    sign_data = COMPLICATION_SIGNS.get(comp_key, {})

    if sign_data:
        primary.setdefault("action", sign_data.get("action", ""))
        raw["trigger_protocol"] = raw.get("trigger_protocol") or sign_data.get("trigger_protocol")
        raw["safe_to_proceed"] = raw.get("safe_to_proceed", sign_data.get("safe_to_proceed", True))

    raw["primary"] = primary
    raw["disclaimer"] = (
        "AesthetiCite Vision is AI-assisted image analysis for clinical decision support only. "
        "It does not replace clinical examination. Never use AI image analysis as the sole basis for treatment decisions. "
        "If vascular compromise or necrosis is suspected, act immediately — do not wait for AI confirmation."
    )
    return raw


# ===========================================================================
# ENDPOINTS
# ===========================================================================

@router.post("/diagnose")
async def diagnose_single(
    file: UploadFile = File(...),
    procedure: str = Form(""),
    region: str = Form(""),
    time_since: str = Form(""),
    product: str = Form(""),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    VisualDX-style: upload one image → get ranked complication differential.
    """
    t0 = time.perf_counter()

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image too large. Maximum 10 MB.")

    media_type = file.content_type or "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode()

    context_parts = []
    if procedure:  context_parts.append(f"Procedure: {procedure}")
    if region:     context_parts.append(f"Region: {region}")
    if time_since: context_parts.append(f"Time since treatment: {time_since}")
    if product:    context_parts.append(f"Product used: {product}")
    context_text = "\n".join(context_parts) if context_parts else "Clinical context not provided."

    raw = await _call_vision_llm(
        system=_SINGLE_IMAGE_SYSTEM,
        images_b64=[(b64, media_type)],
        context_text=f"Clinical context:\n{context_text}",
    )

    if raw.get("_parse_error"):
        raise HTTPException(502, "Vision model returned unparseable response. Please retry.")

    result = _enrich_result(raw)
    result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["image_id"] = str(uuid.uuid4())[:8]

    return result


@router.post("/diagnose-compare")
async def diagnose_compare(
    baseline: UploadFile = File(...),
    followup: UploadFile = File(...),
    procedure: str = Form(""),
    region: str = Form(""),
    days_since_baseline: str = Form(""),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    VisualDX serial comparison: upload BEFORE + AFTER images → detect changes.
    """
    t0 = time.perf_counter()

    baseline_bytes = await baseline.read()
    followup_bytes = await followup.read()

    if len(baseline_bytes) > MAX_IMAGE_BYTES or len(followup_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image too large. Maximum 10 MB each.")

    b64_base   = base64.b64encode(baseline_bytes).decode()
    b64_follow = base64.b64encode(followup_bytes).decode()
    mt_base    = baseline.content_type or "image/jpeg"
    mt_follow  = followup.content_type or "image/jpeg"

    context_parts = []
    if procedure:           context_parts.append(f"Procedure: {procedure}")
    if region:              context_parts.append(f"Region: {region}")
    if days_since_baseline: context_parts.append(f"Days since baseline: {days_since_baseline}")
    context_text = (
        "The FIRST image is the BASELINE (before / day 0). "
        "The SECOND image is the FOLLOW-UP.\n"
        + ("\n".join(context_parts) if context_parts else "")
    )

    raw = await _call_vision_llm(
        system=_COMPARE_IMAGE_SYSTEM,
        images_b64=[(b64_base, mt_base), (b64_follow, mt_follow)],
        context_text=context_text,
    )

    if raw.get("_parse_error"):
        raise HTTPException(502, "Vision model returned unparseable response.")

    concern = raw.get("primary_concern", {})
    comp_key = concern.get("complication", "")
    sign_data = COMPLICATION_SIGNS.get(comp_key, {})
    if sign_data:
        concern.setdefault("action", sign_data.get("action", ""))
        raw["trigger_protocol"] = raw.get("trigger_protocol") or sign_data.get("trigger_protocol")
    raw["primary_concern"] = concern

    raw["disclaimer"] = (
        "AesthetiCite Vision serial comparison is AI-assisted decision support. "
        "It does not replace clinical examination. "
        "If new blanching or discolouration is identified compared to baseline, act immediately."
    )
    raw["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    return raw


@router.get("/complication-signs")
async def get_complication_signs(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return the full complication visual sign dictionary.
    Used by the frontend to show "what to look for" guidance.
    """
    return {
        "complications": {
            key: {
                "display": val["display"],
                "urgency": val["urgency"],
                "risk_level": val["risk_level"],
                "visual_signs": val["visual_signs"],
                "action": val["action"],
            }
            for key, val in COMPLICATION_SIGNS.items()
        },
        "total": len(COMPLICATION_SIGNS),
    }
