"""
AesthetiCite Vision
app/api/vision_followup.py

Serial post-procedure image analysis engine.
Provides timeline comparison, healing trend assessment, complication flagging,
and PDF clinical report export.

Endpoints:
  POST /api/vision/analyze          — full timeline analysis + assessment
  POST /api/vision/analyze/export   — same analysis + PDF export
  GET  /api/vision/procedures       — available procedure options
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from app.core.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vision", tags=["AesthetiCite Vision"])

ENGINE_VERSION = "1.0.0"
EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

MAX_IMAGE_BYTES = 20 * 1024 * 1024   # 20 MB per image
MAX_IMAGES = 10
MIN_IMAGES = 2
NORMALIZE_SIZE = (768, 768)
PREVIEW_SIZE = (480, 480)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class ImageMetrics(BaseModel):
    filename: str
    time_hint_days: int
    asymmetry_raw: float
    redness_raw: float
    brightness_raw: float
    asymmetry_label: str
    redness_label: str
    asymmetry_class: str
    redness_class: str


class VisionAssessment(BaseModel):
    urgency: str
    urgency_class: str
    healing_trend: str
    trend_class: str
    summary: str
    findings: List[str]
    concerns: List[str]
    recommendations: List[str]
    patient_message: str
    positioning_note: str


class VisionResponse(BaseModel):
    request_id: str
    engine_version: str
    generated_at_utc: str
    procedure: str
    notes: str
    image_count: int
    timeline: List[str]
    series_metrics: List[ImageMetrics]
    assessment: VisionAssessment
    baseline_preview: str   # base64 data URI
    latest_preview: str     # base64 data URI
    disclaimer: str


class ExportResponse(BaseModel):
    request_id: str
    filename: str
    pdf_path: str


# ─────────────────────────────────────────────────────────────────────────────
# Image processing — all CPU-bound, runs in thread pool
# ─────────────────────────────────────────────────────────────────────────────

def pil_from_bytes(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return ImageOps.exif_transpose(img)


def check_image_quality(arr: np.ndarray) -> Tuple[bool, List[str]]:
    """Basic sanity checks before analysis. Returns (ok, issues)."""
    issues: List[str] = []
    mean = float(arr.mean())
    std = float(arr.std())
    if mean < 12:
        issues.append("Image appears very dark — check exposure or file integrity")
    if mean > 243:
        issues.append("Image appears overexposed — results will be unreliable")
    if std < 12:
        issues.append("Very low image contrast — image may be a blank or solid colour")
    return len(issues) == 0, issues


def normalize_image(img: Image.Image, size: Tuple[int, int] = NORMALIZE_SIZE) -> np.ndarray:
    """Resize with letterboxing to a consistent canvas size."""
    img = ImageOps.contain(img, size)
    canvas = Image.new("RGB", size, (0, 0, 0))
    x = (size[0] - img.width) // 2
    y = (size[1] - img.height) // 2
    canvas.paste(img, (x, y))
    return np.array(canvas)


def to_b64_preview(arr: np.ndarray, size: Tuple[int, int] = PREVIEW_SIZE) -> str:
    """Resize and encode to base64 JPEG data URI for frontend."""
    img = Image.fromarray(arr.astype(np.uint8))
    img.thumbnail(size)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def central_crop(arr: np.ndarray, procedure: str) -> np.ndarray:
    """Crop to the clinically relevant central region per procedure type."""
    h, w = arr.shape[:2]
    if procedure == "breast_augmentation":
        y1, y2 = int(h * 0.20), int(h * 0.78)
        x1, x2 = int(w * 0.15), int(w * 0.85)
    elif procedure in ("rhinoplasty", "nose"):
        y1, y2 = int(h * 0.12), int(h * 0.65)
        x1, x2 = int(w * 0.25), int(w * 0.75)
    else:
        y1, y2 = int(h * 0.15), int(h * 0.72)
        x1, x2 = int(w * 0.18), int(w * 0.82)
    return arr[y1:y2, x1:x2]


def asymmetry_score(arr: np.ndarray) -> float:
    """
    Pixel-level left-right mirror difference score.
    NOTE: Sensitive to patient head position — a 5-degree head turn can produce
    a score comparable to mild anatomical asymmetry.
    """
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    left = gray[:, :w // 2].astype(np.float32)
    right = cv2.flip(gray[:, w - (w // 2):], 1).astype(np.float32)
    mh = min(left.shape[0], right.shape[0])
    mw = min(left.shape[1], right.shape[1])
    return float(np.abs(left[:mh, :mw] - right[:mh, :mw]).mean() / 255.0)


def redness_score(arr: np.ndarray) -> float:
    """Red channel dominance score. Sensitive to lighting colour temperature."""
    a = arr.astype(np.float32)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    redness = np.clip(r - (g + b) / 2.0, 0, 255)
    return float(redness.mean() / 255.0)


def brightness_score(arr: np.ndarray) -> float:
    """
    Mean image brightness proxy.
    NOT a reliable swelling indicator — strongly influenced by lighting distance.
    """
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (31, 31), 0)
    return float(np.mean(blur) / 255.0)


def classify_band(value: float, low: float, mid: float, high: float) -> str:
    if value < low:
        return "low"
    if value < mid:
        return "mild"
    if value < high:
        return "moderate"
    return "high"


def band_to_class(label: str) -> str:
    return {"low": "ok", "mild": "warn", "moderate": "warn", "high": "danger"}.get(label, "ok")


# ─── Filename timeline hint ───────────────────────────────────────────────────

_TIME_PATTERNS = [
    (r"pre|baseline|day0|day 0|postop0|post-op0", 0),
    (r"day1(?!\d)|day 1", 1),
    (r"day2(?!\d)|day 2", 2),
    (r"day3(?!\d)|day 3", 3),
    (r"day4(?!\d)|day 4", 4),
    (r"day5(?!\d)|day 5", 5),
    (r"day6(?!\d)|day 6", 6),
    (r"week1(?!\d)|week 1", 7),
    (r"week2(?!\d)|week 2", 14),
    (r"week3(?!\d)|week 3", 21),
    (r"week4(?!\d)|week 4|month1(?!\d)|month 1", 30),
    (r"month2(?!\d)|month 2", 60),
    (r"month3(?!\d)|month 3", 90),
    (r"month6(?!\d)|month 6", 180),
    (r"year1(?!\d)|year 1", 365),
]


def parse_time_hint(filename: str) -> int:
    name = filename.lower()
    for pattern, days in _TIME_PATTERNS:
        if re.search(pattern, name):
            return days
    return 999_999


def _note_contains(notes: str, terms: List[str]) -> bool:
    s = notes.lower()
    return any(t in s for t in terms)


# ─────────────────────────────────────────────────────────────────────────────
# Assessment engine
# ─────────────────────────────────────────────────────────────────────────────

def _run_vision_analysis(
    procedure: str,
    notes: str,
    loaded: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """All CPU-bound analysis. Called via asyncio.to_thread — does NOT block event loop."""
    loaded = sorted(loaded, key=lambda x: parse_time_hint(x["filename"]))
    baseline_arr = loaded[0]["array"]
    latest_arr = loaded[-1]["array"]

    series_metrics: List[ImageMetrics] = []
    for item in loaded:
        crop = central_crop(item["array"], procedure)
        asym = asymmetry_score(crop)
        red = redness_score(crop)
        bri = brightness_score(crop)
        asym_label = classify_band(asym, 0.045, 0.075, 0.11)
        red_label = classify_band(red, 0.035, 0.060, 0.090)
        series_metrics.append(ImageMetrics(
            filename=item["filename"],
            time_hint_days=parse_time_hint(item["filename"]),
            asymmetry_raw=round(asym, 4),
            redness_raw=round(red, 4),
            brightness_raw=round(bri, 4),
            asymmetry_label=asym_label.title(),
            redness_label=red_label.title(),
            asymmetry_class=band_to_class(asym_label),
            redness_class=band_to_class(red_label),
        ))

    base_crop = central_crop(baseline_arr, procedure)
    latest_crop = central_crop(latest_arr, procedure)

    base_asym = asymmetry_score(base_crop)
    latest_asym = asymmetry_score(latest_crop)
    base_red = redness_score(base_crop)
    latest_red = redness_score(latest_crop)
    base_bri = brightness_score(base_crop)
    latest_bri = brightness_score(latest_crop)

    delta_asym = latest_asym - base_asym
    delta_red = latest_red - base_red
    delta_bri = latest_bri - base_bri

    has_blanching = _note_contains(notes, ["blanching", "white patch", "pale patch", "skin blanching"])
    has_pain = _note_contains(notes, ["pain", "tender", "tenderness", "severe pain", "throbbing"])
    has_redness_note = _note_contains(notes, ["redness", "erythema", "red", "inflamed", "inflammation"])
    has_warmth = _note_contains(notes, ["warmth", "warm", "hot skin", "heat"])
    has_swelling = _note_contains(notes, ["swelling", "oedema", "edema", "swollen"])
    has_discharge = _note_contains(notes, ["discharge", "pus", "purulent", "drainage"])
    has_fever = _note_contains(notes, ["fever", "temperature", "febrile", "pyrexia"])
    has_vision = _note_contains(notes, ["vision", "visual", "blurred", "diplopia", "sight"])

    findings: List[str] = []
    concerns: List[str] = []
    recommendations: List[str] = []
    urgency = "Routine"
    urgency_class = "ok"

    # ── EMERGENCY: visual symptoms or blanching ────────────────────────────
    if has_vision or (procedure == "injectables" and has_blanching):
        if has_vision:
            concerns.append(
                "Visual symptoms reported. Any visual disturbance after an injectable procedure "
                "is a clinical emergency — immediate escalation is required."
            )
        if has_blanching:
            concerns.append(
                "Blanching reported. This is a high-urgency sign that may indicate vascular "
                "compromise after filler injection. Immediate in-person assessment is required."
            )
        urgency = "Emergency"
        urgency_class = "danger"
        recommendations.append("Do not delay — immediate in-person clinical assessment is required now.")
        recommendations.append("If HA filler was used, initiate your vascular occlusion protocol.")

    # ── URGENT: discharge or fever ────────────────────────────────────────
    elif has_discharge or has_fever:
        concerns.append("Discharge or fever reported — signs compatible with infection or abscess.")
        urgency = "Urgent review"
        urgency_class = "danger"
        recommendations.append("Urgent clinical assessment required. Consider infection or biofilm.")
        if procedure == "breast_augmentation":
            recommendations.append(
                "If breast augmentation: consider imaging and surgical review if abscess is suspected."
            )

    elif has_pain and (has_redness_note or has_warmth):
        concerns.append(
            "Pain with redness or warmth reported. This pattern may indicate inflammation, "
            "infection, or a delayed complication."
        )
        urgency = "Urgent review"
        urgency_class = "danger"
        recommendations.append(
            "Clinical review recommended. Correlate with procedure timing, area treated, and temperature."
        )

    # ── Image-based signals ────────────────────────────────────────────────
    if delta_red > 0.025 or (has_redness_note and latest_red > 0.055):
        findings.append("Redness signal is increased compared with baseline.")
        if urgency == "Routine":
            concerns.append("Increased visual redness signal — monitor for progression.")
            recommendations.append("Check for associated warmth, tenderness, discharge, or fever.")
    else:
        findings.append("No major increase in redness signal versus baseline.")

    if delta_asym > 0.03:
        findings.append("Asymmetry appears more pronounced on the latest image compared with baseline.")
        concerns.append(
            "Progressive asymmetry pattern detected. Note: this metric is sensitive to "
            "patient head position — ensure consistent positioning before interpreting."
        )
        recommendations.append(
            "Clinical review advised to assess for implant position change, fluid collection, "
            "or technique-related asymmetry. Compare with clinical examination findings."
        )
        if urgency == "Routine":
            urgency = "Review advised"
            urgency_class = "warn"
    elif delta_asym > 0.01:
        findings.append(
            "Mild asymmetry change noted. May reflect normal healing variation or "
            "positioning difference between photos."
        )
        recommendations.append(
            "Continue serial comparison. Ensure consistent patient positioning for reliable tracking."
        )
    else:
        findings.append("Symmetry appears stable or improving versus baseline.")

    if delta_bri > 0.018:
        findings.append(
            "Image brightness is higher in the latest photo compared with baseline. "
            "This may reflect increased fullness or a difference in lighting conditions — "
            "brightness alone is not a reliable swelling indicator."
        )
        if has_swelling:
            concerns.append(
                "Swelling reported in notes alongside a brightness increase. "
                "Clinical correlation recommended."
            )
    elif delta_bri < -0.018:
        findings.append(
            "Image brightness is lower in the latest photo — may reflect decreased fullness "
            "or a lighting difference between sessions."
        )
    else:
        findings.append("Image brightness is comparable between baseline and latest photo.")

    if procedure == "breast_augmentation":
        if not concerns and not recommendations:
            recommendations.append(
                "Images appear broadly in line with post-operative healing. "
                "Continue routine follow-up with standardised serial photographs."
            )
        if delta_asym > 0.03 and delta_bri > 0.015:
            concerns.append(
                "Increasing asymmetry with brightness change — hematoma or seroma pattern "
                "cannot be excluded from images alone."
            )
            urgency = "Urgent review"
            urgency_class = "danger"
            recommendations.append(
                "Urgent clinical examination and appropriate imaging should be considered."
            )
    else:
        if not concerns:
            recommendations.append(
                "Continue routine monitoring. Ensure standardised positioning for next follow-up photo."
            )

    if urgency == "Routine" and len(concerns) > 0:
        urgency = "Review advised"
        urgency_class = "warn"

    if urgency in ("Emergency", "Urgent review"):
        healing_trend = "Potential complication pattern"
        trend_class = "danger"
    elif len(concerns) > 0:
        healing_trend = "Closer review recommended"
        trend_class = "warn"
    else:
        healing_trend = "Consistent with recovery"
        trend_class = "ok"

    summary = (
        f"Serial image analysis for {procedure.replace('_', ' ')} across "
        f"{len(loaded)} timepoints. "
        f"Redness signal: {'increased' if delta_red > 0.025 else 'stable/no major change'}. "
        f"Asymmetry: {'increasing trend' if delta_asym > 0.03 else 'stable or improving'}. "
        f"Overall trend: {healing_trend.lower()}."
    )

    patient_message = (
        "Our follow-up image analysis has identified some changes that need to be "
        "reviewed by your clinician. Please contact the clinic as directed."
        if len(concerns) > 0
        else
        "Your follow-up images appear broadly in line with the expected recovery pattern. "
        "Your clinician will review these alongside your clinical examination at your next appointment."
    )

    positioning_note = (
        "Important: image-based metrics (asymmetry, redness, brightness) are sensitive to "
        "patient positioning, lighting conditions, camera distance, and skin tone. "
        "These scores are decision-support indicators and must be interpreted alongside "
        "clinical examination. Consistent positioning across serial photographs is essential "
        "for reliable trend analysis."
    )

    assessment = VisionAssessment(
        urgency=urgency,
        urgency_class=urgency_class,
        healing_trend=healing_trend,
        trend_class=trend_class,
        summary=summary,
        findings=findings,
        concerns=concerns,
        recommendations=recommendations,
        patient_message=patient_message,
        positioning_note=positioning_note,
    )

    return {
        "series_metrics": series_metrics,
        "assessment": assessment,
        "baseline_preview": to_b64_preview(baseline_arr),
        "latest_preview": to_b64_preview(latest_arr),
        "timeline": [item["filename"] for item in loaded],
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF export
# ─────────────────────────────────────────────────────────────────────────────

class _PDFWriter:
    def __init__(self, path: str) -> None:
        self.c = rl_canvas.Canvas(path, pagesize=A4)
        self.width, self.height = A4
        self.left = 18 * mm
        self.right = self.width - 18 * mm
        self.top = self.height - 18 * mm
        self.bottom = 18 * mm
        self.y = self.top

    def _new_page(self) -> None:
        self.c.showPage()
        self.y = self.top

    def _ensure(self, needed: float) -> None:
        if self.y - needed < self.bottom:
            self._new_page()

    def line(self, text: str, font: str = "Helvetica", size: int = 10, leading: int = 14) -> None:
        self._ensure(leading)
        self.c.setFont(font, size)
        self.c.drawString(self.left, self.y, str(text)[:180])
        self.y -= leading

    def wrapped(self, text: str, font: str = "Helvetica", size: int = 10,
                leading: int = 14, bullet: Optional[str] = None) -> None:
        max_w = self.right - self.left
        self.c.setFont(font, size)
        prefix = f"{bullet} " if bullet else ""
        indent = stringWidth(prefix, font, size) if bullet else 0
        usable = max_w - indent
        words = str(text).split()
        current = ""
        first = True

        def flush(t: str, is_first: bool) -> None:
            self._ensure(leading)
            self.c.setFont(font, size)
            if bullet:
                self.c.drawString(
                    self.left if is_first else self.left + indent,
                    self.y,
                    (prefix if is_first else "") + t,
                )
            else:
                self.c.drawString(self.left, self.y, t)
            self.y -= leading

        for word in words:
            candidate = word if not current else f"{current} {word}"
            if stringWidth(candidate, font, size) <= usable:
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


def _export_pdf(response: VisionResponse) -> str:
    filename = f"aestheticite_vision_{response.request_id}.pdf"
    path = os.path.join(EXPORT_DIR, filename)
    pdf = _PDFWriter(path)

    pdf.line("AesthetiCite Vision — Post-Procedure Follow-up Report",
             font="Helvetica-Bold", size=15, leading=20)
    pdf.line(f"Generated: {response.generated_at_utc}")
    pdf.line(f"Engine: v{response.engine_version}  |  Request: {response.request_id}")
    pdf.line(f"Procedure: {response.procedure.replace('_', ' ').title()}")
    pdf.line(f"Images analysed: {response.image_count}")
    pdf.line(f"Timeline: {', '.join(response.timeline)}")
    pdf.y -= 4

    pdf.section(f"Assessment  ·  {response.assessment.urgency}  ·  {response.assessment.healing_trend}")
    pdf.wrapped(response.assessment.summary)

    if response.notes.strip():
        pdf.section("Clinician Notes / Symptoms")
        pdf.wrapped(response.notes.strip())

    pdf.section("Findings")
    for f_item in response.assessment.findings:
        pdf.wrapped(f_item, bullet="•")

    if response.assessment.concerns:
        pdf.section("Concerns")
        for c_item in response.assessment.concerns:
            pdf.wrapped(c_item, bullet="!")

    pdf.section("Recommendations")
    for r_item in response.assessment.recommendations:
        pdf.wrapped(r_item, bullet="->")

    pdf.section("Patient Communication")
    pdf.wrapped(response.assessment.patient_message)

    pdf.section("Image Metrics")
    for m in response.series_metrics:
        pdf.wrapped(
            f"{m.filename}: asymmetry {m.asymmetry_raw} ({m.asymmetry_label}) | "
            f"redness {m.redness_raw} ({m.redness_label}) | "
            f"brightness {m.brightness_raw}",
            bullet="•",
        )

    pdf.section("Positioning Note")
    pdf.wrapped(response.assessment.positioning_note)

    pdf.section("Important Limitation")
    pdf.wrapped(response.disclaimer)

    pdf.save()
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Shared upload + analysis logic
# ─────────────────────────────────────────────────────────────────────────────

async def _build_response(
    procedure: str,
    notes: str,
    files: List[UploadFile],
    request_id: str,
) -> VisionResponse:
    if len(files) < MIN_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"At least {MIN_IMAGES} images are required for timeline analysis.",
        )
    if len(files) > MAX_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_IMAGES} images per analysis.",
        )

    loaded_bytes: List[Tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Image '{f.filename}' exceeds the 20 MB size limit.",
            )
        if not data:
            raise HTTPException(
                status_code=400,
                detail=f"Image '{f.filename}' appears to be empty.",
            )
        loaded_bytes.append((f.filename or f"image_{len(loaded_bytes)+1}.jpg", data))

    def _process() -> List[Dict[str, Any]]:
        processed = []
        for filename, data in loaded_bytes:
            try:
                img = pil_from_bytes(data)
                arr = normalize_image(img)
            except Exception as e:
                raise ValueError(f"Could not decode image '{filename}': {e}")
            ok, issues = check_image_quality(arr)
            if not ok:
                raise ValueError(
                    f"Image quality check failed for '{filename}': {'; '.join(issues)}"
                )
            processed.append({"filename": filename, "array": arr})
        return processed

    try:
        loaded = await asyncio.to_thread(_process)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await asyncio.to_thread(_run_vision_analysis, procedure, notes, loaded)

    return VisionResponse(
        request_id=request_id,
        engine_version=ENGINE_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        procedure=procedure,
        notes=notes,
        image_count=len(files),
        timeline=result["timeline"],
        series_metrics=result["series_metrics"],
        assessment=result["assessment"],
        baseline_preview=result["baseline_preview"],
        latest_preview=result["latest_preview"],
        disclaimer=(
            "AesthetiCite Vision is a clinical decision-support tool. "
            "It does not constitute a medical diagnosis. All image-based signals are "
            "proxy metrics sensitive to patient positioning, lighting, and skin tone. "
            "Results must be interpreted alongside clinical examination, patient history, "
            "and clinician judgment. This output is not a substitute for professional "
            "medical assessment or emergency response where indicated."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

PROCEDURES = {
    "injectables": "Injectables (Fillers / Toxin)",
    "breast_augmentation": "Breast Augmentation",
    "rhinoplasty": "Rhinoplasty / Nose",
    "blepharoplasty": "Blepharoplasty",
    "facelift": "Facelift / Rhytidectomy",
    "liposuction": "Liposuction / Body Contouring",
    "skin_resurfacing": "Skin Resurfacing / Laser",
    "other": "Other / General",
}


@router.post("/analyze", response_model=VisionResponse)
async def analyze(
    procedure: str = Form(...),
    notes: str = Form(""),
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
) -> VisionResponse:
    """Analyse serial post-procedure photos. Returns healing trend, complication flags, per-image metrics."""
    if procedure not in PROCEDURES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown procedure. Valid options: {', '.join(PROCEDURES.keys())}",
        )
    request_id = str(uuid.uuid4())[:12]
    return await _build_response(procedure, notes, files, request_id)


@router.post("/analyze/export", response_model=ExportResponse)
async def analyze_and_export(
    procedure: str = Form(...),
    notes: str = Form(""),
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
) -> ExportResponse:
    """Analyse and export a clinical PDF report."""
    if procedure not in PROCEDURES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown procedure. Valid options: {', '.join(PROCEDURES.keys())}",
        )
    request_id = str(uuid.uuid4())[:12]
    response = await _build_response(procedure, notes, files, request_id)

    try:
        pdf_path = await asyncio.to_thread(_export_pdf, response)
    except Exception as e:
        logger.error(f"Vision PDF export failed: {e}")
        raise HTTPException(status_code=500, detail="PDF export failed.")

    return ExportResponse(
        request_id=request_id,
        filename=os.path.basename(pdf_path),
        pdf_path=pdf_path,
    )


@router.get("/procedures")
async def list_procedures() -> Dict[str, Any]:
    """Return available procedure options for the frontend select."""
    return {"procedures": [{"value": k, "label": v} for k, v in PROCEDURES.items()]}
