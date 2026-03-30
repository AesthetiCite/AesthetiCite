"""
AesthetiCite — Protocol Selection Engine
app/services/protocol_engine.py

choose_protocol(): picks the right protocol ID based on procedure + symptoms.
compute_alerts():  generates structured alert list for the live-view UI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def choose_protocol(
    procedure_type: Optional[str],
    subtype: Optional[str],
    symptoms: List[Dict[str, Any]],
    visual_symptoms: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Returns a protocol_definitions.id string when a known complication pattern
    is matched, otherwise None.
    """
    symptom_names = {s.get("name") for s in symptoms if s.get("present")}

    if procedure_type in ("injectable_filler", "hyaluronic_acid_filler"):
        if {"pain", "blanching", "livedo"} & symptom_names:
            return "vascular-occlusion-v1"
        if visual_symptoms and visual_symptoms.get("present"):
            return "vascular-occlusion-v1"

    if {"urticaria", "angioedema", "hypotension", "bronchospasm"} & symptom_names:
        return "anaphylaxis-v1"

    return None


def compute_alerts(
    symptoms: List[Dict[str, Any]],
    visual_symptoms: Optional[Dict[str, Any]] = None,
    needs_immediate_action: bool = False,
    vision_emergency: bool = False,
    anaphylaxis_probability: Optional[float] = None,
    airway_risk: bool = False,
    red_flags: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Returns a list of alert dicts with keys: type, message.
    type values: 'critical' | 'high' | 'warning' | 'info'
    """
    alerts: List[Dict[str, str]] = []
    symptom_names = {s.get("name") for s in symptoms if s.get("present")}

    if needs_immediate_action:
        alerts.append({
            "type": "critical",
            "message": "Immediate clinical action is indicated.",
        })

    if vision_emergency:
        alerts.append({
            "type": "critical",
            "message": "Vision emergency suspected — ophthalmology referral required immediately.",
        })

    if visual_symptoms and visual_symptoms.get("present"):
        alerts.append({
            "type": "critical",
            "message": "Visual symptoms present. Escalate immediately as an ocular emergency.",
        })

    if anaphylaxis_probability is not None and float(anaphylaxis_probability) >= 0.7:
        pct = int(float(anaphylaxis_probability) * 100)
        alerts.append({
            "type": "critical",
            "message": f"Anaphylaxis probability: {pct}% — administer adrenaline.",
        })

    if airway_risk:
        alerts.append({
            "type": "critical",
            "message": "Airway risk flagged — monitor and prepare for escalation.",
        })

    if "blanching" in symptom_names or "livedo" in symptom_names:
        alerts.append({
            "type": "high",
            "message": "Signs compatible with ischaemia require urgent reassessment.",
        })

    for flag in (red_flags or []):
        alerts.append({"type": "warning", "message": flag})

    return alerts
