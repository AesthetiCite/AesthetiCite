"""
Pilot Events Client
===================
Logs events to the pilot proof service for case timeline tracking.
"""

import os
import json
import time
from typing import Optional, Dict, Any

import httpx

PILOT_BASE_URL = os.getenv("PILOT_BASE_URL", "http://localhost:8000").rstrip("/")
PILOT_ENABLED = os.getenv("PILOT_ENABLED", "1") == "1"
PILOT_TIMEOUT = float(os.getenv("PILOT_TIMEOUT", "1.5"))


def _post(path: str, payload: Dict[str, Any]) -> None:
    """Post to pilot service. Never breaks clinical flows on failure."""
    if not PILOT_ENABLED:
        return
    url = f"{PILOT_BASE_URL}/pilot{path}"
    try:
        with httpx.Client(timeout=PILOT_TIMEOUT) as client:
            client.post(url, json=payload)
    except Exception:  # nosec B110
        pass


def log_event(
    case_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    event_ts: Optional[int] = None
) -> None:
    """
    Log an event to the pilot timeline.
    
    Event types:
    - symptom_onset
    - recognition
    - aestheticite_opened
    - emergency_mode_opened
    - escalation
    - treatment_started
    - follow_up_scheduled
    - case_closed
    """
    _post("/events", {
        "case_id": case_id,
        "event_type": event_type,
        "event_ts": event_ts or int(time.time()),
        "payload": payload or {}
    })


def draft_documentation(
    case_id: str,
    rubric_defaults: Dict[str, bool],
    mode: str = "aestheticite",
    product: Optional[str] = None,
    dose_or_volume: Optional[str] = None,
    technique: Optional[str] = None,
    aftercare: Optional[str] = None,
    follow_up: Optional[str] = None,
    complications: Optional[str] = None,
    escalation: Optional[str] = None
) -> None:
    """
    Create a documentation draft in the pilot DB.
    Clinician only needs to verify and confirm.
    """
    _post("/documentation", {
        "case_id": case_id,
        "mode": mode,
        "rubric": rubric_defaults,
        "product": product,
        "dose_or_volume": dose_or_volume,
        "technique": technique,
        "aftercare": aftercare,
        "follow_up": follow_up,
        "complications": complications,
        "escalation": escalation
    })
