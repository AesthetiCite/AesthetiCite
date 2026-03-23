"""
AesthetiCite — Cases API  (Doximity-inspired network effect)
=============================================================
Endpoints:
  POST /api/cases                     — log a case (quick, 3 required fields)
  GET  /api/cases?complication=...    — similar cases with outcome stats
  GET  /api/cases/stats               — network-level aggregate statistics
  GET  /api/cases/outcomes/{comp}     — outcome breakdown for one complication
  POST /api/cases/{id}/outcome        — update outcome after resolution
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import bearer, decode_token
from app.db.session import get_db
from fastapi.security import HTTPAuthorizationCredentials


def get_optional_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    """Returns the current user dict if authenticated, otherwise None."""
    if creds is None:
        return None
    try:
        from sqlalchemy import text as _text
        user_id = decode_token(creds.credentials)
        row = db.execute(_text("""
            SELECT id::text, email, is_active, role, full_name
            FROM users WHERE id = :id
        """), {"id": user_id}).mappings().first()
        return dict(row) if row and row["is_active"] else None
    except Exception:
        return None

router = APIRouter(prefix="/api/cases", tags=["Cases Network"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clinic_id_from_user(db: Session, user_id: str) -> Optional[str]:
    row = db.execute(
        text("""
            SELECT clinic_id FROM memberships
            WHERE user_id = :uid AND is_active = TRUE
            ORDER BY created_at LIMIT 1
        """),
        {"uid": user_id},
    ).mappings().fetchone()
    return str(row["clinic_id"]) if row else None


def _org_id_from_clinic(db: Session, clinic_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT org_id FROM clinics WHERE id = :cid"),
        {"cid": clinic_id},
    ).mappings().fetchone()
    return str(row["org_id"]) if row else None


def _parse_resolution_minutes(time_str: Optional[str]) -> Optional[int]:
    """Parse free-text time like '2h', '90 min', '45 minutes' → minutes."""
    if not time_str:
        return None
    t = time_str.lower().strip()
    try:
        if "h" in t:
            h = float(t.replace("h", "").replace("ours", "").strip())
            return int(h * 60)
        if "min" in t:
            m = float(t.replace("minutes", "").replace("mins", "").replace("min", "").strip())
            return int(m)
        return int(float(t))
    except (ValueError, TypeError):
        return None


class CaseCreate(BaseModel):
    complication: str = Field(..., min_length=2)
    treatment: str = Field(..., min_length=2)
    outcome: str
    time_to_resolution: Optional[str] = None
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_used: Optional[str] = None
    hyaluronidase_dose: Optional[str] = None
    notes: Optional[str] = None
    clinic_id: Optional[str] = None


class OutcomeUpdate(BaseModel):
    outcome: str
    time_to_resolution: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def log_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    user_id = current_user["id"] if current_user else None

    clinic_id = payload.clinic_id
    if not clinic_id and user_id:
        try:
            clinic_id = _clinic_id_from_user(db, user_id)
        except Exception:
            clinic_id = None

    org_id = None
    if clinic_id:
        try:
            org_id = _org_id_from_clinic(db, clinic_id)
        except Exception:
            pass

    case_id = str(uuid.uuid4())
    res_minutes = _parse_resolution_minutes(payload.time_to_resolution)

    db.execute(
        text("""
            INSERT INTO case_logs (
                id, org_id, clinic_id, created_by,
                patient_reference,
                complication_type, treatment_given, outcome,
                procedure, region, product_used, hyaluronidase_dose, notes
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by,
                'ANONYMOUS',
                :comp, :treatment, :outcome,
                :proc, :region, :product, :hyal, :notes
            )
        """),
        {
            "id":          case_id,
            "org_id":      org_id,
            "clinic_id":   clinic_id,
            "created_by":  user_id or "anonymous",
            "comp":        payload.complication,
            "treatment":   payload.treatment,
            "outcome":     payload.outcome,
            "proc":        payload.procedure,
            "region":      payload.region,
            "product":     payload.product_used,
            "hyal":        payload.hyaluronidase_dose,
            "notes":       payload.notes,
        },
    )
    db.commit()

    if res_minutes:
        try:
            db.execute(
                text("UPDATE case_logs SET notes = COALESCE(notes || ' | ', '') || :rt WHERE id = :id"),
                {"rt": f"Resolution time: {res_minutes} min", "id": case_id},
            )
            db.commit()
        except Exception:
            pass

    return {
        "status": "logged",
        "case_id": case_id,
        "complication": payload.complication,
        "outcome": payload.outcome,
    }


@router.get("/stats")
async def network_stats(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Public network statistics — shown on home screen to demonstrate data density."""
    try:
        total = db.execute(text("SELECT COUNT(*) FROM case_logs")).scalar_one()
        resolved = db.execute(
            text("SELECT COUNT(*) FROM case_logs WHERE LOWER(outcome) LIKE '%resolved%'")
        ).scalar_one()
        by_comp = db.execute(
            text("""
                SELECT complication_type, COUNT(*) as cnt
                FROM case_logs
                WHERE complication_type IS NOT NULL
                GROUP BY complication_type
                ORDER BY cnt DESC
                LIMIT 8
            """)
        ).mappings().fetchall()

        return {
            "total_cases": total,
            "resolved_cases": resolved,
            "resolution_rate_pct": round(resolved / max(total, 1) * 100, 1),
            "top_complications": [
                {"complication": r["complication_type"], "count": r["cnt"]}
                for r in by_comp
            ],
            "data_quality": "good" if total >= 50 else "building" if total >= 10 else "early",
        }
    except Exception:
        return {"total_cases": 0, "resolved_cases": 0, "resolution_rate_pct": 0.0,
                "top_complications": [], "data_quality": "early"}


@router.get("/outcomes/{complication}")
async def outcome_breakdown(
    complication: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    rows = db.execute(
        text("""
            SELECT outcome, COUNT(*) as cnt
            FROM case_logs
            WHERE LOWER(complication_type) LIKE :comp AND outcome IS NOT NULL
            GROUP BY outcome ORDER BY cnt DESC
        """),
        {"comp": f"%{complication.lower()}%"},
    ).mappings().fetchall()

    total = sum(r["cnt"] for r in rows)
    if not total:
        return {"complication": complication, "total": 0, "breakdown": []}

    return {
        "complication": complication,
        "total": total,
        "breakdown": [
            {"outcome": r["outcome"], "count": r["cnt"], "pct": round(r["cnt"] / total * 100, 1)}
            for r in rows
        ],
    }


@router.get("")
async def get_similar_cases(
    complication: str = Query(..., min_length=2),
    region: Optional[str] = Query(None),
    procedure: Optional[str] = Query(None),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    filters = ["LOWER(complication_type) LIKE :comp"]
    params: Dict[str, Any] = {"comp": f"%{complication.lower()}%", "limit": limit}

    if region:
        filters.append("LOWER(region) LIKE :region")
        params["region"] = f"%{region.lower()}%"

    if procedure:
        filters.append("LOWER(procedure) LIKE :proc")
        params["proc"] = f"%{procedure.lower()}%"

    where = " AND ".join(filters)

    all_rows = db.execute(
        text(f"""
            SELECT complication_type, treatment_given, outcome,
                   product_used, hyaluronidase_dose, region, procedure,
                   notes, created_at
            FROM case_logs
            WHERE {where}
            ORDER BY created_at DESC
        """),
        {k: v for k, v in params.items() if k != "limit"},
    ).mappings().fetchall()

    total = len(all_rows)

    if total == 0:
        return {
            "complication": complication,
            "network_size": 0,
            "outcome_stats": None,
            "similar_cases": [],
            "message": "No cases logged yet for this complication. Be the first to contribute.",
        }

    outcomes = [r["outcome"] for r in all_rows if r["outcome"]]
    outcome_counts = dict(Counter(o.lower() for o in outcomes))

    resolved_count = sum(
        1 for o in outcomes
        if any(kw in o.lower() for kw in ("resolved", "resolution", "improved", "cleared"))
    )
    resolution_rate = round(resolved_count / max(total, 1) * 100, 1)

    treatments = [r["treatment_given"] for r in all_rows if r["treatment_given"]]
    treatment_terms: Counter = Counter()
    for t in treatments:
        for kw in ["hyaluronidase", "aspirin", "antibiotics", "prednisolone", "apraclonidine",
                   "5-fu", "nitroglycerin", "adrenaline", "epinephrine", "co-amoxiclav",
                   "clarithromycin", "ciprofloxacin", "steroid", "antihistamine", "ice",
                   "warm compress", "massage", "observation"]:
            if kw in t.lower():
                treatment_terms[kw] += 1
    top_treatments = [{"treatment": t, "cases": c} for t, c in treatment_terms.most_common(6)]

    hyal_doses = [r["hyaluronidase_dose"] for r in all_rows if r["hyaluronidase_dose"]]
    hyal_dist: Counter = Counter()
    for d in hyal_doses:
        for dose_range in ["150", "300", "600", "1000", "1500", "3000", "10000"]:
            if dose_range in d:
                hyal_dist[f"{dose_range} IU"] += 1
    hyal_summary = [{"dose": d, "cases": c} for d, c in hyal_dist.most_common(4)]

    res_times: List[int] = []
    for r in all_rows:
        notes = r["notes"] or ""
        if "Resolution time:" in notes:
            try:
                rt_str = notes.split("Resolution time:")[-1].split("|")[0].strip()
                rt = int(rt_str.replace("min", "").strip())
                res_times.append(rt)
            except (ValueError, IndexError):
                pass

    time_stats = None
    if res_times:
        time_stats = {
            "median_minutes": int(median(res_times)),
            "average_minutes": int(mean(res_times)),
            "fastest_minutes": min(res_times),
            "slowest_minutes": max(res_times),
            "sample_size": len(res_times),
        }

    outcome_stats = {
        "total_cases": total,
        "resolution_rate_pct": resolution_rate,
        "outcome_breakdown": outcome_counts,
        "top_treatments": top_treatments,
        "hyaluronidase_doses": hyal_summary,
        "resolution_time": time_stats,
    }

    recent_rows = all_rows[:limit]
    similar = []
    for r in recent_rows:
        created = r["created_at"]
        try:
            now = datetime.now(timezone.utc)
            if hasattr(created, "tzinfo") and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            diff = now - created
            days = diff.days
            time_ago = (
                "Today" if days < 1 else
                f"{days}d ago" if days < 7 else
                f"{days // 7}w ago" if days < 30 else
                f"{days // 30}mo ago"
            )
        except Exception:
            time_ago = "Recently"

        similar.append({
            "complication": r["complication_type"],
            "treatment":    r["treatment_given"],
            "outcome":      r["outcome"],
            "region":       r["region"],
            "procedure":    r["procedure"],
            "product":      r["product_used"],
            "hyal_dose":    r["hyaluronidase_dose"],
            "time_ago":     time_ago,
        })

    return {
        "complication": complication,
        "network_size": total,
        "outcome_stats": outcome_stats,
        "similar_cases": similar,
    }


@router.post("/{case_id}/outcome")
async def update_outcome(
    case_id: str,
    payload: OutcomeUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    res_minutes = _parse_resolution_minutes(payload.time_to_resolution)
    note_suffix = ""
    if res_minutes:
        note_suffix = f" | Resolution time: {res_minutes} min"
    if payload.notes:
        note_suffix += f" | {payload.notes}"

    db.execute(
        text("""
            UPDATE case_logs
            SET outcome = :outcome,
                notes = COALESCE(notes, '') || :note,
                updated_at = now()
            WHERE id = :id
        """),
        {"outcome": payload.outcome, "note": note_suffix, "id": case_id},
    )
    db.commit()
    return {"status": "updated", "case_id": case_id, "outcome": payload.outcome}
