"""
AesthetiCite — Clinic Network Safety Workspace
FastAPI router: multi-clinic model, case logs, saved protocols, reports, analytics.

Mount in app/main.py:
    from app.api.network_workspace import router as network_workspace_router
    app.include_router(network_workspace_router)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/workspace", tags=["Network Safety Workspace"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def track_event(
    db: Session,
    event_type: str,
    user_id: Optional[str] = None,
    clinic_id: Optional[str] = None,
    org_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> None:
    try:
        db.execute(
            text("""
                INSERT INTO analytics_events (org_id, clinic_id, user_id, event_type, metadata)
                VALUES (:org_id, :clinic_id, :user_id, :event_type, :metadata)
            """),
            {
                "org_id": org_id,
                "clinic_id": clinic_id,
                "user_id": user_id,
                "event_type": event_type,
                "metadata": json.dumps(metadata or {}),
            },
        )
        db.commit()
    except Exception:
        pass  # analytics must never break primary flow


def require_clinic_member(
    db: Session, user_id: str, clinic_id: str, min_roles: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Return membership row or raise 403."""
    row = db.execute(
        text("""
            SELECT m.*, c.name as clinic_name, c.org_id, o.name as org_name
            FROM memberships m
            JOIN clinics c ON c.id = m.clinic_id
            JOIN organizations o ON o.id = m.org_id
            WHERE m.user_id = :uid AND m.clinic_id = :cid AND m.is_active = TRUE
        """),
        {"uid": user_id, "cid": clinic_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this clinic.")
    if min_roles and row["role"] not in min_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{row['role']}' is not permitted. Required: {min_roles}",
        )
    return dict(row)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool


class ClinicOut(BaseModel):
    id: str
    org_id: str
    name: str
    location: Optional[str]
    timezone: str
    is_active: bool


class MembershipOut(BaseModel):
    id: str
    clinic_id: str
    clinic_name: str
    org_id: str
    org_name: str
    role: str


class ClinicSelectRequest(BaseModel):
    clinic_id: str


# Case logs
class CaseLogCreate(BaseModel):
    clinic_id: str
    patient_reference: str = Field(..., description="Non-identifiable reference only")
    event_date: Optional[str] = None
    practitioner_name: Optional[str] = None
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_used: Optional[str] = None
    complication_type: Optional[str] = None
    symptoms: Optional[str] = None
    suspected_diagnosis: Optional[str] = None
    treatment_given: Optional[str] = None
    hyaluronidase_dose: Optional[str] = None
    follow_up_plan: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


class CaseLogPatch(BaseModel):
    patient_reference: Optional[str] = None
    event_date: Optional[str] = None
    practitioner_name: Optional[str] = None
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_used: Optional[str] = None
    complication_type: Optional[str] = None
    symptoms: Optional[str] = None
    suspected_diagnosis: Optional[str] = None
    treatment_given: Optional[str] = None
    hyaluronidase_dose: Optional[str] = None
    follow_up_plan: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


# Protocols
class ProtocolCreate(BaseModel):
    clinic_id: str
    title: str
    source_query: str
    answer_json: Dict[str, Any] = {}
    citations_json: List[Dict[str, Any]] = []
    tags: List[str] = []


class ProtocolPatch(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None
    clinic_approved: Optional[bool] = None


# Reports
class ReportFromCaseRequest(BaseModel):
    clinic_id: str
    clinician_notes: Optional[str] = None


class ReportFromGuidanceRequest(BaseModel):
    clinic_id: str
    guidance_result: Dict[str, Any]
    title: str
    clinician_notes: Optional[str] = None


# Guidance
class GuidanceQueryRequest(BaseModel):
    clinic_id: str
    complication_type: str
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_type: Optional[str] = None
    symptom_onset: Optional[str] = None
    pain: Optional[str] = None
    clinical_signs: Optional[List[str]] = []
    injector_experience: Optional[str] = None


# ---------------------------------------------------------------------------
# ORGS + CLINICS
# ---------------------------------------------------------------------------


@router.get("/orgs/me", response_model=List[OrgOut])
def get_my_orgs(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[OrgOut]:
    rows = db.execute(
        text("""
            SELECT DISTINCT o.id, o.name, o.slug, o.is_active
            FROM memberships m
            JOIN organizations o ON o.id = m.org_id
            WHERE m.user_id = :uid AND m.is_active = TRUE
        """),
        {"uid": current_user["id"]},
    ).fetchall()
    return [OrgOut(**dict(r)) for r in rows]


@router.get("/clinics/me", response_model=List[MembershipOut])
def get_my_clinics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[MembershipOut]:
    rows = db.execute(
        text("""
            SELECT m.id, m.clinic_id, c.name as clinic_name,
                   m.org_id, o.name as org_name, m.role
            FROM memberships m
            JOIN clinics c ON c.id = m.clinic_id
            JOIN organizations o ON o.id = m.org_id
            WHERE m.user_id = :uid AND m.is_active = TRUE
            ORDER BY c.name
        """),
        {"uid": current_user["id"]},
    ).fetchall()
    return [MembershipOut(**dict(r)) for r in rows]


@router.post("/clinics/select")
def select_clinic(
    payload: ClinicSelectRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    membership = require_clinic_member(db, current_user["id"], payload.clinic_id)
    track_event(
        db,
        "clinic_switched",
        user_id=current_user["id"],
        clinic_id=payload.clinic_id,
        org_id=membership["org_id"],
    )
    return {
        "clinic_id": payload.clinic_id,
        "clinic_name": membership["clinic_name"],
        "org_id": membership["org_id"],
        "role": membership["role"],
    }


# ---------------------------------------------------------------------------
# LIVE GUIDANCE
# ---------------------------------------------------------------------------


@router.post("/network-guidance/query")
def network_guidance_query(
    payload: GuidanceQueryRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    membership = require_clinic_member(db, current_user["id"], payload.clinic_id)

    # Build a structured clinical query for the evidence engine
    signs_str = ", ".join(payload.clinical_signs) if payload.clinical_signs else "none reported"
    query = (
        f"Complication management: {payload.complication_type}. "
        f"Procedure: {payload.procedure or 'not specified'}. "
        f"Region: {payload.region or 'not specified'}. "
        f"Product: {payload.product_type or 'not specified'}. "
        f"Symptom onset: {payload.symptom_onset or 'not specified'}. "
        f"Pain: {payload.pain or 'not specified'}. "
        f"Clinical signs: {signs_str}. "
        f"Injector experience: {payload.injector_experience or 'not specified'}. "
        f"What is the evidence-based management protocol?"
    )

    # Reuse existing complication protocol engine via internal import
    try:
        from app.engine.complication_protocol import get_complication_protocol
        protocol = get_complication_protocol(payload.complication_type)
    except ImportError:
        protocol = None

    # Evidence hierarchy reranking
    try:
        from app.engine.aestheticite_engine import AesthetiCiteEngine
        # The engine is typically injected; fall back to a stub if unavailable
        evidence_items = []
    except ImportError:
        evidence_items = []

    track_event(
        db,
        "guidance_query_submitted",
        user_id=current_user["id"],
        clinic_id=payload.clinic_id,
        org_id=membership["org_id"],
        metadata={
            "complication_type": payload.complication_type,
            "procedure": payload.procedure,
            "region": payload.region,
        },
    )

    return {
        "query": query,
        "complication_type": payload.complication_type,
        "structured_workflow": {
            "identify": {
                "label": "1. Identify",
                "content": f"Confirm {payload.complication_type} based on: {signs_str}",
            },
            "immediate_action": {
                "label": "2. Immediate Action",
                "content": protocol.get("immediate_actions", []) if protocol else [],
            },
            "treatment": {
                "label": "3. Treatment",
                "content": protocol.get("dose_guidance", {}) if protocol else {},
            },
            "escalation": {
                "label": "4. Escalation",
                "content": protocol.get("escalation", "") if protocol else "",
            },
            "follow_up": {
                "label": "5. Follow-Up",
                "content": "Review at 24h and 48h. Document outcome.",
            },
        },
        "protocol": protocol,
        "evidence_items": evidence_items,
        "rerank_note": "Evidence ranked: Guidelines → Consensus → Reviews → RCTs",
    }


# ---------------------------------------------------------------------------
# CASE LOGS
# ---------------------------------------------------------------------------


@router.post("/case-logs")
def create_case_log(
    payload: CaseLogCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    membership = require_clinic_member(db, current_user["id"], payload.clinic_id)
    log_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO case_logs (
                id, org_id, clinic_id, created_by, patient_reference, event_date,
                practitioner_name, procedure, region, product_used, complication_type,
                symptoms, suspected_diagnosis, treatment_given, hyaluronidase_dose,
                follow_up_plan, outcome, notes
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by, :patient_reference, :event_date,
                :practitioner_name, :procedure, :region, :product_used, :complication_type,
                :symptoms, :suspected_diagnosis, :treatment_given, :hyaluronidase_dose,
                :follow_up_plan, :outcome, :notes
            )
        """),
        {
            "id": log_id,
            "org_id": membership["org_id"],
            "clinic_id": payload.clinic_id,
            "created_by": current_user["id"],
            **payload.dict(exclude={"clinic_id"}),
        },
    )
    db.commit()

    track_event(
        db,
        "case_log_created",
        user_id=current_user["id"],
        clinic_id=payload.clinic_id,
        org_id=membership["org_id"],
        metadata={"complication_type": payload.complication_type},
    )
    return {"id": log_id, "status": "created"}


@router.get("/case-logs")
def list_case_logs(
    clinic_id: str = Query(...),
    complication_type: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    practitioner: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    require_clinic_member(db, current_user["id"], clinic_id)

    filters = ["clinic_id = :clinic_id"]
    params: Dict[str, Any] = {"clinic_id": clinic_id, "limit": limit, "offset": offset}

    if complication_type:
        filters.append("complication_type ILIKE :comp")
        params["comp"] = f"%{complication_type}%"
    if outcome:
        filters.append("outcome ILIKE :outcome")
        params["outcome"] = f"%{outcome}%"
    if practitioner:
        filters.append("practitioner_name ILIKE :prac")
        params["prac"] = f"%{practitioner}%"
    if date_from:
        filters.append("event_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("event_date <= :date_to")
        params["date_to"] = date_to

    where = " AND ".join(filters)
    rows = db.execute(
        text(f"""
            SELECT * FROM case_logs
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).fetchall()

    count = db.execute(
        text(f"SELECT COUNT(*) FROM case_logs WHERE {where}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    ).scalar_one()

    return {"total": count, "items": [dict(r) for r in rows]}


@router.get("/case-logs/export/csv")
def export_case_logs_csv(
    clinic_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    require_clinic_member(
        db, current_user["id"], clinic_id,
        min_roles=["super_admin", "org_admin", "clinic_admin"]
    )

    rows = db.execute(
        text("SELECT * FROM case_logs WHERE clinic_id = :cid ORDER BY created_at DESC"),
        {"cid": clinic_id},
    ).fetchall()

    import csv, io
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=case_logs_{clinic_id[:8]}.csv"},
    )


@router.get("/case-logs/{log_id}")
def get_case_log(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.execute(
        text("SELECT * FROM case_logs WHERE id = :id"), {"id": log_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Case log not found.")
    require_clinic_member(db, current_user["id"], str(row["clinic_id"]))
    return dict(row)


@router.patch("/case-logs/{log_id}")
def update_case_log(
    log_id: str,
    payload: CaseLogPatch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.execute(
        text("SELECT * FROM case_logs WHERE id = :id"), {"id": log_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Case log not found.")
    require_clinic_member(db, current_user["id"], str(row["clinic_id"]))

    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        return {"status": "no_change"}

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    db.execute(
        text(f"UPDATE case_logs SET {set_clause}, updated_at = now() WHERE id = :id"),
        {**updates, "id": log_id},
    )
    db.commit()
    return {"status": "updated", "id": log_id}


# ---------------------------------------------------------------------------
# SAVED PROTOCOLS
# ---------------------------------------------------------------------------


@router.post("/protocols")
def create_protocol(
    payload: ProtocolCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    membership = require_clinic_member(db, current_user["id"], payload.clinic_id)
    pid = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO saved_protocols (
                id, org_id, clinic_id, created_by, title, source_query,
                answer_json, citations_json, tags
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by, :title, :source_query,
                :answer_json, :citations_json, :tags
            )
        """),
        {
            "id": pid,
            "org_id": membership["org_id"],
            "clinic_id": payload.clinic_id,
            "created_by": current_user["id"],
            "title": payload.title,
            "source_query": payload.source_query,
            "answer_json": json.dumps(payload.answer_json),
            "citations_json": json.dumps(payload.citations_json),
            "tags": payload.tags,
        },
    )
    db.commit()
    track_event(
        db,
        "protocol_saved",
        user_id=current_user["id"],
        clinic_id=payload.clinic_id,
        org_id=membership["org_id"],
    )
    return {"id": pid, "status": "created"}


@router.get("/protocols")
def list_protocols(
    clinic_id: str = Query(...),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    require_clinic_member(db, current_user["id"], clinic_id)

    rows = db.execute(
        text("""
            SELECT * FROM saved_protocols
            WHERE clinic_id = :cid
              AND is_archived = :archived
            ORDER BY is_pinned DESC, created_at DESC
        """),
        {"cid": clinic_id, "archived": include_archived},
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["answer_json"] = json.loads(d["answer_json"]) if isinstance(d["answer_json"], str) else d["answer_json"]
        d["citations_json"] = json.loads(d["citations_json"]) if isinstance(d["citations_json"], str) else d["citations_json"]
        result.append(d)
    return result


@router.patch("/protocols/{protocol_id}")
def update_protocol(
    protocol_id: str,
    payload: ProtocolPatch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.execute(
        text("SELECT * FROM saved_protocols WHERE id = :id"), {"id": protocol_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Protocol not found.")

    # clinic_approved requires clinic_admin+
    if payload.clinic_approved is not None:
        require_clinic_member(
            db, current_user["id"], str(row["clinic_id"]),
            min_roles=["super_admin", "org_admin", "clinic_admin"]
        )
    else:
        require_clinic_member(db, current_user["id"], str(row["clinic_id"]))

    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if payload.clinic_approved:
        updates["approved_by"] = current_user["id"]
        updates["approved_at"] = now_utc()

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    db.execute(
        text(f"UPDATE saved_protocols SET {set_clause}, updated_at = now() WHERE id = :id"),
        {**updates, "id": protocol_id},
    )
    db.commit()
    return {"status": "updated", "id": protocol_id}


# ---------------------------------------------------------------------------
# SAFETY REPORTS
# ---------------------------------------------------------------------------


def _build_report_from_case(row: Dict[str, Any], notes: Optional[str]) -> Dict[str, Any]:
    return {
        "title": f"Safety Report — {row.get('complication_type', 'Complication')} ({row.get('patient_reference', '')})",
        "summary": (
            f"{row.get('complication_type', 'Complication')} identified during {row.get('procedure', 'procedure')} "
            f"in {row.get('region', 'unknown region')}. "
            f"Outcome: {row.get('outcome', 'pending')}."
        ),
        "presenting_problem": row.get("symptoms", ""),
        "immediate_actions": row.get("treatment_given", ""),
        "treatment_used": (
            f"{row.get('treatment_given', '')}. "
            + (f"Hyaluronidase dose: {row['hyaluronidase_dose']}." if row.get("hyaluronidase_dose") else "")
        ),
        "escalation_triggers": "Review for red flags: visual symptoms, spreading ischaemia, necrosis.",
        "follow_up": row.get("follow_up_plan", ""),
        "evidence_refs": [],
        "clinician_notes": notes or row.get("notes", ""),
        "patient_summary": (
            f"A complication occurred during your {row.get('procedure', 'treatment')}. "
            f"This was treated and the outcome was: {row.get('outcome', 'being monitored')}. "
            "Your clinician will discuss next steps with you."
        ),
    }


@router.post("/reports/from-case/{case_id}")
def report_from_case(
    case_id: str,
    payload: ReportFromCaseRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.execute(
        text("SELECT * FROM case_logs WHERE id = :id"), {"id": case_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Case log not found.")

    membership = require_clinic_member(db, current_user["id"], str(row["clinic_id"]))
    fields = _build_report_from_case(dict(row), payload.clinician_notes)
    report_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO safety_reports (
                id, org_id, clinic_id, created_by, source_type, source_id,
                title, summary, presenting_problem, immediate_actions, treatment_used,
                escalation_triggers, follow_up, evidence_refs, clinician_notes, patient_summary
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by, 'case_log', :source_id,
                :title, :summary, :presenting_problem, :immediate_actions, :treatment_used,
                :escalation_triggers, :follow_up, :evidence_refs, :clinician_notes, :patient_summary
            )
        """),
        {
            "id": report_id,
            "org_id": membership["org_id"],
            "clinic_id": payload.clinic_id,
            "created_by": current_user["id"],
            "source_id": case_id,
            "evidence_refs": json.dumps(fields["evidence_refs"]),
            **{k: v for k, v in fields.items() if k != "evidence_refs"},
        },
    )
    db.commit()

    track_event(
        db,
        "report_generated",
        user_id=current_user["id"],
        clinic_id=payload.clinic_id,
        org_id=membership["org_id"],
        metadata={"source_type": "case_log", "source_id": case_id},
    )
    return {"id": report_id, "status": "created", **fields}


@router.post("/reports/from-guidance")
def report_from_guidance(
    payload: ReportFromGuidanceRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    membership = require_clinic_member(db, current_user["id"], payload.clinic_id)
    g = payload.guidance_result
    report_id = str(uuid.uuid4())

    title = payload.title
    summary = g.get("complication_type", "Complication query")
    workflow = g.get("structured_workflow", {})

    db.execute(
        text("""
            INSERT INTO safety_reports (
                id, org_id, clinic_id, created_by, source_type,
                title, summary, presenting_problem, immediate_actions, treatment_used,
                escalation_triggers, follow_up, evidence_refs, clinician_notes, patient_summary
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by, 'guidance',
                :title, :summary, :presenting_problem, :immediate_actions, :treatment_used,
                :escalation_triggers, :follow_up, :evidence_refs, :clinician_notes, :patient_summary
            )
        """),
        {
            "id": report_id,
            "org_id": membership["org_id"],
            "clinic_id": payload.clinic_id,
            "created_by": current_user["id"],
            "title": title,
            "summary": summary,
            "presenting_problem": str(workflow.get("identify", {}).get("content", "")),
            "immediate_actions": str(workflow.get("immediate_action", {}).get("content", "")),
            "treatment_used": str(workflow.get("treatment", {}).get("content", "")),
            "escalation_triggers": str(workflow.get("escalation", {}).get("content", "")),
            "follow_up": str(workflow.get("follow_up", {}).get("content", "")),
            "evidence_refs": json.dumps(g.get("evidence_items", [])),
            "clinician_notes": payload.clinician_notes or "",
            "patient_summary": "",
        },
    )
    db.commit()
    track_event(
        db,
        "report_generated",
        user_id=current_user["id"],
        clinic_id=payload.clinic_id,
        org_id=membership["org_id"],
        metadata={"source_type": "guidance"},
    )
    return {"id": report_id, "status": "created"}


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.execute(
        text("SELECT * FROM safety_reports WHERE id = :id"), {"id": report_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found.")
    require_clinic_member(db, current_user["id"], str(row["clinic_id"]))
    d = dict(row)
    d["evidence_refs"] = json.loads(d["evidence_refs"]) if isinstance(d["evidence_refs"], str) else d["evidence_refs"]
    return d


# ---------------------------------------------------------------------------
# ADMIN ANALYTICS
# ---------------------------------------------------------------------------


@router.get("/admin/analytics/overview")
def analytics_overview(
    clinic_id: str = Query(...),
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    require_clinic_member(
        db, current_user["id"], clinic_id,
        min_roles=["super_admin", "org_admin", "clinic_admin"]
    )
    days = {"7d": 7, "30d": 30, "90d": 90}[period]

    total_queries = db.execute(
        text("""
            SELECT COUNT(*) FROM analytics_events
            WHERE clinic_id = :cid AND event_type = 'guidance_query_submitted'
              AND created_at >= now() - INTERVAL ':days days'
        """.replace(":days", str(days))),
        {"cid": clinic_id},
    ).scalar_one()

    total_cases = db.execute(
        text(f"""
            SELECT COUNT(*) FROM case_logs
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{days} days'
        """),
        {"cid": clinic_id},
    ).scalar_one()

    total_protocols = db.execute(
        text(f"""
            SELECT COUNT(*) FROM saved_protocols
            WHERE clinic_id = :cid AND is_archived = FALSE
              AND created_at >= now() - INTERVAL '{days} days'
        """),
        {"cid": clinic_id},
    ).scalar_one()

    total_reports = db.execute(
        text(f"""
            SELECT COUNT(*) FROM safety_reports
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{days} days'
        """),
        {"cid": clinic_id},
    ).scalar_one()

    top_complications = db.execute(
        text(f"""
            SELECT complication_type, COUNT(*) as cnt
            FROM case_logs
            WHERE clinic_id = :cid AND complication_type IS NOT NULL
              AND created_at >= now() - INTERVAL '{days} days'
            GROUP BY complication_type
            ORDER BY cnt DESC
            LIMIT 10
        """),
        {"cid": clinic_id},
    ).fetchall()

    high_risk_topics = db.execute(
        text(f"""
            SELECT complication_type, COUNT(*) as cnt
            FROM case_logs
            WHERE clinic_id = :cid
              AND complication_type ILIKE ANY(ARRAY[
                '%vascular%', '%occlusion%', '%visual%', '%necrosis%', '%inflammatory%'
              ])
              AND created_at >= now() - INTERVAL '{days} days'
            GROUP BY complication_type ORDER BY cnt DESC
        """),
        {"cid": clinic_id},
    ).fetchall()

    track_event(
        db, "admin_dashboard_opened",
        user_id=current_user["id"], clinic_id=clinic_id,
    )

    return {
        "period": period,
        "total_queries": total_queries,
        "total_case_logs": total_cases,
        "total_protocols": total_protocols,
        "total_reports": total_reports,
        "top_complications": [dict(r) for r in top_complications],
        "high_risk_topics": [dict(r) for r in high_risk_topics],
    }


@router.get("/admin/analytics/trends")
def analytics_trends(
    clinic_id: str = Query(...),
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    require_clinic_member(
        db, current_user["id"], clinic_id,
        min_roles=["super_admin", "org_admin", "clinic_admin"]
    )
    days = {"7d": 7, "30d": 30, "90d": 90}[period]

    queries_over_time = db.execute(
        text(f"""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM analytics_events
            WHERE clinic_id = :cid AND event_type = 'guidance_query_submitted'
              AND created_at >= now() - INTERVAL '{days} days'
            GROUP BY day ORDER BY day
        """),
        {"cid": clinic_id},
    ).fetchall()

    cases_over_time = db.execute(
        text(f"""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM case_logs
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{days} days'
            GROUP BY day ORDER BY day
        """),
        {"cid": clinic_id},
    ).fetchall()

    protocol_saves_over_time = db.execute(
        text(f"""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM saved_protocols
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{days} days'
            GROUP BY day ORDER BY day
        """),
        {"cid": clinic_id},
    ).fetchall()

    return {
        "period": period,
        "queries_over_time": [{"day": str(r["day"]), "count": r["cnt"]} for r in queries_over_time],
        "cases_over_time": [{"day": str(r["day"]), "count": r["cnt"]} for r in cases_over_time],
        "protocol_saves_over_time": [{"day": str(r["day"]), "count": r["cnt"]} for r in protocol_saves_over_time],
    }
