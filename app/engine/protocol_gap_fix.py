from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class ProtocolRule:
    name: str
    trigger_patterns: List[str]
    mandatory_concepts: List[str]
    preferred_concepts: List[str]
    anti_drift_concepts: List[str]
    required_phrases: List[str]
    concept_boosts: Dict[str, float]


PROTOCOL_RULES: Dict[str, ProtocolRule] = {
    "delayed_inflammatory_nodules": ProtocolRule(
        name="delayed_inflammatory_nodules",
        trigger_patterns=[
            r"\bdelayed inflammatory nodules?\b",
            r"\bnodules?\b",
            r"\bfiller nodules?\b",
            r"\bpost[- ]filler nodules?\b",
            r"\binflammatory nodules?\b",
            r"\bgranuloma\b",
        ],
        mandatory_concepts=[
            "rule out infection",
            "antibiotics",
            "corticosteroids",
            "hyaluronidase",
        ],
        preferred_concepts=[
            "culture",
            "ultrasound",
            "doxycycline",
            "clarithromycin",
            "oral steroids",
            "intralesional steroid",
            "refractory cases",
            "methotrexate",
            "allopurinol",
        ],
        anti_drift_concepts=[
            "methotrexate only",
            "hyaluronidase only",
        ],
        required_phrases=[
            "Infection should be excluded first.",
            "First-line treatment commonly includes antibiotics and/or corticosteroids depending on the presentation.",
            "Hyaluronidase is considered when residual hyaluronic acid filler is suspected.",
        ],
        concept_boosts={
            "antibiotics": 0.22,
            "doxycycline": 0.18,
            "clarithromycin": 0.18,
            "corticosteroids": 0.22,
            "oral steroids": 0.18,
            "intralesional steroid": 0.18,
            "hyaluronidase": 0.18,
            "infection": 0.22,
            "biofilm": 0.15,
            "culture": 0.12,
            "ultrasound": 0.10,
            "methotrexate": 0.08,
        },
    ),
    "hyaluronidase_hypersensitivity": ProtocolRule(
        name="hyaluronidase_hypersensitivity",
        trigger_patterns=[
            r"\bhyaluronidase\b.*\ballergy\b",
            r"\bhyaluronidase\b.*\bhypersens",
            r"\bbee venom\b",
            r"\bhypersensitivity\b",
            r"\bskin testing\b",
        ],
        mandatory_concepts=[
            "allergy risk",
            "skin test",
            "intradermal test",
            "observe for reaction",
        ],
        preferred_concepts=[
            "diluted dose",
            "emergency preparedness",
            "anaphylaxis",
            "resuscitation equipment",
            "clinical caution",
        ],
        anti_drift_concepts=[
            "no testing needed",
        ],
        required_phrases=[
            "When hypersensitivity risk is a concern, intradermal skin testing with a small diluted dose should be considered before treatment.",
            "The patient should then be observed for a local or systemic hypersensitivity reaction.",
            "Emergency medications and resuscitation capability should be available when hyaluronidase is administered in at-risk patients.",
        ],
        concept_boosts={
            "skin test": 0.28,
            "intradermal": 0.24,
            "diluted dose": 0.18,
            "observe": 0.14,
            "anaphylaxis": 0.18,
            "resuscitation": 0.16,
            "bee venom": 0.18,
            "allergy": 0.20,
        },
    ),
    "botox_eyelid_ptosis": ProtocolRule(
        name="botox_eyelid_ptosis",
        trigger_patterns=[
            r"\beyelid ptosis\b",
            r"\bptosis\b",
            r"\bbotulinum\b.*\bptosis\b",
            r"\bneurotoxin\b.*\bptosis\b",
            r"\bbotox\b.*\bptosis\b",
        ],
        mandatory_concepts=[
            "apraclonidine",
            "symptomatic treatment",
            "self-limited",
        ],
        preferred_concepts=[
            "alpha-adrenergic",
            "Muller muscle",
            "temporary",
            "weeks",
            "eyelid support",
        ],
        anti_drift_concepts=[
            "supportive care only",
        ],
        required_phrases=[
            "Apraclonidine eye drops are commonly used as first-line symptomatic treatment for botulinum toxin\u2013related eyelid ptosis.",
            "The condition is usually temporary and improves as the toxin effect wears off.",
            "Patients should be counseled that treatment is supportive and recovery typically occurs over time.",
        ],
        concept_boosts={
            "apraclonidine": 0.30,
            "eye drops": 0.18,
            "Muller muscle": 0.12,
            "alpha-adrenergic": 0.12,
            "temporary": 0.10,
            "self-limited": 0.10,
            "weeks": 0.08,
        },
    ),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _contains(text: str, phrase: str) -> bool:
    return _normalize(phrase) in _normalize(text)


def detect_protocol_topic(user_query: str) -> Optional[str]:
    q = _normalize(user_query)

    if "hyaluronidase" in q and ("allergy" in q or "hypersens" in q or "bee venom" in q):
        return "hyaluronidase_hypersensitivity"

    if "ptosis" in q and ("botox" in q or "botulinum" in q or "neurotoxin" in q or "toxin" in q):
        return "botox_eyelid_ptosis"

    filler_context = any(w in q for w in ["filler", "hyaluronic", "dermal", "injection"])
    if filler_context and any(w in q for w in ["nodule", "granuloma", "inflammatory"]):
        return "delayed_inflammatory_nodules"

    if "delayed inflammatory nodule" in q or "filler nodule" in q or "post-filler nodule" in q:
        return "delayed_inflammatory_nodules"

    return None


def build_protocol_prompt_block(
    user_query: str,
    chunks: List[Dict[str, Any]],
) -> str:
    topic = detect_protocol_topic(user_query)
    if not topic or topic not in PROTOCOL_RULES:
        return ""

    rule = PROTOCOL_RULES[topic]

    joined = "\n".join(
        f"{c.get('title', '')} {c.get('text', '')} {c.get('chunk_text', '')}"
        for c in chunks
    )

    missing_mandatory = [c for c in rule.mandatory_concepts if not _contains(joined, c)]

    lines: List[str] = []
    lines.append(f"\nProtocol-sensitive topic: {rule.name}")
    lines.append("IMPORTANT protocol rules for this answer:")
    lines.append("- Prioritize clinical completeness and explicit first-line management steps.")
    lines.append("- Do not skip standard first-line interventions even if refractory options are also discussed.")

    if topic == "delayed_inflammatory_nodules":
        lines.append("- Explicitly state that infection should be excluded first.")
        lines.append("- Explicitly mention first-line antibiotics (e.g., doxycycline, clarithromycin) and/or corticosteroids.")
        lines.append("- Mention hyaluronidase when residual hyaluronic acid filler is suspected.")
        lines.append("- Position methotrexate or other immunomodulators as refractory/second-line options only.")
    elif topic == "hyaluronidase_hypersensitivity":
        lines.append("- Explicitly mention intradermal skin testing with a small diluted dose when hypersensitivity risk is relevant.")
        lines.append("- Explicitly mention observation for a reaction after testing.")
        lines.append("- Explicitly mention emergency preparedness (resuscitation equipment, emergency medications).")
    elif topic == "botox_eyelid_ptosis":
        lines.append("- Explicitly mention apraclonidine (0.5%) eye drops as first-line symptomatic treatment.")
        lines.append("- Make clear the condition is usually temporary/self-limited (typically resolves in weeks).")
        lines.append("- Mention the mechanism: apraclonidine stimulates Muller's muscle via alpha-adrenergic agonism.")

    if missing_mandatory:
        lines.append(f"- These concepts were weak in retrieved evidence but MUST be addressed: {', '.join(missing_mandatory)}.")

    return "\n".join(lines)


def rerank_chunks_for_protocol(
    user_query: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    topic = detect_protocol_topic(user_query)
    if not topic or topic not in PROTOCOL_RULES:
        return chunks

    rule = PROTOCOL_RULES[topic]

    scored = []
    for c in chunks:
        text = f"{c.get('title', '')} {c.get('text', '')} {c.get('chunk_text', '')}"
        boost = 0.0
        for concept, bonus in rule.concept_boosts.items():
            if _contains(text, concept):
                boost += bonus
        scored.append((boost, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:len(chunks)]]


def enforce_protocol_completeness(
    answer_text: str,
    user_query: str,
) -> str:
    topic = detect_protocol_topic(user_query)
    if not topic or topic not in PROTOCOL_RULES:
        return answer_text

    text = _normalize(answer_text)

    if topic == "delayed_inflammatory_nodules":
        inserts = []
        if "antibiotic" not in text:
            inserts.append("Per established consensus, antibiotics (e.g., doxycycline, clarithromycin) should be considered when infection or biofilm-related involvement is suspected.")
        if "corticosteroid" not in text and "steroid" not in text:
            inserts.append("Per established consensus, corticosteroids (oral or intralesional) are commonly part of first-line management when inflammatory nodules predominate.")
        if "hyaluronidase" not in text:
            inserts.append("Per established consensus, hyaluronidase should be considered when residual hyaluronic acid filler is suspected.")
        if inserts:
            answer_text += "\n\n**Standard Protocol Reminder** *(per published consensus guidelines)*:\n- " + "\n- ".join(inserts)

    elif topic == "hyaluronidase_hypersensitivity":
        inserts = []
        if "skin test" not in text and "intradermal" not in text:
            inserts.append("Per established guidance, intradermal skin testing with a small diluted dose should be considered before full treatment in at-risk patients.")
        if "observe" not in text and "observation" not in text and "monitor" not in text:
            inserts.append("Per established guidance, the patient should be observed for a hypersensitivity reaction after testing.")
        if "resuscitation" not in text and "emergency" not in text and "epinephrine" not in text:
            inserts.append("Per established guidance, emergency medications and resuscitation capability should be available when hyaluronidase is administered in at-risk patients.")
        if inserts:
            answer_text += "\n\n**Standard Protocol Reminder** *(per published consensus guidelines)*:\n- " + "\n- ".join(inserts)

    elif topic == "botox_eyelid_ptosis":
        if "apraclonidine" not in text:
            answer_text += (
                "\n\n**Standard Protocol Reminder** *(per published consensus guidelines)*:\n"
                "- Apraclonidine (0.5%) eye drops are commonly used as first-line symptomatic treatment for botulinum toxin\u2013related eyelid ptosis, "
                "stimulating Muller's muscle via alpha-adrenergic agonism to temporarily elevate the eyelid."
            )

    return answer_text


def build_enhanced_answer_context(
    user_query: str,
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    topic = detect_protocol_topic(user_query)
    if not topic:
        return {
            "topic": None,
            "reranked_chunks": chunks,
            "protocol_prompt_block": "",
            "coverage_gaps": [],
        }

    reranked = rerank_chunks_for_protocol(user_query, chunks)
    prompt_block = build_protocol_prompt_block(user_query, reranked)

    rule = PROTOCOL_RULES.get(topic)
    coverage_gaps = []
    if rule:
        joined = "\n".join(
            f"{c.get('title', '')} {c.get('text', '')} {c.get('chunk_text', '')}"
            for c in reranked
        )
        coverage_gaps = [
            c for c in rule.mandatory_concepts if not _contains(joined, c)
        ]

    return {
        "topic": topic,
        "reranked_chunks": reranked,
        "protocol_prompt_block": prompt_block,
        "coverage_gaps": coverage_gaps,
    }


def generate_answer_with_gap_fix(
    user_query: str,
    user_language: str,
    retrieved_docs: List[Dict[str, Any]],
    llm_generate_fn: Callable[[str, str], str],
) -> Dict[str, Any]:
    ctx = build_enhanced_answer_context(user_query, retrieved_docs)

    prompt_addition = ctx["protocol_prompt_block"]
    answer_text = llm_generate_fn(user_query, prompt_addition)

    answer_text = enforce_protocol_completeness(answer_text, user_query)

    return {
        "answer_text": answer_text,
        "topic": ctx["topic"],
        "coverage_gaps": ctx["coverage_gaps"],
        "reranked_chunks": ctx["reranked_chunks"],
    }
