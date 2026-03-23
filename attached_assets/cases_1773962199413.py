"""
AesthetiCite — Cases API  (Doximity-inspired network effect)
=============================================================
Endpoints:
  POST /api/cases                     — log a case (quick, 3 required fields)
  GET  /api/cases?complication=...    — similar cases with outcome stats
  GET  /api/cases/stats               — network-level aggregate statistics
  GET  /api/cases/outcomes/{comp}     — outcome breakdown for one complication
  POST /api/cases/{id}/outcome        — update outcome after resolution

Design:
  - Uses the existing case_logs PostgreSQL table (from network_workspace.py)
  - All responses are fully anonymised — no patient reference, no clinic name
  - Outcome aggregation is the core value: "78% resolved, avg 2h"
  - Minimum viable case: complication + treatment + outcome
  - Resolution time is stored and shown to demonstrate network effect
"""
from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_optional_user
from app.db.session import get_db

router = APIRouter(prefix="/api/cases", tags=["Cases Network"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clinic_id_from_user(db: Session, user_id: str) -> Optional[str]:
    """Get the user's primary clinic (first active membership)."""
    row = db.execute(
        text("""
            SELECT clinic_id FROM memberships
            WHERE user_id = :uid AND is_active = TRUE
            ORDER BY created_at LIMIT 1
        """),
        {"uid": user_id},
    ).fetchone()
    return str(row["clinic_id"]) if row else None


def _org_id_from_clinic(db: Session, clinic_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT org_id FROM clinics WHERE id = :cid"),
        {"cid": clinic_id},
    ).fetchone()
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
        # bare number → assume minutes
        return int(float(t))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CaseCreate(BaseModel):
    """Minimal case log — 3 required fields, everything else optional."""
    complication: str = Field(..., min_length=2, description="e.g. 'vascular occlusion'")
    treatment: str = Field(..., min_length=2, description="e.g. 'hyaluronidase 1500 IU + aspirin'")
    outcome: str = Field(..., description="e.g. 'resolved', 'ongoing', 'urgent referral'")
    # Optional enrichment
    time_to_resolution: Optional[str] = None   # e.g. "2h", "90 min"
    procedure: Optional[str] = None
    region: Optional[str] = None
    product_used: Optional[str] = None
    hyaluronidase_dose: Optional[str] = None
    notes: Optional[str] = None
    # Allow explicit clinic/org — fall back to user's primary clinic
    clinic_id: Optional[str] = None


class OutcomeUpdate(BaseModel):
    outcome: str
    time_to_resolution: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /api/cases — quick case log
# ---------------------------------------------------------------------------

@router.post("")
async def log_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    Log a case. Designed to be fast — minimum 3 fields.
    Can be called from:
      - The complication decision page ("Log This Case" button)
      - The case log tab in the network workspace
      - API integrations
    """
    user_id = current_user["id"] if current_user else None

    # Resolve clinic
    clinic_id = payload.clinic_id
    if not clinic_id and user_id:
        clinic_id = _clinic_id_from_user(db, user_id)

    org_id = _org_id_from_clinic(db, clinic_id) if clinic_id else None

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

    # Store resolution time in a metadata column if possible, else in notes
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


# ---------------------------------------------------------------------------
# GET /api/cases — similar cases with outcome aggregation
# ---------------------------------------------------------------------------

@router.get("")
async def get_similar_cases(
    complication: str = Query(..., min_length=2),
    region: Optional[str] = Query(None),
    procedure: Optional[str] = Query(None),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    Returns:
      - outcome_stats: aggregated resolution rates, most common treatments
      - similar_cases: anonymised individual cases
      - network_size: total cases for this complication
    """
    # Build query — case-insensitive partial match
    filters = ["LOWER(complication_type) LIKE :comp"]
    params: Dict[str, Any] = {
        "comp": f"%{complication.lower()}%",
        "limit": limit,
    }

    if region:
        filters.append("LOWER(region) LIKE :region")
        params["region"] = f"%{region.lower()}%"

    if procedure:
        filters.append("LOWER(procedure) LIKE :proc")
        params["proc"] = f"%{procedure.lower()}%"

    where = " AND ".join(filters)

    # Fetch cases for statistics (no limit — we need all for accurate stats)
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
    ).fetchall()

    total = len(all_rows)

    if total == 0:
        return {
            "complication": complication,
            "network_size": 0,
            "outcome_stats": None,
            "similar_cases": [],
            "message": "No cases logged yet for this complication. Be the first to contribute.",
        }

    # ---------------------------------------------------------------------------
    # Aggregate statistics
    # ---------------------------------------------------------------------------

    outcomes = [r["outcome"] for r in all_rows if r["outcome"]]
    outcome_counts = dict(Counter(o.lower() for o in outcomes))

    # Resolution rate
    resolved_count = sum(
        1 for o in outcomes
        if any(kw in o.lower() for kw in ("resolved", "resolution", "improved", "cleared"))
    )
    resolution_rate = round(resolved_count / max(total, 1) * 100, 1)

    # Most common treatments
    treatments = [r["treatment_given"] for r in all_rows if r["treatment_given"]]
    treatment_terms: Counter = Counter()
    for t in treatments:
        # Extract key terms from treatment text
        for kw in ["hyaluronidase", "aspirin", "antibiotics", "prednisolone", "apraclonidine",
                    "5-fu", "nitroglycerin", "adrenaline", "epinephrine", "co-amoxiclav",
                    "clarithromycin", "ciprofloxacin", "steroid", "antihistamine", "ice",
                    "warm compress", "massage", "observation"]:
            if kw in t.lower():
                treatment_terms[kw] += 1
    top_treatments = [{"treatment": t, "cases": c} for t, c in treatment_terms.most_common(6)]

    # Hyaluronidase dose distribution
    hyal_doses = [r["hyaluronidase_dose"] for r in all_rows if r["hyaluronidase_dose"]]
    hyal_dist: Counter = Counter()
    for d in hyal_doses:
        for dose_range in ["150", "300", "600", "1000", "1500", "3000", "10000"]:
            if dose_range in d:
                hyal_dist[f"{dose_range} IU"] += 1
    hyal_summary = [{"dose": d, "cases": c} for d, c in hyal_dist.most_common(4)]

    # Resolution time extraction from notes
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

    # ---------------------------------------------------------------------------
    # Individual similar cases (anonymised, limited)
    # ---------------------------------------------------------------------------

    recent_rows = all_rows[:limit]
    similar = []
    for r in recent_rows:
        # Calculate time_ago
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
            # Fully anonymised — no patient ref, no clinic, no practitioner
        })

    return {
        "complication": complication,
        "network_size": total,
        "outcome_stats": outcome_stats,
        "similar_cases": similar,
    }


# ---------------------------------------------------------------------------
# GET /api/cases/stats — network-level aggregate
# ---------------------------------------------------------------------------

@router.get("/stats")
async def network_stats(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Public network statistics — used on the home screen to show data density."""
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
        ).fetchall()

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


# ---------------------------------------------------------------------------
# GET /api/cases/outcomes/{complication} — outcome breakdown
# ---------------------------------------------------------------------------

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
    ).fetchall()

    total = sum(r["cnt"] for r in rows)
    if not total:
        return {"complication": complication, "total": 0, "breakdown": []}

    return {
        "complication": complication,
        "total": total,
        "breakdown": [
            {
                "outcome": r["outcome"],
                "count": r["cnt"],
                "pct": round(r["cnt"] / total * 100, 1),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# POST /api/cases/{id}/outcome — update outcome after resolution
# ---------------------------------------------------------------------------

@router.post("/{case_id}/outcome")
async def update_outcome(
    case_id: str,
    payload: OutcomeUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    Called when a clinician updates the outcome after seeing how the case resolved.
    This is how the dataset improves over time.
    """
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
