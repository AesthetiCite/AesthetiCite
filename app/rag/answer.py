from __future__ import annotations
from typing import List, Dict, Optional, Tuple
from app.core.config import settings
from app.core.evidence_grading import (
    grade_evidence, 
    aggregate_evidence_levels, 
    get_evidence_summary_text,
    format_evidence_badge,
    EvidenceGrade
)

def build_answer(
    question: str,
    mode: str,
    domain: str,
    retrieved: List[Dict],
    escalation_note: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """
    OpenEvidence-style answer with inline numbered citations [1], [2], etc.
    Returns (answer_text, related_questions)
    """
    if not retrieved:
        return _build_no_evidence_answer(domain, escalation_note), []

    citation_map = {}
    for i, r in enumerate(retrieved[:8]):
        source_id = r.get("source_id", f"source_{i}")
        if source_id not in citation_map:
            citation_map[source_id] = len(citation_map) + 1

    key_points = []
    for r in retrieved[:6]:
        txt = " ".join((r.get("text") or "").split())
        if not txt or len(txt) < 50:
            continue
        
        source_id = r.get("source_id", "")
        cite_num = citation_map.get(source_id, 1)
        
        snippet = _extract_key_sentence(txt, question)
        if snippet:
            key_points.append(f"{snippet} [{cite_num}]")

    if mode == "deep_dive":
        answer = _build_deep_dive_answer(question, domain, key_points, retrieved, citation_map, escalation_note)
    else:
        answer = _build_clinic_answer(question, domain, key_points, retrieved, citation_map, escalation_note)

    related = _generate_related_questions(question, domain, retrieved)

    return answer, related


def _extract_key_sentence(text: str, question: str) -> str:
    """Extract the most relevant sentence or key finding from text."""
    sentences = text.replace("…", ".").split(". ")
    
    q_lower = question.lower()
    keywords = [w for w in q_lower.split() if len(w) > 3]
    
    best_sentence = ""
    best_score = 0
    
    for sent in sentences:
        if len(sent) < 30 or len(sent) > 300:
            continue
        sent_lower = sent.lower()
        score = sum(1 for kw in keywords if kw in sent_lower)
        
        if any(w in sent_lower for w in ["recommend", "guideline", "consensus", "suggest", "evidence", "study", "found", "showed"]):
            score += 2
        if any(w in sent_lower for w in ["dosing", "dose", "concentration", "protocol", "treatment"]):
            score += 1
            
        if score > best_score:
            best_score = score
            best_sentence = sent.strip()
    
    if not best_sentence and sentences:
        for sent in sentences:
            if 50 < len(sent) < 250:
                best_sentence = sent.strip()
                break
    
    if best_sentence and not best_sentence.endswith((".", "?", "!")):
        best_sentence += "."
    
    return best_sentence[:280] if best_sentence else ""


def _build_clinic_answer(
    question: str,
    domain: str,
    key_points: List[str],
    retrieved: List[Dict],
    citation_map: Dict[str, int],
    escalation_note: Optional[str],
) -> str:
    """Build concise clinic-mode answer with inline citations."""
    
    sections = []
    
    sections.append("**Clinical Summary**")
    sections.append("")
    
    if key_points:
        sections.append("**Key Findings:**")
        for point in key_points[:4]:
            sections.append(f"- {point}")
        sections.append("")
    
    sections.append("**Recommendations:**")
    recommendations = _extract_recommendations(retrieved)
    if recommendations:
        for rec in recommendations[:3]:
            source_id = rec.get("source_id", "")
            cite_num = citation_map.get(source_id, 1)
            sections.append(f"- {rec['text']} [{cite_num}]")
    else:
        sections.append("- Consult retrieved sources for specific protocol guidance.")
    sections.append("")
    
    sections.append("**Safety Note:**")
    if escalation_note:
        sections.append(f"- {escalation_note}")
    sections.append("- For time-critical emergencies (ischemia, vision symptoms), follow local emergency protocols immediately.")
    sections.append("- This summary does not replace clinical judgment.")
    
    return "\n".join(sections)


def _build_deep_dive_answer(
    question: str,
    domain: str,
    key_points: List[str],
    retrieved: List[Dict],
    citation_map: Dict[str, int],
    escalation_note: Optional[str],
) -> str:
    """Build comprehensive deep-dive answer with detailed evidence."""
    
    sections = []
    
    sections.append("**Evidence Summary**")
    sections.append("")
    
    sections.append("**Background:**")
    background = _extract_background(retrieved)
    if background:
        source_id = background.get("source_id", "")
        cite_num = citation_map.get(source_id, 1)
        sections.append(f"{background['text']} [{cite_num}]")
    sections.append("")
    
    if key_points:
        sections.append("**Key Evidence:**")
        for point in key_points[:6]:
            sections.append(f"- {point}")
        sections.append("")
    
    sections.append("**Clinical Implications:**")
    recommendations = _extract_recommendations(retrieved)
    if recommendations:
        for rec in recommendations[:4]:
            source_id = rec.get("source_id", "")
            cite_num = citation_map.get(source_id, 1)
            sections.append(f"- {rec['text']} [{cite_num}]")
    sections.append("")
    
    sections.append("**Evidence Quality:**")
    grades = []
    for r in retrieved[:6]:
        text = r.get("text", "")
        title = r.get("title", "")
        doc_type = r.get("document_type", "")
        journal = r.get("organization_or_journal", "")
        grade = grade_evidence(text, title, doc_type, journal)
        grades.append(grade)
    
    aggregate = aggregate_evidence_levels(grades)
    evidence_summary = get_evidence_summary_text(aggregate)
    sections.append(f"- {evidence_summary}")
    
    level_counts = aggregate.get("level_counts", {})
    if level_counts:
        level_breakdown = ", ".join([f"Level {k}: {v}" for k, v in sorted(level_counts.items())])
        sections.append(f"- Evidence breakdown: {level_breakdown}")
    sections.append("")
    
    sections.append("**Limitations:**")
    sections.append("- This synthesis reflects retrieved evidence only.")
    sections.append("- Consult original sources and local protocols for definitive guidance.")
    if escalation_note:
        sections.append(f"- Note: {escalation_note}")
    
    return "\n".join(sections)


def _build_no_evidence_answer(domain: str, escalation_note: Optional[str]) -> str:
    """Answer when no evidence is retrieved."""
    sections = [
        "**Insufficient Evidence**",
        "",
        "The knowledge base did not contain sufficient evidence to answer this question with citations.",
        "",
        "**Recommendations:**",
        "- Consult primary literature sources (PubMed, specialty journals)",
        "- Review institutional protocols and guidelines",
        "- Consider expert consultation for complex cases",
    ]
    if escalation_note:
        sections.append(f"- Note: {escalation_note}")
    return "\n".join(sections)


def _extract_recommendations(retrieved: List[Dict]) -> List[Dict]:
    """Extract recommendation-like statements from retrieved text."""
    recommendations = []
    rec_keywords = ["recommend", "should", "suggest", "guideline", "protocol", "advised", "indicated", "treatment of choice"]
    
    for r in retrieved[:6]:
        text = r.get("text", "")
        sentences = text.split(". ")
        for sent in sentences:
            sent_lower = sent.lower()
            if any(kw in sent_lower for kw in rec_keywords) and 40 < len(sent) < 250:
                recommendations.append({
                    "text": sent.strip() + ("." if not sent.endswith(".") else ""),
                    "source_id": r.get("source_id", "")
                })
                break
    
    return recommendations[:4]


def _extract_background(retrieved: List[Dict]) -> Optional[Dict]:
    """Extract a background/context sentence."""
    for r in retrieved[:4]:
        text = r.get("text", "")
        sentences = text.split(". ")
        for sent in sentences:
            if 60 < len(sent) < 200:
                return {
                    "text": sent.strip() + ("." if not sent.endswith(".") else ""),
                    "source_id": r.get("source_id", "")
                }
    return None


def _generate_related_questions(question: str, domain: str, retrieved: List[Dict]) -> List[str]:
    """Generate related follow-up questions based on the topic."""
    q_lower = question.lower()
    related = []
    
    if "hyaluronidase" in q_lower or "dissolve" in q_lower or "dissolving" in q_lower:
        related.extend([
            "What is the recommended hyaluronidase concentration for filler dissolution?",
            "How long should I wait between hyaluronidase injections?",
            "What are the signs of posthyaluronidase syndrome?",
        ])
    
    if "vascular" in q_lower or "occlusion" in q_lower or "ischemia" in q_lower:
        related.extend([
            "What are the early signs of vascular occlusion after filler injection?",
            "How quickly should treatment be initiated for vascular compromise?",
            "What is the role of aspirin in managing filler-induced vascular occlusion?",
        ])
    
    if "vision" in q_lower or "blind" in q_lower or "eye" in q_lower:
        related.extend([
            "What is the mechanism of filler-induced vision loss?",
            "Is retrobulbar hyaluronidase effective for filler-induced blindness?",
            "Which injection sites have the highest risk of vision complications?",
        ])
    
    if "necrosis" in q_lower or "skin" in q_lower:
        related.extend([
            "What are the stages of filler-induced skin necrosis?",
            "How should skin necrosis from fillers be managed?",
            "What is the role of hyperbaric oxygen in treating filler necrosis?",
        ])
    
    if "dose" in q_lower or "dosing" in q_lower or "concentration" in q_lower:
        related.extend([
            "What factors affect hyaluronidase dosing requirements?",
            "Should high-dose or low-dose hyaluronidase protocols be used?",
            "How does filler type affect dissolution requirements?",
        ])
    
    if "cannula" in q_lower or "needle" in q_lower:
        related.extend([
            "What evidence supports cannula over needle for filler safety?",
            "In which facial zones is cannula preferred over needle?",
            "What are the limitations of cannula use for fillers?",
        ])
    
    if not related:
        related = [
            "What are the most common complications of dermal fillers?",
            "What are the high-risk zones for facial filler injection?",
            "What is the recommended emergency kit for filler practitioners?",
        ]
    
    seen = set()
    unique = []
    for q in related:
        if q.lower() not in seen and q.lower() != question.lower():
            seen.add(q.lower())
            unique.append(q)
    
    return unique[:3]
