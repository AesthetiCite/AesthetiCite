from __future__ import annotations

def normalize_evidence_level(raw: str | None) -> str:
    if not raw:
        return "Other"
    r = raw.strip().lower()
    mapping = {
        "guideline": "Guideline",
        "guidelines": "Guideline",
        "consensus": "Consensus",
        "position statement": "Consensus",
        "ifu": "IFU",
        "instructions for use": "IFU",
        "review": "Review",
        "systematic review": "Review",
        "meta-analysis": "Review",
        "rct": "RCT",
        "randomized": "RCT",
        "other": "Other",
        "textbook": "Other",
    }
    for k, v in mapping.items():
        if k in r:
            return v
    return "Other"
