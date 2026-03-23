"""
AesthetiCite — Org Analytics & Session Intelligence
=====================================================
Pigment-inspired:   cross-clinic comparative analytics for org admins
Contentsquare-inspired: clinician session event tracking + answer heatmaps

Endpoints:
  POST /api/analytics/events              — track a clinician event
  GET  /api/analytics/session-heatmap     — which answer sections get used
  GET  /api/analytics/org-overview/{org}  — cross-clinic comparative view
  GET  /api/analytics/clinic-benchmark    — how does this clinic compare to org avg
  GET  /api/analytics/answer-quality      — which answers get copied/printed/saved
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/analytics", tags=["Org Analytics"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _require_org_member(db: Session, user_id: str, org_id: str) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT role FROM memberships
            WHERE user_id = :uid AND org_id = :oid AND is_active = TRUE
            LIMIT 1
        """),
        {"uid": user_id, "oid": org_id},
    ).fetchone()
    if not row:
        raise HTTPException(403, "Not a member of this organisation.")
    return dict(row)


def _require_org_admin(db: Session, user_id: str, org_id: str) -> None:
    row = db.execute(
        text("""
            SELECT role FROM memberships
            WHERE user_id = :uid AND org_id = :oid AND is_active = TRUE
              AND role IN ('super_admin', 'org_admin')
            LIMIT 1
        """),
        {"uid": user_id, "oid": org_id},
    ).fetchone()
    if not row:
        raise HTTPException(403, "Org admin required.")


def _require_clinic_member(db: Session, user_id: str, clinic_id: str) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ClinicianEvent(BaseModel):
    clinic_id: Optional[str] = None
    org_id: Optional[str] = None
    session_id: Optional[str] = None
    event_type: str
    target_element: Optional[str] = None
    answer_section: Optional[str] = None
    query_id: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Contentsquare-inspired: event tracking
# ---------------------------------------------------------------------------


@router.post("/events")
def track_event(
    payload: ClinicianEvent,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    db.execute(
        text("""
            INSERT INTO clinician_events
                (org_id, clinic_id, user_id, session_id, event_type,
                 target_element, answer_section, query_id, duration_ms, metadata)
            VALUES
                (:org_id, :clinic_id, :user_id, :session_id, :event_type,
                 :target, :section, :query_id, :dur, :meta)
        """),
        {
            "org_id": payload.org_id,
            "clinic_id": payload.clinic_id,
            "user_id": current_user["id"],
            "session_id": payload.session_id,
            "event_type": payload.event_type,
            "target": payload.target_element,
            "section": payload.answer_section,
            "query_id": payload.query_id,
            "dur": payload.duration_ms,
            "meta": json.dumps(payload.metadata),
        },
    )
    db.commit()
    return {"status": "recorded"}


@router.get("/session-heatmap")
def session_heatmap(
    clinic_id: str = Query(...),
    period_days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Which answer sections do clinicians interact with most?
    Track: view, copy, print, scroll_past, expand, save
    """
    _require_clinic_member(db, current_user["id"], clinic_id)

    sections = db.execute(
        text(f"""
            SELECT answer_section, event_type, COUNT(*) as cnt
            FROM clinician_events
            WHERE clinic_id = :cid
              AND answer_section IS NOT NULL
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY answer_section, event_type
            ORDER BY cnt DESC
        """),
        {"cid": clinic_id},
    ).fetchall()

    # Build heatmap matrix: section → {event_type: count}
    heatmap: Dict[str, Dict[str, int]] = {}
    for r in sections:
        sec = r["answer_section"]
        ev = r["event_type"]
        if sec not in heatmap:
            heatmap[sec] = {}
        heatmap[sec][ev] = r["cnt"]

    # Most copied/printed sections = highest value to clinicians
    value_score = {
        sec: (
            events.get("copy", 0) * 3
            + events.get("print", 0) * 3
            + events.get("save", 0) * 2
            + events.get("expand", 0)
        )
        for sec, events in heatmap.items()
    }

    ranked = sorted(value_score.items(), key=lambda x: x[1], reverse=True)

    top_event = db.execute(
        text(f"""
            SELECT event_type, COUNT(*) as cnt
            FROM clinician_events
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        """),
        {"cid": clinic_id},
    ).fetchall()

    return {
        "period_days": period_days,
        "section_heatmap": heatmap,
        "highest_value_sections": [{"section": s, "value_score": v} for s, v in ranked[:10]],
        "top_events": [dict(r) for r in top_event],
    }


@router.get("/answer-quality")
def answer_quality(
    clinic_id: str = Query(...),
    period_days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Track which query types generate the most copied / saved answers."""
    _require_clinic_member(db, current_user["id"], clinic_id)

    by_query = db.execute(
        text(f"""
            SELECT query_id, event_type, COUNT(*) as cnt
            FROM clinician_events
            WHERE clinic_id = :cid
              AND query_id IS NOT NULL
              AND event_type IN ('copy','save','print','bookmark')
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY query_id, event_type
            ORDER BY cnt DESC
            LIMIT 50
        """),
        {"cid": clinic_id},
    ).fetchall()

    return {
        "period_days": period_days,
        "high_value_queries": [dict(r) for r in by_query],
    }


# ---------------------------------------------------------------------------
# Pigment-inspired: org-level comparative analytics
# ---------------------------------------------------------------------------


@router.get("/org-overview/{org_id}")
def org_overview(
    org_id: str,
    period_days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Cross-clinic view for org admins:
    - Which clinic has most case logs?
    - Which has highest risk alerts?
    - Evidence of network-level complication patterns
    """
    _require_org_admin(db, current_user["id"], org_id)

    clinics = db.execute(
        text("SELECT id, name, location FROM clinics WHERE org_id = :oid AND is_active = TRUE"),
        {"oid": org_id},
    ).fetchall()

    clinic_ids = [str(c["id"]) for c in clinics]
    if not clinic_ids:
        return {"org_id": org_id, "clinics": [], "network_summary": {}}

    id_list = ", ".join(f"'{cid}'" for cid in clinic_ids)

    # Case logs per clinic
    case_counts = db.execute(
        text(f"""
            SELECT clinic_id, COUNT(*) as case_count
            FROM case_logs
            WHERE clinic_id IN ({id_list})
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY clinic_id
        """),
    ).fetchall()
    cases_by_clinic = {str(r["clinic_id"]): r["case_count"] for r in case_counts}

    # Alert counts per clinic
    alert_counts = db.execute(
        text(f"""
            SELECT clinic_id, COUNT(*) as alert_count,
                   SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical_count
            FROM complication_alerts
            WHERE clinic_id IN ({id_list})
              AND is_dismissed = FALSE
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY clinic_id
        """),
    ).fetchall()
    alerts_by_clinic = {
        str(r["clinic_id"]): {
            "total": r["alert_count"],
            "critical": r["critical_count"],
        }
        for r in alert_counts
    }

    # Protocol saves per clinic
    protocol_counts = db.execute(
        text(f"""
            SELECT clinic_id, COUNT(*) as protocol_count
            FROM saved_protocols
            WHERE clinic_id IN ({id_list})
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY clinic_id
        """),
    ).fetchall()
    protocols_by_clinic = {str(r["clinic_id"]): r["protocol_count"] for r in protocol_counts}

    # Top complications across the network
    network_complications = db.execute(
        text(f"""
            SELECT complication_type, COUNT(*) as cnt
            FROM case_logs
            WHERE clinic_id IN ({id_list})
              AND complication_type IS NOT NULL
              AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY complication_type
            ORDER BY cnt DESC LIMIT 10
        """),
    ).fetchall()

    # Build per-clinic summary
    clinic_summaries = []
    for c in clinics:
        cid = str(c["id"])
        cases = cases_by_clinic.get(cid, 0)
        alerts = alerts_by_clinic.get(cid, {"total": 0, "critical": 0})
        protocols = protocols_by_clinic.get(cid, 0)
        # Simple risk index: (critical_alerts * 5 + alerts * 2) / max(cases,1)
        risk_index = round(
            (alerts["critical"] * 5 + alerts["total"] * 2) / max(cases, 1), 2
        )
        clinic_summaries.append({
            "clinic_id": cid,
            "clinic_name": c["name"],
            "location": c["location"],
            "case_logs": cases,
            "active_alerts": alerts["total"],
            "critical_alerts": alerts["critical"],
            "saved_protocols": protocols,
            "risk_index": risk_index,
        })

    # Sort by risk_index descending
    clinic_summaries.sort(key=lambda x: x["risk_index"], reverse=True)

    total_cases = sum(s["case_logs"] for s in clinic_summaries)
    total_alerts = sum(s["active_alerts"] for s in clinic_summaries)

    return {
        "org_id": org_id,
        "period_days": period_days,
        "clinic_count": len(clinic_summaries),
        "network_summary": {
            "total_case_logs": total_cases,
            "total_active_alerts": total_alerts,
            "avg_case_logs_per_clinic": round(total_cases / max(len(clinic_summaries), 1), 1),
            "top_complications": [dict(r) for r in network_complications],
        },
        "clinics": clinic_summaries,
    }


@router.get("/clinic-benchmark")
def clinic_benchmark(
    clinic_id: str = Query(...),
    period_days: int = Query(30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    How does this clinic compare to the org network average?
    Returns percentile ranks for key metrics.
    """
    mem = _require_clinic_member(db, current_user["id"], clinic_id)
    org_id = str(mem["org_id"])

    # This clinic stats
    clinic_cases = db.execute(
        text(f"""
            SELECT COUNT(*) as n,
                   SUM(CASE WHEN complication_type ILIKE '%vascular%' OR complication_type ILIKE '%occlusion%' THEN 1 ELSE 0 END) as vascular,
                   SUM(CASE WHEN outcome ILIKE '%resolved%' THEN 1 ELSE 0 END) as resolved
            FROM case_logs
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{period_days} days'
        """),
        {"cid": clinic_id},
    ).fetchone()

    # All clinics in org
    all_clinics = db.execute(
        text(f"""
            SELECT clinic_id,
                   COUNT(*) as n,
                   SUM(CASE WHEN outcome ILIKE '%resolved%' THEN 1 ELSE 0 END) as resolved
            FROM case_logs
            WHERE clinic_id IN (
                SELECT id FROM clinics WHERE org_id = :oid AND is_active = TRUE
            )
            AND created_at >= now() - INTERVAL '{period_days} days'
            GROUP BY clinic_id
        """),
        {"oid": org_id},
    ).fetchall()

    if not all_clinics:
        return {"clinic_id": clinic_id, "benchmark": "insufficient_data"}

    all_counts = sorted([r["n"] for r in all_clinics])
    this_count = clinic_cases["n"] if clinic_cases else 0

    # Percentile rank: what % of clinics have fewer cases than this one
    below = sum(1 for c in all_counts if c < this_count)
    percentile = round(below / len(all_counts) * 100, 0) if all_counts else 0

    resolution_rates = []
    for r in all_clinics:
        if r["n"] > 0:
            resolution_rates.append(r["resolved"] / r["n"])

    this_resolution = (
        clinic_cases["resolved"] / clinic_cases["n"]
        if clinic_cases and clinic_cases["n"] > 0
        else 0
    )
    avg_resolution = (
        sum(resolution_rates) / len(resolution_rates) if resolution_rates else 0
    )

    return {
        "clinic_id": clinic_id,
        "period_days": period_days,
        "this_clinic": {
            "case_logs": this_count,
            "vascular_cases": clinic_cases["vascular"] if clinic_cases else 0,
            "resolution_rate": round(this_resolution * 100, 1),
        },
        "network_average": {
            "case_logs": round(sum(all_counts) / len(all_counts), 1),
            "resolution_rate": round(avg_resolution * 100, 1),
        },
        "percentiles": {
            "case_volume_percentile": percentile,
            "above_average_resolution": this_resolution > avg_resolution,
        },
        "clinic_count_in_network": len(all_clinics),
    }
