"""
AesthetiCite — Medico-Legal Report Generator
=============================================
POST /api/generate-report        → JSON report + store
POST /api/generate-report/pdf    → Binary PDF download (reportlab)
GET  /api/generate-report/{id}   → Retrieve stored report

12 MDO-standard sections. All fields optional except complication.
Storage best-effort — report generated even if DB write fails.
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/api/generate-report", tags=["Medico-Legal Report"])

ENGINE_VERSION = "1.0"
REPORT_REVISION = "2026-03"


# ── Auth helper (mirrors cases.py pattern) ────────────────────────────────────

try:
    from app.core.auth import bearer, decode_token

    async def get_optional_user(token: str = Depends(bearer)) -> Optional[dict]:
        try:
            return decode_token(token)
        except Exception:
            return None
except Exception:
    async def get_optional_user() -> Optional[dict]:
        return None


# ── Input model ───────────────────────────────────────────────────────────────

class ReportInput(BaseModel):
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    report_date: Optional[str] = None
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None

    practitioner_name: Optional[str] = None
    practitioner_role: Optional[str] = None
    practitioner_registration: Optional[str] = None

    patient_reference: Optional[str] = Field(None, description="Non-identifiable reference only")
    patient_age_range: Optional[str] = None

    procedure: Optional[str] = None
    region: Optional[str] = None
    product_name: Optional[str] = None
    product_batch: Optional[str] = None
    volume_ml: Optional[str] = None
    technique: Optional[str] = None
    injector_experience: Optional[str] = None

    complication: str = Field(..., min_length=2)
    onset_time: Optional[str] = None
    symptoms: Optional[str] = None
    suspected_diagnosis: Optional[str] = None

    timeline: Optional[str] = None

    treatment_given: Optional[str] = None
    hyaluronidase_dose: Optional[str] = None
    medications_given: Optional[List[str]] = None
    time_of_first_intervention: Optional[str] = None

    patient_response: Optional[str] = None
    outcome: Optional[str] = None
    time_to_resolution: Optional[str] = None

    escalation_actions: Optional[str] = None
    referrals_made: Optional[str] = None
    emergency_services_called: bool = False

    follow_up_plan: Optional[str] = None
    review_date: Optional[str] = None

    evidence_refs: Optional[List[Dict[str, Any]]] = None
    protocol_used: Optional[str] = None

    clinician_notes: Optional[str] = None

    clinic_id: Optional[str] = None
    save_to_db: bool = True


# ── Report builder ────────────────────────────────────────────────────────────

def _now_display() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")


def _or(value: Optional[str], fallback: str = "Not recorded") -> str:
    return value.strip() if value and value.strip() else fallback


def build_report_sections(inp: ReportInput, report_id: str) -> Dict[str, Any]:
    now = _now_display()
    report_date = inp.report_date or now

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

    tx_parts = []
    if inp.treatment_given:
        tx_parts.append(inp.treatment_given)
    if inp.hyaluronidase_dose:
        tx_parts.append(f"Hyaluronidase: {inp.hyaluronidase_dose}")
    if inp.medications_given:
        tx_parts.extend(inp.medications_given)
    treatment_summary = "\n".join(f"• {t}" for t in tx_parts) if tx_parts else "Not recorded."

    return {
        "report_id":       report_id,
        "report_date":     report_date,
        "engine_version":  ENGINE_VERSION,
        "report_revision": REPORT_REVISION,

        "incident": {
            "clinic_name":      _or(inp.clinic_name, "Clinic name not recorded"),
            "clinic_address":   _or(inp.clinic_address),
            "incident_date":    _or(inp.incident_date),
            "incident_time":    _or(inp.incident_time),
            "report_generated": now,
        },

        "clinician": {
            "name":         _or(inp.practitioner_name),
            "role":         _or(inp.practitioner_role),
            "registration": _or(inp.practitioner_registration),
        },

        "patient": {
            "reference":    _or(inp.patient_reference, "ANONYMISED"),
            "age_range":    _or(inp.patient_age_range),
            "privacy_note": "This document contains no directly identifying patient information.",
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

        "timeline": timeline,

        "treatment": {
            "summary":              treatment_summary,
            "first_intervention":   _or(inp.time_of_first_intervention),
            "hyaluronidase_dose":   _or(inp.hyaluronidase_dose),
        },

        "patient_response":     _or(inp.patient_response),
        "outcome":              _or(inp.outcome),
        "time_to_resolution":   _or(inp.time_to_resolution),

        "escalation": {
            "actions":             _or(inp.escalation_actions, "No escalation required."),
            "referrals":           _or(inp.referrals_made, "No referrals made."),
            "emergency_services":  "Emergency services called." if inp.emergency_services_called else "Not required.",
        },

        "follow_up": {
            "plan":        _or(inp.follow_up_plan),
            "review_date": _or(inp.review_date),
        },

        "evidence": {
            "protocol_used": _or(inp.protocol_used, "AesthetiCite clinical protocol"),
            "references":    inp.evidence_refs or [],
        },

        "clinician_notes": _or(inp.clinician_notes),

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


# ── PDF builder ───────────────────────────────────────────────────────────────

def _build_pdf(sections: Dict[str, Any], report_id: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        W, H = A4

        LEFT   = 18 * mm
        RIGHT  = W - 18 * mm
        TOP    = H - 16 * mm
        BOTTOM = 18 * mm
        y = TOP

        def ensure(space: float) -> None:
            nonlocal y
            if y - space < BOTTOM:
                _page_footer()
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
            c.drawRightString(RIGHT, H - 9 * mm,
                              f"Report ID: {report_id[:8].upper()}  |  {sections['report_date']}")
            y = H - 18 * mm

        def _page_footer() -> None:
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.setFont("Helvetica", 7)
            c.drawString(LEFT, BOTTOM - 5 * mm,
                         "AesthetiCite clinical decision support. Not a substitute for clinical judgment. "
                         "Retain per data retention policy.")

        def text_line(txt: str, font: str = "Helvetica", size: int = 9,
                      leading: int = 13, color: tuple = (0.1, 0.1, 0.1)) -> None:
            nonlocal y
            ensure(leading + 2)
            c.setFillColorRGB(*color)
            c.setFont(font, size)
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
                        ensure(leading + 2)
                    line = word
            if line:
                c.drawString(LEFT, y, line)
                y -= leading

        def section_title(title: str) -> None:
            nonlocal y
            ensure(22)
            y -= 4
            c.setFillColorRGB(0.04, 0.07, 0.14)
            c.rect(LEFT, y - 2, RIGHT - LEFT, 14, fill=True, stroke=False)
            c.setFillColorRGB(1, 1, 1)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(LEFT + 3, y + 3, title)
            y -= 16

        def field(label: str, value: str) -> None:
            nonlocal y
            ensure(14)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(LEFT, y, f"{label}:")
            label_w = stringWidth(f"{label}:  ", "Helvetica-Bold", 9)
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("Helvetica", 9)
            val = str(value)
            max_val_w = RIGHT - LEFT - label_w
            if stringWidth(val, "Helvetica", 9) <= max_val_w:
                c.drawString(LEFT + label_w, y, val)
                y -= 13
            else:
                y -= 13
                text_line(val)

        def bullet(txt: str) -> None:
            nonlocal y
            ensure(13)
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("Helvetica", 9)
            c.drawString(LEFT, y, "•")
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

        # Cover header
        _draw_page_header()
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
        y -= 14

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

        section_title("2.  Treating Clinician")
        cl = sections["clinician"]
        for lbl, val in [("Name", cl["name"]), ("Role", cl["role"]), ("Registration No.", cl["registration"])]:
            field(lbl, val)
        y -= 4

        section_title("3.  Patient Reference (Non-Identifiable)")
        pt = sections["patient"]
        field("Patient reference", pt["reference"])
        field("Age range", pt["age_range"])
        text_line(pt["privacy_note"], color=(0.5, 0.5, 0.5), size=8)
        y -= 4

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

        section_title("6.  Chronological Timeline")
        for line_txt in sections["timeline"].split("\n"):
            if line_txt.strip():
                bullet(line_txt.strip())
        y -= 4

        section_title("7.  Treatment Given")
        tx = sections["treatment"]
        field("First intervention", tx["first_intervention"])
        if tx["hyaluronidase_dose"] != "Not recorded":
            field("Hyaluronidase dose", tx["hyaluronidase_dose"])
        text_line("Interventions:")
        for line_txt in tx["summary"].split("\n"):
            if line_txt.strip():
                bullet(line_txt.strip(" •"))
        y -= 4

        section_title("8.  Patient Response & Outcome")
        field("Patient response", sections["patient_response"])
        field("Outcome", sections["outcome"])
        field("Time to resolution", sections["time_to_resolution"])
        y -= 4

        section_title("9.  Escalation & Referrals")
        esc = sections["escalation"]
        field("Escalation actions", esc["actions"])
        field("Referrals made", esc["referrals"])
        field("Emergency services", esc["emergency_services"])
        y -= 4

        section_title("10. Follow-Up Plan")
        fu = sections["follow_up"]
        field("Plan", fu["plan"])
        field("Review date", fu["review_date"])
        y -= 4

        section_title("11. Evidence Basis")
        ev = sections["evidence"]
        field("Protocol used", ev["protocol_used"])
        if ev["references"]:
            text_line("References:", font="Helvetica-Bold", size=9)
            for ref in ev["references"][:8]:
                title = ref.get("title", "")
                source = ref.get("source", "")
                year = ref.get("year", "")
                bullet(f"{title} — {source} {year}".strip(" —"))
        y -= 4

        if sections["clinician_notes"] != "Not recorded":
            section_title("12. Clinician Notes")
            text_line(sections["clinician_notes"])
            y -= 4

        section_title("Declaration")
        text_line(sections["declaration"])
        y -= 8

        ensure(30)
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(LEFT, y, RIGHT, y)
        y -= 8
        text_line(sections["disclaimer"], color=(0.5, 0.5, 0.5), size=8)

        _page_footer()
        c.save()
        buf.seek(0)
        return buf.read()

    except ImportError:
        return _build_plain_text(sections).encode("utf-8")


def _build_plain_text(sections: Dict[str, Any]) -> str:
    lines = [
        "=" * 60,
        "  AESTHETICITE CLINICAL INCIDENT REPORT",
        f"  Report ID: {sections['report_id'][:8].upper()}",
        f"  Generated: {sections['report_date']}",
        "=" * 60,
        "",
    ]

    def sec(title: str) -> None:
        lines.extend(["", f"──── {title} ────"])

    def row(label: str, value: str) -> None:
        lines.append(f"  {label}: {value}")

    sec("1. INCIDENT DETAILS")
    for k, v in sections["incident"].items():
        row(k.replace("_", " ").title(), v)
    sec("2. CLINICIAN")
    for k, v in sections["clinician"].items():
        row(k.title(), v)
    sec("3. PATIENT")
    for k, v in sections["patient"].items():
        row(k.replace("_", " ").title(), str(v))
    sec("4. PROCEDURE")
    for k, v in sections["procedure"].items():
        row(k.replace("_", " ").title(), v)
    sec("5. COMPLICATION")
    for k, v in sections["complication"].items():
        row(k.replace("_", " ").title(), v)
    sec("6. TIMELINE")
    lines.append(sections["timeline"])
    sec("7. TREATMENT")
    lines.append(sections["treatment"]["summary"])
    sec("8. PATIENT RESPONSE & OUTCOME")
    row("Response", sections["patient_response"])
    row("Outcome", sections["outcome"])
    row("Time to resolution", sections["time_to_resolution"])
    sec("9. ESCALATION")
    for k, v in sections["escalation"].items():
        row(k.replace("_", " ").title(), v)
    sec("10. FOLLOW-UP")
    row("Plan", sections["follow_up"]["plan"])
    row("Review date", sections["follow_up"]["review_date"])
    sec("11. EVIDENCE BASIS")
    row("Protocol", sections["evidence"]["protocol_used"])
    sec("DECLARATION")
    lines.append(sections["declaration"])
    lines.extend(["", "=" * 60, sections["disclaimer"], "=" * 60])
    return "\n".join(lines)


# ── Storage ───────────────────────────────────────────────────────────────────

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
        pass  # Storage is best-effort


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("")
async def generate_report(
    inp: ReportInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
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
    try:
        uuid.UUID(report_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid report ID format.")
    try:
        row = db.execute(
            text("SELECT * FROM safety_reports WHERE id = :id"),
            {"id": report_id},
        ).fetchone()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format.")
    if not row:
        raise HTTPException(404, "Report not found.")
    d = dict(row)
    if isinstance(d.get("evidence_refs"), str):
        d["evidence_refs"] = json.loads(d["evidence_refs"])
    return d
