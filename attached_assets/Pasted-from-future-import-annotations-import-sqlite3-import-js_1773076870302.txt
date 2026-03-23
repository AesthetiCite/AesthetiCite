from __future__ import annotations

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = "clinical_utility.db"

app = FastAPI(title="AesthetiCite Clinical Utility Tracker", version="1.0.0")


# ============================================================
# DATABASE
# ============================================================

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clinicians (
        clinician_id TEXT PRIMARY KEY,
        name TEXT,
        specialty TEXT,
        clinic_name TEXT,
        country TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS query_sessions (
        session_id TEXT PRIMARY KEY,
        clinician_id TEXT NOT NULL,
        question TEXT NOT NULL,
        language TEXT,
        answer_text TEXT,
        response_seconds REAL,
        source_count INTEGER,
        citation_count INTEGER,
        safety_present INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (clinician_id) REFERENCES clinicians(clinician_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clinician_feedback (
        feedback_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        clinician_id TEXT NOT NULL,
        useful INTEGER NOT NULL,
        faster_than_search INTEGER NOT NULL,
        trusted_citations INTEGER NOT NULL,
        would_use_in_practice INTEGER NOT NULL,
        accuracy_score INTEGER NOT NULL,
        free_text TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES query_sessions(session_id),
        FOREIGN KEY (clinician_id) REFERENCES clinicians(clinician_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS feature_events (
        event_id TEXT PRIMARY KEY,
        session_id TEXT,
        clinician_id TEXT,
        event_type TEXT NOT NULL,
        payload_json TEXT,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


# ============================================================
# HELPERS
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bool_to_int(value: bool) -> int:
    return 1 if value else 0


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def avg_or_none(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 1)


# ============================================================
# MODELS
# ============================================================

class ClinicianCreate(BaseModel):
    name: str
    specialty: Optional[str] = None
    clinic_name: Optional[str] = None
    country: Optional[str] = None


class QuerySessionCreate(BaseModel):
    clinician_id: str
    question: str
    language: Optional[str] = "en"
    answer_text: Optional[str] = None
    response_seconds: Optional[float] = None
    source_count: Optional[int] = 0
    citation_count: Optional[int] = 0
    safety_present: Optional[bool] = False


class FeedbackCreate(BaseModel):
    session_id: str
    clinician_id: str
    useful: bool
    faster_than_search: bool
    trusted_citations: bool
    would_use_in_practice: bool
    accuracy_score: int = Field(ge=1, le=5)
    free_text: Optional[str] = None


class FeatureEventCreate(BaseModel):
    clinician_id: Optional[str] = None
    session_id: Optional[str] = None
    event_type: str
    payload: Optional[Dict[str, Any]] = None


# ============================================================
# CLINICIAN ENDPOINTS
# ============================================================

@app.post("/clinicians")
def create_clinician(payload: ClinicianCreate) -> Dict[str, Any]:
    clinician_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO clinicians (
        clinician_id, name, specialty, clinic_name, country, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        clinician_id,
        payload.name,
        payload.specialty,
        payload.clinic_name,
        payload.country,
        now_iso(),
    ))

    conn.commit()
    conn.close()

    return {
        "clinician_id": clinician_id,
        "message": "Clinician created successfully."
    }


@app.get("/clinicians")
def list_clinicians() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clinicians ORDER BY created_at DESC")
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(rows), "items": rows}


# ============================================================
# QUERY SESSION ENDPOINTS
# ============================================================

@app.post("/sessions")
def create_session(payload: QuerySessionCreate) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT clinician_id FROM clinicians WHERE clinician_id = ?", (payload.clinician_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Clinician not found.")

    session_id = str(uuid.uuid4())

    cur.execute("""
    INSERT INTO query_sessions (
        session_id, clinician_id, question, language, answer_text,
        response_seconds, source_count, citation_count, safety_present, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        payload.clinician_id,
        payload.question,
        payload.language,
        payload.answer_text,
        payload.response_seconds,
        payload.source_count,
        payload.citation_count,
        bool_to_int(bool(payload.safety_present)),
        now_iso(),
    ))

    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "message": "Session logged successfully."
    }


@app.get("/sessions")
def list_sessions(clinician_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    if clinician_id:
        cur.execute("""
        SELECT * FROM query_sessions
        WHERE clinician_id = ?
        ORDER BY created_at DESC
        """, (clinician_id,))
    else:
        cur.execute("""
        SELECT * FROM query_sessions
        ORDER BY created_at DESC
        """)

    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(rows), "items": rows}


# ============================================================
# FEEDBACK ENDPOINTS
# ============================================================

@app.post("/feedback")
def create_feedback(payload: FeedbackCreate) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT session_id FROM query_sessions WHERE session_id = ?", (payload.session_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    cur.execute("SELECT clinician_id FROM clinicians WHERE clinician_id = ?", (payload.clinician_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Clinician not found.")

    feedback_id = str(uuid.uuid4())

    cur.execute("""
    INSERT INTO clinician_feedback (
        feedback_id, session_id, clinician_id,
        useful, faster_than_search, trusted_citations, would_use_in_practice,
        accuracy_score, free_text, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        feedback_id,
        payload.session_id,
        payload.clinician_id,
        bool_to_int(payload.useful),
        bool_to_int(payload.faster_than_search),
        bool_to_int(payload.trusted_citations),
        bool_to_int(payload.would_use_in_practice),
        payload.accuracy_score,
        payload.free_text,
        now_iso(),
    ))

    conn.commit()
    conn.close()

    return {
        "feedback_id": feedback_id,
        "message": "Feedback recorded successfully."
    }


@app.get("/feedback")
def list_feedback(clinician_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    if clinician_id:
        cur.execute("""
        SELECT * FROM clinician_feedback
        WHERE clinician_id = ?
        ORDER BY created_at DESC
        """, (clinician_id,))
    else:
        cur.execute("""
        SELECT * FROM clinician_feedback
        ORDER BY created_at DESC
        """)

    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"count": len(rows), "items": rows}


# ============================================================
# FEATURE EVENTS
# ============================================================

@app.post("/events")
def create_event(payload: FeatureEventCreate) -> Dict[str, Any]:
    event_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO feature_events (
        event_id, session_id, clinician_id, event_type, payload_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        event_id,
        payload.session_id,
        payload.clinician_id,
        payload.event_type,
        json.dumps(payload.payload or {}, ensure_ascii=False),
        now_iso(),
    ))

    conn.commit()
    conn.close()

    return {"event_id": event_id, "message": "Event logged successfully."}


# ============================================================
# CORE INVESTOR / CLINIC METRICS
# ============================================================

@app.get("/metrics/pilot")
def pilot_metrics() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM clinicians")
    clinician_count = int(cur.fetchone()["n"])

    cur.execute("SELECT COUNT(*) AS n FROM query_sessions")
    session_count = int(cur.fetchone()["n"])

    cur.execute("SELECT COUNT(*) AS n FROM clinician_feedback")
    feedback_count = int(cur.fetchone()["n"])

    cur.execute("""
    SELECT
        SUM(useful) AS useful_yes,
        SUM(faster_than_search) AS faster_yes,
        SUM(trusted_citations) AS trusted_yes,
        SUM(would_use_in_practice) AS adoption_yes,
        AVG(accuracy_score) AS avg_accuracy
    FROM clinician_feedback
    """)
    agg = cur.fetchone()

    useful_yes = int(agg["useful_yes"] or 0)
    faster_yes = int(agg["faster_yes"] or 0)
    trusted_yes = int(agg["trusted_yes"] or 0)
    adoption_yes = int(agg["adoption_yes"] or 0)
    avg_accuracy = round(float(agg["avg_accuracy"] or 0.0), 2)

    cur.execute("""
    SELECT response_seconds
    FROM query_sessions
    WHERE response_seconds IS NOT NULL
    """)
    response_times = [float(r["response_seconds"]) for r in cur.fetchall()]
    avg_response_seconds = avg_or_none(response_times)

    cur.execute("""
    SELECT source_count
    FROM query_sessions
    WHERE source_count IS NOT NULL
    """)
    source_counts = [int(r["source_count"]) for r in cur.fetchall()]
    avg_source_count = avg_or_none(source_counts)

    cur.execute("""
    SELECT citation_count
    FROM query_sessions
    WHERE citation_count IS NOT NULL
    """)
    citation_counts = [int(r["citation_count"]) for r in cur.fetchall()]
    avg_citation_count = avg_or_none(citation_counts)

    cur.execute("""
    SELECT COUNT(*) AS n
    FROM query_sessions
    WHERE safety_present = 1
    """)
    safety_yes = int(cur.fetchone()["n"])
    safety_rate = pct(safety_yes, session_count)

    conn.close()

    return {
        "pilot_size": {
            "clinicians": clinician_count,
            "sessions": session_count,
            "feedback_entries": feedback_count,
        },
        "clinical_utility": {
            "usefulness_rate_pct": pct(useful_yes, feedback_count),
            "faster_than_search_rate_pct": pct(faster_yes, feedback_count),
            "trusted_citations_rate_pct": pct(trusted_yes, feedback_count),
            "adoption_rate_pct": pct(adoption_yes, feedback_count),
            "average_accuracy_score_5pt": avg_accuracy,
        },
        "system_performance": {
            "average_response_seconds": avg_response_seconds,
            "average_sources_per_answer": avg_source_count,
            "average_citations_per_answer": avg_citation_count,
            "safety_present_rate_pct": safety_rate,
        },
        "investor_readiness_signal": compute_investor_signal(
            usefulness_pct=pct(useful_yes, feedback_count),
            faster_pct=pct(faster_yes, feedback_count),
            trust_pct=pct(trusted_yes, feedback_count),
            adoption_pct=pct(adoption_yes, feedback_count),
            avg_accuracy=avg_accuracy,
        )
    }


def compute_investor_signal(
    usefulness_pct: float,
    faster_pct: float,
    trust_pct: float,
    adoption_pct: float,
    avg_accuracy: float,
) -> Dict[str, Any]:
    score = 0

    if usefulness_pct >= 80:
        score += 1
    if faster_pct >= 80:
        score += 1
    if trust_pct >= 85:
        score += 1
    if adoption_pct >= 70:
        score += 1
    if avg_accuracy >= 4.2:
        score += 1

    if score == 5:
        status = "Excellent pilot signal"
    elif score >= 4:
        status = "Strong pilot signal"
    elif score >= 3:
        status = "Promising but needs refinement"
    else:
        status = "Not yet investment-ready"

    return {
        "score_out_of_5": score,
        "status": status,
        "thresholds": {
            "usefulness_target_pct": 80,
            "faster_than_search_target_pct": 80,
            "trusted_citations_target_pct": 85,
            "adoption_target_pct": 70,
            "avg_accuracy_target_5pt": 4.2,
        }
    }


# ============================================================
# CLINICIAN RETENTION / REPEAT USAGE
# ============================================================

@app.get("/metrics/retention")
def retention_metrics() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT clinician_id, COUNT(*) AS session_count
    FROM query_sessions
    GROUP BY clinician_id
    """)
    rows = cur.fetchall()

    total_clinicians = len(rows)
    repeated_users = sum(1 for r in rows if int(r["session_count"]) >= 2)
    power_users = sum(1 for r in rows if int(r["session_count"]) >= 5)

    conn.close()

    return {
        "total_active_clinicians": total_clinicians,
        "repeat_usage_rate_pct": pct(repeated_users, total_clinicians),
        "power_user_rate_pct": pct(power_users, total_clinicians),
    }


# ============================================================
# CLINIC-READY SUMMARY
# ============================================================

@app.get("/summary/executive")
def executive_summary() -> Dict[str, Any]:
    pilot = pilot_metrics()
    retention = retention_metrics()

    utility = pilot["clinical_utility"]
    perf = pilot["system_performance"]
    signal = pilot["investor_readiness_signal"]

    summary_lines = [
        f"Usefulness: {utility['usefulness_rate_pct']}%",
        f"Faster than search: {utility['faster_than_search_rate_pct']}%",
        f"Trusted citations: {utility['trusted_citations_rate_pct']}%",
        f"Would use in practice: {utility['adoption_rate_pct']}%",
        f"Average clinician-rated accuracy: {utility['average_accuracy_score_5pt']} / 5",
        f"Average response time: {perf['average_response_seconds']} seconds",
        f"Average sources per answer: {perf['average_sources_per_answer']}",
        f"Average citations per answer: {perf['average_citations_per_answer']}",
        f"Safety section present: {perf['safety_present_rate_pct']}%",
        f"Repeat usage rate: {retention['repeat_usage_rate_pct']}%",
        f"Pilot signal: {signal['status']}",
    ]

    return {
        "headline": signal["status"],
        "summary": " | ".join(summary_lines),
        "details": {
            "pilot": pilot,
            "retention": retention,
        }
    }


# ============================================================
# OPTIONAL DEMO SEED
# ============================================================

@app.post("/demo/seed")
def seed_demo_data() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()

    clinician_id = str(uuid.uuid4())
    cur.execute("""
    INSERT INTO clinicians (clinician_id, name, specialty, clinic_name, country, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        clinician_id,
        "Demo Aesthetic Physician",
        "Aesthetic Medicine",
        "Demo Clinic",
        "Morocco",
        now_iso(),
    ))

    for i in range(1, 6):
        session_id = str(uuid.uuid4())
        cur.execute("""
        INSERT INTO query_sessions (
            session_id, clinician_id, question, language, answer_text,
            response_seconds, source_count, citation_count, safety_present, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            clinician_id,
            f"Demo question {i}",
            "en",
            f"Demo answer {i}",
            4.2 + (i * 0.2),
            24 + i,
            5,
            1,
            now_iso(),
        ))

        cur.execute("""
        INSERT INTO clinician_feedback (
            feedback_id, session_id, clinician_id,
            useful, faster_than_search, trusted_citations, would_use_in_practice,
            accuracy_score, free_text, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            session_id,
            clinician_id,
            1,
            1,
            1,
            1 if i < 5 else 0,
            5 if i < 4 else 4,
            "Demo feedback",
            now_iso(),
        ))

    conn.commit()
    conn.close()

    return {"message": "Demo data inserted successfully."}