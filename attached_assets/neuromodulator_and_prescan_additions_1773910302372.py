"""
AesthetiCite — Complication Protocol Engine Additions
======================================================
Add to: app/api/complication_protocol_engine.py

New content:
  1. Neuromodulator Resistance / Pseudo-Resistance Protocol
     (new PROTOCOL entry + matching keywords)
  2. Pre-Scan Briefing endpoint
     POST /api/complications/prescan-briefing
     Returns structured ultrasound checklist before injection
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1.  ADD THIS ENTRY to your PROTOCOLS dict in complication_protocol_engine.py
#     Key: "neuromodulator_resistance"
# ─────────────────────────────────────────────────────────────────────────────

NEUROMODULATOR_RESISTANCE_PROTOCOL = {
    "key": "neuromodulator_resistance",
    "name": "Neuromodulator Resistance / Treatment Failure",
    "aliases": [
        "botox resistance", "toxin resistance", "neurotoxin resistance",
        "botox not working", "botox wearing off", "toxin failure",
        "no response botox", "shortened duration botox",
        "pseudo-resistance", "neuromodulator failure",
        "botulinum resistance", "toxin not lasting",
        "dysport resistance", "xeomin resistance",
    ],
    "severity": "moderate",
    "urgency": "routine",
    "risk_score": 35,
    "likely_time_critical": False,
    "evidence_strength": "moderate",
    "clinical_summary": (
        "Neuromodulator treatment failure presents as reduced duration, no clinical response, "
        "or a specific area failing to respond despite adequate dosing. Two distinct mechanisms "
        "must be differentiated: true immunological resistance (antibody-mediated neutralisation "
        "of botulinum toxin) versus pseudo-resistance — inadequate dose, incorrect placement, "
        "altered anatomy, incorrect storage or reconstitution, or patient expectation mismatch. "
        "CMAC 2025 highlighted pseudo-resistance as the more common and more actionable cause. "
        "Management differs significantly between these two categories."
    ),
    "immediate_actions": [
        {
            "step_number": 1,
            "action": "Classify as true resistance vs pseudo-resistance",
            "rationale": (
                "True resistance: complete absence of any effect across multiple areas and multiple "
                "products. Pseudo-resistance: partial response, one area not responding, or shortened "
                "duration only. This classification drives all subsequent management."
            ),
            "priority": "primary",
        },
        {
            "step_number": 2,
            "action": "Audit dose, dilution, storage, and technique",
            "rationale": (
                "Check: was dilution correct? Was product stored properly (2–8°C, not frozen)? "
                "Was dose adequate for the muscle mass and patient? Was injection depth correct? "
                "Pseudo-resistance from these factors is the most common correctable cause."
            ),
            "priority": "primary",
        },
        {
            "step_number": 3,
            "action": "Assess anatomical factors and patient expectations",
            "rationale": (
                "Strong or hypertrophic muscles (masseter, frontalis) may require higher doses. "
                "Dynamic anatomy changes (weight loss, GLP-1 patients) may alter muscle mass. "
                "Some patients expect paralysis; others prefer mild softening — clarify expectations."
            ),
            "priority": "primary",
        },
        {
            "step_number": 4,
            "action": "For pseudo-resistance: adjust dose, depth, or technique",
            "rationale": (
                "Increase total dose incrementally. Reassess injection points against current anatomy. "
                "Consider electromyographic (EMG) guidance for difficult cases. "
                "Use a different dilution volume if diffusion is needed."
            ),
            "priority": "primary",
        },
        {
            "step_number": 5,
            "action": "For suspected true resistance: switch to a different serotype or formulation",
            "rationale": (
                "Antibody-mediated resistance is typically specific to the toxin serotype and often "
                "the specific commercial preparation. Switching from OnabotulinumtoxinA to "
                "IncobotulinumtoxinA (Xeomin, lowest antigenic protein load) may restore response. "
                "High-frequency repeat dosing and high-dose treatments increase immunogenicity risk."
            ),
            "priority": "primary",
        },
        {
            "step_number": 6,
            "action": "Consider the CMAC 2025 'reset technique' for pseudo-resistance cases",
            "rationale": (
                "Described at CMAC 2025: a structured rest period followed by targeted re-injection "
                "using EMG to confirm target muscle activity, with dose recalibration. "
                "This has shown efficacy in a select group of patients with shortened duration "
                "who were not truly antibody-resistant."
            ),
            "priority": "secondary",
        },
    ],
    "dose_guidance": [
        {
            "substance": "OnabotulinumtoxinA (Botox/Vistabel)",
            "recommendation": "Consider dose escalation 20–30% above prior ineffective dose before switching product",
            "notes": "Document exact dose, injection points, and dilution for each session to track response patterns.",
        },
        {
            "substance": "IncobotulinumtoxinA (Xeomin)",
            "recommendation": "Switch to Xeomin if true resistance suspected — lowest complexing protein load reduces immunogenicity",
            "notes": "Units are approximately equivalent to OnabotulinumtoxinA; adjust dose based on clinical response.",
        },
        {
            "substance": "AbobotulinumtoxinA (Dysport)",
            "recommendation": "Alternative if switching within serotype A; unit conversion ~2.5–3:1 relative to OnabotulinumtoxinA",
            "notes": "Higher diffusion profile may be advantageous in some anatomical regions.",
        },
    ],
    "red_flags": [
        "Complete absence of ANY effect across multiple sites and multiple products — escalate to neurology for immunological testing.",
        "Neurological symptoms emerging alongside apparent toxin failure — immediate escalation required.",
        "Systemic symptoms (dysphagia, weakness beyond injection site) — emergency assessment.",
        "Resistance emerging after years of successful treatment — document and investigate systematically.",
    ],
    "escalation": [
        "Refer to dermatology or neurology for formal resistance testing if true immunological failure is suspected.",
        "Mouse hemidiaphragm assay or cell-based neutralisation assays can confirm antibody-mediated resistance.",
        "Consider referral to specialist centre if management remains unclear after 2–3 adjusted treatment cycles.",
    ],
    "monitoring": [
        "Photograph injection points and document dose precisely at each session.",
        "Track onset (days), duration (weeks), and peak effect systematically.",
        "Use validated scales (e.g. Wrinkle Severity Rating Scale) for objective response tracking.",
        "Monitor for any systemic symptoms at each review.",
    ],
    "limitations": [
        "True immunological resistance is rare (<1–3% of patients) but underdiagnosed due to poor documentation.",
        "Pseudo-resistance likely accounts for the majority of apparent treatment failures.",
        "Formal neutralising antibody testing is not widely available in clinical practice.",
        "Evidence base for management of resistance is mostly observational.",
    ],
    "follow_up_questions": [
        "Has the patient responded normally to neuromodulators in the past?",
        "Has anything changed in storage, dilution, or administration since the last successful treatment?",
        "Is the failure global (all areas) or regional (one specific area)?",
        "What is the patient's expectation — paralysis or softening?",
    ],
    "evidence": [
        {
            "source_id": "NR-01",
            "title": "Botulinum toxin resistance in aesthetic practice — mechanisms and management",
            "note": "Reviews true vs pseudo-resistance, antibody formation risk factors, and clinical management strategies.",
            "source_type": "Narrative Review",
            "relevance_score": 0.88,
        },
        {
            "source_id": "NR-02",
            "title": "IncobotulinumtoxinA: lower immunogenic protein load and clinical implications",
            "note": "Supports switching to Xeomin in antibody-mediated resistance due to absence of complexing proteins.",
            "source_type": "Clinical Review",
            "relevance_score": 0.82,
        },
        {
            "source_id": "NR-03",
            "title": "CMAC 2025 — Pseudo-resistance: a new concept in neuromodulator management",
            "note": "Introduced the clinical distinction between true resistance and pseudo-resistance, with technique reset protocol.",
            "source_type": "Conference Presentation",
            "relevance_score": 0.91,
        },
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION: Add to your PROTOCOLS dict:
#
#   PROTOCOLS["neuromodulator_resistance"] = NEUROMODULATOR_RESISTANCE_PROTOCOL
#
# Add matching keywords to your match_protocol() function:
#   "neuromodulator_resistance": [
#       "resistance", "not working", "wearing off", "failure", "no response",
#       "shortened duration", "pseudo-resistance", "toxin failure", "botox failure"
#   ]
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# 2.  NEW ENDPOINT — Pre-Scan Briefing
#     POST /api/complications/prescan-briefing
#     Add this router function to complication_protocol_engine.py
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from fastapi import APIRouter
import uuid
from datetime import datetime, timezone

# Pre-scan briefing data per region
# Based on RSNA 2025, Journal of Cosmetic Dermatology 2025, CMAC 2025

PRESCAN_BRIEFINGS: Dict[str, Dict[str, Any]] = {
    "nose": {
        "label": "Nose / Nasal Dorsum",
        "risk_level": "very_high",
        "structures_to_identify": [
            "Dorsal nasal artery (runs along nasal dorsum — identify and avoid)",
            "Angular artery (at alar base — communicates with ophthalmic territory)",
            "Lateral nasal artery (branches off facial artery near alar groove)",
            "Columellar artery (runs along columella — thin skin, easily compressed)",
            "Existing filler (check for residual product from previous treatments)",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). B-mode + colour Doppler. Low wall filter for small vessels.",
        "key_findings_to_document": [
            "Location and course of dorsal nasal artery relative to planned injection point",
            "Any pre-existing filler material (hyperechoic zones)",
            "Skin thickness at planned injection site",
            "Vascular anomalies or unusual anatomy",
        ],
        "safe_windows": [
            "Supraperiosteal plane along nasal dorsum (deep to angular artery territory)",
            "Avoid superficial subcutaneous plane entirely in this region",
        ],
        "abort_criteria": [
            "Vessel directly in needle path with no safe deviation",
            "Existing filler within same tissue plane and unclear residual volume",
            "Patient cannot remain still during scan",
        ],
        "evidence_note": "RSNA 2025: 35% of nasal filler complications showed absent major vessel flow on ultrasound. Nasal vessels communicate with ophthalmic territory — vision loss risk.",
    },
    "temple": {
        "label": "Temple / Temporal Hollow",
        "risk_level": "high",
        "structures_to_identify": [
            "Superficial temporal artery and vein (palpable, runs within temporoparietal fascia)",
            "Middle temporal vein (deep to temporoparietal fascia, crosses injection zone)",
            "Zygomaticoorbital artery (branch of superficial temporal, periorbital area)",
            "Deep temporal arteries (below temporalis fascia — confirm injection plane is above)",
            "Existing filler deposits if repeat treatment",
        ],
        "doppler_settings": "High-frequency transducer (12–18 MHz). B-mode to identify filler/fat layer. Colour Doppler for vessel mapping.",
        "key_findings_to_document": [
            "Course of superficial temporal artery — mark on skin before injection",
            "Depth of preferred injection plane (deep to temporalis fascia for filler)",
            "Any vascular anomalies in the temporal hollow",
        ],
        "safe_windows": [
            "Deep subfascial plane (below superficial layer of deep temporal fascia) — below main vessel territory",
            "Periosteal plane over temporal bone — safest for structural filler",
        ],
        "abort_criteria": [
            "Superficial temporal artery crossing planned injection path without safe detour",
            "Extremely thin temporal fat pad with no identifiable safe plane",
        ],
        "evidence_note": "Temporal hollow filler carries significant risk of intravascular injection — STA is palpable in many patients but its exact course requires ultrasound confirmation.",
    },
    "forehead": {
        "label": "Forehead / Frontal",
        "risk_level": "high",
        "structures_to_identify": [
            "Supratrochlear artery (medial forehead — emerges above supraorbital rim)",
            "Supraorbital artery (lateral to supratrochlear — both supply forehead skin)",
            "Sentinel vein / zygomaticotemporal vein (lateral forehead — surgical landmark)",
            "Frontal branch of facial nerve (risk with deep injections laterally)",
            "Existing filler if repeat treatment",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). Colour Doppler to identify medial forehead vessels at supraorbital level.",
        "key_findings_to_document": [
            "Supratrochlear artery exit point from supraorbital foramen — mark before injection",
            "Supraorbital artery course across central forehead",
            "Planned injection plane relative to these vessels (periosteal preferred for filler)",
        ],
        "safe_windows": [
            "Deep periosteal plane — below the subgaleal plane, avoids main vessel territory",
            "Lateral forehead above brow: inject in midforehead away from medial vessel territory",
        ],
        "abort_criteria": [
            "Supratrochlear or supraorbital artery directly within planned injection path",
            "Existing large filler deposits altering anatomy",
        ],
        "evidence_note": "Supratrochlear and supraorbital vessels communicate with central retinal artery. Ischaemic complications in forehead can be vision-threatening.",
    },
    "tear trough": {
        "label": "Tear Trough / Periorbital",
        "risk_level": "high",
        "structures_to_identify": [
            "Infraorbital artery and vein (exits infraorbital foramen — map precisely)",
            "Angular artery (medial canthus — connects with ophthalmic territory)",
            "Orbicularis oculi muscle (identify correct injection plane relative to muscle)",
            "Periosteum (supraperiosteal plane is safest for deep filler placement)",
            "Existing filler material (common site for product accumulation over years)",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). Gentle pressure only — avoid compressing periorbital vessels. Colour Doppler for angular and infraorbital vessels.",
        "key_findings_to_document": [
            "Location of infraorbital foramen relative to planned injection vector",
            "Presence and volume of any residual filler from previous treatments",
            "Tissue plane: identify suborbicularis vs periosteal space",
            "Angular artery course at medial canthus",
        ],
        "safe_windows": [
            "Supraperiosteal plane lateral to infraorbital foramen — safest anatomical window",
            "Deep suborbicularis plane — avoids superficial Tyndall risk",
        ],
        "abort_criteria": [
            "Large volume of residual filler from previous treatments — defer until partially dissolved",
            "Infraorbital foramen directly in planned injection path",
            "Any patient-reported visual symptoms prior to treatment",
        ],
        "evidence_note": "Periorbital region carries Tyndall risk with superficial HA and vascular occlusion risk from angular artery proximity to ophthalmic territory.",
    },
    "glabella": {
        "label": "Glabella / Frown Lines",
        "risk_level": "very_high",
        "structures_to_identify": [
            "Supratrochlear artery (medial — immediately adjacent to corrugator injection sites)",
            "Supraorbital artery (lateral — both communicate with ophthalmic/retinal territory)",
            "Procerus muscle (identify depth and borders)",
            "Corrugator supercilii muscle (key toxin target — identify precisely)",
            "Any existing filler from previous treatments (HA only acceptable here)",
        ],
        "doppler_settings": "High-frequency transducer (15–22 MHz). Colour Doppler essential. Identify both supratrochlear vessels bilaterally before injection.",
        "key_findings_to_document": [
            "Exact location of bilateral supratrochlear arteries — mark on skin",
            "Depth of supratrochlear arteries relative to corrugator muscle",
            "Any pre-existing filler (filler in glabella is high-risk — consider dissolving first)",
        ],
        "safe_windows": [
            "Intramuscular plane of procerus/corrugator — for toxin only",
            "No safe plane for filler in central glabella — HA only and with extreme caution",
        ],
        "abort_criteria": [
            "For filler: any non-HA product planned — abort (non-reversible in this territory)",
            "Supratrochlear artery coursing through planned injection point",
            "Existing filler in glabella — dissolve first if any uncertainty about residual volume",
            "Junior or intermediate injector without senior supervision — this is a senior-only zone",
        ],
        "evidence_note": "Glabella has the highest documented rate of vision loss from filler-related vascular complications. Supratrochlear vessels directly communicate with retinal circulation.",
    },
    "nasolabial fold": {
        "label": "Nasolabial Fold",
        "risk_level": "moderate",
        "structures_to_identify": [
            "Facial artery (courses medially — confirm position varies between patients)",
            "Angular artery (superior NLF — often medial to fold, variable anatomy)",
            "Superior labial artery (at inferior NLF — enters lip territory)",
            "Infraorbital neurovascular bundle (superior NLF territory)",
        ],
        "doppler_settings": "High-frequency transducer (12–18 MHz). Colour Doppler to trace facial artery course along the NLF before injection.",
        "key_findings_to_document": [
            "Course of facial artery relative to NLF — medial, within, or lateral to fold",
            "Any vessel directly in planned injection path at mid-NLF level",
        ],
        "safe_windows": [
            "Subcutaneous plane lateral to facial artery — if artery can be mapped medially",
            "Dermal/subdermal plane for superficial correction with low volume",
        ],
        "abort_criteria": [
            "Facial artery running directly within planned injection path without safe lateral window",
        ],
        "evidence_note": "NLF facial artery course is highly variable — in some patients it runs within or immediately medial to the fold, creating significant occlusion risk.",
    },
}


class PreScanBriefingRequest(BaseModel):
    region: str = Field(..., min_length=2, description="Anatomical region for injection")
    procedure: Optional[str] = None
    injector_experience_level: Optional[str] = None
    has_ultrasound: bool = True


class PreScanBriefingResponse(BaseModel):
    request_id: str
    generated_at_utc: str
    region_label: str
    risk_level: str
    structures_to_identify: List[str]
    doppler_settings: str
    key_findings_to_document: List[str]
    safe_windows: List[str]
    abort_criteria: List[str]
    evidence_note: str
    disclaimer: str
    junior_note: Optional[str] = None


def _match_prescan_region(region: str) -> Optional[Dict[str, Any]]:
    r = region.lower().strip()
    for key, data in PRESCAN_BRIEFINGS.items():
        if key in r or any(alias in r for alias in key.split()):
            return data
    # fuzzy fallback
    if any(x in r for x in ["nose", "nasal", "dorsum", "rhinoplasty"]):
        return PRESCAN_BRIEFINGS["nose"]
    if any(x in r for x in ["temple", "temporal", "hollow"]):
        return PRESCAN_BRIEFINGS["temple"]
    if any(x in r for x in ["forehead", "frontal", "brow"]):
        return PRESCAN_BRIEFINGS["forehead"]
    if any(x in r for x in ["tear", "trough", "periorbital", "infraorbital", "under eye"]):
        return PRESCAN_BRIEFINGS["tear trough"]
    if any(x in r for x in ["glabella", "frown", "procerus", "corrugator"]):
        return PRESCAN_BRIEFINGS["glabella"]
    if any(x in r for x in ["nasolabial", "nlf", "smile line"]):
        return PRESCAN_BRIEFINGS["nasolabial fold"]
    return None


# Add this to your router in complication_protocol_engine.py:

# @router.post("/prescan-briefing", response_model=PreScanBriefingResponse)
def prescan_briefing(payload: PreScanBriefingRequest) -> PreScanBriefingResponse:
    """
    POST /api/complications/prescan-briefing

    Returns a structured pre-scan checklist for the clinician to use
    before performing ultrasound-guided injection in a given region.

    Inspired by:
    - RSNA 2025 vascular mapping protocols
    - Journal of Cosmetic Dermatology 2025 AI-ultrasound integration
    - CMAC 2025 structured complication prevention framework
    """
    data = _match_prescan_region(payload.region)

    if not data:
        # Generic fallback
        data = {
            "label": payload.region.title(),
            "risk_level": "moderate",
            "structures_to_identify": [
                "Local arterial supply — identify named vessels for this region before injection",
                "Venous anatomy — map superficial and deep veins",
                "Any existing filler deposits from previous treatments",
                "Tissue planes — confirm depth of planned injection relative to identified structures",
            ],
            "doppler_settings": "High-frequency transducer (12–22 MHz depending on depth). B-mode + colour Doppler. Adjust gain to visualise small vessels.",
            "key_findings_to_document": [
                "Named vessels identified and their position relative to planned injection site",
                "Any pre-existing filler present",
                "Skin and subcutaneous tissue thickness",
            ],
            "safe_windows": ["Confirm injection plane is away from identified vessels"],
            "abort_criteria": ["Named vessel directly in needle path with no deviation possible"],
            "evidence_note": "Ultrasound guidance significantly reduces vascular complication rates across all injectable aesthetic procedures.",
        }

    junior_note = None
    if payload.injector_experience_level in ("junior", "intermediate"):
        junior_note = (
            "Junior/intermediate injector note: this region benefits from senior supervision "
            "when ultrasound is used for the first time. Ensure you have completed structured "
            "ultrasound training (e.g. AIA Ultrasound Fundamentals) before relying on real-time "
            "guidance for vascular avoidance in high-risk zones."
        )

    return PreScanBriefingResponse(
        request_id=str(uuid.uuid4()),
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        region_label=data["label"],
        risk_level=data["risk_level"],
        structures_to_identify=data["structures_to_identify"],
        doppler_settings=data["doppler_settings"],
        key_findings_to_document=data["key_findings_to_document"],
        safe_windows=data["safe_windows"],
        abort_criteria=data["abort_criteria"],
        evidence_note=data["evidence_note"],
        disclaimer=(
            "This pre-scan briefing is clinical decision support only. "
            "It does not replace formal ultrasound training, anatomical expertise, or clinical judgement. "
            "Ultrasound interpretation must be performed by a trained clinician."
        ),
        junior_note=junior_note,
    )
