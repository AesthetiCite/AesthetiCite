"""
AesthetiCite Visual Differential Engine v1.0
============================================
POST /api/visual/differential

Takes an uploaded visual_id + optional clinical context.
Returns a structured ranked differential diagnosis with:
  - Ranked diagnoses (most_likely / possible / rule_out)
  - Confidence score per diagnosis
  - Key visual findings
  - Protocol trigger if high-risk findings detected
  - Immediate actions if urgency is critical/high
  - Evidence citations

Integrates with existing:
  - visual upload store (visual_id → image bytes)
  - complication protocol engine (auto-trigger)
  - VeriDoc evidence retriever

Mount in main.py:
    from app.api.visual_differential import router as visual_diff_router
    app.include_router(visual_diff_router, prefix="/api/visual")
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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# OpenAI client — reuses existing env vars
# ---------------------------------------------------------------------------

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )

VISION_MODEL = "gpt-4o"  # needs vision capability

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DifferentialRequest(BaseModel):
    visual_id: str = Field(..., description="ID returned by /api/visual/upload")
    clinical_context: Optional[str] = Field(
        None,
        description="Free-text context: region injected, product, time since injection, symptoms",
    )
    injected_region: Optional[str] = None
    product_type: Optional[str] = None
    time_since_injection_minutes: Optional[int] = None
    additional_symptoms: Optional[List[str]] = Field(default_factory=list)


class DiagnosisItem(BaseModel):
    rank: int
    diagnosis: str
    tier: str  # "most_likely" | "possible" | "rule_out"
    confidence: int  # 0-100
    confidence_label: str  # "High" | "Moderate" | "Low"
    key_visual_findings: List[str]
    distinguishing_features: str
    urgency: str  # "immediate" | "urgent" | "same_day" | "routine"
    protocol_key: Optional[str] = None  # links to complication protocol engine


class ImmediateAction(BaseModel):
    action: str
    priority: str  # "primary" | "secondary"
    rationale: str


class EvidenceRef(BaseModel):
    source_id: str
    title: str
    note: str
    source_type: str


class ProtocolTrigger(BaseModel):
    triggered: bool
    protocol_key: Optional[str] = None
    protocol_name: Optional[str] = None
    trigger_reason: Optional[str] = None
    urgency: Optional[str] = None
    redirect_url: Optional[str] = None


class DifferentialResponse(BaseModel):
    request_id: str
    visual_id: str
    generated_at_utc: str
    processing_ms: int
    overall_urgency: str  # "immediate" | "urgent" | "same_day" | "routine" | "none"
    urgency_rationale: str
    visual_summary: str  # 2-3 sentence description of what's seen
    differential: List[DiagnosisItem]
    immediate_actions: List[ImmediateAction]
    protocol_trigger: ProtocolTrigger
    evidence: List[EvidenceRef]
    disclaimer: str
    limitations: List[str]

# ---------------------------------------------------------------------------
# Visual store access
# Reuses the same in-memory / file store as the existing visual upload endpoint.
# Adjust _load_image_bytes() if your store uses a DB or object storage.
# ---------------------------------------------------------------------------

# Simple in-process dict populated by the upload endpoint.
# If the existing upload endpoint uses a different mechanism, swap this out.
_VISUAL_STORE: Dict[str, bytes] = {}

def register_visual(visual_id: str, image_bytes: bytes) -> None:
    """Called by the upload endpoint to register image bytes under visual_id."""
    _VISUAL_STORE[visual_id] = image_bytes

def _load_image_bytes(visual_id: str) -> Optional[bytes]:
    """Load raw image bytes for a visual_id."""
    # 1. Check in-memory store
    if visual_id in _VISUAL_STORE:
        return _VISUAL_STORE[visual_id]

    # 2. Fall back to uploads directory (common Replit pattern)
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join("uploads", f"{visual_id}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()

    return None

# ---------------------------------------------------------------------------
# Structured vision prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are AesthetiCite, a clinical safety AI for aesthetic injectable medicine.

You are analysing a clinical photograph uploaded by an aesthetic clinician.
Your role is to provide a structured differential diagnosis focused on injectable complications.

RULES:
1. Be clinically precise. Use correct terminology.
2. Always consider vascular occlusion when blanching, livedo, dusky discolouration, or mottling are visible.
3. Rank by likelihood given the visual evidence.
4. If you see ANY signs of vascular compromise — flag urgency as "immediate" and trigger protocol.
5. Return ONLY valid JSON matching the schema. No prose before or after.
6. Do not invent findings not visible in the image. If image quality is poor, say so in limitations.
7. Confidence scores: 70-100 = High, 40-69 = Moderate, 10-39 = Low.

PROTOCOL KEYS (use exactly these when triggering):
- vascular_occlusion_ha_filler
- anaphylaxis_in_clinic
- tyndall_effect_ha_filler
- botulinum_toxin_ptosis
- infection_or_biofilm_after_filler
- filler_nodules_inflammatory_or_noninflammatory

URGENCY LEVELS:
- immediate: life/limb/vision threatening — act now
- urgent: within 1 hour
- same_day: review today
- routine: non-urgent follow-up
- none: no complication identified
"""

def _build_user_prompt(req: DifferentialRequest) -> str:
    ctx_parts = []
    if req.injected_region:
        ctx_parts.append(f"Injected region: {req.injected_region}")
    if req.product_type:
        ctx_parts.append(f"Product: {req.product_type}")
    if req.time_since_injection_minutes is not None:
        ctx_parts.append(f"Time since injection: {req.time_since_injection_minutes} minutes")
    if req.additional_symptoms:
        ctx_parts.append(f"Additional symptoms reported: {', '.join(req.additional_symptoms)}")
    if req.clinical_context:
        ctx_parts.append(f"Clinical context: {req.clinical_context}")

    ctx_block = "\n".join(ctx_parts) if ctx_parts else "No additional clinical context provided."

    return f"""Analyse this clinical photograph and return a structured differential diagnosis.

Clinical context:
{ctx_block}

Return JSON in EXACTLY this structure:
{{
  "overall_urgency": "immediate|urgent|same_day|routine|none",
  "urgency_rationale": "one sentence explaining urgency level",
  "visual_summary": "2-3 sentence description of visible findings",
  "differential": [
    {{
      "rank": 1,
      "diagnosis": "diagnosis name",
      "tier": "most_likely|possible|rule_out",
      "confidence": 85,
      "confidence_label": "High|Moderate|Low",
      "key_visual_findings": ["finding 1", "finding 2"],
      "distinguishing_features": "what makes this the leading diagnosis vs alternatives",
      "urgency": "immediate|urgent|same_day|routine",
      "protocol_key": "vascular_occlusion_ha_filler or null"
    }}
  ],
  "immediate_actions": [
    {{
      "action": "action description",
      "priority": "primary|secondary",
      "rationale": "why"
    }}
  ],
  "protocol_trigger": {{
    "triggered": true,
    "protocol_key": "vascular_occlusion_ha_filler or null",
    "protocol_name": "full protocol name or null",
    "trigger_reason": "reason for triggering or null",
    "urgency": "immediate or null"
  }},
  "evidence": [
    {{
      "source_id": "S1",
      "title": "evidence source title",
      "note": "how it supports the differential",
      "source_type": "guideline|review|consensus"
    }}
  ],
  "limitations": ["limitation 1", "limitation 2"]
}}

Include 3-5 diagnoses in the differential. Order by likelihood.
Only include immediate_actions if urgency is immediate or urgent.
"""

# ---------------------------------------------------------------------------
# Confidence label helper
# ---------------------------------------------------------------------------

def _confidence_label(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Moderate"
    return "Low"

# ---------------------------------------------------------------------------
# Protocol trigger builder
# ---------------------------------------------------------------------------

PROTOCOL_NAMES = {
    "vascular_occlusion_ha_filler": "Suspected vascular occlusion after HA filler",
    "anaphylaxis_in_clinic": "Anaphylaxis in clinic",
    "tyndall_effect_ha_filler": "Tyndall effect after HA filler",
    "botulinum_toxin_ptosis": "Upper eyelid ptosis post-botulinum toxin",
    "infection_or_biofilm_after_filler": "Infection or biofilm after filler",
    "filler_nodules_inflammatory_or_noninflammatory": "Filler nodules — inflammatory or non-inflammatory",
}

PROTOCOL_URLS = {
    "vascular_occlusion_ha_filler": "/emergency?protocol=vascular_occlusion_ha_filler",
    "anaphylaxis_in_clinic": "/emergency?protocol=anaphylaxis_in_clinic",
    "tyndall_effect_ha_filler": "/complications?protocol=tyndall_effect_ha_filler",
    "botulinum_toxin_ptosis": "/complications?protocol=botulinum_toxin_ptosis",
    "infection_or_biofilm_after_filler": "/complications?protocol=infection_or_biofilm_after_filler",
    "filler_nodules_inflammatory_or_noninflammatory": "/complications?protocol=filler_nodules_inflammatory_or_noninflammatory",
}

def _build_protocol_trigger(raw: Dict[str, Any]) -> ProtocolTrigger:
    triggered = bool(raw.get("triggered"))
    pk = raw.get("protocol_key") or None
    if triggered and pk and pk not in PROTOCOL_NAMES:
        triggered = False
        pk = None
    return ProtocolTrigger(
        triggered=triggered,
        protocol_key=pk,
        protocol_name=PROTOCOL_NAMES.get(pk) if pk else None,
        trigger_reason=raw.get("trigger_reason") or None,
        urgency=raw.get("urgency") or None,
        redirect_url=PROTOCOL_URLS.get(pk) if pk else None,
    )

# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.post("/differential", response_model=DifferentialResponse)
def visual_differential(req: DifferentialRequest) -> DifferentialResponse:
    start = time.time()
    request_id = str(uuid.uuid4())

    # 1. Load image
    image_bytes = _load_image_bytes(req.visual_id)
    if not image_bytes:
        raise HTTPException(
            status_code=404,
            detail=f"Visual ID '{req.visual_id}' not found. Upload an image first via /api/visual/upload."
        )

    # 2. Encode to base64
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    # 3. Call vision model
    client = _get_client()
    user_prompt = _build_user_prompt(req)

    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            max_tokens=2000,
            temperature=0.1,  # low temp for clinical consistency
        )
    except Exception as e:
        logger.error(f"[VisualDiff] Vision model error: {e}")
        raise HTTPException(status_code=502, detail=f"Vision model unavailable: {str(e)[:120]}")

    # 4. Parse JSON response
    raw_text = response.choices[0].message.content or ""
    raw_text = re.sub(r"```json|```", "", raw_text).strip()

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"[VisualDiff] JSON parse error: {e}\nRaw: {raw_text[:400]}")
        raise HTTPException(status_code=500, detail="Model returned malformed JSON. Please retry.")

    # 5. Build typed response
    differential: List[DiagnosisItem] = []
    for d in raw.get("differential", []):
        score = int(d.get("confidence", 50))
        differential.append(DiagnosisItem(
            rank=int(d.get("rank", len(differential) + 1)),
            diagnosis=d.get("diagnosis", "Unknown"),
            tier=d.get("tier", "possible"),
            confidence=score,
            confidence_label=_confidence_label(score),
            key_visual_findings=d.get("key_visual_findings", []),
            distinguishing_features=d.get("distinguishing_features", ""),
            urgency=d.get("urgency", "routine"),
            protocol_key=d.get("protocol_key") or None,
        ))

    immediate_actions: List[ImmediateAction] = [
        ImmediateAction(
            action=a.get("action", ""),
            priority=a.get("priority", "secondary"),
            rationale=a.get("rationale", ""),
        )
        for a in raw.get("immediate_actions", [])
    ]

    evidence: List[EvidenceRef] = [
        EvidenceRef(
            source_id=e.get("source_id", f"S{i+1}"),
            title=e.get("title", ""),
            note=e.get("note", ""),
            source_type=e.get("source_type", "review"),
        )
        for i, e in enumerate(raw.get("evidence", []))
    ]

    protocol_trigger = _build_protocol_trigger(raw.get("protocol_trigger", {}))

    processing_ms = int((time.time() - start) * 1000)

    return DifferentialResponse(
        request_id=request_id,
        visual_id=req.visual_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        processing_ms=processing_ms,
        overall_urgency=raw.get("overall_urgency", "routine"),
        urgency_rationale=raw.get("urgency_rationale", ""),
        visual_summary=raw.get("visual_summary", ""),
        differential=differential,
        immediate_actions=immediate_actions,
        protocol_trigger=protocol_trigger,
        evidence=evidence,
        disclaimer=(
            "This output is clinical decision support only and does not replace clinician judgement. "
            "Image-based assessment has inherent limitations including lighting, angle, and resolution. "
            "Escalate immediately for visual symptoms, signs of vascular compromise, or diagnostic uncertainty."
        ),
        limitations=raw.get("limitations", [
            "Image quality may affect diagnostic accuracy",
            "Clinical context not visible in photograph may be relevant",
            "This analysis supports but does not replace in-person clinical assessment",
        ]),
    )
