"""
AesthetiCite Vision Extensions
================================
Solves four gaps in the Vision Engine. Single additive router — no existing
files are modified except for two import lines in visual_counseling.py.

Endpoints added:
  POST /visual/export-pdf            — PDF export of a visual session (Gap 1)
  POST /visual/log-serial-case       — Serial comparison → case log (Gap 2)
  GET  /visual/glossary              — Live RAG-wired glossary (Gap 3)
  POST /visual/preprocedure-from-vision  — Vision → pre-procedure check (Gap 4)

Integration:
  In app/api/visual_counseling.py, add at the top:
      from app.api.vision_extensions import router as vision_ext_router
  And in main.py (after visual_counseling_router is included):
      app.include_router(vision_ext_router)

Dependencies already in the project:
  reportlab, fastapi, pydantic, asyncio
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visual", tags=["Vision Extensions"])

EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_date() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


# ─────────────────────────────────────────────────────────────────────────────
# GAP 1 — PDF Export of Visual Session
# POST /visual/export-pdf
# ─────────────────────────────────────────────────────────────────────────────

class TriggeredProtocolForPDF(BaseModel):
    protocol_name: str
    urgency: str
    confidence: float
    detected_signals: List[str] = []
    headline: str
    immediate_action: str


class VisualSessionPDFRequest(BaseModel):
    """All fields are optional — export whatever the clinician has at the time."""
    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None
    patient_ref: Optional[str] = None          # de-identified ref, not a name
    visual_id: Optional[str] = None
    question: Optional[str] = None
    analysis_text: Optional[str] = None
    triggered_protocols: List[TriggeredProtocolForPDF] = []
    serial_comparison_summary: Optional[str] = None  # from /serial-compare
    notes: Optional[str] = None


class _PDF:
    """Minimal ReportLab writer — same pattern as complication_protocol_engine."""

    BRAND = "#1a1a2e"
    RED   = "#e53e3e"
    ORANGE = "#dd6b20"
    GREY  = "#4a5568"

    def __init__(self, path: str) -> None:
        self.c = canvas.Canvas(path, pagesize=A4)
        self.w, self.h = A4
        self.L = 18 * mm
        self.R = self.w - 18 * mm
        self.T = self.h - 18 * mm
        self.B = 22 * mm
        self.y = self.T

    def _ensure(self, need: float) -> None:
        if self.y - need < self.B:
            self.c.showPage()
            self.y = self.T

    def _hex(self, h: str) -> tuple:
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

    def title_block(self, title: str, subtitle: str) -> None:
        r, g, b = self._hex(self.BRAND)
        self.c.setFillColorRGB(r, g, b)
        self.c.rect(0, self.h - 28 * mm, self.w, 28 * mm, fill=1, stroke=0)
        self.c.setFillColorRGB(1, 1, 1)
        self.c.setFont("Helvetica-Bold", 14)
        self.c.drawString(self.L, self.h - 12 * mm, title)
        self.c.setFont("Helvetica", 9)
        self.c.drawString(self.L, self.h - 18 * mm, subtitle)
        self.y = self.h - 35 * mm

    def section(self, text: str) -> None:
        self._ensure(16)
        self.y -= 4
        r, g, b = self._hex(self.BRAND)
        self.c.setFillColorRGB(r, g, b)
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawString(self.L, self.y, text.upper())
        self.y -= 2
        self.c.setStrokeColorRGB(r, g, b)
        self.c.line(self.L, self.y, self.R, self.y)
        self.y -= 10

    def body(self, text: str, font: str = "Helvetica", size: int = 9,
             leading: int = 13, bullet: Optional[str] = None, color: Optional[str] = None) -> None:
        if color:
            r, g, b = self._hex(color)
            self.c.setFillColorRGB(r, g, b)
        else:
            self.c.setFillColorRGB(0.1, 0.1, 0.1)
        self.c.setFont(font, size)
        prefix = f"{bullet} " if bullet else ""
        indent = stringWidth(prefix, font, size) if bullet else 0
        max_w = self.R - self.L - indent

        words = text.split()
        line = ""
        first = True
        for word in words:
            test = (line + " " + word).strip()
            if stringWidth(test, font, size) <= max_w:
                line = test
            else:
                self._ensure(leading)
                x = self.L + (0 if first else indent)
                self.c.drawString(x, self.y, (prefix if first else "") + line)
                self.y -= leading
                line = word
                first = False
        if line:
            self._ensure(leading)
            x = self.L + (0 if first else indent)
            self.c.drawString(x, self.y, (prefix if first else "") + line)
            self.y -= leading

    def footer(self) -> None:
        self.c.setFont("Helvetica", 7)
        self.c.setFillColorRGB(0.5, 0.5, 0.5)
        disclaimer = (
            "AesthetiCite Visual Session Report — AI-assisted clinical decision support. "
            "Not a substitute for clinical examination or professional judgement."
        )
        self.c.drawString(self.L, 12 * mm, disclaimer)

    def save(self) -> None:
        self.footer()
        self.c.save()


def _build_visual_pdf(req: VisualSessionPDFRequest, path: str) -> None:
    pdf = _PDF(path)

    subtitle_parts = [f"Generated: {_short_date()}"]
    if req.patient_ref:
        subtitle_parts.append(f"Patient ref: {req.patient_ref}")
    if req.clinician_id:
        subtitle_parts.append(f"Clinician: {req.clinician_id}")
    if req.clinic_id:
        subtitle_parts.append(f"Clinic: {req.clinic_id}")

    pdf.title_block(
        "AesthetiCite Visual Session Report",
        "  |  ".join(subtitle_parts),
    )

    # ── Clinical question ──────────────────────────────────────────────────
    if req.question:
        pdf.section("Clinical Question")
        pdf.body(req.question, font="Helvetica-Bold", size=10)

    # ── GPT-4o analysis ────────────────────────────────────────────────────
    if req.analysis_text:
        pdf.section("Visual Analysis (AI-Assisted)")
        pdf.body(req.analysis_text)

    # ── Triggered protocols ────────────────────────────────────────────────
    if req.triggered_protocols:
        pdf.section("Triggered Complication Protocols")
        for p in req.triggered_protocols:
            urgency_color = {
                "critical": pdf.RED,
                "high": pdf.ORANGE,
                "moderate": "#d69e2e",
            }.get(p.urgency, pdf.GREY)

            pdf.body(
                f"{p.protocol_name.upper()} — {p.urgency.upper()} "
                f"(confidence {round(p.confidence * 100)}%)",
                font="Helvetica-Bold",
                size=9,
                color=urgency_color,
            )
            pdf.body(p.headline, bullet="→")
            pdf.body(f"Immediate action: {p.immediate_action}", bullet="⚠")
            if p.detected_signals:
                pdf.body(
                    "Detected signals: " + ", ".join(
                        s.replace("_", " ").title() for s in p.detected_signals
                    ),
                    bullet=" ",
                    color=pdf.GREY,
                )
            pdf.y -= 4

    # ── Serial comparison ──────────────────────────────────────────────────
    if req.serial_comparison_summary:
        pdf.section("Serial Comparison / Healing Tracker")
        pdf.body(req.serial_comparison_summary)

    # ── Clinician notes ────────────────────────────────────────────────────
    if req.notes:
        pdf.section("Clinician Notes")
        pdf.body(req.notes)

    # ── Disclaimer ─────────────────────────────────────────────────────────
    pdf.section("Disclaimer")
    pdf.body(
        "This report contains AI-assisted visual analysis. It is clinical decision support "
        "only and must not be used as a substitute for clinical examination, histological "
        "assessment, or professional clinical judgement. All triggered protocols should be "
        "verified against current guidelines and local emergency procedures."
    )

    pdf.save()


@router.post("/export-pdf", summary="Export a visual session as a medico-legal PDF")
def export_visual_session_pdf(req: VisualSessionPDFRequest) -> Dict[str, Any]:
    """
    Accepts the full visual session payload (analysis text, triggered protocols,
    serial comparison summary, clinician notes) and returns a downloadable PDF.
    """
    filename = f"visual_session_{uuid.uuid4().hex[:10]}_{datetime.now().strftime('%Y%m%d')}.pdf"
    path = os.path.join(EXPORT_DIR, filename)
    try:
        _build_visual_pdf(req, path)
    except Exception as e:
        logger.exception("Visual session PDF generation failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    return {
        "status": "ok",
        "filename": filename,
        "pdf_path": path,
        "download_url": f"/visual/download-pdf/{filename}",
    }


@router.get("/download-pdf/{filename}", summary="Download a previously generated visual PDF")
def download_visual_pdf(filename: str) -> FileResponse:
    path = os.path.join(EXPORT_DIR, filename)
    if not os.path.exists(path) or ".." in filename:
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=filename)


# ─────────────────────────────────────────────────────────────────────────────
# GAP 2 — Serial Comparison → Case Log
# POST /visual/log-serial-case
# ─────────────────────────────────────────────────────────────────────────────

class SerialCaseLogRequest(BaseModel):
    clinic_id: Optional[str] = None
    clinician_id: Optional[str] = None
    patient_ref: Optional[str] = None        # de-identified
    visual_id_before: Optional[str] = None
    visual_id_after: Optional[str] = None
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_type: Optional[str] = None
    protocol_key: Optional[str] = None       # e.g. "vascular_occlusion" if applicable
    symptoms: List[str] = []
    comparison_summary: Optional[str] = None  # GPT-4o serial comparison text
    outcome: Optional[str] = None            # e.g. "resolved", "improving", "worsening"
    days_between_images: Optional[int] = None


class SerialCaseLogResponse(BaseModel):
    status: str
    case_id: str
    logged_at_utc: str


# In-memory store (matches the same pattern as complication_protocol_engine.py
# CASE_STORE — swap for Postgres when ready, same as the rest of the platform)
_SERIAL_CASE_STORE: List[Dict[str, Any]] = []


@router.post(
    "/log-serial-case",
    response_model=SerialCaseLogResponse,
    summary="Log a serial comparison as a case record",
)
def log_serial_case(req: SerialCaseLogRequest) -> SerialCaseLogResponse:
    """
    Persists the serial comparison (before/after) as a structured case record.
    This populates the proprietary complication dataset from visual sessions.

    Also attempts to wire into the complication protocol engine's case log
    if protocol_key is provided, so the dataset grows from both text and visual
    case sources.
    """
    case_id = str(uuid.uuid4())
    logged_at = _now()

    record: Dict[str, Any] = {
        "case_id": case_id,
        "logged_at_utc": logged_at,
        "source": "vision_serial",
        "clinic_id": req.clinic_id,
        "clinician_id": req.clinician_id,
        "patient_ref": req.patient_ref,
        "visual_id_before": req.visual_id_before,
        "visual_id_after": req.visual_id_after,
        "procedure": req.procedure,
        "region": req.region,
        "product_type": req.product_type,
        "protocol_key": req.protocol_key,
        "symptoms": req.symptoms,
        "comparison_summary": req.comparison_summary,
        "outcome": req.outcome,
        "days_between_images": req.days_between_images,
    }
    _SERIAL_CASE_STORE.append(record)

    # ── Also wire into complication engine case store if protocol_key given ──
    if req.protocol_key:
        try:
            from app.api.complication_protocol_engine import (
                CASE_STORE as COMP_CASE_STORE,
                LoggedCase,
            )
            comp_case = LoggedCase(
                case_id=case_id,
                logged_at_utc=logged_at,
                clinic_id=req.clinic_id,
                clinician_id=req.clinician_id,
                protocol_key=req.protocol_key,
                region=req.region,
                procedure=req.procedure,
                product_type=req.product_type,
                symptoms=req.symptoms,
                outcome=req.outcome,
            )
            COMP_CASE_STORE.append(comp_case)
            logger.info(
                f"[VisionExt] Serial case {case_id} also written to "
                f"complication engine store (protocol={req.protocol_key})"
            )
        except Exception as e:
            logger.warning(f"[VisionExt] Could not write to complication store: {e}")

    logger.info(f"[VisionExt] Serial case logged: {case_id} (outcome={req.outcome})")
    return SerialCaseLogResponse(status="ok", case_id=case_id, logged_at_utc=logged_at)


@router.get("/serial-cases", summary="List all logged serial visual cases")
def list_serial_cases(
    clinic_id: Optional[str] = None,
    clinician_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    cases = _SERIAL_CASE_STORE
    if clinic_id:
        cases = [c for c in cases if c.get("clinic_id") == clinic_id]
    if clinician_id:
        cases = [c for c in cases if c.get("clinician_id") == clinician_id]
    return {"total": len(cases), "cases": cases[-limit:][::-1]}


# ─────────────────────────────────────────────────────────────────────────────
# GAP 3 — Feature Glossary wired to RAG evidence retrieval
# GET /visual/glossary
# GET /visual/glossary/{term}
# ─────────────────────────────────────────────────────────────────────────────

# Static glossary terms (the same ones previously decorative)
_GLOSSARY_TERMS: Dict[str, Dict[str, str]] = {
    "blanching": {
        "definition": "Localised pallor of skin indicating reduced or absent perfusion.",
        "clinical_significance": "Immediate red flag for vascular occlusion post-filler. Stop treatment.",
        "retrieval_query": "blanching after filler injection vascular occlusion",
    },
    "mottling": {
        "definition": "Irregular, blotchy skin discolouration often in a net-like pattern.",
        "clinical_significance": "May indicate impaired perfusion or livedo reticularis pattern. High urgency.",
        "retrieval_query": "mottling filler injection vascular compromise livedo",
    },
    "tyndall_effect": {
        "definition": "Blue-grey discolouration caused by superficially placed hyaluronic acid filler.",
        "clinical_significance": "Cosmetic complication; requires hyaluronidase dissolution.",
        "retrieval_query": "Tyndall effect hyaluronic acid filler blue discolouration",
    },
    "ptosis": {
        "definition": "Drooping of the upper eyelid or brow, often following botulinum toxin diffusion.",
        "clinical_significance": "Can be treated with apraclonidine 0.5% eye drops. Usually temporary.",
        "retrieval_query": "ptosis botulinum toxin diffusion treatment apraclonidine",
    },
    "hyaluronidase": {
        "definition": "Enzyme that dissolves hyaluronic acid filler; first-line treatment for HA-related vascular occlusion.",
        "clinical_significance": "Must be immediately available in all HA filler clinics.",
        "retrieval_query": "hyaluronidase dose vascular occlusion filler emergency",
    },
    "vascular_occlusion": {
        "definition": "Blockage of a blood vessel by filler material, leading to ischaemia.",
        "clinical_significance": "Time-critical emergency. Initiate protocol immediately on any blanching.",
        "retrieval_query": "vascular occlusion filler treatment hyaluronidase ischaemia",
    },
    "danger_zones": {
        "definition": "Anatomical regions where filler injection carries heightened risk of vascular injury.",
        "clinical_significance": "Include nasal tip, glabella, nasolabial fold, and periorbital area.",
        "retrieval_query": "facial danger zones filler injection vascular anatomy",
    },
    "biofilm": {
        "definition": "Bacterial community embedded in a matrix, forming around implanted material including filler.",
        "clinical_significance": "Associated with delayed inflammatory nodules. Requires specific antibiotic regimen.",
        "retrieval_query": "biofilm filler delayed nodule infection treatment antibiotics",
    },
    "cannula": {
        "definition": "Blunt-tipped flexible needle used to inject filler with reduced vascular risk.",
        "clinical_significance": "Generally safer than sharp needle in high-risk zones; does not eliminate vascular risk.",
        "retrieval_query": "cannula versus needle filler injection vascular safety",
    },
    "aci_score": {
        "definition": "Aesthetic Confidence Index — AesthetiCite's per-answer evidence quality score (0–10).",
        "clinical_significance": "Higher ACI = stronger evidence grounding. Use lower-ACI answers with greater caution.",
        "retrieval_query": "evidence grading aesthetic medicine clinical decision support",
    },
}


async def _fetch_rag_evidence(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """
    Pull top-k relevant chunks from the RAG corpus for a glossary term.
    Falls back to empty list gracefully if retriever is unavailable.
    """
    try:
        import asyncio
        from app.rag.retriever import retrieve_db

        # retrieve_db is sync — wrap in thread so we don't block the event loop
        results = await asyncio.to_thread(retrieve_db, query, k=k)
        return [
            {
                "title": r.get("title", ""),
                "source": r.get("journal") or r.get("source") or "",
                "year": r.get("year"),
                "snippet": (r.get("text") or "")[:300],
            }
            for r in (results or [])
        ]
    except Exception as e:
        logger.debug(f"[VisionExt] Glossary RAG fallback for '{query}': {e}")
        return []


@router.get("/glossary", summary="Full aesthetic medicine visual glossary with live RAG evidence")
async def get_full_glossary() -> Dict[str, Any]:
    """
    Returns all glossary terms. Each term includes static definition + clinical
    significance. Evidence snippets are fetched live from the RAG corpus.
    """
    terms_out = []
    for key, meta in _GLOSSARY_TERMS.items():
        evidence = await _fetch_rag_evidence(meta["retrieval_query"])
        terms_out.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "definition": meta["definition"],
            "clinical_significance": meta["clinical_significance"],
            "evidence": evidence,
        })
    return {"count": len(terms_out), "terms": terms_out}


@router.get("/glossary/{term_key}", summary="Single glossary term with live RAG evidence")
async def get_glossary_term(term_key: str) -> Dict[str, Any]:
    """
    Returns a single glossary term with live RAG evidence retrieval.
    Use this on the frontend when the clinician clicks a term tooltip.
    """
    meta = _GLOSSARY_TERMS.get(term_key)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Term '{term_key}' not found. "
                   f"Valid keys: {list(_GLOSSARY_TERMS.keys())}",
        )
    evidence = await _fetch_rag_evidence(meta["retrieval_query"])
    return {
        "key": term_key,
        "label": term_key.replace("_", " ").title(),
        "definition": meta["definition"],
        "clinical_significance": meta["clinical_significance"],
        "evidence": evidence,
        "retrieved_at_utc": _now(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GAP 4 — Vision → Pre-Procedure Safety Check
# POST /visual/preprocedure-from-vision
# ─────────────────────────────────────────────────────────────────────────────

class VisionPreProcedureRequest(BaseModel):
    """
    The clinician provides procedure context; the vision analysis_text provides
    additional patient factor signals to enrich the risk score.
    """
    procedure: str = Field(..., description="e.g. 'lip filler'")
    region: str = Field(..., description="e.g. 'lips'")
    product_type: str = Field(..., description="e.g. 'HA filler'")
    technique: Optional[str] = None
    injector_experience_level: Optional[str] = None

    # Vision-derived context
    analysis_text: Optional[str] = None       # GPT-4o analysis of patient image
    triggered_signals: List[str] = []         # from vision protocol bridge

    # Manual patient factor overrides (optional — vision signals fill gaps)
    prior_vascular_event: Optional[bool] = None
    active_infection_near_site: Optional[bool] = None
    anticoagulation: Optional[bool] = None
    smoking: Optional[bool] = None
    prior_filler_in_same_area: Optional[bool] = None
    allergy_history: Optional[bool] = None

    clinician_id: Optional[str] = None
    clinic_id: Optional[str] = None


def _infer_patient_factors_from_vision(
    analysis_text: str,
    triggered_signals: List[str],
    overrides: Dict[str, Optional[bool]],
) -> Dict[str, Any]:
    """
    Maps vision signals and analysis text to PatientFactors fields.
    Manual overrides take precedence.
    """
    text = (analysis_text or "").lower()
    signals = set(triggered_signals)

    def _resolve(key: str, vision_condition: bool) -> Optional[bool]:
        if overrides.get(key) is not None:
            return overrides[key]
        return True if vision_condition else None

    return {
        "prior_vascular_event": _resolve(
            "prior_vascular_event",
            "vascular" in text or "blanching" in signals or "mottling" in signals,
        ),
        "active_infection_near_site": _resolve(
            "active_infection_near_site",
            any(s in signals for s in ["infection_signs", "fluctuance"]) or
            any(w in text for w in ["infection", "purulent", "abscess"]),
        ),
        "anticoagulation": _resolve(
            "anticoagulation",
            "anticoagul" in text or "bruising" in text,
        ),
        "smoking": _resolve(
            "smoking",
            "smok" in text,
        ),
        "prior_filler_in_same_area": _resolve(
            "prior_filler_in_same_area",
            "previous filler" in text or "prior filler" in text or "existing filler" in text,
        ),
        "allergy_history": _resolve(
            "allergy_history",
            any(s in signals for s in ["angioedema", "systemic_allergic"]) or
            "allerg" in text,
        ),
        "autoimmune_history": None,
        "vascular_disease": _resolve(
            "prior_vascular_event",  # reuse same signal
            "vascular disease" in text,
        ),
    }


@router.post(
    "/preprocedure-from-vision",
    summary="Run pre-procedure safety check enriched by vision analysis",
)
def preprocedure_from_vision(req: VisionPreProcedureRequest) -> Dict[str, Any]:
    """
    Takes a vision analysis result and the clinician's intended procedure,
    infers patient factors from the image analysis, and runs the full
    pre-procedure safety engine.

    This closes the loop: Vision → Patient factor inference → Risk score →
    Go/Caution/High-risk decision → PDF exportable result.
    """
    try:
        from app.api.preprocedure_safety_engine import (
            PreProcedureRequest,
            PatientFactors,
            build_response,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Pre-procedure safety engine not available: {e}",
        )

    # Build patient factors from vision signals + manual overrides
    overrides = {
        "prior_vascular_event": req.prior_vascular_event,
        "active_infection_near_site": req.active_infection_near_site,
        "anticoagulation": req.anticoagulation,
        "smoking": req.smoking,
        "prior_filler_in_same_area": req.prior_filler_in_same_area,
        "allergy_history": req.allergy_history,
    }
    inferred = _infer_patient_factors_from_vision(
        req.analysis_text or "",
        req.triggered_signals,
        overrides,
    )

    try:
        pf = PatientFactors(**inferred)
    except Exception:
        pf = PatientFactors()  # fall back to no factors rather than crashing

    safety_request = PreProcedureRequest(
        procedure=req.procedure,
        region=req.region,
        product_type=req.product_type,
        technique=req.technique,
        injector_experience_level=req.injector_experience_level,
        patient_factors=pf,
        clinician_id=req.clinician_id,
        clinic_id=req.clinic_id,
    )

    try:
        result = build_response(safety_request)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pre-procedure check from vision failed")
        raise HTTPException(status_code=500, detail=f"Safety engine error: {e}")

    # Attach the source context so the frontend can show what was inferred
    result_dict = result.model_dump()
    result_dict["vision_context"] = {
        "analysis_text_used": bool(req.analysis_text),
        "triggered_signals_used": req.triggered_signals,
        "inferred_patient_factors": {
            k: v for k, v in inferred.items() if v is not None
        },
        "manual_overrides_applied": {
            k: v for k, v in overrides.items() if v is not None
        },
    }
    return result_dict
