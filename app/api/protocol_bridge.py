"""
AesthetiCite — Protocol Bridge
app/api/protocol_bridge.py

Wires the complication_protocol_engine into the main ask_v2 stream.
When a query matches a protocol trigger, the bridge runs the protocol
engine inline and emits the result as a structured SSE event alongside
the normal evidence answer.

No new endpoints. No schema changes. Pure wiring.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


# ─── Trigger detection ────────────────────────────────────────────────────────

_PROTOCOL_TRIGGERS: Dict[str, List[str]] = {
    "vascular_occlusion_ha_filler": [
        "vascular occlusion", "blanching", "mottling", "livedo", "ischemia",
        "necrosis", "capillary refill", "tissue ischemia", "filler occlusion",
        "filler embolism", "hyaluronidase dose", "hyaluronidase protocol",
        "vascular compromise", "skin necrosis after filler",
        "vision loss after filler", "blindness after filler",
        "ophthalmic artery", "retinal artery", "ocular filler",
    ],
    "anaphylaxis_allergic_reaction": [
        "anaphylaxis", "anaphylactic", "allergic reaction", "epinephrine dose",
        "adrenaline dose", "urticaria", "angioedema", "wheeze after injection",
        "systemic allergic", "hypotension after filler",
    ],
    "botulinum_toxin_ptosis": [
        "ptosis after botox", "eyelid ptosis", "eyelid drooping", "brow ptosis",
        "diplopia after toxin", "botulinum ptosis", "toxin ptosis",
        "ptosis management", "droopy eyelid after injection",
    ],
    "tyndall_effect_ha_filler": [
        "tyndall effect", "tyndall", "blue discoloration filler",
        "bluish tinge filler", "superficial filler discoloration",
        "blue grey filler", "tear trough discoloration",
    ],
    "infection_or_biofilm_after_filler": [
        "infection after filler", "biofilm", "infected filler",
        "abscess after filler", "filler infection", "hot nodule",
        "tender swelling filler", "erythema after filler",
        "fluctuance filler", "drainage filler",
    ],
    "filler_nodules_inflammatory_or_noninflammatory": [
        "filler nodule", "nodule after filler", "lump after filler",
        "bump after filler", "granuloma filler", "delayed nodule",
        "filler granuloma", "hard lump filler",
    ],
}

_GENERAL_SAFETY_TERMS = [
    "complication", "emergency", "what to do if", "management of",
    "treat", "protocol for", "how to manage", "urgent", "immediate action",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def detect_protocol_key(query: str, free_text: Optional[str] = None) -> Optional[str]:
    """
    Returns the most likely protocol key for a query, or None if no match.
    Scores by number of keyword matches; returns highest scorer above threshold.
    """
    blob = _normalize(f"{query} {free_text or ''}")

    scores: Dict[str, int] = {}
    for key, keywords in _PROTOCOL_TRIGGERS.items():
        score = sum(1 for kw in keywords if kw in blob)
        if score > 0:
            scores[key] = score

    if not scores:
        has_safety_intent = any(t in blob for t in _GENERAL_SAFETY_TERMS)
        if not has_safety_intent:
            return None
        return "__freetext__"

    return max(scores, key=lambda k: scores[k])


# Broad flat-list trigger check — sourced from protocol_engine_app.py.
# Complements detect_protocol_key() as a lightweight boolean pre-filter:
# use is_protocol_query() first; if True, call detect_protocol_key() to
# get the specific protocol key for complication_protocol_engine dispatch.
_FLAT_PROTOCOL_TRIGGERS = [
    "vascular occlusion", "blanching", "livedo", "severe pain", "visual symptoms",
    "hyaluronidase", "infection", "hematoma", "seroma", "capsular contracture",
    "complication", "what should i do", "what would you do", "protocol", "urgent",
    "emergency", "necrosis", "redness", "warmth", "asymmetry", "ptosis",
    "post op", "post-op", "after filler", "after injection", "after augmentation",
    "delayed healing", "blindness", "ischemia",
]


def is_protocol_query(
    query: str,
    procedure: str = "",
    region: str = "",
    symptoms: str = "",
    patient_factors: str = "",
) -> bool:
    """
    Broad boolean check: returns True if the query (and any optional context
    strings) contains any clinical protocol or complication trigger term.

    Use as a cheap pre-filter before calling detect_protocol_key().
    """
    blob = _normalize(" ".join(filter(None, [query, procedure, region, symptoms, patient_factors])))
    return any(x in blob for x in _FLAT_PROTOCOL_TRIGGERS)


# ─── Urgency / confidence helpers ─────────────────────────────────────────────
# Sourced from protocol_engine_app.py and adapted to use plain strings.
# These are exported for use by ask_v2.py and any downstream consumers
# that need urgency/confidence signals without a full engine round-trip.

ProtocolUrgency = Literal["Routine", "Review advised", "Urgent review", "Emergency"]
ConfidenceLevel = Literal["High", "Moderate", "Low"]


def urgency_from_query(
    query: str,
    symptoms: str = "",
    procedure: str = "",
    region: str = "",
) -> ProtocolUrgency:
    """
    Classifies urgency from free-text query and optional context strings.
    Returns one of: 'Emergency', 'Urgent review', 'Review advised', 'Routine'.
    """
    text = _normalize(" ".join(filter(None, [query, symptoms, procedure, region])))
    if any(x in text for x in ["vision", "visual", "blindness", "emergency"]):
        return "Emergency"
    if any(x in text for x in ["vascular occlusion", "blanching", "livedo", "severe pain", "necrosis"]):
        return "Emergency"
    if any(x in text for x in ["infection", "hematoma", "seroma", "capsular contracture", "urgent"]):
        return "Urgent review"
    if any(x in text for x in ["redness", "warmth", "asymmetry", "delayed healing", "pain"]):
        return "Review advised"
    return "Routine"


def confidence_from_rows(rows: List[Dict[str, Any]]) -> ConfidenceLevel:
    """
    Derives a confidence level from the top-3 retrieved evidence rows.
    'High' if a guideline or Level-I source is present; 'Moderate' for reviews
    or Level II; 'Low' otherwise.
    """
    if not rows:
        return "Low"
    top_types = [str(r.get("document_type", "")).lower() for r in rows[:3]]
    top_levels = [str(r.get("evidence_level", "")).upper() for r in rows[:3]]
    if any(t == "guideline" for t in top_types) or any(lv == "I" for lv in top_levels):
        return "High"
    if any(t == "review" for t in top_types) or any(lv == "II" for lv in top_levels):
        return "Moderate"
    return "Low"


# ─── Protocol assembly prompt template ────────────────────────────────────────
# Sourced from protocol_engine_app.py, fixed: uses chat.completions format with
# gpt-4o-mini (not responses.create / gpt-4.1-mini).
# To use: fill {answer_language}, {query}, {procedure}, {region}, {symptoms},
#         {patient_factors}, {evidence_block}, then call:
#
#   client.chat.completions.create(
#       model="gpt-4o-mini",
#       messages=[{"role": "user", "content": _PROTOCOL_ASSEMBLY_PROMPT_TEMPLATE.format(...)}],
#       max_tokens=1500, temperature=0.15,
#   )
#
# The model must return strict JSON with these keys:
#   protocol_title, recognition, immediate_actions, treatment,
#   escalation, monitoring, evidence_summary, answer

_PROTOCOL_ASSEMBLY_PROMPT_TEMPLATE = """\
You are the protocol engine for AesthetiCite.

Task:
Build a structured clinical protocol, not a generic paragraph answer.

Rules:
- Answer in {answer_language}.
- Use ONLY the evidence below.
- Prioritize guidelines and consensus statements first.
- Then use systematic reviews/meta-analyses.
- Then use RCTs/reviews.
- Do NOT invent steps, studies, citations, or facts.
- Cite only with the provided ids like [src_1].
- If evidence is weak or mixed, state that clearly.
- Keep sections concise and clinically actionable.

Return strict JSON with these keys only:
{{
  "protocol_title": "string",
  "recognition": ["string"],
  "immediate_actions": ["string"],
  "treatment": ["string"],
  "escalation": ["string"],
  "monitoring": ["string"],
  "evidence_summary": "string",
  "answer": "string"
}}

Case context:
- Query: {query}
- Procedure: {procedure}
- Region: {region}
- Symptoms: {symptoms}
- Patient factors: {patient_factors}

Evidence:
{evidence_block}"""


# ─── Protocol bridge ──────────────────────────────────────────────────────────

class ProtocolBridge:
    """
    Evaluates a query and, if it matches a protocol trigger,
    runs the complication protocol engine and returns a structured card.
    """

    def evaluate(
        self,
        query: str,
        context_hints: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        hints = context_hints or {}
        free_text = hints.get("free_text") or hints.get("region") or ""
        protocol_key = detect_protocol_key(query, free_text)

        if not protocol_key:
            return None

        try:
            return self._run_protocol(query, protocol_key, hints)
        except Exception as e:
            logger.warning(f"ProtocolBridge: engine call failed for key={protocol_key}: {e}")
            return None

    def _run_protocol(
        self,
        query: str,
        protocol_key: str,
        hints: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        from app.api.complication_protocol_engine import (
            ProtocolRequest, ClinicalContext, build_protocol_response,
        )

        context = ClinicalContext(
            region=hints.get("region"),
            procedure=hints.get("procedure"),
            product_type=hints.get("product_type"),
            symptoms=hints.get("symptoms", []),
            free_text=hints.get("free_text"),
            visual_symptoms=hints.get("visual_symptoms"),
            capillary_refill_delayed=hints.get("capillary_refill_delayed"),
            filler_confirmed_ha=hints.get("filler_confirmed_ha"),
            tenderness=hints.get("tenderness"),
            warmth=hints.get("warmth"),
            erythema=hints.get("erythema"),
            eyelid_droop=hints.get("eyelid_droop"),
        )

        req = ProtocolRequest(
            query=query if protocol_key == "__freetext__" else f"{query} [{protocol_key}]",
            context=context,
            mode="decision_support",
        )

        response = build_protocol_response(req)

        try:
            card = response.model_dump()
        except AttributeError:
            card = response.dict()

        card["_card_type"] = "complication_protocol"
        card["_triggered_by"] = protocol_key
        card["_query"] = query

        return card


# ─── Singleton ────────────────────────────────────────────────────────────────

_bridge_instance: Optional[ProtocolBridge] = None


def get_bridge() -> ProtocolBridge:
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ProtocolBridge()
    return _bridge_instance
