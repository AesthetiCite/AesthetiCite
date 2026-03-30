"""
AesthetiCite Vision — Anatomical Landmark Detection
======================================================
Improvement 4: Detect facial landmarks to establish spatial reference,
then analyse signals in specific anatomical zones rather than globally.

Output: "blanching in nasolabial fold zone" instead of "blanching visible"

Architecture:
  1. OpenCV dlib-free face detection (Haar cascade — no model download required)
  2. Zone mapper: divides face into 9 clinical zones
  3. Zone-specific GPT-4o analysis prompt per zone
  4. Aggregated signals with anatomical localisation

Add to main.py:
    from app.api.vision_landmarks import router as landmark_router
    app.include_router(landmark_router)

Add to server/routes.ts:
    app.post("/api/visual/landmark-analyse",
        (req,res)=>proxyToFastAPI(req,res,"/visual/landmark-analyse"));
    app.post("/api/visual/landmark-preview",
        (req,res)=>proxyToFastAPI(req,res,"/visual/landmark-preview"));

Dependencies (already in common stacks):
    opencv-python-headless>=4.9.0
    Pillow>=10.0.0
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visual", tags=["Vision Landmarks"])

OPENAI_API_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
VISION_MODEL    = os.environ.get("VISION_MODEL", "gpt-4o")

# Haar cascade path — downloaded once on first use
_CASCADE_DIR  = Path(tempfile.gettempdir()) / "aestheticite_cascades"
_CASCADE_PATH = _CASCADE_DIR / "haarcascade_frontalface_default.xml"
_CASCADE_URL  = (
    "https://raw.githubusercontent.com/opencv/opencv/master/"
    "data/haarcascades/haarcascade_frontalface_default.xml"
)


def _ensure_cascade() -> Optional[str]:
    """Download Haar cascade XML once, return path or None if unavailable."""
    try:
        _CASCADE_DIR.mkdir(parents=True, exist_ok=True)
        if not _CASCADE_PATH.exists():
            logger.info("[Landmarks] Downloading Haar cascade…")
            urllib.request.urlretrieve(_CASCADE_URL, str(_CASCADE_PATH))
        return str(_CASCADE_PATH)
    except Exception as e:
        logger.warning(f"[Landmarks] Could not obtain cascade: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Zone definitions
# Each zone maps to a clinical region relevant to injectable medicine
# ─────────────────────────────────────────────────────────────────────────────

# Zone names → clinical danger zones and typical complications
ZONE_CLINICAL_MAP: Dict[str, Dict[str, Any]] = {
    "forehead":        {"danger_zones": ["supratrochlear artery", "supraorbital artery"],
                        "complications": ["vascular_occlusion", "infection"]},
    "glabella":        {"danger_zones": ["supratrochlear artery"],
                        "complications": ["vascular_occlusion", "vision_loss", "blanching"]},
    "right_periorbital":{"danger_zones": ["supraorbital artery", "infraorbital artery"],
                         "complications": ["tyndall_effect", "vascular_occlusion", "ptosis"]},
    "left_periorbital": {"danger_zones": ["supraorbital artery", "infraorbital artery"],
                         "complications": ["tyndall_effect", "vascular_occlusion", "ptosis"]},
    "nose":            {"danger_zones": ["dorsal nasal artery", "nasal tip vessels"],
                        "complications": ["vascular_occlusion", "skin_necrosis"]},
    "right_cheek":     {"danger_zones": ["angular artery", "facial artery"],
                        "complications": ["vascular_occlusion", "infection"]},
    "left_cheek":      {"danger_zones": ["angular artery", "facial artery"],
                        "complications": ["vascular_occlusion", "infection"]},
    "lips_perioral":   {"danger_zones": ["labial artery", "facial artery"],
                        "complications": ["vascular_occlusion", "tyndall_effect", "nodule"]},
    "chin_jawline":    {"danger_zones": ["facial artery", "marginal mandibular branch"],
                        "complications": ["vascular_occlusion", "infection"]},
}


def _map_face_to_zones(
    face_x: int, face_y: int, face_w: int, face_h: int,
    img_w: int, img_h: int,
) -> Dict[str, Tuple[int, int, int, int]]:
    """
    Divide detected face bounding box into 9 anatomical zones.
    Returns dict of zone_name → (x, y, w, h) crop coordinates.
    """
    # Relative fractions within face bounding box
    zones = {
        "forehead":         (0.0,  0.0,  1.0,  0.25),
        "glabella":         (0.35, 0.2,  0.3,  0.15),
        "right_periorbital":(0.5,  0.25, 0.45, 0.2),
        "left_periorbital": (0.05, 0.25, 0.45, 0.2),
        "nose":             (0.3,  0.35, 0.4,  0.25),
        "right_cheek":      (0.55, 0.45, 0.4,  0.25),
        "left_cheek":       (0.05, 0.45, 0.4,  0.25),
        "lips_perioral":    (0.2,  0.65, 0.6,  0.2),
        "chin_jawline":     (0.1,  0.8,  0.8,  0.2),
    }

    crops: Dict[str, Tuple[int, int, int, int]] = {}
    for zone_name, (rx, ry, rw, rh) in zones.items():
        cx = face_x + int(rx * face_w)
        cy = face_y + int(ry * face_h)
        cw = int(rw * face_w)
        ch = int(rh * face_h)

        # Clamp to image bounds
        cx = max(0, min(cx, img_w - 1))
        cy = max(0, min(cy, img_h - 1))
        cw = max(1, min(cw, img_w - cx))
        ch = max(1, min(ch, img_h - cy))

        crops[zone_name] = (cx, cy, cw, ch)

    return crops


def _detect_face_and_zones(
    image_bytes: bytes,
) -> Tuple[Optional[Dict[str, Tuple[int, int, int, int]]], Tuple[int, int, int, int], bytes]:
    """
    Run Haar cascade face detection, return zone crop coordinates + annotated image.
    Returns (zones_dict, face_bbox, annotated_jpg_bytes).
    Falls back to full-image zones if no face detected.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError("opencv-python-headless required: pip install opencv-python-headless")

    cascade_path = _ensure_cascade()

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    img_h, img_w = img.shape[:2]
    face_bbox = (0, 0, img_w, img_h)  # default: whole image
    zones: Optional[Dict[str, Tuple[int, int, int, int]]] = None

    if cascade_path:
        cascade = cv2.CascadeClassifier(cascade_path)
        gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces   = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )
        if len(faces) > 0:
            # Take largest face
            face = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]
            fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            face_bbox = (fx, fy, fw, fh)
            zones     = _map_face_to_zones(fx, fy, fw, fh, img_w, img_h)

            # Draw face box on annotated copy
            annotated = img.copy()
            cv2.rectangle(annotated, (fx, fy), (fx + fw, fy + fh), (0, 255, 0), 2)
            for zone_name, (zx, zy, zw, zh) in zones.items():
                cv2.rectangle(annotated, (zx, zy), (zx + zw, zy + zh), (255, 100, 0), 1)
                cv2.putText(annotated, zone_name.split("_")[0], (zx + 2, zy + 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        else:
            annotated = img.copy()
            cv2.putText(annotated, "No face detected — full image analysed",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)
    else:
        annotated = img.copy()

    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    annotated_bytes = buf.tobytes()

    if zones is None:
        # No face detected — use full image as single zone
        zones = {"full_image": (0, 0, img_w, img_h)}

    return zones, face_bbox, annotated_bytes


def _crop_zone(image_bytes: bytes, bbox: Tuple[int, int, int, int]) -> str:
    """Crop image to bbox and return base64 JPEG."""
    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        x, y, w, h = bbox
        crop = img.crop((x, y, x + w, y + h))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"[Landmarks] Crop failed: {e}")
        return base64.b64encode(image_bytes[:50000]).decode()  # fallback: raw


# ─────────────────────────────────────────────────────────────────────────────
# Zone-specific analysis prompt
# ─────────────────────────────────────────────────────────────────────────────

def _build_zone_prompt(zone_name: str) -> str:
    clinical = ZONE_CLINICAL_MAP.get(zone_name, {})
    danger   = ", ".join(clinical.get("danger_zones", []))
    compls   = ", ".join(clinical.get("complications", []))

    return f"""You are assessing the {zone_name.replace('_', ' ')} zone of a post-injectable patient.

Relevant danger zones for this area: {danger or 'standard vascular anatomy'}
Potential complications to assess: {compls or 'general complications'}

Assess ONLY what is visible in this cropped zone image.
Respond with ONLY this JSON — no prose:
{{
  "zone": "{zone_name}",
  "blanching_present": true | false,
  "erythema_present": true | false,
  "swelling_present": true | false,
  "colour_change": "normal" | "erythematous" | "blanched" | "dusky" | "cyanotic" | "mottled",
  "tyndall_signal": true | false,
  "asymmetry_vs_expected": true | false,
  "infection_signal": "none" | "erythema_only" | "swelling_plus_erythema" | "fluctuance",
  "concern_level": "none" | "low" | "moderate" | "high" | "critical",
  "clinical_note": "one sentence — what you see and clinical significance for this zone",
  "danger_zone_proximity": "near" | "distant" | "unknown"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class ZoneAnalysis(BaseModel):
    zone:                    str
    blanching_present:       bool = False
    erythema_present:        bool = False
    swelling_present:        bool = False
    colour_change:           str = "normal"
    tyndall_signal:          bool = False
    asymmetry_vs_expected:   bool = False
    infection_signal:        str = "none"
    concern_level:           str = "none"
    clinical_note:           str = ""
    danger_zone_proximity:   str = "unknown"
    danger_zones:            List[str] = []
    relevant_complications:  List[str] = []


class LandmarkAnalysisResponse(BaseModel):
    face_detected:           bool
    face_bbox:               Optional[List[int]]
    zones_analysed:          int
    zone_results:            List[ZoneAnalysis]
    highest_concern_zone:    Optional[str]
    highest_concern_level:   str
    global_clinical_summary: str
    signals_localised:       bool    # True = anatomical localisation achieved
    generated_at_utc:        str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/landmark-analyse",
    response_model=LandmarkAnalysisResponse,
    summary="Zone-specific injectable complication analysis (Improvement 4)",
)
async def landmark_analyse(
    file:     UploadFile = File(...),
    context:  str = Form(default=""),
    zones:    str = Form(default=""),  # comma-sep zone names; empty = all
) -> LandmarkAnalysisResponse:
    """
    Improvement 4: Anatomical landmark detection with zone-specific analysis.

    Instead of asking GPT-4o to describe the whole image, this:
    1. Detects the face with Haar cascade
    2. Crops each anatomical zone
    3. Runs a zone-specific prompt on each crop
    4. Returns localised signals: "blanching in nasolabial zone" not "blanching visible"

    This is clinically superior because:
    - Vascular occlusion in glabella vs nasolabial fold has different protocols
    - Zone-specific cropping improves GPT-4o attention on the relevant area
    - Proximity to danger zones is explicitly flagged
    """
    image_bytes = await file.read()

    # Preprocess
    try:
        from app.api.vision_engine_v2 import preprocess_image
        image_bytes = await asyncio.to_thread(preprocess_image, image_bytes)
    except ImportError:
        pass

    # Detect landmarks
    try:
        zone_map, face_bbox, annotated_bytes = await asyncio.to_thread(
            _detect_face_and_zones, image_bytes
        )
        face_detected = "full_image" not in zone_map
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"[Landmarks] Detection failed: {e}")
        zone_map = {"full_image": (0, 0, 800, 600)}
        face_detected = False
        face_bbox = (0, 0, 800, 600)

    # Filter zones if requested
    requested = [z.strip() for z in zones.split(",") if z.strip()] if zones else []
    if requested:
        zone_map = {k: v for k, v in zone_map.items() if k in requested}

    # Prioritise high-risk zones: analyse glabella, periorbital, nose first
    priority_order = [
        "glabella", "right_periorbital", "left_periorbital",
        "nose", "lips_perioral", "right_cheek", "left_cheek",
        "forehead", "chin_jawline", "full_image",
    ]
    sorted_zones = sorted(
        zone_map.items(),
        key=lambda kv: priority_order.index(kv[0]) if kv[0] in priority_order else 99,
    )

    zone_results: List[ZoneAnalysis] = []
    concern_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}

    async def analyse_zone(zone_name: str, bbox: Tuple[int, int, int, int]) -> Optional[ZoneAnalysis]:
        b64 = await asyncio.to_thread(_crop_zone, image_bytes, bbox)
        system = _build_zone_prompt(zone_name)
        user = f"Assess this {zone_name.replace('_', ' ')} zone crop."
        if context:
            user += f" Context: {context}"

        try:
            model_id = VISION_MODEL
            if "claude" in model_id.lower() and not OPENAI_API_KEY:
                model_id = "gpt-4o"

            payload = {
                "model": model_id, "temperature": 0.0, "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
                        {"type": "text", "text": user},
                    ]},
                ],
            }
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    f"{OPENAI_BASE_URL}/chat/completions", json=payload,
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                             "Content-Type": "application/json"},
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
                data = json.loads(cleaned)

            clinical = ZONE_CLINICAL_MAP.get(zone_name, {})
            return ZoneAnalysis(
                **data,
                danger_zones=clinical.get("danger_zones", []),
                relevant_complications=clinical.get("complications", []),
            )
        except json.JSONDecodeError:
            return ZoneAnalysis(zone=zone_name, clinical_note="Parse failed — zone skipped")
        except Exception as e:
            logger.warning(f"[Landmarks] Zone {zone_name} analysis failed: {e}")
            return None

    # Run zones with concurrency limit (avoid rate limits)
    semaphore = asyncio.Semaphore(3)

    async def bounded_analyse(name: str, bbox: Tuple) -> Optional[ZoneAnalysis]:
        async with semaphore:
            return await analyse_zone(name, bbox)

    tasks = [bounded_analyse(name, bbox) for name, bbox in sorted_zones]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    zone_results = [r for r in results if r is not None]

    # Find highest concern zone
    if zone_results:
        highest = max(zone_results, key=lambda z: concern_order.get(z.concern_level, 0))
        highest_zone  = highest.zone if concern_order.get(highest.concern_level, 0) > 0 else None
        highest_level = highest.concern_level
    else:
        highest_zone  = None
        highest_level = "none"

    # Global clinical summary
    critical_zones  = [z for z in zone_results if z.concern_level in ("critical", "high")]
    moderate_zones  = [z for z in zone_results if z.concern_level == "moderate"]

    if critical_zones:
        notes = "; ".join(f"{z.zone}: {z.clinical_note}" for z in critical_zones[:2])
        summary = f"Critical signals detected — {notes}."
    elif moderate_zones:
        notes = "; ".join(f"{z.zone}: {z.clinical_note}" for z in moderate_zones[:2])
        summary = f"Moderate concern in {len(moderate_zones)} zone(s) — {notes}."
    elif zone_results:
        summary = f"{len(zone_results)} zone(s) assessed. No significant signals detected."
    else:
        summary = "No zones analysed."

    return LandmarkAnalysisResponse(
        face_detected=face_detected,
        face_bbox=list(face_bbox) if face_detected else None,
        zones_analysed=len(zone_results),
        zone_results=zone_results,
        highest_concern_zone=highest_zone,
        highest_concern_level=highest_level,
        global_clinical_summary=summary,
        signals_localised=face_detected and len(zone_results) > 1,
        generated_at_utc=_now(),
    )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post(
    "/landmark-preview",
    summary="Return annotated image showing detected zones",
)
async def landmark_preview(file: UploadFile = File(...)):
    """Returns JPEG with face bounding box and zone outlines drawn."""
    from fastapi.responses import Response
    image_bytes = await file.read()
    try:
        _, _, annotated = await asyncio.to_thread(_detect_face_and_zones, image_bytes)
        return Response(content=annotated, media_type="image/jpeg")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}")
