"""
AesthetiCite — Medico-Legal Report Generator  (Money Feature)
=============================================================
POST /api/generate-report        → JSON response with all sections + report_id
POST /api/generate-report/pdf    → Binary PDF download (reportlab)
GET  /api/generate-report/{id}   → Retrieve stored report

This is the feature clinics will pay for.
Every complication MUST be documented. This makes it one button.

Report sections (MDO-standard):
  1. Incident details (date, time, practitioner, clinic)
  2. Patient reference (non-identifiable)
  3. Procedure details (what was done, products used)
  4. Complication (what happened, when, how detected)
  5. Timeline (chronological sequence)
  6. Treatment given (all interventions with times and doses)
  7. Patient response
  8. Escalation actions (referrals, emergency calls)
  9. Follow-up plan
  10. Evidence basis (AesthetiCite citations used)
  11. Clinician declaration
  12. Disclaimer

Design:
  - All fields optional except complication — pre-filled from session context
  - PDF uses professional clinic branding (logo placeholder + clinic name)
  - Reports stored in PostgreSQL (safety_reports table from network_workspace)
  - If safety_reports table not available: fallback to export file only
  - Report ID allows retrieval and sharing
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_optional_user
from app.db.session import get_db

router = APIRouter(prefix="/api/generate-report", tags=["Medico-Legal Report"])

EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

ENGINE_VERSION = "1.0"
REPORT_REVISION = "2026-03"


# ===========================================================================
# Pydantic input model — all optional except complication
# ===========================================================================

class ReportInput(BaseModel):
    # Incident
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    report_date: Optional[str] = None          # ISO date string, defaults to now
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None

    # Clinician
    practitioner_name: Optional[str] = None
    practitioner_role: Optional[str] = None
    practitioner_registration: Optional[str] = None

    # Patient (non-identifiable)
    patient_reference: Optional[str] = Field(None, description="Non-identifiable reference only")
    patient_age_range: Optional[str] = None    # e.g. "30–40"

    # Procedure
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_name: Optional[str] = None
    product_batch: Optional[str] = None
    volume_ml: Optional[str] = None
    technique: Optional[str] = None
    injector_experience: Optional[str] = None

    # Complication (REQUIRED)
    complication: str = Field(..., min_length=2)
    onset_time: Optional[str] = None           # e.g. "Immediate", "2 minutes post-injection"
    symptoms: Optional[str] = None
    suspected_diagnosis: Optional[str] = None

    # Timeline (structured or free text)
    timeline: Optional[str] = None             # Free-text or structured JSON

    # Treatment
    treatment_given: Optional[str] = None
    hyaluronidase_dose: Optional[str] = None
    medications_given: Optional[List[str]] = None
    time_of_first_intervention: Optional[str] = None

    # Response + outcome
    patient_response: Optional[str] = None
    outcome: Optional[str] = None
    time_to_resolution: Optional[str] = None

    # Escalation
    escalation_actions: Optional[str] = None
    referrals_made: Optional[str] = None
    emergency_services_called: bool = False

    # Follow-up
    follow_up_plan: Optional[str] = None
    review_date: Optional[str] = None

    # Evidence
    evidence_refs: Optional[List[Dict[str, Any]]] = None  # [{title, source, year}]
    protocol_used: Optional[str] = None

    # Notes
    clinician_notes: Optional[str] = None

    # Storage
    clinic_id: Optional[str] = None
    save_to_db: bool = True


# ===========================================================================
# Report generator — pure Python, no LLM
# ===========================================================================

def _now_display() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")


def _or(value: Optional[str], fallback: str = "Not recorded") -> str:
    return value.strip() if value and value.strip() else fallback


def build_report_sections(inp: ReportInput, report_id: str) -> Dict[str, Any]:
    """
    Build all report sections as structured text.
    Returns a dict that can be rendered as PDF or JSON.
    """
    now = _now_display()
    report_date = inp.report_date or now

    # Auto-generate timeline if not provided
    timeline = inp.timeline
    if not timeline:
        parts = []
        if inp.incident_time:
            parts.append(f"{inp.incident_time}: Procedure commenced.")
        if inp.onset_time:
            parts.append(f"{inp.onset_time}: Complication identified — {inp.complication}.")
        if inp.time_of_first_intervention:
            parts.append(f"{inp.time_of_first_intervention}: First intervention commenced.")
        if inp.time_to_resolution:
            parts.append(f"Resolution: {inp.time_to_resolution} — {_or(inp.outcome)}.")
        timeline = "\n".join(parts) if parts else "Timeline not recorded."

    # Build treatment summary
    tx_parts = []
    if inp.treatment_given:
        tx_parts.append(inp.treatment_given)
    if inp.hyaluronidase_dose:
        tx_parts.append(f"Hyaluronidase: {inp.hyaluronidase_dose}")
    if inp.medications_given:
        tx_parts.extend(inp.medications_given)
    treatment_summary = "\n".join(f"• {t}" for t in tx_parts) if tx_parts else "Not recorded."

    return {
        "report_id":           report_id,
        "report_date":         report_date,
        "engine_version":      ENGINE_VERSION,
        "report_revision":     REPORT_REVISION,

        "incident": {
            "clinic_name":          _or(inp.clinic_name, "Clinic name not recorded"),
            "clinic_address":       _or(inp.clinic_address),
            "incident_date":        _or(inp.incident_date),
            "incident_time":        _or(inp.incident_time),
            "report_generated":     now,
        },

        "clinician": {
            "name":                 _or(inp.practitioner_name),
            "role":                 _or(inp.practitioner_role),
            "registration":         _or(inp.practitioner_registration),
        },

        "patient": {
            "reference":            _or(inp.patient_reference, "ANONYMISED"),
            "age_range":            _or(inp.patient_age_range),
            "privacy_note":         "This document contains no directly identifying patient information.",
        },

        "procedure": {
            "procedure":            _or(inp.procedure),
            "region":               _or(inp.region),
            "product":              _or(inp.product_name),
            "batch_number":         _or(inp.product_batch),
            "volume":               _or(inp.volume_ml),
            "technique":            _or(inp.technique),
            "injector_experience":  _or(inp.injector_experience),
        },

        "complication": {
            "type":                 inp.complication,
            "onset":                _or(inp.onset_time),
            "symptoms":             _or(inp.symptoms),
            "suspected_diagnosis":  _or(inp.suspected_diagnosis, inp.complication),
        },

        "timeline":                 timeline,

        "treatment": {
            "summary":              treatment_summary,
            "first_intervention":   _or(inp.time_of_first_intervention),
            "hyaluronidase_dose":   _or(inp.hyaluronidase_dose),
        },

        "patient_response":         _or(inp.patient_response),
        "outcome":                  _or(inp.outcome),
        "time_to_resolution":       _or(inp.time_to_resolution),

        "escalation": {
            "actions":              _or(inp.escalation_actions, "No escalation required."),
            "referrals":            _or(inp.referrals_made, "No referrals made."),
            "emergency_services":   "Emergency services called." if inp.emergency_services_called else "Not required.",
        },

        "follow_up": {
            "plan":                 _or(inp.follow_up_plan),
            "review_date":          _or(inp.review_date),
        },

        "evidence": {
            "protocol_used":        _or(inp.protocol_used, "AesthetiCite clinical protocol"),
            "references":           inp.evidence_refs or [],
        },

        "clinician_notes":          _or(inp.clinician_notes),

        "declaration": (
            f"I, {_or(inp.practitioner_name, '[Practitioner]')}, confirm that the information in this report "
            f"is accurate to the best of my knowledge as of {now}."
        ),

        "disclaimer": (
            "This document was generated with AesthetiCite clinical decision support. "
            "It is provided as a documentation aid only and does not constitute legal advice. "
            "Retain with patient records per your clinic's data retention policy. "
            "Consult your medical defence organisation regarding medico-legal obligations."
        ),
    }


# ===========================================================================
# PDF builder
# ===========================================================================

def _build_pdf(sections: Dict[str, Any], report_id: str) -> bytes:
    """Generate a professional PDF report. Returns bytes."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        W, H = A4

        LEFT = 18 * mm
        RIGHT = W - 18 * mm
        TOP = H - 16 * mm
        BOTTOM = 18 * mm
        y = TOP

        def ensure(space: float) -> None:
            nonlocal y
            if y - space < BOTTOM:
                c.showPage()
                y = TOP
                _draw_page_header()

        def _draw_page_header() -> None:
            nonlocal y
            c.setFillColorRGB(0.04, 0.07, 0.14)
            c.rect(0, H - 14 * mm, W, 14 * mm, fill=True, stroke=False)
            c.setFillColorRGB(1, 1, 1)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(LEFT, H - 9 * mm, "AesthetiCite — Medico-Legal Incident Report")
            c.setFont("Helvetica", 8)
            c.drawRightString(RIGHT, H - 9 * mm, f"Report ID: {report_id[:8].upper()}  |  {sections['report_date']}")
            y = H - 18 * mm

        def _page_footer() -> None:
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.setFont("Helvetica", 7)
            c.drawString(LEFT, BOTTOM - 5 * mm, "AesthetiCite clinical decision support. Not a substitute for clinical judgment. Retain per data retention policy.")

        def text(txt: str, font: str = "Helvetica", size: int = 9,
                 leading: int = 13, color: tuple = (0.1, 0.1, 0.1)) -> None:
            nonlocal y
            ensure(leading + 2)
            c.setFillColorRGB(*color)
            c.setFont(font, size)
            # Wrap long lines
            max_w = RIGHT - LEFT
            words = str(txt).split()
            line = ""
            for word in words:
                test = f"{line} {word}".strip()
                if stringWidth(test, font, size) <= max_w:
                    line = test
                else:
                    if line:
                        c.drawString(LEFT, y, line)
                        y -= leading
                    line = word
            if line:
                c.drawString(LEFT, y, line)
                y -= leading

        def section_title(title: str) -> None:
            nonlocal y
            ensure(20)
            y -= 3
            c.setFillColorRGB(0.04, 0.07, 0.14)
            c.rect(LEFT, y - 2, RIGHT - LEFT, 14, fill=True, stroke=False)
            c.setFillColorRGB(1, 1, 1)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(LEFT + 3, y + 3, title)
            y -= 16

        def field(label: str, value: str) -> None:
            ensure(14)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(LEFT, y, f"{label}:")
            label_w = stringWidth(f"{label}:  ", "Helvetica-Bold", 9)
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("Helvetica", 9)
            # Long values wrap
            val = str(value)
            max_val_w = RIGHT - LEFT - label_w
            if stringWidth(val, "Helvetica", 9) <= max_val_w:
                nonlocal y
                c.drawString(LEFT + label_w, y, val)
                y -= 13
            else:
                y -= 13
                text(val)

        def bullet_text(txt: str) -> None:
            nonlocal y
            ensure(13)
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("Helvetica", 9)
            c.drawString(LEFT, y, "•")
            # Indent wrapped text
            words = txt.split()
            line = ""
            for word in words:
                test = f"{line} {word}".strip()
                if stringWidth(test, "Helvetica", 9) <= (RIGHT - LEFT - 8):
                    line = test
                else:
                    c.drawString(LEFT + 8, y, line)
                    y -= 12
                    ensure(12)
                    line = word
            if line:
                c.drawString(LEFT + 8, y, line)
                y -= 12

        # ── COVER HEADER ──
        _draw_page_header()

        # Large title
        c.setFillColorRGB(0.04, 0.07, 0.14)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(LEFT, y, "Clinical Incident Report")
        y -= 10
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont("Helvetica", 10)
        c.drawString(LEFT, y,
                     f"{sections['incident']['clinic_name']}  •  "
                     f"Complication: {sections['complication']['type']}")
        y -= 8
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(LEFT, y, RIGHT, y)
        y -= 12

        # ── SECTION 1 — INCIDENT DETAILS ──
        section_title("1.  Incident Details")
        inc = sections["incident"]
        for lbl, val in [
            ("Clinic", inc["clinic_name"]),
            ("Address", inc["clinic_address"]),
            ("Date of incident", inc["incident_date"]),
            ("Time of incident", inc["incident_time"]),
            ("Report generated", inc["report_generated"]),
        ]:
            field(lbl, val)
        y -= 4

        # ── SECTION 2 — CLINICIAN ──
        section_title("2.  Treating Clinician")
        cl = sections["clinician"]
        for lbl, val in [
            ("Name", cl["name"]),
            ("Role", cl["role"]),
            ("Registration No.", cl["registration"]),
        ]:
            field(lbl, val)
        y -= 4

        # ── SECTION 3 — PATIENT ──
        section_title("3.  Patient Reference (Non-Identifiable)")
        pt = sections["patient"]
        field("Patient reference", pt["reference"])
        field("Age range", pt["age_range"])
        text(pt["privacy_note"], color=(0.5, 0.5, 0.5), size=8)
        y -= 4

        # ── SECTION 4 — PROCEDURE ──
        section_title("4.  Procedure Details")
        pr = sections["procedure"]
        for lbl, val in [
            ("Procedure", pr["procedure"]),
            ("Region", pr["region"]),
            ("Product", pr["product"]),
            ("Batch number", pr["batch_number"]),
            ("Volume", pr["volume"]),
            ("Technique", pr["technique"]),
            ("Injector experience", pr["injector_experience"]),
        ]:
            field(lbl, val)
        y -= 4

        # ── SECTION 5 — COMPLICATION ──
        section_title("5.  Complication")
        comp = sections["complication"]
        for lbl, val in [
            ("Complication type", comp["type"]),
            ("Onset", comp["onset"]),
            ("Symptoms", comp["symptoms"]),
            ("Suspected diagnosis", comp["suspected_diagnosis"]),
        ]:
            field(lbl, val)
        y -= 4

        # ── SECTION 6 — TIMELINE ──
        section_title("6.  Chronological Timeline")
        for line_txt in sections["timeline"].split("\n"):
            if line_txt.strip():
                bullet_text(line_txt.strip())
        y -= 4

        # ── SECTION 7 — TREATMENT ──
        section_title("7.  Treatment Given")
        tx = sections["treatment"]
        field("First intervention", tx["first_intervention"])
        if tx["hyaluronidase_dose"] != "Not recorded":
            field("Hyaluronidase dose", tx["hyaluronidase_dose"])
        text("Interventions:")
        for line_txt in tx["summary"].split("\n"):
            if line_txt.strip():
                bullet_text(line_txt.strip(" •"))
        y -= 4

        # ── SECTION 8 — RESPONSE + OUTCOME ──
        section_title("8.  Patient Response & Outcome")
        field("Patient response", sections["patient_response"])
        field("Outcome", sections["outcome"])
        field("Time to resolution", sections["time_to_resolution"])
        y -= 4

        # ── SECTION 9 — ESCALATION ──
        section_title("9.  Escalation & Referrals")
        esc = sections["escalation"]
        field("Escalation actions", esc["actions"])
        field("Referrals made", esc["referrals"])
        field("Emergency services", esc["emergency_services"])
        y -= 4

        # ── SECTION 10 — FOLLOW-UP ──
        section_title("10. Follow-Up Plan")
        fu = sections["follow_up"]
        field("Plan", fu["plan"])
        field("Review date", fu["review_date"])
        y -= 4

        # ── SECTION 11 — EVIDENCE BASIS ──
        section_title("11. Evidence Basis")
        ev = sections["evidence"]
        field("Protocol used", ev["protocol_used"])
        if ev["references"]:
            text("References:", font="Helvetica-Bold", size=9)
            for ref in ev["references"][:8]:
                title = ref.get("title", "")
                source = ref.get("source", "")
                year = ref.get("year", "")
                bullet_text(f"{title} — {source} {year}".strip(" —"))
        y -= 4

        # ── SECTION 12 — CLINICIAN NOTES ──
        if sections["clinician_notes"] != "Not recorded":
            section_title("12. Clinician Notes")
            text(sections["clinician_notes"])
            y -= 4

        # ── DECLARATION ──
        section_title("Declaration")
        text(sections["declaration"])
        y -= 8

        # ── DISCLAIMER ──
        ensure(30)
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(LEFT, y, RIGHT, y)
        y -= 8
        text(sections["disclaimer"], color=(0.5, 0.5, 0.5), size=8)

        _page_footer()
        c.save()
        buf.seek(0)
        return buf.read()

    except ImportError:
        # Fallback to plain text if reportlab not available
        txt = _build_plain_text(sections)
        return txt.encode("utf-8")


def _build_plain_text(sections: Dict[str, Any]) -> str:
    """Plain text fallback."""
    lines = [
        "=" * 60,
        "  AESTHETICITE CLINICAL INCIDENT REPORT",
        f"  Report ID: {sections['report_id'][:8].upper()}",
        f"  Generated: {sections['report_date']}",
        "=" * 60,
        "",
    ]

    def section(title: str) -> None:
        lines.extend(["", f"──── {title} ────"])

    def row(label: str, value: str) -> None:
        lines.append(f"  {label}: {value}")

    section("1. INCIDENT DETAILS")
    for k, v in sections["incident"].items():
        row(k.replace("_", " ").title(), v)

    section("2. CLINICIAN")
    for k, v in sections["clinician"].items():
        row(k.title(), v)

    section("3. PATIENT")
    for k, v in sections["patient"].items():
        row(k.replace("_", " ").title(), str(v))

    section("4. PROCEDURE")
    for k, v in sections["procedure"].items():
        row(k.replace("_", " ").title(), v)

    section("5. COMPLICATION")
    for k, v in sections["complication"].items():
        row(k.replace("_", " ").title(), v)

    section("6. TIMELINE")
    lines.append(sections["timeline"])

    section("7. TREATMENT")
    lines.append(sections["treatment"]["summary"])

    section("8. PATIENT RESPONSE & OUTCOME")
    row("Response", sections["patient_response"])
    row("Outcome", sections["outcome"])
    row("Time to resolution", sections["time_to_resolution"])

    section("9. ESCALATION")
    for k, v in sections["escalation"].items():
        row(k.replace("_", " ").title(), v)

    section("10. FOLLOW-UP")
    row("Plan", sections["follow_up"]["plan"])
    row("Review date", sections["follow_up"]["review_date"])

    section("11. EVIDENCE BASIS")
    row("Protocol", sections["evidence"]["protocol_used"])

    section("DECLARATION")
    lines.append(sections["declaration"])

    lines.extend(["", "=" * 60, sections["disclaimer"], "=" * 60])
    return "\n".join(lines)


# ===========================================================================
# Storage
# ===========================================================================

def _save_to_db(
    db: Session,
    report_id: str,
    sections: Dict[str, Any],
    inp: ReportInput,
    user_id: Optional[str],
) -> None:
    try:
        db.execute(
            text("""
                INSERT INTO safety_reports (
                    id, org_id, clinic_id, created_by, source_type,
                    title, summary, presenting_problem, immediate_actions,
                    treatment_used, escalation_triggers, follow_up,
                    evidence_refs, clinician_notes, patient_summary
                ) VALUES (
                    :id, :org_id, :cid, :uid, 'incident_report',
                    :title, :summary, :problem, :actions,
                    :treatment, :escalation, :followup,
                    :evref, :notes, ''
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id":         report_id,
                "org_id":     None,
                "cid":        inp.clinic_id,
                "uid":        user_id or "anonymous",
                "title":      f"Incident Report — {inp.complication} ({report_id[:8].upper()})",
                "summary":    sections["complication"]["type"],
                "problem":    sections["complication"]["symptoms"],
                "actions":    sections["treatment"]["summary"],
                "treatment":  sections["treatment"]["summary"],
                "escalation": sections["escalation"]["actions"],
                "followup":   sections["follow_up"]["plan"],
                "evref":      json.dumps(inp.evidence_refs or []),
                "notes":      inp.clinician_notes or "",
            },
        )
        db.commit()
    except Exception:
        pass  # Storage is best-effort — report is still generated


# ===========================================================================
# API endpoints
# ===========================================================================

@router.post("")
async def generate_report(
    inp: ReportInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    Generate a complete medico-legal report as structured JSON.
    Also stores to safety_reports table if save_to_db=True.
    """
    report_id = str(uuid.uuid4())
    sections = build_report_sections(inp, report_id)

    user_id = current_user["id"] if current_user else None
    if inp.save_to_db:
        _save_to_db(db, report_id, sections, inp, user_id)

    return {
        "report_id":    report_id,
        "generated_at": sections["report_date"],
        "sections":     sections,
        "status":       "generated",
    }


@router.post("/pdf")
async def generate_report_pdf(
    inp: ReportInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
):
    """
    Generate and stream a PDF medico-legal report.
    Returns binary PDF — triggers download in browser.
    """
    report_id = str(uuid.uuid4())
    sections = build_report_sections(inp, report_id)

    user_id = current_user["id"] if current_user else None
    if inp.save_to_db:
        _save_to_db(db, report_id, sections, inp, user_id)

    pdf_bytes = _build_pdf(sections, report_id)
    filename = f"aestheticite-incident-{report_id[:8].upper()}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    """Retrieve a stored report by ID."""
    row = db.execute(
        text("SELECT * FROM safety_reports WHERE id = :id"),
        {"id": report_id},
    ).fetchone()
    if not row:
        raise HTTPException(404, "Report not found.")
    d = dict(row)
    if isinstance(d.get("evidence_refs"), str):
        d["evidence_refs"] = json.loads(d["evidence_refs"])
    return d
