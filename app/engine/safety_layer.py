"""
AesthetiCite — Safety Layer  (UpToDate-inspired)
=================================================
Single source of truth for safety assessment across every response.

Design principles:
  1. Runs on EVERY query — not just complications. General queries also need
     safety guidance (e.g. "what dose of botox" → "verify with IFU").
  2. Zero latency — pure rule-based, no LLM. Runs in < 1ms.
  3. Returns a structured SafetyAssessment that is injected into the SSE
     meta payload of every answer.
  4. Risk level drives frontend emphasis (critical→red banner, low→subtle).
  5. Medico-legal block always included — defensibility by default.

Output structure (matches build plan exactly):
  {
    "risk_level":    "critical" | "high" | "moderate" | "low",
    "risk_warning":  str,
    "actions":       [{ "action": str, "priority": "immediate"|"urgent"|"routine" }],
    "when_to_stop":  [str],
    "when_to_refer": [str],
    "escalation":    str,
    "escalation_criteria": [str],
    "monitoring":    [str],
    "medico_legal":  { "document": [str], "disclaimer": str },
    "query_type":    str,
    "call_emergency": bool,
  }
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ===========================================================================
# QUERY CLASSIFICATION
# ===========================================================================

_COMPLICATION_TRIGGERS = frozenset([
    "vascular", "occlusion", "blanching", "livedo", "ischaemia", "ischemia",
    "necrosis", "blindness", "vision", "visual", "embol",
    "anaphylaxis", "anaphylactic", "allergic reaction", "urticaria",
    "ptosis", "drooping", "eyelid",
    "nodule", "granuloma", "lump", "bump", "biofilm",
    "infection", "abscess", "cellulitis", "fever",
    "tyndall", "blue discolouration",
    "delayed inflammatory", "dir",
    "bruising", "haematoma",
    "migration", "filler migration",
    "airway", "wheeze", "stridor",
    "complication", "adverse event", "emergency",
])

_HIGH_RISK_ANATOMY = frozenset([
    "glabella", "forehead", "temple", "periorbital", "tear trough",
    "nose", "nasal", "lip", "lips", "infraorbital",
    "angular artery", "supratrochlear", "supraorbital",
    "danger zone", "high risk area",
])

_TECHNIQUE_TRIGGERS = frozenset([
    "dose", "dosage", "units", "volume", "dilution", "reconstitution",
    "injection plane", "depth", "technique", "cannula", "needle", "bolus",
    "fanning", "linear threading", "retrograde",
])

_REGULATORY_TRIGGERS = frozenset([
    "licensed", "unlicensed", "off-label", "approved", "contraindicated",
    "pregnancy", "breastfeeding", "consent", "legal",
])


def classify_query(query: str) -> Tuple[str, int]:
    """
    Returns (query_type, risk_base_score).
    query_type: "complication_critical" | "complication_vascular" | "complication" |
                "high_risk_anatomy" | "technique" | "regulatory" | "general"
    """
    q = query.lower()

    if any(t in q for t in _COMPLICATION_TRIGGERS):
        if any(t in q for t in ("anaphylaxis", "airway", "wheeze", "stridor", "blindness", "necrosis")):
            return "complication_critical", 95
        if any(t in q for t in ("vascular", "occlusion", "blanching", "vision", "visual", "livedo")):
            return "complication_vascular", 90
        return "complication", 70

    if any(t in q for t in _HIGH_RISK_ANATOMY):
        return "high_risk_anatomy", 55

    if any(t in q for t in _TECHNIQUE_TRIGGERS):
        return "technique", 35

    if any(t in q for t in _REGULATORY_TRIGGERS):
        return "regulatory", 40

    return "general", 15


# ===========================================================================
# SAFETY RULE LIBRARY
# ===========================================================================

_SAFETY_RULES: Dict[str, Dict[str, Any]] = {

    "complication_critical": {
        "risk_level": "critical",
        "risk_warning": "Life-threatening complication. Emergency response required.",
        "call_emergency": True,
        "actions": [
            {"action": "Call 999 / emergency services immediately", "priority": "immediate"},
            {"action": "Do not leave the patient unattended", "priority": "immediate"},
            {"action": "Administer adrenaline 0.5mg IM for anaphylaxis, or hyaluronidase 1500 IU for vascular occlusion, as appropriate", "priority": "immediate"},
            {"action": "Document time of onset and all actions taken", "priority": "urgent"},
        ],
        "when_to_stop": [
            "Stop all injections immediately",
            "Do not apply pressure to the affected area if vascular occlusion is suspected",
        ],
        "when_to_refer": [
            "Any visual symptoms → immediate ophthalmology referral",
            "Any airway compromise → 999 + emergency services",
            "Any suspected necrosis → same-day plastic surgery referral",
            "No improvement within 60 minutes → emergency department",
        ],
        "escalation": "Call 999 immediately. This is a life-threatening emergency.",
        "escalation_criteria": [
            "Any visual change, diplopia, or vision loss → 999 + ophthalmology now",
            "Airway involvement, wheeze, or stridor → 999 now",
            "Haemodynamic instability → 999 now",
            "No clinical improvement after initial treatment → escalate",
        ],
        "monitoring": [
            "Continuous observation — do not leave patient",
            "Vital signs every 5 minutes until emergency team arrives",
            "Document every action with precise timestamps",
        ],
        "medico_legal": {
            "document": [
                "Time of symptom onset (exact)",
                "Sequence of events and all clinical decisions",
                "All medications given, doses, routes, and times",
                "Patient's response at each stage",
                "Who was contacted and when",
                "Patient consent and pre-procedure screening",
            ],
            "disclaimer": (
                "This output is clinical decision support only. "
                "Activate your clinic's emergency protocol immediately. "
                "AesthetiCite does not replace clinical training or emergency procedures."
            ),
        },
    },

    "complication_vascular": {
        "risk_level": "high",
        "risk_warning": "Suspected vascular complication. Time-critical — treatment window is 60 minutes.",
        "call_emergency": False,
        "actions": [
            {"action": "Stop injection immediately", "priority": "immediate"},
            {"action": "Hyaluronidase 1500 IU — inject immediately if HA filler used", "priority": "immediate"},
            {"action": "Aspirin 300 mg orally (unless contraindicated)", "priority": "immediate"},
            {"action": "Warm compress to affected area", "priority": "urgent"},
            {"action": "Nitroglycerin paste 2% applied topically", "priority": "urgent"},
            {"action": "Assess for visual symptoms every 5 minutes", "priority": "immediate"},
            {"action": "Photograph area at baseline and every 15–30 minutes", "priority": "urgent"},
        ],
        "when_to_stop": [
            "Stop all injections in the affected region immediately",
            "Do not massage or apply pressure directly to blanched area",
            "Stop and call 999 if any visual symptom appears",
        ],
        "when_to_refer": [
            "Any visual change → immediate ophthalmology referral + 999",
            "No blanching resolution at 60 minutes → emergency department",
            "Spreading livedo beyond the injection site → escalate",
            "Skin turning dark purple or black → plastic surgery same-day",
        ],
        "escalation": "If no improvement in 30–60 min → emergency department referral.",
        "escalation_criteria": [
            "Visual symptoms at any point → 999 + ophthalmology immediately",
            "Persistent blanching at 60 minutes → emergency department",
            "Expanding livedo reticularis → escalate dose and consider emergency",
            "Dark discolouration (necrosis risk) → same-day plastic surgery",
        ],
        "monitoring": [
            "Capillary refill every 5–10 minutes",
            "Skin colour and temperature every 10 minutes",
            "Pain assessment every 10 minutes",
            "Visual acuity check every 5 minutes if near orbital area",
            "Document all findings with timestamps",
        ],
        "medico_legal": {
            "document": [
                "Time injection was stopped (exact)",
                "Time hyaluronidase was given and dose used",
                "Capillary refill and skin colour at each assessment",
                "Any visual symptoms reported by patient",
                "All referrals made and times",
                "Product batch number and lot",
            ],
            "disclaimer": (
                "This is clinical decision support. Vascular occlusion requires immediate clinical response. "
                "AesthetiCite output does not replace clinical judgement or emergency protocols."
            ),
        },
    },

    "complication": {
        "risk_level": "high",
        "risk_warning": "Aesthetic complication identified. Prompt assessment and documentation required.",
        "call_emergency": False,
        "actions": [
            {"action": "Stop treatment and assess the patient immediately", "priority": "immediate"},
            {"action": "Take baseline photographs before any intervention", "priority": "urgent"},
            {"action": "Assess vital signs if systemic involvement is possible", "priority": "urgent"},
            {"action": "Document the complication in full", "priority": "urgent"},
        ],
        "when_to_stop": [
            "Stop all treatment in or near the affected area",
            "Do not continue if diagnosis is uncertain",
        ],
        "when_to_refer": [
            "Systemic symptoms (fever, spreading redness, unwell) → same-day GP or A&E",
            "No improvement at 48 hours → senior clinician review",
            "Any diagnostic uncertainty → refer",
        ],
        "escalation": "If no improvement within 48h or any deterioration → refer urgently.",
        "escalation_criteria": [
            "Systemic symptoms → same-day GP or A&E",
            "Progressive worsening → escalate",
            "Diagnostic uncertainty → seek senior review",
        ],
        "monitoring": [
            "Review at 24–48 hours",
            "Document with photographs at each review",
            "Record any change in symptoms or signs",
        ],
        "medico_legal": {
            "document": [
                "Full complication description with onset time",
                "Photographs (baseline and follow-up)",
                "All treatments given",
                "Referrals made",
                "Patient communication and consent for any further treatment",
            ],
            "disclaimer": (
                "Document this incident per your clinic's adverse event protocol. "
                "Notify your medical defence organisation if appropriate. "
                "AesthetiCite is clinical decision support only."
            ),
        },
    },

    "high_risk_anatomy": {
        "risk_level": "moderate",
        "risk_warning": "High-risk anatomical region. Vascular danger zones apply.",
        "call_emergency": False,
        "actions": [
            {"action": "Review vascular anatomy for this region before proceeding", "priority": "urgent"},
            {"action": "Aspirate before each injection (note: not reliable for all products)", "priority": "urgent"},
            {"action": "Use lowest effective volume", "priority": "urgent"},
            {"action": "Inject slowly with continuous movement", "priority": "urgent"},
            {"action": "Ensure hyaluronidase is immediately available", "priority": "urgent"},
            {"action": "Have emergency protocol visible and accessible", "priority": "routine"},
        ],
        "when_to_stop": [
            "Stop if patient reports sudden severe pain",
            "Stop if blanching or colour change appears",
            "Stop if patient reports visual disturbance",
        ],
        "when_to_refer": [
            "Any vascular occlusion signs → immediate vascular occlusion protocol",
            "Any visual change → immediate ophthalmology referral",
        ],
        "escalation": "Any vascular compromise sign → stop immediately and activate vascular occlusion protocol.",
        "escalation_criteria": [
            "Blanching or livedo → activate vascular occlusion protocol now",
            "Visual symptoms → 999 + ophthalmology immediately",
        ],
        "monitoring": [
            "Observe patient for 15–30 minutes post-procedure",
            "Review capillary refill and skin colour before patient leaves",
        ],
        "medico_legal": {
            "document": [
                "Pre-procedure risk discussion with patient",
                "Anatomy review conducted",
                "Product, volume, and technique used",
                "Patient observation period completed",
            ],
            "disclaimer": (
                "High-risk anatomy requires advanced training. "
                "Ensure compliance with your indemnity requirements and local guidelines."
            ),
        },
    },

    "technique": {
        "risk_level": "low",
        "risk_warning": "Always verify doses and techniques against product IFU and current guidelines.",
        "call_emergency": False,
        "actions": [
            {"action": "Verify dose against product IFU before injection", "priority": "routine"},
            {"action": "Confirm product is within expiry and stored correctly", "priority": "routine"},
            {"action": "Ensure patient has completed pre-procedure consent", "priority": "routine"},
        ],
        "when_to_stop": [
            "Stop if patient reports unexpected or severe pain",
            "Stop if any vascular compromise signs appear",
        ],
        "when_to_refer": [
            "Any unexpected adverse event → follow adverse event protocol",
        ],
        "escalation": "Any unexpected adverse response → stop treatment and assess immediately.",
        "escalation_criteria": [
            "Unexpected severe pain → stop",
            "Any vascular sign → vascular occlusion protocol",
        ],
        "monitoring": [
            "Observe for immediate adverse reactions before patient leaves",
            "Provide patient with written aftercare and emergency contact",
        ],
        "medico_legal": {
            "document": [
                "Product name, batch number, expiry date",
                "Volume and technique used",
                "Consent completed",
                "Post-procedure advice given",
            ],
            "disclaimer": (
                "Dosing information is for reference only. "
                "Always follow product IFU, manufacturer guidance, and your training."
            ),
        },
    },

    "regulatory": {
        "risk_level": "moderate",
        "risk_warning": "Regulatory or consent considerations identified. Verify legal requirements before proceeding.",
        "call_emergency": False,
        "actions": [
            {"action": "Verify that treatment is within your scope of practice and licensure", "priority": "urgent"},
            {"action": "Ensure full informed consent is documented", "priority": "urgent"},
            {"action": "Confirm off-label use is disclosed to patient where applicable", "priority": "urgent"},
        ],
        "when_to_stop": [
            "Stop if valid consent has not been obtained",
            "Stop if the patient is not a suitable candidate per contraindications",
        ],
        "when_to_refer": [
            "Any uncertainty about scope of practice → seek senior or regulatory advice",
        ],
        "escalation": "Seek medical defence advice before proceeding with any legally uncertain treatment.",
        "escalation_criteria": [
            "Scope of practice uncertainty → pause and seek advice",
        ],
        "monitoring": [
            "Retain all consent documentation",
            "Document basis for clinical decision",
        ],
        "medico_legal": {
            "document": [
                "Full informed consent including off-label status if applicable",
                "Basis for clinical decision",
                "Any advice sought from senior clinicians or MDO",
            ],
            "disclaimer": (
                "Regulatory requirements vary by jurisdiction. "
                "Consult your medical defence organisation for advice on specific cases."
            ),
        },
    },

    "general": {
        "risk_level": "low",
        "risk_warning": "This output is clinical decision support. Verify against current guidelines before clinical use.",
        "call_emergency": False,
        "actions": [
            {"action": "Cross-reference with current clinical guidelines before applying", "priority": "routine"},
            {"action": "Apply clinical judgement — this output is not a substitute", "priority": "routine"},
        ],
        "when_to_stop": [
            "Do not proceed if clinical presentation is unclear",
        ],
        "when_to_refer": [
            "Any diagnostic uncertainty → seek senior or specialist advice",
        ],
        "escalation": "Escalate to senior colleague or specialist if any uncertainty exists.",
        "escalation_criteria": [
            "Diagnostic uncertainty → refer",
        ],
        "monitoring": [],
        "medico_legal": {
            "document": [
                "Clinical decision and rationale",
                "Sources consulted",
            ],
            "disclaimer": (
                "AesthetiCite provides evidence-based decision support. "
                "All clinical decisions remain the responsibility of the treating clinician."
            ),
        },
    },
}


# ===========================================================================
# PUBLIC API
# ===========================================================================

def assess_safety(
    query: str,
    *,
    symptoms: Optional[List[str]] = None,
    region: Optional[str] = None,
    procedure: Optional[str] = None,
    existing_protocol_risk_level: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Primary entry point. Call this on EVERY answer generation.

    Returns a structured SafetyAssessment dict ready for injection into
    the SSE meta payload or any API response.
    """
    combined = " ".join(filter(None, [
        query,
        " ".join(symptoms or []),
        region or "",
        procedure or "",
    ])).lower()

    query_type, risk_score = classify_query(combined)

    if existing_protocol_risk_level:
        upgrade_map = {
            "critical": ("complication_critical", 95),
            "high":     ("complication_vascular",  85),
            "moderate": ("complication",            70),
        }
        if existing_protocol_risk_level in upgrade_map:
            alt_type, alt_score = upgrade_map[existing_protocol_risk_level]
            if alt_score > risk_score:
                query_type, risk_score = alt_type, alt_score

    rules = _SAFETY_RULES.get(query_type, _SAFETY_RULES["general"])

    region_lower = (region or "").lower()
    region_upgrade = any(r in region_lower for r in _HIGH_RISK_ANATOMY)
    if region_upgrade and rules["risk_level"] == "low":
        rules = dict(rules)
        rules["risk_level"] = "moderate"
        rules["when_to_refer"] = (
            rules.get("when_to_refer", [])
            + ["High-risk anatomy — monitor for vascular compromise before patient leaves"]
        )

    return {
        "risk_level":          rules["risk_level"],
        "risk_warning":        rules["risk_warning"],
        "call_emergency":      rules.get("call_emergency", False),
        "actions":             rules["actions"],
        "when_to_stop":        rules["when_to_stop"],
        "when_to_refer":       rules["when_to_refer"],
        "escalation":          rules["escalation"],
        "escalation_criteria": rules["escalation_criteria"],
        "monitoring":          rules["monitoring"],
        "medico_legal":        rules["medico_legal"],
        "query_type":          query_type,
        "risk_score":          risk_score,
    }


def safety_block_for_prompt(query: str) -> str:
    """
    Returns a compact safety block string for injection into the LLM prompt.
    """
    query_type, _ = classify_query(query.lower())
    rules = _SAFETY_RULES.get(query_type, _SAFETY_RULES["general"])

    stop_text  = " | ".join(rules["when_to_stop"][:2]) or "Stop if clinical situation is unclear."
    refer_text = " | ".join(rules["when_to_refer"][:2]) or "Refer if diagnostic uncertainty."
    esc_text   = rules["escalation"]

    return (
        f"SAFETY RULES (include in every answer):\n"
        f"- When to stop: {stop_text}\n"
        f"- When to refer: {refer_text}\n"
        f"- Escalation: {esc_text}\n"
        f"- Risk level: {rules['risk_level'].upper()}\n"
        f"- Disclaimer: {rules['medico_legal']['disclaimer']}"
    )


def enrich_meta_payload(
    meta_payload: Dict[str, Any],
    query: str,
    *,
    symptoms: Optional[List[str]] = None,
    region: Optional[str] = None,
    procedure: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inject safety assessment into an existing SSE meta payload.
    Call this in ask_v2.py and oe_upgrade.py before emitting the meta event.
    """
    existing_risk = None
    if meta_payload.get("complication_protocol"):
        existing_risk = meta_payload["complication_protocol"].get("risk_level")

    safety = assess_safety(
        query,
        symptoms=symptoms,
        region=region,
        procedure=procedure,
        existing_protocol_risk_level=existing_risk,
    )
    meta_payload["safety"] = safety
    return meta_payload
