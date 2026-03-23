"""
AesthetiCite — Risk Intelligence Engine  (Shift Technology-inspired)
=====================================================================
Features:
  1. Practitioner risk scoring — per-practitioner complication analysis
  2. Pattern detection — cross-case clustering triggers auto alerts
  3. Alert management — view, dismiss, escalate

Endpoints:
  POST /api/risk/scores/compute         — compute scores for a clinic
  GET  /api/risk/scores                 — list scores for clinic
  GET  /api/risk/scores/{practitioner}  — single practitioner detail
  GET  /api/risk/alerts                 — list unresolved alerts
  POST /api/risk/alerts/{id}/dismiss    — dismiss alert
  POST /api/risk/detect-patterns        — run pattern detection now
  GET  /api/risk/heatmap                — complication heatmap (procedure × region)
"""
from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/risk", tags=["Risk Intelligence"])

# ---------------------------------------------------------------------------
# Risk weight table
# ---------------------------------------------------------------------------

COMPLICATION_WEIGHTS: Dict[str, float] = {
    "vascular occlusion":               10.0,
    "vision change":                     10.0,
    "visual disturbance":               10.0,
    "skin necrosis":                     9.0,
    "necrosis":                          9.0,
    "anaphylaxis":                       9.0,
    "infection":                         6.0,
    "biofilm":                           6.0,
    "delayed inflammatory reaction":     5.0,
    "dir":                               5.0,
    "ptosis":                            4.0,
    "inflammatory nodule":               4.0,
    "granuloma":                         4.0,
    "filler migration":                  3.0,
    "tyndall effect":                    2.0,
    "asymmetry":                         1.5,
    "bruising":                          1.0,
    "oedema":                            1.0,
    "swelling":                          1.0,
}

OUTCOME_WEIGHTS: Dict[str, float] = {
    "urgent referral":      3.0,
    "ongoing":              2.0,
    "partial resolution":   1.5,
    "lost to follow-up":    1.5,
    "resolved":             0.0,
}

HIGH_RISK_KEYWORDS = [
    "vascular", "occlusion", "visual", "vision", "necrosis", "blanching",
    "livedo", "ischaemia", "ischemia",
]


def _weight_for_complication(comp: str) -> float:
    c = (comp or "").lower()
    for key, weight in COMPLICATION_WEIGHTS.items():
        if key in c:
            return weight
    return 1.0


def _weight_for_outcome(outcome: str) -> float:
    o = (outcome or "").lower()
    for key, weight in OUTCOME_WEIGHTS.items():
        if key in o:
            return weight
    return 0.5


def _is_high_risk(comp: str, symptoms: str) -> bool:
    text_lower = f"{comp or ''} {symptoms or ''}".lower()
    return any(kw in text_lower for kw in HIGH_RISK_KEYWORDS)


def _risk_level(score: float) -> str:
    if score >= 30:
        return "critical"
    if score >= 15:
        return "high"
    if score >= 6:
        return "elevated"
    return "normal"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ComputeScoresRequest(BaseModel):
    clinic_id: str
    period_days: int = 90


class AlertDismissRequest(BaseModel):
    clinic_id: str


class PatternDetectRequest(BaseModel):
    clinic_id: str
    window_days: int = 30
    threshold: int = 2


# ---------------------------------------------------------------------------
# Core scoring logic
# ---------------------------------------------------------------------------


def _compute_scores_for_clinic(
    db: Session, clinic_id: str, period_days: int
) -> List[Dict[str, Any]]:
    period_start = (datetime.now(timezone.utc) - timedelta(days=period_days)).date()
    period_end = datetime.now(timezone.utc).date()

    rows = db.execute(
        text(f"""
            SELECT practitioner_name, complication_type, outcome, symptoms, org_id
            FROM case_logs
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{period_days} days'
              AND practitioner_name IS NOT NULL
            ORDER BY practitioner_name
        """),
        {"cid": clinic_id},
    ).fetchall()

    if not rows:
        return []

    org_id = str(rows[0]["org_id"]) if rows else None

    # Group by practitioner
    by_prac: Dict[str, list] = defaultdict(list)
    for r in rows:
        by_prac[r["practitioner_name"]].append(dict(r))

    results = []
    for prac, cases in by_prac.items():
        total = len(cases)
        raw_score = 0.0
        high_risk_count = 0
        vascular_count = 0
        necrosis_count = 0
        visual_count = 0
        unresolved_count = 0
        comp_counter: Counter = Counter()

        for c in cases:
            comp = c.get("complication_type") or ""
            outcome = c.get("outcome") or ""
            symptoms = c.get("symptoms") or ""

            comp_weight = _weight_for_complication(comp)
            outcome_weight = _weight_for_outcome(outcome)
            raw_score += comp_weight + outcome_weight

            if _is_high_risk(comp, symptoms):
                high_risk_count += 1

            comp_lower = comp.lower()
            if "vascular" in comp_lower or "occlusion" in comp_lower:
                vascular_count += 1
            if "necrosis" in comp_lower:
                necrosis_count += 1
            if "visual" in comp_lower or "vision" in comp_lower:
                visual_count += 1
            if outcome.lower() in ("ongoing", "urgent referral", "lost to follow-up", "partial resolution"):
                unresolved_count += 1

            if comp:
                comp_counter[comp] += 1

        # Normalize score per 10 cases to allow fair comparison
        normalised = round((raw_score / max(total, 1)) * 10, 2)
        level = _risk_level(raw_score)
        top_comps = [{"type": t, "count": n} for t, n in comp_counter.most_common(5)]

        # Upsert score
        score_id = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO practitioner_risk_scores (
                    id, org_id, clinic_id, practitioner_name,
                    period_start, period_end, total_cases, high_risk_cases,
                    vascular_cases, necrosis_cases, visual_cases, unresolved_cases,
                    risk_score, risk_level, top_complications
                ) VALUES (
                    :id, :org_id, :clinic_id, :prac,
                    :ps, :pe, :total, :high_risk,
                    :vascular, :necrosis, :visual, :unresolved,
                    :score, :level, :top_comps
                )
                ON CONFLICT (clinic_id, practitioner_name, period_start, period_end)
                DO UPDATE SET
                    total_cases = EXCLUDED.total_cases,
                    high_risk_cases = EXCLUDED.high_risk_cases,
                    vascular_cases = EXCLUDED.vascular_cases,
                    necrosis_cases = EXCLUDED.necrosis_cases,
                    visual_cases = EXCLUDED.visual_cases,
                    unresolved_cases = EXCLUDED.unresolved_cases,
                    risk_score = EXCLUDED.risk_score,
                    risk_level = EXCLUDED.risk_level,
                    top_complications = EXCLUDED.top_complications,
                    generated_at = now()
            """),
            {
                "id": score_id,
                "org_id": org_id,
                "clinic_id": clinic_id,
                "prac": prac,
                "ps": period_start.isoformat(),
                "pe": period_end.isoformat(),
                "total": total,
                "high_risk": high_risk_count,
                "vascular": vascular_count,
                "necrosis": necrosis_count,
                "visual": visual_count,
                "unresolved": unresolved_count,
                "score": normalised,
                "level": level,
                "top_comps": json.dumps(top_comps),
            },
        )

        results.append({
            "practitioner_name": prac,
            "total_cases": total,
            "high_risk_cases": high_risk_count,
            "vascular_cases": vascular_count,
            "necrosis_cases": necrosis_count,
            "visual_cases": visual_count,
            "unresolved_cases": unresolved_count,
            "risk_score": normalised,
            "risk_level": level,
            "top_complications": top_comps,
        })

    db.commit()
    return sorted(results, key=lambda x: x["risk_score"], reverse=True)


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

PATTERN_RULES = [
    {
        "id": "vascular_cluster",
        "name": "Vascular Occlusion Cluster",
        "keywords": ["vascular", "occlusion", "blanching", "livedo"],
        "threshold": 2,
        "severity": "critical",
        "window_days": 30,
    },
    {
        "id": "repeated_product_comp",
        "name": "Repeated Complication — Same Product",
        "keywords": [],
        "threshold": 3,
        "severity": "warning",
        "window_days": 30,
        "group_by": "product_used",
    },
    {
        "id": "unresolved_spike",
        "name": "Unresolved Cases Spike",
        "keywords": ["ongoing", "urgent referral"],
        "threshold": 3,
        "severity": "warning",
        "window_days": 14,
    },
    {
        "id": "necrosis_any",
        "name": "Necrosis / Ischaemia Event",
        "keywords": ["necrosis", "ischaemia", "ischemia"],
        "threshold": 1,
        "severity": "critical",
        "window_days": 30,
    },
    {
        "id": "visual_event",
        "name": "Visual Symptom Reported",
        "keywords": ["visual", "vision", "blindness", "diplopia"],
        "threshold": 1,
        "severity": "critical",
        "window_days": 30,
    },
]


def _run_pattern_detection(
    db: Session, clinic_id: str, org_id: str, window_days: int
) -> List[Dict[str, Any]]:
    triggered = []

    for rule in PATTERN_RULES:
        days = rule.get("window_days", window_days)
        threshold = rule["threshold"]
        keywords = rule.get("keywords", [])
        group_by = rule.get("group_by")

        if keywords:
            kw_conditions = " OR ".join(
                f"LOWER(complication_type) LIKE '%{kw}%' OR LOWER(symptoms) LIKE '%{kw}%' OR LOWER(outcome) LIKE '%{kw}%'"
                for kw in keywords
            )
            rows = db.execute(
                text(f"""
                    SELECT complication_type, product_used, outcome, count(*) as cnt
                    FROM case_logs
                    WHERE clinic_id = :cid
                      AND created_at >= now() - INTERVAL '{days} days'
                      AND ({kw_conditions})
                    GROUP BY complication_type, product_used, outcome
                """),
                {"cid": clinic_id},
            ).fetchall()
            total = sum(r["cnt"] for r in rows)
        elif group_by:
            rows = db.execute(
                text(f"""
                    SELECT {group_by}, complication_type, count(*) as cnt
                    FROM case_logs
                    WHERE clinic_id = :cid
                      AND created_at >= now() - INTERVAL '{days} days'
                      AND {group_by} IS NOT NULL
                    GROUP BY {group_by}, complication_type
                    HAVING count(*) >= :threshold
                """),
                {"cid": clinic_id, "threshold": threshold},
            ).fetchall()
            total = len(rows)
        else:
            total = 0
            rows = []

        if total >= threshold:
            evidence = {
                "rule_id": rule["id"],
                "matched_cases": total,
                "threshold": threshold,
                "window_days": days,
                "details": [dict(r) for r in rows[:10]],
            }
            alert_id = str(uuid.uuid4())

            # Avoid duplicate open alerts for same rule + clinic
            existing = db.execute(
                text("""
                    SELECT id FROM complication_alerts
                    WHERE clinic_id = :cid
                      AND alert_type = :atype
                      AND is_dismissed = FALSE
                      AND created_at >= now() - INTERVAL '24 hours'
                """),
                {"cid": clinic_id, "atype": rule["id"]},
            ).fetchone()

            if not existing:
                db.execute(
                    text("""
                        INSERT INTO complication_alerts
                            (id, org_id, clinic_id, alert_type, severity, title, body, evidence_json)
                        VALUES (:id, :org_id, :cid, :atype, :sev, :title, :body, :ev)
                    """),
                    {
                        "id": alert_id,
                        "org_id": org_id,
                        "cid": clinic_id,
                        "atype": rule["id"],
                        "sev": rule["severity"],
                        "title": rule["name"],
                        "body": (
                            f"{total} case(s) matching '{rule['name']}' detected in the last {days} days. "
                            f"Threshold: {threshold}. Review case logs immediately."
                        ),
                        "ev": json.dumps(evidence),
                    },
                )
                triggered.append({"rule": rule["id"], "severity": rule["severity"], "matched": total})

    db.commit()
    return triggered


# ---------------------------------------------------------------------------
# Membership check (reuse from network_workspace)
# ---------------------------------------------------------------------------


def _require_member(db: Session, user_id: str, clinic_id: str, admin_only: bool = False) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT m.role, m.org_id, c.name as clinic_name, o.name as org_name
            FROM memberships m
            JOIN clinics c ON c.id = m.clinic_id
            JOIN organizations o ON o.id = m.org_id
            WHERE m.user_id = :uid AND m.clinic_id = :cid AND m.is_active = TRUE
        """),
        {"uid": user_id, "cid": clinic_id},
    ).fetchone()
    if not row:
        raise HTTPException(403, "Not a member of this clinic.")
    if admin_only and row["role"] not in ("super_admin", "org_admin", "clinic_admin"):
        raise HTTPException(403, "Admin role required.")
    return dict(row)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/scores/compute")
def compute_scores(
    payload: ComputeScoresRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    mem = _require_member(db, current_user["id"], payload.clinic_id, admin_only=True)
    scores = _compute_scores_for_clinic(db, payload.clinic_id, payload.period_days)

    # Auto-run pattern detection after computing scores
    triggered = _run_pattern_detection(db, payload.clinic_id, str(mem["org_id"]), payload.period_days)

    return {
        "clinic_id": payload.clinic_id,
        "period_days": payload.period_days,
        "practitioner_count": len(scores),
        "scores": scores,
        "alerts_triggered": triggered,
    }


@router.get("/scores")
def list_scores(
    clinic_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    _require_member(db, current_user["id"], clinic_id, admin_only=True)
    rows = db.execute(
        text("""
            SELECT * FROM practitioner_risk_scores
            WHERE clinic_id = :cid
            ORDER BY generated_at DESC, risk_score DESC
        """),
        {"cid": clinic_id},
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("top_complications"), str):
            d["top_complications"] = json.loads(d["top_complications"])
        result.append(d)
    return result


@router.get("/scores/{practitioner_name}")
def get_practitioner_score(
    practitioner_name: str,
    clinic_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_member(db, current_user["id"], clinic_id, admin_only=True)

    score_row = db.execute(
        text("""
            SELECT * FROM practitioner_risk_scores
            WHERE clinic_id = :cid AND practitioner_name = :prac
            ORDER BY generated_at DESC LIMIT 1
        """),
        {"cid": clinic_id, "prac": practitioner_name},
    ).fetchone()

    cases = db.execute(
        text("""
            SELECT complication_type, outcome, event_date, region, product_used, symptoms
            FROM case_logs
            WHERE clinic_id = :cid AND practitioner_name = :prac
            ORDER BY created_at DESC LIMIT 50
        """),
        {"cid": clinic_id, "prac": practitioner_name},
    ).fetchall()

    return {
        "practitioner_name": practitioner_name,
        "score": dict(score_row) if score_row else None,
        "recent_cases": [dict(c) for c in cases],
    }


@router.get("/alerts")
def list_alerts(
    clinic_id: str = Query(...),
    include_dismissed: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    _require_member(db, current_user["id"], clinic_id)
    rows = db.execute(
        text("""
            SELECT * FROM complication_alerts
            WHERE clinic_id = :cid
              AND (:inc_dismissed = TRUE OR is_dismissed = FALSE)
            ORDER BY severity DESC, created_at DESC
        """),
        {"cid": clinic_id, "inc_dismissed": include_dismissed},
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("evidence_json"), str):
            d["evidence_json"] = json.loads(d["evidence_json"])
        result.append(d)
    return result


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(
    alert_id: str,
    payload: AlertDismissRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_member(db, current_user["id"], payload.clinic_id, admin_only=True)
    db.execute(
        text("""
            UPDATE complication_alerts
            SET is_dismissed = TRUE, dismissed_by = :uid, dismissed_at = now()
            WHERE id = :id AND clinic_id = :cid
        """),
        {"id": alert_id, "uid": current_user["id"], "cid": payload.clinic_id},
    )
    db.commit()
    return {"status": "dismissed", "id": alert_id}


@router.post("/detect-patterns")
def detect_patterns(
    payload: PatternDetectRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    mem = _require_member(db, current_user["id"], payload.clinic_id, admin_only=True)
    triggered = _run_pattern_detection(
        db, payload.clinic_id, str(mem["org_id"]), payload.window_days
    )
    return {
        "clinic_id": payload.clinic_id,
        "window_days": payload.window_days,
        "patterns_triggered": len(triggered),
        "alerts": triggered,
    }


@router.get("/heatmap")
def complication_heatmap(
    clinic_id: str = Query(...),
    period_days: int = Query(90),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_member(db, current_user["id"], clinic_id, admin_only=True)

    rows = db.execute(
        text(f"""
            SELECT procedure, region, complication_type, count(*) as cnt
            FROM case_logs
            WHERE clinic_id = :cid
              AND created_at >= now() - INTERVAL '{period_days} days'
              AND procedure IS NOT NULL AND region IS NOT NULL
            GROUP BY procedure, region, complication_type
            ORDER BY cnt DESC
        """),
        {"cid": clinic_id},
    ).fetchall()

    # Build matrix: procedure → region → [complication counts]
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        matrix[r["procedure"]][r["region"]] += r["cnt"]

    return {
        "clinic_id": clinic_id,
        "period_days": period_days,
        "matrix": {proc: dict(regions) for proc, regions in matrix.items()},
        "raw": [dict(r) for r in rows],
    }
