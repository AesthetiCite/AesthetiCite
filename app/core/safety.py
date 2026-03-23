import re
from dataclasses import dataclass
from typing import Optional

MAX_QUESTION_LENGTH = 1200

HIGH_RISK_KEYWORDS = [
    "blindness", "vision loss", "stroke", "necrosis", "ischemia",
    "nécrose", "ischémie", "cécité", "perte de vision",
    "vascular occlusion", "occlusion vasculaire",
]

INJECTION_PATTERNS = re.compile(
    r"(system\s*:|assistant\s*:|<\|im_start\|>|<\|im_end\|>|<<SYS>>|<</SYS>>|"
    r"\[INST\]|\[/INST\]|ignore previous instructions|forget your instructions)",
    re.IGNORECASE,
)


@dataclass
class SafetyResult:
    allowed: bool
    refusal_reason: Optional[str] = None
    escalation_note: Optional[str] = None


def sanitize_input(q: str) -> str:
    q = q.strip()
    if len(q) > MAX_QUESTION_LENGTH:
        q = q[:MAX_QUESTION_LENGTH]
    q = INJECTION_PATTERNS.sub("", q)
    return q.strip()


def safety_screen(question: str) -> SafetyResult:
    q = sanitize_input(question).lower()

    if len(q) < 5:
        return SafetyResult(False, "Question too short to assess safely.")

    escalation = None
    if any(k in q for k in HIGH_RISK_KEYWORDS):
        escalation = (
            "High-risk complication context detected. "
            "If any red flags are present (e.g., visual symptoms, rapidly worsening pain, expanding ischemia), "
            "initiate urgent escalation per local emergency pathways. "
            "This system provides evidence summaries and does not replace clinical judgment."
        )

    return SafetyResult(True, escalation_note=escalation)
