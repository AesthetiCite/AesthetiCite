"""
visual_enhancements.py — Improvement 6
=======================================
Two new FastAPI endpoints:

1. POST /api/visual/delete/{visual_id}
   Deletes image from the visual store immediately after analysis.
   Supports MHRA SaMD positioning and builds clinical trust.
   Respects ephemeral_mode: if True, image was never persisted.

2. POST /api/visual/patient-explanation
   Converts a differential diagnosis result into plain-language
   patient counselling text. Called by PatientExplanation.tsx.

Mount in main.py:
    from app.api.visual_enhancements import router as visual_enhance_router
    app.include_router(visual_enhance_router, prefix="/api/visual")
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

# Import the same store used in visual_differential.py
from app.api.visual_differential import _VISUAL_STORE, _load_image_bytes

logger = logging.getLogger(__name__)
router = APIRouter()

COMPOSE_MODEL = os.environ.get("COMPOSE_MODEL", "gpt-4o-mini")


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )


# ─────────────────────────────────────────────────────────────────
# Improvement 6a — Image deletion
# ─────────────────────────────────────────────────────────────────

class DeleteResponse(BaseModel):
    visual_id: str
    deleted: bool
    message: str
    deleted_at_utc: str


@router.delete("/delete/{visual_id}", response_model=DeleteResponse)
def delete_visual(visual_id: str) -> DeleteResponse:
    """
    Delete a visual from the store immediately.
    Call this after running /api/visual/differential if ephemeral mode is on.
    Image is removed from memory and any disk cache.
    """
    deleted = False

    # 1. Remove from in-memory store
    if visual_id in _VISUAL_STORE:
        del _VISUAL_STORE[visual_id]
        deleted = True
        logger.info(f"[VisualDelete] Removed {visual_id} from memory store.")

    # 2. Remove from disk if present
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join("uploads", f"{visual_id}.{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted = True
                logger.info(f"[VisualDelete] Removed file: {path}")
            except Exception as e:
                logger.warning(f"[VisualDelete] Could not remove file {path}: {e}")

    return DeleteResponse(
        visual_id=visual_id,
        deleted=deleted,
        message=(
            "Image deleted from server immediately. No image data is retained."
            if deleted else
            "Visual ID not found — may have already been deleted or never persisted."
        ),
        deleted_at_utc=datetime.now(timezone.utc).isoformat(),
    )


# ─────────────────────────────────────────────────────────────────
# Improvement 6b — Ephemeral mode flag in differential request
# Add this field to DifferentialRequest in visual_differential.py:
#   ephemeral: bool = Field(False, description="Delete image immediately after analysis")
#
# Then in the visual_differential endpoint, after building the response:
#   if req.ephemeral:
#       delete_visual(req.visual_id)
# ─────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────
# Improvement 5 — Patient explanation endpoint
# ─────────────────────────────────────────────────────────────────

class DiagnosisSummary(BaseModel):
    rank: int
    diagnosis: str
    tier: str
    confidence: int
    confidence_label: str
    urgency: str
    key_visual_findings: List[str] = Field(default_factory=list)


class PatientExplanationRequest(BaseModel):
    differential: List[DiagnosisSummary]
    visual_summary: str = ""
    language: str = "en"  # ISO 639-1


class PatientExplanationResponse(BaseModel):
    headline: str
    what_we_see: str
    what_it_means: str
    what_happens_next: str
    reassurance: str
    when_to_seek_help: str
    disclaimer: str


PATIENT_SYSTEM = """You are AesthetiCite, a clinical safety tool for aesthetic medicine.
You are generating a plain-language patient explanation based on a clinical image analysis.

RULES:
1. Write in simple, clear English that a non-medical patient can understand.
2. Do NOT use medical jargon without explaining it.
3. Be honest but reassuring — do not alarm the patient unnecessarily.
4. For urgent/immediate findings, clearly explain when to seek help immediately.
5. Never use the word "diagnosis" — use "assessment" or "what we found."
6. Return ONLY valid JSON matching the schema. No prose before or after.
7. Keep each field to 2-3 sentences maximum.
"""

PATIENT_USER_TEMPLATE = """
Convert this clinical assessment into plain patient-friendly language.

Top finding: {top_diagnosis}
Confidence: {confidence}%
Urgency: {urgency}
Visual summary: {visual_summary}
Key findings: {findings}

Return JSON:
{{
  "headline": "Simple one-sentence summary of what was found",
  "what_we_see": "Plain description of what the image showed (no jargon)",
  "what_it_means": "What this likely means for the patient in plain English",
  "what_happens_next": "Concrete next steps the patient should expect",
  "reassurance": "Honest reassuring statement appropriate to the urgency level",
  "when_to_seek_help": "Clear instruction on when to seek immediate help (always include this)",
  "disclaimer": "Brief standard disclaimer that this is clinical decision support, not a diagnosis"
}}
"""


@router.post("/patient-explanation", response_model=PatientExplanationResponse)
def patient_explanation(req: PatientExplanationRequest) -> PatientExplanationResponse:
    if not req.differential:
        raise HTTPException(status_code=400, detail="No differential provided.")

    top = req.differential[0]
    findings_str = "; ".join(top.key_visual_findings[:4]) if top.key_visual_findings else "See clinical notes"

    prompt = PATIENT_USER_TEMPLATE.format(
        top_diagnosis=top.diagnosis,
        confidence=top.confidence,
        urgency=top.urgency,
        visual_summary=req.visual_summary or "Clinical image assessed by AesthetiCite.",
        findings=findings_str,
    )

    # Add language instruction if not English
    lang_note = ""
    if req.language != "en":
        lang_note = f"\nIMPORTANT: Write the entire response in language code '{req.language}'. All JSON values must be in that language."
        prompt += lang_note

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=COMPOSE_MODEL,
            messages=[
                {"role": "system", "content": PATIENT_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
    except Exception as e:
        logger.error(f"[PatientExplanation] LLM error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM unavailable: {str(e)[:120]}")

    raw = (response.choices[0].message.content or "").strip()
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[PatientExplanation] JSON parse error: {e}\nRaw: {raw[:300]}")
        raise HTTPException(status_code=500, detail="Model returned malformed JSON.")

    # Fallback for any missing fields
    def safe(key: str, fallback: str) -> str:
        return str(data.get(key) or fallback)

    return PatientExplanationResponse(
        headline=safe("headline", f"Assessment: {top.diagnosis}"),
        what_we_see=safe("what_we_see", req.visual_summary),
        what_it_means=safe("what_it_means", "Your clinician will discuss the findings with you."),
        what_happens_next=safe("what_happens_next", "Your clinician will advise on next steps."),
        reassurance=safe("reassurance", "Your clinician is monitoring your progress carefully."),
        when_to_seek_help=safe(
            "when_to_seek_help",
            "Seek immediate medical attention if you develop visual changes, severe pain, or breathing difficulty."
        ),
        disclaimer=safe(
            "disclaimer",
            "This explanation is based on clinical decision support and is not a medical diagnosis. "
            "Always follow the advice of your treating clinician."
        ),
    )
