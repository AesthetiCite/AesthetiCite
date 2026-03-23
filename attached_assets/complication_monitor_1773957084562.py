"""
AesthetiCite — Complication Monitor  (DentalMonitoring-inspired)
================================================================
Async post-procedure monitoring:
  - Clinician creates a monitor case for a patient
  - Patient / nurse submits photo + notes at 24h, 48h, 1 week
  - AI assesses each submission for complication signs
  - If red flags detected → alert auto-generated

Endpoints:
  POST /api/monitor/cases              — create monitor
  GET  /api/monitor/cases              — list for clinic
  GET  /api/monitor/cases/{id}         — case detail + submissions
  POST /api/monitor/cases/{id}/submit  — add photo submission (AI screens it)
  PATCH /api/monitor/cases/{id}/status — update status
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/monitor", tags=["Complication Monitor"])

# ---------------------------------------------------------------------------
# LLM screening prompt
# ---------------------------------------------------------------------------

SCREENING_SYSTEM = """You are AesthetiCite, a clinical safety AI for aesthetic medicine.
You will be shown a post-procedure photo and clinical notes. Assess the image for signs of:
- Vascular occlusion (blanching, livedo reticularis, skin discolouration)
- Skin necrosis (dark discolouration, eschar, breakdown)
- Infection or biofilm (erythema, warmth, purulent discharge, swelling beyond expected)
- Severe oedema or haematoma (disproportionate swelling)
- Tyndall effect (bluish tint, surface irregularity)
- Normal post-procedure healing

Return ONLY valid JSON in this exact structure, no markdown, no preamble:
{
  "risk_level": "normal|low|moderate|high|critical",
  "findings": ["finding 1", "finding 2"],
  "red_flags": ["red flag 1"],
  "recommended_action": "Brief clinical action recommended",
  "requires_alert": true|false,
  "confidence": 0.0-1.0,
  "disclaimer": "This is AI decision support only. Clinical judgment takes precedence."
}"""


async def _ai_screen_image(
    image_b64: str, notes: str, procedure: Optional[str], region: Optional[str]
) -> Dict[str, Any]:
    """Call OpenAI vision model to screen the image for complication signs."""
    try:
        import openai as _openai
        client = _openai.AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL") or None,
        )

        user_content: List[Any] = [
            {
                "type": "text",
                "text": (
                    f"Post-procedure photo for: {procedure or 'aesthetic procedure'}, "
                    f"region: {region or 'unspecified'}.\n"
                    f"Clinical notes from submitter: {notes or 'None provided.'}\n\n"
                    "Assess for any post-procedure complications. Respond ONLY with JSON."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"},
            },
        ]

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SCREENING_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=600,
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "risk_level": "unknown",
            "findings": [],
            "red_flags": [],
            "recommended_action": "Manual review required — AI parse error.",
            "requires_alert": False,
            "confidence": 0.0,
            "disclaimer": "AI assessment failed. Clinician review required.",
        }
    except Exception as e:
        return {
            "risk_level": "unknown",
            "findings": [],
            "red_flags": [],
            "recommended_action": f"AI unavailable: {str(e)[:100]}. Manual review required.",
            "requires_alert": False,
            "confidence": 0.0,
            "disclaimer": "AI assessment failed. Clinician review required.",
        }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _require_member(db: Session, user_id: str, clinic_id: str) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT m.role, m.org_id FROM memberships m
            WHERE m.user_id = :uid AND m.clinic_id = :cid AND m.is_active = TRUE
        """),
        {"uid": user_id, "cid": clinic_id},
    ).fetchone()
    if not row:
        raise HTTPException(403, "Not a member of this clinic.")
    return dict(row)


def _create_alert(db: Session, org_id: str, clinic_id: str, monitor_id: str, assessment: Dict) -> None:
    db.execute(
        text("""
            INSERT INTO complication_alerts
                (id, org_id, clinic_id, alert_type, severity, title, body, evidence_json)
            VALUES (:id, :org_id, :cid, 'photo_monitor', :sev, :title, :body, :ev)
        """),
        {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "cid": clinic_id,
            "sev": "critical" if assessment.get("risk_level") == "critical" else "warning",
            "title": f"Monitor Alert — {assessment.get('risk_level', 'unknown').upper()} risk detected",
            "body": (
                f"AI screening detected {assessment.get('risk_level')} risk signs on photo submission. "
                f"Findings: {', '.join(assessment.get('findings', [])[:3])}. "
                f"Action: {assessment.get('recommended_action', 'Review immediately.')} "
                f"Monitor case: {monitor_id}"
            ),
            "ev": json.dumps(assessment),
        },
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MonitorCreate(BaseModel):
    clinic_id: str
    patient_reference: str
    procedure: Optional[str] = None
    region: Optional[str] = None
    case_log_id: Optional[str] = None


class MonitorStatusPatch(BaseModel):
    clinic_id: str
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/cases")
async def create_monitor(
    payload: MonitorCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    mem = _require_member(db, current_user["id"], payload.clinic_id)
    mid = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO complication_monitors
                (id, org_id, clinic_id, case_log_id, created_by,
                 patient_reference, procedure, region)
            VALUES (:id, :org_id, :cid, :case_log_id, :created_by,
                    :patient_ref, :proc, :region)
        """),
        {
            "id": mid,
            "org_id": str(mem["org_id"]),
            "cid": payload.clinic_id,
            "case_log_id": payload.case_log_id,
            "created_by": current_user["id"],
            "patient_ref": payload.patient_reference,
            "proc": payload.procedure,
            "region": payload.region,
        },
    )
    db.commit()
    return {"id": mid, "status": "active", "patient_reference": payload.patient_reference}


@router.get("/cases")
def list_monitors(
    clinic_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    _require_member(db, current_user["id"], clinic_id)
    filters = "clinic_id = :cid"
    params: Dict[str, Any] = {"cid": clinic_id}
    if status:
        filters += " AND monitor_status = :status"
        params["status"] = status

    rows = db.execute(
        text(f"""
            SELECT m.*,
                   COUNT(s.id) as submission_count,
                   MAX(s.submitted_at) as last_submission
            FROM complication_monitors m
            LEFT JOIN monitor_submissions s ON s.monitor_id = m.id
            WHERE {filters}
            GROUP BY m.id
            ORDER BY m.created_at DESC
        """),
        params,
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/cases/{monitor_id}")
def get_monitor(
    monitor_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    monitor = db.execute(
        text("SELECT * FROM complication_monitors WHERE id = :id"), {"id": monitor_id}
    ).fetchone()
    if not monitor:
        raise HTTPException(404, "Monitor not found.")
    _require_member(db, current_user["id"], str(monitor["clinic_id"]))

    submissions = db.execute(
        text("""
            SELECT id, notes, ai_assessment, alert_triggered, submitted_at
            FROM monitor_submissions
            WHERE monitor_id = :mid
            ORDER BY submitted_at ASC
        """),
        {"mid": monitor_id},
    ).fetchall()

    result = dict(monitor)
    result["submissions"] = []
    for s in submissions:
        sub = dict(s)
        if isinstance(sub.get("ai_assessment"), str):
            sub["ai_assessment"] = json.loads(sub["ai_assessment"])
        result["submissions"].append(sub)
    return result


@router.post("/cases/{monitor_id}/submit")
async def submit_photo(
    monitor_id: str,
    clinic_id: str = Form(...),
    notes: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    monitor = db.execute(
        text("SELECT * FROM complication_monitors WHERE id = :id"), {"id": monitor_id}
    ).fetchone()
    if not monitor:
        raise HTTPException(404, "Monitor not found.")

    mem = _require_member(db, current_user["id"], clinic_id)

    # Read and encode image
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large. Max 10MB.")

    image_b64 = base64.b64encode(image_bytes).decode()

    # AI screening
    assessment = await _ai_screen_image(
        image_b64,
        notes,
        monitor["procedure"],
        monitor["region"],
    )

    requires_alert = assessment.get("requires_alert", False) or assessment.get("risk_level") in ("high", "critical")
    sub_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO monitor_submissions
                (id, monitor_id, submitted_by, image_b64, notes, ai_assessment, alert_triggered)
            VALUES (:id, :mid, :uid, :img, :notes, :assess, :alert)
        """),
        {
            "id": sub_id,
            "mid": monitor_id,
            "uid": current_user["id"],
            "img": image_b64[:500] + "…[truncated]",  # store ref, not full b64
            "notes": notes,
            "assess": json.dumps(assessment),
            "alert": requires_alert,
        },
    )

    # Auto-generate alert if needed
    if requires_alert:
        _create_alert(db, str(mem["org_id"]), clinic_id, monitor_id, assessment)

        # Escalate monitor status
        if assessment.get("risk_level") in ("critical",):
            db.execute(
                text("UPDATE complication_monitors SET monitor_status = 'escalated', updated_at = now() WHERE id = :id"),
                {"id": monitor_id},
            )

    db.commit()

    return {
        "submission_id": sub_id,
        "assessment": assessment,
        "alert_triggered": requires_alert,
        "message": (
            "⚠️ Alert generated — review required immediately."
            if requires_alert
            else "Submission recorded. No immediate red flags detected."
        ),
    }


@router.patch("/cases/{monitor_id}/status")
def update_monitor_status(
    monitor_id: str,
    payload: MonitorStatusPatch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    valid = ("active", "resolved", "escalated", "closed")
    if payload.status not in valid:
        raise HTTPException(400, f"Status must be one of: {valid}")
    _require_member(db, current_user["id"], payload.clinic_id)
    db.execute(
        text("UPDATE complication_monitors SET monitor_status = :s, updated_at = now() WHERE id = :id"),
        {"s": payload.status, "id": monitor_id},
    )
    db.commit()
    return {"status": payload.status, "id": monitor_id}
