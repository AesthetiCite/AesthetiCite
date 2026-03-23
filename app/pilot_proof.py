"""
AesthetiCite — Risk & Documentation Proof Pack (Pilot Instrumentation)
=====================================================================

This module implements a clinic pilot measurement layer to PROVE:
1) Better complication recognition workflows
2) Faster escalation decisions
3) Standardized notes that reduce medico-legal exposure

It adds:
- Case lifecycle tracking (create case → log events → close case)
- Time-to-recognition / time-to-escalation metrics
- Documentation completeness scoring (audit rubric)
- AesthetiCite-generated standardized note templates + structured fields
- Exportable pilot reports (JSON) for investors/clinics

Notes:
- This code DOES NOT store patient identifiers. Use a site-local "case_ref" or hashed ID.
- Can run alongside existing AesthetiCite app or merge endpoints.

What you get out:
- Real, defensible metrics you can quote:
  - median time to recognition
  - median time to escalation
  - % cases with complete documentation
  - % cases with documented red flags
  - before/after comparisons (baseline vs AesthetiCite-enabled)
"""

from __future__ import annotations

import os
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import text

from app.db.session import SessionLocal
from app.pilot.rubric_autofill import autofill_rubric_from_note


# -----------------------------
# Config
# -----------------------------
APP_NAME = "AesthetiCite Pilot Proof"

# Pilot "documentation completeness" rubric (edit to match your clinic)
RUBRIC = [
    ("consent_documented", "Consent documented (yes/no)"),
    ("risks_discussed", "Risks discussed (e.g., vascular occlusion, ptosis, infection)"),
    ("product_documented", "Product documented (name/lot if applicable)"),
    ("dose_or_volume_documented", "Dose/volume documented"),
    ("technique_documented", "Technique documented (site/plane/needle-cannula as used)"),
    ("aftercare_documented", "Aftercare instructions documented"),
    ("follow_up_plan", "Follow-up plan documented"),
    ("complication_assessed", "Complication assessment documented (if relevant)"),
    ("red_flags_documented", "Red flags documented (pain, blanching, neuro/visual symptoms)"),
    ("escalation_rationale", "Escalation rationale documented (if escalation occurred)"),
]

# Event types for measuring timelines
EventType = Literal[
    "symptom_onset",          # when first abnormal symptom noticed/reported
    "recognition",            # when clinician first correctly suspects/recognizes complication
    "aestheticite_opened",    # when AesthetiCite used for the case
    "emergency_mode_opened",  # emergency mode opened
    "escalation",             # escalation action taken (call senior/ED/referral/transfer)
    "treatment_started",      # treatment action started (e.g., rescue protocol step)
    "follow_up_scheduled",    # follow-up arranged
    "case_closed",            # case closed
]

# Escalation categories (for evidence)
EscalationType = Literal[
    "senior_clinician",
    "ophthalmology",
    "emergency_department",
    "transfer",
    "ambulance",
    "other"
]


# -----------------------------
# DB Schema (PostgreSQL)
# -----------------------------
PILOT_SCHEMA_SQL = """
-- Pilot sites/clinics
CREATE TABLE IF NOT EXISTS pilot_sites (
    site_id TEXT PRIMARY KEY,
    site_name TEXT NOT NULL,
    country TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pilot users (clinicians)
CREATE TABLE IF NOT EXISTS pilot_users (
    user_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES pilot_sites(site_id),
    email TEXT,
    role TEXT DEFAULT 'clinician',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pilot cases (no PII)
CREATE TABLE IF NOT EXISTS pilot_cases (
    case_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES pilot_sites(site_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    phase TEXT NOT NULL DEFAULT 'aestheticite',
    case_ref TEXT,
    procedure TEXT,
    area TEXT,
    suspected_complication TEXT,
    notes TEXT
);

-- Pilot events
CREATE TABLE IF NOT EXISTS pilot_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES pilot_cases(case_id),
    event_type TEXT NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pilot documentation records
CREATE TABLE IF NOT EXISTS pilot_documentation (
    doc_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES pilot_cases(case_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    mode TEXT NOT NULL DEFAULT 'aestheticite',
    fields_json JSONB NOT NULL,
    generated_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_pilot_cases_site ON pilot_cases(site_id);
CREATE INDEX IF NOT EXISTS idx_pilot_events_case ON pilot_events(case_id);
CREATE INDEX IF NOT EXISTS idx_pilot_docs_case ON pilot_documentation(case_id);
"""


def init_pilot_db():
    """Initialize pilot database tables."""
    db = SessionLocal()
    try:
        db.execute(text(PILOT_SCHEMA_SQL))
        db.commit()
        print("Pilot proof tables initialized.")
    finally:
        db.close()


# -----------------------------
# Helpers
# -----------------------------
def _now() -> datetime:
    return datetime.utcnow()

def _iso(dt: datetime) -> str:
    return dt.isoformat() + "Z" if dt else None

def _ts_to_seconds(dt: datetime) -> int:
    return int(dt.timestamp()) if dt else None


# -----------------------------
# Models
# -----------------------------
class SiteCreate(BaseModel):
    site_name: str
    country: Optional[str] = None

class UserCreate(BaseModel):
    site_id: str
    email: Optional[EmailStr] = None
    role: Optional[str] = "clinician"

class CaseCreate(BaseModel):
    site_id: str
    phase: Literal["baseline", "aestheticite"] = "aestheticite"
    case_ref: Optional[str] = None
    procedure: Optional[str] = None
    area: Optional[str] = None
    suspected_complication: Optional[str] = None
    notes: Optional[str] = None

class EventLog(BaseModel):
    case_id: str
    event_type: str
    event_ts: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None

class DocumentSubmit(BaseModel):
    case_id: str
    mode: Literal["baseline", "aestheticite"] = "aestheticite"
    rubric: Dict[str, Any] = Field(default_factory=dict)
    product: Optional[str] = None
    dose_or_volume: Optional[str] = None
    technique: Optional[str] = None
    aftercare: Optional[str] = None
    follow_up: Optional[str] = None
    complications: Optional[str] = None
    escalation: Optional[str] = None

class NoteGenerate(BaseModel):
    case_id: str
    include_rubric_checklist: bool = True

class ReportRequest(BaseModel):
    site_id: str
    phase: Optional[Literal["baseline", "aestheticite"]] = None
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None


# -----------------------------
# Core metrics
# -----------------------------
def _rubric_score(fields: Dict[str, Any]) -> Dict[str, Any]:
    total = len(RUBRIC)
    present = 0
    missing = []
    detail = []
    for key, label in RUBRIC:
        val = fields.get(key)
        ok = bool(val) if isinstance(val, bool) else (val is not None and str(val).strip() != "")
        if ok:
            present += 1
        else:
            missing.append(key)
        detail.append({"key": key, "label": label, "value": val})
    pct = round(100.0 * present / total, 1) if total else 0.0
    return {"present": present, "total": total, "percent": pct, "missing": missing, "detail": detail}


def _get_event_ts(db, case_id: str, event_type: str) -> Optional[datetime]:
    result = db.execute(text("""
        SELECT event_ts FROM pilot_events 
        WHERE case_id = :case_id AND event_type = :event_type 
        ORDER BY event_ts ASC LIMIT 1
    """), {"case_id": case_id, "event_type": event_type}).fetchone()
    return result[0] if result else None


def _case_metrics(db, case_id: str) -> Dict[str, Any]:
    onset = _get_event_ts(db, case_id, "symptom_onset")
    recog = _get_event_ts(db, case_id, "recognition")
    escal = _get_event_ts(db, case_id, "escalation")
    opened = _get_event_ts(db, case_id, "aestheticite_opened")
    emode = _get_event_ts(db, case_id, "emergency_mode_opened")

    def dt_seconds(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
        if a and b and b >= a:
            return int((b - a).total_seconds())
        return None

    t_recognition = dt_seconds(onset, recog)
    t_escalation = dt_seconds(onset, escal)
    t_to_tool = dt_seconds(onset, opened) if onset else None

    doc = db.execute(text("""
        SELECT fields_json FROM pilot_documentation 
        WHERE case_id = :case_id ORDER BY created_at DESC LIMIT 1
    """), {"case_id": case_id}).fetchone()
    
    if doc:
        fields = doc[0] if isinstance(doc[0], dict) else json.loads(doc[0])
        rubric = _rubric_score(fields.get("rubric", {}))
    else:
        rubric = _rubric_score({})

    return {
        "case_id": case_id,
        "time_to_recognition_s": t_recognition,
        "time_to_escalation_s": t_escalation,
        "time_to_aestheticite_opened_s": t_to_tool,
        "used_aestheticite": opened is not None or emode is not None,
        "used_emergency_mode": emode is not None,
        "documentation_score": rubric,
    }


def _median(values: List[int]) -> Optional[float]:
    vals = sorted([v for v in values if v is not None])
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def _aggregate_report(db, site_id: str, phase: Optional[str], start_ts: Optional[int], end_ts: Optional[int]) -> Dict[str, Any]:
    query = "SELECT case_id, created_at, phase FROM pilot_cases WHERE site_id = :site_id"
    params = {"site_id": site_id}
    
    if phase:
        query += " AND phase = :phase"
        params["phase"] = phase
    if start_ts:
        query += " AND created_at >= to_timestamp(:start_ts)"
        params["start_ts"] = start_ts
    if end_ts:
        query += " AND created_at <= to_timestamp(:end_ts)"
        params["end_ts"] = end_ts

    rows = db.execute(text(query), params).fetchall()
    case_ids = [r[0] for r in rows]

    metrics = [_case_metrics(db, cid) for cid in case_ids]
    ttr = [m["time_to_recognition_s"] for m in metrics if m["time_to_recognition_s"] is not None]
    tte = [m["time_to_escalation_s"] for m in metrics if m["time_to_escalation_s"] is not None]
    doc_pct = [m["documentation_score"]["percent"] for m in metrics if m.get("documentation_score")]

    recog_logged = sum(1 for m in metrics if m["time_to_recognition_s"] is not None)
    escal_logged = sum(1 for m in metrics if m["time_to_escalation_s"] is not None)
    used_tool = sum(1 for m in metrics if m["used_aestheticite"])
    used_emode = sum(1 for m in metrics if m["used_emergency_mode"])

    COMPLETE_THRESHOLD = 85.0
    complete_docs = sum(1 for m in metrics if m["documentation_score"]["percent"] >= COMPLETE_THRESHOLD)

    return {
        "site_id": site_id,
        "phase": phase or "all",
        "window": {
            "start_ts": start_ts,
            "end_ts": end_ts,
        },
        "counts": {
            "cases": len(case_ids),
            "recognition_logged": recog_logged,
            "escalation_logged": escal_logged,
            "used_aestheticite": used_tool,
            "used_emergency_mode": used_emode,
            "complete_documentation_cases": complete_docs,
        },
        "time_metrics_seconds": {
            "median_time_to_recognition": _median(ttr),
            "median_time_to_escalation": _median(tte),
        },
        "documentation": {
            "median_completeness_percent": _median([int(x * 10) for x in doc_pct]) / 10.0 if doc_pct else None,
            "complete_threshold_percent": COMPLETE_THRESHOLD,
            "complete_rate_percent": round(100.0 * complete_docs / max(1, len(case_ids)), 1),
        },
        "case_metrics_sample": metrics[:25],
    }


# -----------------------------
# Standardized Note Generator
# -----------------------------
def generate_standard_note(case_row: dict, doc_fields: Dict[str, Any], include_rubric_checklist: bool) -> str:
    procedure = case_row.get("procedure") or "Procedure"
    area = case_row.get("area") or "N/A"
    suspected = case_row.get("suspected_complication") or "N/A"
    phase = case_row.get("phase", "aestheticite")

    product = doc_fields.get("product") or "N/A"
    dose = doc_fields.get("dose_or_volume") or "N/A"
    technique = doc_fields.get("technique") or "N/A"
    aftercare = doc_fields.get("aftercare") or "N/A"
    follow_up = doc_fields.get("follow_up") or "N/A"
    complications = doc_fields.get("complications") or "N/A"
    escalation = doc_fields.get("escalation") or "N/A"

    lines = []
    lines.append("CHIEF CONCERN / INDICATION")
    lines.append(f"- {procedure} ({area}).")
    lines.append("")
    lines.append("COUNSELING & CONSENT")
    lines.append("- Informed consent discussed and documented as per clinic policy.")
    lines.append("- Expected benefits, common side effects, and rare serious risks were reviewed.")
    lines.append("")
    lines.append("PROCEDURE DETAILS")
    lines.append(f"- Product: {product}")
    lines.append(f"- Dose/Volume: {dose}")
    lines.append(f"- Technique: {technique}")
    lines.append("")
    lines.append("POST-PROCEDURE INSTRUCTIONS")
    lines.append(f"- Aftercare: {aftercare}")
    lines.append(f"- Follow-up: {follow_up}")
    lines.append("")
    lines.append("COMPLICATIONS / ASSESSMENT")
    lines.append(f"- Suspected complication: {suspected}")
    lines.append(f"- Assessment/notes: {complications}")
    lines.append("")
    lines.append("ESCALATION / REFERRAL (if applicable)")
    lines.append(f"- Escalation actions/rationale: {escalation}")
    lines.append("")
    lines.append("SYSTEM NOTE")
    lines.append(f"- Pilot phase: {phase}. Generated using AesthetiCite standardized documentation template.")
    
    if include_rubric_checklist:
        rubric = _rubric_score(doc_fields.get("rubric", {}))
        lines.append("")
        lines.append("DOCUMENTATION CHECKLIST (internal)")
        lines.append(f"- Completeness: {rubric['percent']}% ({rubric['present']}/{rubric['total']})")
        if rubric["missing"]:
            lines.append(f"- Missing: {', '.join(rubric['missing'])}")
    
    return "\n".join(lines).strip()


# -----------------------------
# FastAPI Router
# -----------------------------
router = APIRouter(prefix="/pilot", tags=["Pilot Proof"])


@router.get("/health")
def health():
    return {"ok": True, "app": APP_NAME, "time": datetime.utcnow().isoformat() + "Z"}


@router.post("/init-db")
def init_db_endpoint():
    init_pilot_db()
    return {"ok": True, "message": "Pilot database initialized"}


# ---- Sites & users ----
@router.post("/sites")
def create_site(req: SiteCreate):
    site_id = "site_" + uuid.uuid4().hex[:12]
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO pilot_sites(site_id, site_name, country) 
            VALUES(:site_id, :site_name, :country)
        """), {"site_id": site_id, "site_name": req.site_name, "country": req.country})
        db.commit()
    finally:
        db.close()
    return {"ok": True, "site_id": site_id}


@router.post("/users")
def create_user(req: UserCreate):
    db = SessionLocal()
    try:
        site = db.execute(text("SELECT site_id FROM pilot_sites WHERE site_id = :sid"), 
                         {"sid": req.site_id}).fetchone()
        if not site:
            raise HTTPException(404, "site not found")
        
        user_id = "user_" + uuid.uuid4().hex[:12]
        db.execute(text("""
            INSERT INTO pilot_users(user_id, site_id, email, role) 
            VALUES(:uid, :sid, :email, :role)
        """), {"uid": user_id, "sid": req.site_id, "email": str(req.email) if req.email else None, "role": req.role})
        db.commit()
    finally:
        db.close()
    return {"ok": True, "user_id": user_id}


# ---- Case lifecycle ----
@router.post("/cases")
def create_case(req: CaseCreate):
    db = SessionLocal()
    try:
        site = db.execute(text("SELECT site_id FROM pilot_sites WHERE site_id = :sid"), 
                         {"sid": req.site_id}).fetchone()
        if not site:
            raise HTTPException(404, "site not found")

        case_id = "case_" + uuid.uuid4().hex[:16]
        db.execute(text("""
            INSERT INTO pilot_cases(case_id, site_id, phase, case_ref, procedure, area, suspected_complication, notes)
            VALUES(:case_id, :site_id, :phase, :case_ref, :procedure, :area, :complication, :notes)
        """), {
            "case_id": case_id, "site_id": req.site_id, "phase": req.phase,
            "case_ref": req.case_ref, "procedure": req.procedure, "area": req.area,
            "complication": req.suspected_complication, "notes": req.notes
        })
        db.commit()
    finally:
        db.close()
    return {"ok": True, "case_id": case_id}


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    db = SessionLocal()
    try:
        case = db.execute(text("SELECT * FROM pilot_cases WHERE case_id = :cid"), 
                         {"cid": case_id}).fetchone()
        if not case:
            raise HTTPException(404, "case not found")
        
        events = db.execute(text("""
            SELECT event_type, event_ts, payload FROM pilot_events 
            WHERE case_id = :cid ORDER BY event_ts ASC
        """), {"cid": case_id}).fetchall()
        
        doc = db.execute(text("""
            SELECT * FROM pilot_documentation 
            WHERE case_id = :cid ORDER BY created_at DESC LIMIT 1
        """), {"cid": case_id}).fetchone()
        
        metrics = _case_metrics(db, case_id)
        
        return {
            "case": dict(case._mapping) if case else None,
            "events": [{"event_type": e[0], "event_ts": _iso(e[1]), "payload": e[2]} for e in events],
            "documentation_latest": dict(doc._mapping) if doc else None,
            "metrics": metrics,
        }
    finally:
        db.close()


@router.post("/events")
def log_event(req: EventLog):
    db = SessionLocal()
    try:
        case = db.execute(text("SELECT case_id FROM pilot_cases WHERE case_id = :cid"), 
                         {"cid": req.case_id}).fetchone()
        if not case:
            raise HTTPException(404, "case not found")
        
        event_id = "evt_" + uuid.uuid4().hex[:16]
        event_ts = datetime.utcfromtimestamp(req.event_ts) if req.event_ts else _now()
        
        db.execute(text("""
            INSERT INTO pilot_events(event_id, case_id, event_type, event_ts, payload)
            VALUES(:eid, :cid, :etype, :ets, :payload)
        """), {
            "eid": event_id, "cid": req.case_id, "etype": req.event_type,
            "ets": event_ts, "payload": json.dumps(req.payload or {})
        })
        
        if req.event_type == "case_closed":
            db.execute(text("UPDATE pilot_cases SET closed_at = :ts WHERE case_id = :cid"),
                      {"ts": event_ts, "cid": req.case_id})
        
        db.commit()
    finally:
        db.close()
    return {"ok": True, "event_id": event_id, "event_ts": _iso(event_ts)}


@router.post("/cases/{case_id}/close")
def close_case(case_id: str):
    db = SessionLocal()
    try:
        case = db.execute(text("SELECT case_id FROM pilot_cases WHERE case_id = :cid"), 
                         {"cid": case_id}).fetchone()
        if not case:
            raise HTTPException(404, "case not found")
        
        ts = _now()
        db.execute(text("UPDATE pilot_cases SET closed_at = :ts WHERE case_id = :cid"),
                  {"ts": ts, "cid": case_id})
        
        event_id = "evt_" + uuid.uuid4().hex[:16]
        db.execute(text("""
            INSERT INTO pilot_events(event_id, case_id, event_type, event_ts, payload)
            VALUES(:eid, :cid, 'case_closed', :ets, '{}')
        """), {"eid": event_id, "cid": case_id, "ets": ts})
        
        db.commit()
    finally:
        db.close()
    return {"ok": True, "closed_at": _iso(ts)}


# ---- Documentation submission + scoring ----
@router.post("/documentation")
def submit_documentation(req: DocumentSubmit):
    db = SessionLocal()
    try:
        case = db.execute(text("SELECT * FROM pilot_cases WHERE case_id = :cid"), 
                         {"cid": req.case_id}).fetchone()
        if not case:
            raise HTTPException(404, "case not found")

        fields = {
            "rubric": req.rubric,
            "product": req.product,
            "dose_or_volume": req.dose_or_volume,
            "technique": req.technique,
            "aftercare": req.aftercare,
            "follow_up": req.follow_up,
            "complications": req.complications,
            "escalation": req.escalation,
        }

        score = _rubric_score(req.rubric)
        doc_id = "doc_" + uuid.uuid4().hex[:16]
        
        db.execute(text("""
            INSERT INTO pilot_documentation(doc_id, case_id, mode, fields_json)
            VALUES(:did, :cid, :mode, :fields)
        """), {"did": doc_id, "cid": req.case_id, "mode": req.mode, "fields": json.dumps(fields)})
        db.commit()
    finally:
        db.close()
    return {"ok": True, "doc_id": doc_id, "documentation_score": score}


@router.post("/documentation/generate-note")
def generate_note(req: NoteGenerate):
    db = SessionLocal()
    try:
        case = db.execute(text("SELECT * FROM pilot_cases WHERE case_id = :cid"), 
                         {"cid": req.case_id}).fetchone()
        if not case:
            raise HTTPException(404, "case not found")
        
        doc = db.execute(text("""
            SELECT * FROM pilot_documentation 
            WHERE case_id = :cid ORDER BY created_at DESC LIMIT 1
        """), {"cid": req.case_id}).fetchone()
        
        if not doc:
            raise HTTPException(400, "submit /documentation first")

        case_dict = dict(case._mapping)
        fields = doc[4] if isinstance(doc[4], dict) else json.loads(doc[4])
        note = generate_standard_note(case_dict, fields, req.include_rubric_checklist)
        
        rubric_defaults = autofill_rubric_from_note(note)
        
        db.execute(text("UPDATE pilot_documentation SET generated_note = :note WHERE doc_id = :did"),
                  {"note": note, "did": doc[0]})
        db.commit()
    finally:
        db.close()
    return {
        "ok": True, 
        "doc_id": doc[0], 
        "generated_note": note,
        "rubric_defaults": rubric_defaults
    }


# ---- Reporting ----
@router.post("/reports/site")
def site_report(req: ReportRequest):
    db = SessionLocal()
    try:
        site = db.execute(text("SELECT site_id FROM pilot_sites WHERE site_id = :sid"), 
                         {"sid": req.site_id}).fetchone()
        if not site:
            raise HTTPException(404, "site not found")
        return _aggregate_report(db, req.site_id, req.phase, req.start_ts, req.end_ts)
    finally:
        db.close()


@router.post("/reports/compare")
def compare_baseline_vs_aestheticite(req: ReportRequest):
    """
    Produces side-by-side baseline vs aestheticite comparisons for the same time window.
    This is the investor-friendly proof output.
    """
    db = SessionLocal()
    try:
        site = db.execute(text("SELECT site_id FROM pilot_sites WHERE site_id = :sid"), 
                         {"sid": req.site_id}).fetchone()
        if not site:
            raise HTTPException(404, "site not found")

        baseline = _aggregate_report(db, req.site_id, "baseline", req.start_ts, req.end_ts)
        aesth = _aggregate_report(db, req.site_id, "aestheticite", req.start_ts, req.end_ts)

        def pct_change(old, new):
            if old is None or new is None or old == 0:
                return None
            return round(100.0 * (new - old) / old, 1)

        return {
            "site_id": req.site_id,
            "window": baseline["window"],
            "baseline": baseline,
            "aestheticite": aesth,
            "deltas": {
                "median_time_to_recognition_s_change_pct": pct_change(
                    baseline["time_metrics_seconds"]["median_time_to_recognition"],
                    aesth["time_metrics_seconds"]["median_time_to_recognition"]
                ),
                "median_time_to_escalation_s_change_pct": pct_change(
                    baseline["time_metrics_seconds"]["median_time_to_escalation"],
                    aesth["time_metrics_seconds"]["median_time_to_escalation"]
                ),
                "complete_documentation_rate_change_pct": pct_change(
                    baseline["documentation"]["complete_rate_percent"],
                    aesth["documentation"]["complete_rate_percent"]
                ),
            },
            "investor_summary": {
                "baseline_cases": baseline["counts"]["cases"],
                "aestheticite_cases": aesth["counts"]["cases"],
                "improvement_time_to_recognition": pct_change(
                    baseline["time_metrics_seconds"]["median_time_to_recognition"],
                    aesth["time_metrics_seconds"]["median_time_to_recognition"]
                ),
                "improvement_documentation_completeness": pct_change(
                    baseline["documentation"]["complete_rate_percent"],
                    aesth["documentation"]["complete_rate_percent"]
                ),
            }
        }
    finally:
        db.close()


@router.get("/rubric")
def get_rubric():
    """Return the documentation completeness rubric for frontend display."""
    return {
        "rubric": [{"key": key, "label": label} for key, label in RUBRIC],
        "complete_threshold_percent": 85.0,
    }
