"""
Rubric Auto-Fill
================
Automatically fills documentation rubric from generated note text.
Conservative defaults: set True only if we see strong signals.
Clinician can still edit.
"""

import re
from typing import Dict

RUBRIC_KEYS = [
    "consent_documented",
    "risks_discussed",
    "product_documented",
    "dose_or_volume_documented",
    "technique_documented",
    "aftercare_documented",
    "follow_up_plan",
    "complication_assessed",
    "red_flags_documented",
    "escalation_rationale",
]


def autofill_rubric_from_note(note_text: str) -> Dict[str, bool]:
    """
    Extract rubric defaults from generated note text.
    
    Conservative defaults: set True only if we see strong signals.
    Clinician can still edit before final submission.
    
    Returns:
        Dict with all 10 rubric keys and boolean values.
    """
    t = (note_text or "").lower()

    def has_any(*patterns: str) -> bool:
        return any(re.search(p, t) for p in patterns)

    rubric = {k: False for k in RUBRIC_KEYS}

    rubric["consent_documented"] = has_any(
        r"\bconsent\b", 
        r"\binformed consent\b"
    )
    
    rubric["risks_discussed"] = has_any(
        r"\brisks?\b", 
        r"\brare serious\b", 
        r"\bvascular\b", 
        r"\bptosis\b", 
        r"\binfection\b",
        r"\bocclusion\b",
        r"\bblindness\b"
    )
    
    rubric["product_documented"] = has_any(
        r"\bproduct:\b",
        r"\bjuvederm\b",
        r"\brestylane\b",
        r"\bbotox\b",
        r"\bdysport\b",
        r"\bsculptra\b",
        r"\bradiesse\b"
    )
    
    rubric["dose_or_volume_documented"] = has_any(
        r"dose/volume:", 
        r"\bdose:\b",
        r"\bunits?\b", 
        r"\d+\s*ml\b",
        r"\d+\s*cc\b",
        r"\bsyringe\b",
        r"\bvolume:\b"
    )
    
    rubric["technique_documented"] = has_any(
        r"\btechnique:\b", 
        r"\bplane\b", 
        r"\bcannula\b", 
        r"\bneedle\b",
        r"\binjection site\b",
        r"\bbolus\b",
        r"\blinear threading\b",
        r"\bfanning\b"
    )
    
    rubric["aftercare_documented"] = has_any(
        r"\baftercare:\b", 
        r"\bpost-procedure\b",
        r"\bice\b",
        r"\bavoid\b",
        r"\bpressure\b",
        r"\bmassage\b"
    )
    
    rubric["follow_up_plan"] = has_any(
        r"\bfollow-up\b", 
        r"\bfollow up\b", 
        r"\b48h\b", 
        r"\b24h\b", 
        r"\bweek\b",
        r"\breturn\b",
        r"\bcheck\b",
        r"\breview\b"
    )
    
    rubric["complication_assessed"] = has_any(
        r"\bcomplication\b", 
        r"\bassessment\b", 
        r"\bsuspected complication\b",
        r"\badverse\b",
        r"\breaction\b"
    )
    
    rubric["red_flags_documented"] = has_any(
        r"\bred flags?\b", 
        r"\bsevere pain\b", 
        r"\bblanch\w*\b", 
        r"\bvision\b", 
        r"\bneurolog\w*\b",
        r"\bstroke\b",
        r"\bblindness\b",
        r"\bpain out of proportion\b"
    )
    
    rubric["escalation_rationale"] = has_any(
        r"\bescalation\b", 
        r"\breferral\b", 
        r"\bconsult\b", 
        r"\bemergency\b",
        r"\btransfer\b",
        r"\bophthalmolog\w*\b",
        r"\bsenior\b"
    )

    return rubric


def get_rubric_completion_percent(rubric: Dict[str, bool]) -> float:
    """Calculate completion percentage from rubric dict."""
    total = len(RUBRIC_KEYS)
    present = sum(1 for k in RUBRIC_KEYS if rubric.get(k))
    return round(100.0 * present / total, 1)
