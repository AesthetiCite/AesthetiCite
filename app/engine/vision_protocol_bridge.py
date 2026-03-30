"""
AesthetiCite Vision Protocol Bridge
=====================================
Connects the Vision Engine (GPT-4o image analysis) to the Complication Protocol Engine.

When GPT-4o analyses a patient photo and returns a text description, this bridge:
  1. Scans that text for clinical complication signals
  2. Scores all known protocols against detected signals
  3. Returns any protocols that breach the confidence threshold

Pure deterministic text matching — adds ~0ms latency, no LLM call.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TRIGGER_THRESHOLD = 0.40
CRITICAL_THRESHOLD = 0.70
HIGH_THRESHOLD = 0.50

VISUAL_SIGNALS: List[Tuple[str, List[str], float]] = [
    ("blanching",           ["blanch", "white", "pale", "pallor", "pallid", "avascular"],        3.0),
    ("mottling",            ["mottl", "livedo", "reticulari", "blotch"],                         3.0),
    ("dusky",               ["dusky", "violaceous", "purple", "bluish skin", "cyanotic skin"],   2.5),
    ("erythema",            ["erythema", "redness", "red", "inflamed skin", "flushed"],          1.5),
    ("blue_gray_tyndall",   ["blue-gray", "bluish tint", "tyndall", "blue discolouration"],      2.5),
    ("angioedema",          ["angioedema", "tongue swelling", "facial swelling", "lip swelling", "urticaria"], 3.5),
    ("swelling",            ["swelling", "oedema", "edema", "puffiness", "distension"],          1.0),
    ("vision_change",       ["blurred vision", "diplopia", "double vision", "visual disturbance",
                             "ptosis", "eyelid droop", "brow drop", "brow heaviness"],           4.0),
    ("ptosis_lid",          ["ptosis", "drooping eyelid", "eyelid droop", "lid lag"],            3.0),
    ("nodule",              ["nodule", "lump", "bump", "granuloma", "firmness"],                 2.0),
    ("fluctuance",          ["fluctuant", "fluctuance", "fluid-filled", "abscess", "pus"],       2.5),
    ("infection_signs",     ["infection", "purulent", "drainage", "warmth", "fever", "cellulitis"], 2.5),
    ("necrosis",            ["necrosis", "necrotic", "tissue loss", "eschara", "eschar",
                             "dead tissue", "slough"],                                            4.0),
    ("systemic_allergic",   ["anaphylaxis", "anaphylactic", "wheeze", "stridor", "hypotension",
                             "generalised urticaria", "systemic reaction"],                      4.0),
    ("recent_injection",    ["post-injection", "after injection", "following injection",
                             "recently injected", "same day", "hours after"],                    1.0),
]

PROTOCOL_PROFILES: Dict[str, Dict[str, Any]] = {
    "vascular_occlusion": {
        "name": "Vascular Occlusion",
        "urgency_base": "critical",
        "driving_signals": {
            "blanching": 3.0, "mottling": 3.0, "dusky": 2.5,
            "necrosis": 4.0, "vision_change": 3.0, "recent_injection": 1.0,
        },
        "max_possible": 17.5,
        "headline": "Possible vascular compromise detected in image.",
        "immediate_action": (
            "Stop treatment immediately if ongoing. Initiate your clinic's vascular occlusion "
            "protocol. Assess perfusion, capillary refill, and skin colour. Escalate urgently "
            "for any ocular or neurological symptoms."
        ),
    },
    "anaphylaxis": {
        "name": "Anaphylaxis / Severe Allergic Reaction",
        "urgency_base": "critical",
        "driving_signals": {
            "angioedema": 3.5, "systemic_allergic": 4.0, "erythema": 0.5, "swelling": 0.5,
        },
        "max_possible": 8.5,
        "headline": "Signs consistent with severe allergic reaction or anaphylaxis.",
        "immediate_action": (
            "Assess airway, breathing, circulation. Call emergency services if airway compromise "
            "suspected. Administer adrenaline per local protocol. Lay flat, elevate legs."
        ),
    },
    "tyndall_effect": {
        "name": "Tyndall Effect",
        "urgency_base": "moderate",
        "driving_signals": {"blue_gray_tyndall": 2.5, "erythema": 0.3},
        "max_possible": 2.8,
        "headline": "Possible Tyndall effect (superficial HA filler) visible in image.",
        "immediate_action": (
            "Document onset and filler product. Consider hyaluronidase dissolution following "
            "your protocol. Do not inject additional product over affected area."
        ),
    },
    "ptosis": {
        "name": "Botulinum Toxin-Induced Ptosis",
        "urgency_base": "high",
        "driving_signals": {"ptosis_lid": 3.0, "vision_change": 2.0},
        "max_possible": 5.0,
        "headline": "Eyelid or brow ptosis pattern detected in image.",
        "immediate_action": (
            "Document asymmetry and time since toxin injection. Advise patient on expected "
            "timeline. Consider apraclonidine 0.5% eye drops if confirmed lid ptosis — discuss "
            "with ophthalmology. Reassure and monitor."
        ),
    },
    "infection_biofilm": {
        "name": "Infection / Biofilm",
        "urgency_base": "high",
        "driving_signals": {
            "infection_signs": 2.5, "fluctuance": 2.5, "nodule": 1.0, "erythema": 0.5,
        },
        "max_possible": 6.5,
        "headline": "Signs of possible infection or biofilm reaction in image.",
        "immediate_action": (
            "Do not inject into or near affected area. Culture if possible. Initiate appropriate "
            "antimicrobial therapy per local protocol. Consider hyaluronidase if HA filler "
            "related. Refer if not improving within 24–48 hours."
        ),
    },
    "filler_nodule": {
        "name": "Filler Nodule",
        "urgency_base": "moderate",
        "driving_signals": {"nodule": 2.0, "erythema": 0.3, "infection_signs": 0.5},
        "max_possible": 2.8,
        "headline": "Palpable or visible nodule pattern detected in image.",
        "immediate_action": (
            "Determine nodule type (inflammatory vs non-inflammatory vs infectious). "
            "For HA — consider hyaluronidase. For inflammatory — consider intralesional "
            "corticosteroid. Rule out biofilm before steroid use."
        ),
    },
}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _detect_signals(text: str) -> Dict[str, float]:
    norm = _normalise(text)
    detected: Dict[str, float] = {}
    for label, keywords, weight in VISUAL_SIGNALS:
        for kw in keywords:
            if kw in norm:
                detected[label] = weight
                break
    return detected


def _score_protocol(
    profile: Dict[str, Any],
    detected_signals: Dict[str, float],
) -> Tuple[float, float, List[str]]:
    raw = 0.0
    matched: List[str] = []
    for signal_label, signal_weight in profile["driving_signals"].items():
        if signal_label in detected_signals:
            raw += signal_weight
            matched.append(signal_label)
    fraction = raw / max(profile["max_possible"], 0.001)
    return raw, min(fraction, 1.0), matched


def _urgency(fraction: float, base: str) -> str:
    if base == "critical":
        return "critical" if fraction >= HIGH_THRESHOLD else "high"
    if fraction >= CRITICAL_THRESHOLD:
        return "critical"
    if fraction >= HIGH_THRESHOLD:
        return "high"
    return "moderate"


def detect_protocols_from_vision_text(
    analysis_text: str,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Scan GPT-4o vision analysis text for clinical complication signals.
    Returns list of triggered protocol dicts sorted by urgency then confidence.
    Returns [] if nothing breaches TRIGGER_THRESHOLD.
    """
    if not analysis_text:
        return []

    combined = f"{query}\n{analysis_text}" if query else analysis_text
    detected_signals = _detect_signals(combined)

    if not detected_signals:
        return []

    triggered: List[Dict[str, Any]] = []
    for protocol_key, profile in PROTOCOL_PROFILES.items():
        _raw, fraction, matched = _score_protocol(profile, detected_signals)
        if fraction < TRIGGER_THRESHOLD:
            continue
        urgency = _urgency(fraction, profile["urgency_base"])
        triggered.append({
            "protocol_key": protocol_key,
            "protocol_name": profile["name"],
            "urgency": urgency,
            "confidence": round(fraction, 3),
            "detected_signals": matched,
            "headline": profile["headline"],
            "immediate_action": profile["immediate_action"],
            "view_protocol_url": f"/complications?protocol={protocol_key}",
            "disclaimer": (
                "Visual signal detection is AI-assisted and not a substitute for clinical "
                "examination. Always apply clinical judgement."
            ),
        })

    urgency_order = {"critical": 0, "high": 1, "moderate": 2}
    triggered.sort(key=lambda p: (urgency_order[p["urgency"]], -p["confidence"]))

    if triggered:
        logger.info(
            f"[VisionBridge] {len(triggered)} protocol(s) triggered: "
            f"{[p['protocol_key'] for p in triggered]} | signals={list(detected_signals.keys())}"
        )

    return triggered


def build_protocol_alert_sse(triggered: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Returns a JSON-serialisable dict ready to emit as SSE event type='protocol_alert'."""
    return {
        "type": "protocol_alert",
        "triggered_protocols": triggered,
        "count": len(triggered),
        "has_critical": any(p["urgency"] == "critical" for p in triggered),
    }
