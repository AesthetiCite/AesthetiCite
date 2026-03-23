"""
Evidence Grading System for AesthetiCite

Implements a structured evidence classification system based on:
- Oxford Centre for Evidence-Based Medicine (OCEBM) levels
- GRADE (Grading of Recommendations Assessment, Development and Evaluation)

Evidence Levels:
- Level I: High-quality systematic reviews, meta-analyses, RCTs
- Level II: Lower-quality RCTs, prospective cohort studies
- Level III: Case-control studies, retrospective cohort studies
- Level IV: Case series, case reports, expert opinion
"""

import re
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(Enum):
    LEVEL_I = "I"
    LEVEL_II = "II"
    LEVEL_III = "III"
    LEVEL_IV = "IV"
    UNKNOWN = "?"


@dataclass
class EvidenceGrade:
    level: EvidenceLevel
    label: str
    description: str
    confidence: float  # 0.0 to 1.0
    study_type: Optional[str] = None


LEVEL_DESCRIPTIONS = {
    EvidenceLevel.LEVEL_I: {
        "label": "High Quality",
        "description": "Systematic review, meta-analysis, or well-designed RCT",
        "color": "#10b981"  # Green
    },
    EvidenceLevel.LEVEL_II: {
        "label": "Moderate Quality", 
        "description": "Lower-quality RCT or prospective cohort study",
        "color": "#3b82f6"  # Blue
    },
    EvidenceLevel.LEVEL_III: {
        "label": "Low Quality",
        "description": "Case-control or retrospective cohort study",
        "color": "#f59e0b"  # Amber
    },
    EvidenceLevel.LEVEL_IV: {
        "label": "Very Low Quality",
        "description": "Case series, case report, or expert opinion",
        "color": "#6b7280"  # Gray
    },
    EvidenceLevel.UNKNOWN: {
        "label": "Ungraded",
        "description": "Evidence level not determined",
        "color": "#9ca3af"
    }
}

# Keywords for study type detection
STUDY_TYPE_KEYWORDS = {
    "systematic_review": [
        "systematic review", "meta-analysis", "meta analysis", 
        "pooled analysis", "cochrane", "prisma"
    ],
    "rct": [
        "randomized controlled trial", "randomised controlled trial",
        "rct", "double-blind", "double blind", "placebo-controlled",
        "randomized clinical trial", "randomised clinical trial"
    ],
    "prospective_cohort": [
        "prospective cohort", "prospective study", "longitudinal study",
        "follow-up study", "prospective analysis"
    ],
    "retrospective_cohort": [
        "retrospective cohort", "retrospective study", "retrospective analysis",
        "chart review", "medical record review"
    ],
    "case_control": [
        "case-control", "case control", "matched controls"
    ],
    "case_series": [
        "case series", "consecutive cases", "consecutive patients"
    ],
    "case_report": [
        "case report", "case presentation", "clinical case"
    ],
    "review": [
        "narrative review", "literature review", "review article"
    ],
    "guideline": [
        "guideline", "consensus", "recommendation", "expert panel",
        "position statement", "practice advisory"
    ],
    "expert_opinion": [
        "expert opinion", "commentary", "editorial", "letter"
    ]
}

# Mapping study types to evidence levels
STUDY_TYPE_TO_LEVEL = {
    "systematic_review": EvidenceLevel.LEVEL_I,
    "rct": EvidenceLevel.LEVEL_I,
    "prospective_cohort": EvidenceLevel.LEVEL_II,
    "retrospective_cohort": EvidenceLevel.LEVEL_III,
    "case_control": EvidenceLevel.LEVEL_III,
    "case_series": EvidenceLevel.LEVEL_IV,
    "case_report": EvidenceLevel.LEVEL_IV,
    "review": EvidenceLevel.LEVEL_IV,
    "guideline": EvidenceLevel.LEVEL_II,  # Guidelines can be high quality
    "expert_opinion": EvidenceLevel.LEVEL_IV
}


def detect_study_type(text: str, title: str = "") -> Optional[str]:
    """
    Detect the study type from text content and title.
    Returns the study type key or None if not detected.
    """
    combined = f"{title.lower()} {text.lower()[:3000]}"
    
    # Check each study type in order of specificity (most specific first)
    priority_order = [
        "systematic_review", "rct", "prospective_cohort", 
        "retrospective_cohort", "case_control", "case_series",
        "case_report", "guideline", "review", "expert_opinion"
    ]
    
    for study_type in priority_order:
        keywords = STUDY_TYPE_KEYWORDS[study_type]
        for keyword in keywords:
            if keyword in combined:
                return study_type
    
    return None


def grade_evidence(
    text: str, 
    title: str = "",
    document_type: Optional[str] = None,
    journal: Optional[str] = None
) -> EvidenceGrade:
    """
    Grade the evidence level of a source based on its content and metadata.
    
    Args:
        text: The document text content
        title: Document title
        document_type: Optional document type from metadata
        journal: Optional journal name
    
    Returns:
        EvidenceGrade with level, description, and confidence
    """
    # Detect study type from content
    study_type = detect_study_type(text, title)
    
    # Use document_type hint if provided
    if not study_type and document_type:
        doc_type_lower = document_type.lower()
        for st, keywords in STUDY_TYPE_KEYWORDS.items():
            if any(kw in doc_type_lower for kw in keywords):
                study_type = st
                break
    
    # Determine evidence level
    if study_type:
        level = STUDY_TYPE_TO_LEVEL[study_type]
        confidence = 0.8 if study_type in ["systematic_review", "rct"] else 0.6
    else:
        # Default to Level IV with low confidence
        level = EvidenceLevel.LEVEL_IV
        study_type = "unknown"
        confidence = 0.3
    
    # Boost confidence for high-impact journals
    high_impact_journals = [
        "jama", "nejm", "lancet", "bmj", "nature", "science",
        "dermatologic surgery", "aesthetic surgery journal",
        "plastic and reconstructive surgery"
    ]
    if journal:
        journal_lower = journal.lower()
        if any(hj in journal_lower for hj in high_impact_journals):
            confidence = min(1.0, confidence + 0.1)
    
    level_info = LEVEL_DESCRIPTIONS[level]
    
    return EvidenceGrade(
        level=level,
        label=level_info["label"],
        description=level_info["description"],
        confidence=confidence,
        study_type=study_type
    )


def format_evidence_badge(grade: EvidenceGrade) -> Dict:
    """
    Format evidence grade as a badge for frontend display.
    """
    level_info = LEVEL_DESCRIPTIONS[grade.level]
    return {
        "level": grade.level.value,
        "label": grade.label,
        "description": grade.description,
        "color": level_info["color"],
        "study_type": grade.study_type,
        "confidence": round(grade.confidence, 2)
    }


def aggregate_evidence_levels(grades: List[EvidenceGrade]) -> Dict:
    """
    Aggregate multiple evidence grades to provide an overall assessment.
    """
    if not grades:
        return {
            "overall_level": "?",
            "highest_level": "?",
            "level_counts": {},
            "average_confidence": 0.0
        }
    
    level_counts = {}
    confidences = []
    
    for grade in grades:
        level_val = grade.level.value
        level_counts[level_val] = level_counts.get(level_val, 0) + 1
        confidences.append(grade.confidence)
    
    # Determine highest level (I > II > III > IV)
    priority = ["I", "II", "III", "IV", "?"]
    highest = "?"
    for p in priority:
        if p in level_counts:
            highest = p
            break
    
    # Overall level is the most common high-quality level
    overall = highest
    if level_counts.get("I", 0) >= 2:
        overall = "I"
    elif level_counts.get("II", 0) >= 2:
        overall = "II"
    elif level_counts.get("III", 0) >= 2:
        overall = "III"
    
    return {
        "overall_level": overall,
        "highest_level": highest,
        "level_counts": level_counts,
        "average_confidence": round(sum(confidences) / len(confidences), 2)
    }


def get_evidence_summary_text(aggregate: Dict) -> str:
    """
    Generate a human-readable summary of evidence quality.
    """
    level = aggregate.get("overall_level", "?")
    counts = aggregate.get("level_counts", {})
    
    total = sum(counts.values())
    high_quality = counts.get("I", 0) + counts.get("II", 0)
    
    if level == "I":
        return f"Supported by high-quality evidence ({high_quality}/{total} sources are Level I-II)"
    elif level == "II":
        return f"Supported by moderate-quality evidence ({high_quality}/{total} sources are Level I-II)"
    elif level == "III":
        return f"Limited evidence quality ({counts.get('III', 0)}/{total} sources are Level III)"
    elif level == "IV":
        return f"Based primarily on case reports and expert opinion"
    else:
        return "Evidence quality could not be determined"
