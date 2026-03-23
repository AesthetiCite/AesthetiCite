"""
AesthetiCite — MCQ Exam Mode
============================
Specialized answering mode for multiple-choice medical exam questions.
Designed to match OpenEvidence's 100% USMLE performance.
"""

from __future__ import annotations

import re
import json
import logging
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


def llm_text(system: str, user: str, temperature: float = 0.0) -> str:
    from app.openai_wiring import llm_text as _llm_text
    return _llm_text(system, user, temperature=temperature)


def llm_json(system: str, user: str, temperature: float = 0.0) -> dict:
    txt = llm_text(system, user, temperature=temperature).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        txt = m.group(0)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {txt[:300]}")
        return {}


MCQ_SYSTEM_PROMPT = """You are a medical expert taking a USMLE-style medical licensing examination.
You must select the SINGLE BEST answer from the options provided.

Your response MUST be valid JSON in this exact format:
{
  "selected_answer": "A",
  "confidence": 0.95,
  "reasoning": "Brief explanation of why this is correct",
  "key_concept": "The medical concept being tested"
}

Rules:
1. selected_answer MUST be exactly one letter: A, B, C, or D
2. confidence is 0.0 to 1.0
3. Use the evidence provided to support your answer
4. If evidence is insufficient, use your medical knowledge but lower confidence
5. ALWAYS pick the SINGLE BEST answer - never refuse to answer

Important medical exam strategies:
- Read the question stem carefully for key clinical clues
- Eliminate obviously wrong answers first
- Consider mechanism of action for pharmacology questions
- Think anatomically for procedural questions
- Safety-critical answers often involve immediate interventions
"""


def format_evidence_for_mcq(chunks: List[dict], max_chunks: int = 8) -> str:
    """Format retrieved evidence chunks for MCQ answering."""
    if not chunks:
        return "No specific evidence retrieved. Use general medical knowledge."
    
    lines = []
    seen = set()
    for c in chunks[:max_chunks]:
        title = c.get("title", "Unknown")
        if title in seen:
            continue
        seen.add(title)
        
        text = (c.get("text") or "")[:600]
        source_type = c.get("source_type", "other")
        year = c.get("year", "")
        
        lines.append(f"[{source_type}] {title} ({year})")
        lines.append(f"  {text[:400]}...")
        lines.append("")
    
    return "\n".join(lines)


def answer_mcq(
    question: str,
    options: List[str],
    retrieve_chunks: Callable[[str, Optional[dict], Optional[int]], List[dict]],
    filters: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Answer a multiple-choice question in exam mode.
    Returns the selected answer letter and reasoning.
    """
    chunks = retrieve_chunks(question, filters, 20) or []
    
    evidence_text = format_evidence_for_mcq(chunks, max_chunks=8)
    
    options_text = "\n".join(options)
    
    user_prompt = f"""QUESTION:
{question}

OPTIONS:
{options_text}

RELEVANT EVIDENCE:
{evidence_text}

Select the SINGLE BEST answer. Return JSON only."""

    result = llm_json(MCQ_SYSTEM_PROMPT, user_prompt, temperature=0.0)
    
    selected = result.get("selected_answer", "").upper().strip()
    if selected not in ["A", "B", "C", "D"]:
        for letter in ["A", "B", "C", "D"]:
            if letter in str(result).upper():
                selected = letter
                break
        if selected not in ["A", "B", "C", "D"]:
            selected = "B"
    
    return {
        "selected_answer": selected,
        "confidence": result.get("confidence", 0.5),
        "reasoning": result.get("reasoning", ""),
        "key_concept": result.get("key_concept", ""),
        "evidence_used": len(chunks),
    }


def run_mcq_benchmark(
    questions: List[dict],
    retrieve_chunks: Callable[[str, Optional[dict], Optional[int]], List[dict]],
    filters: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Run a full MCQ benchmark.
    
    Each question should have:
    - question: str
    - options: List[str] (e.g., ["A. ...", "B. ...", "C. ...", "D. ..."])
    - correct_answer: str (e.g., "A")
    - expected_keywords: List[str] (optional)
    """
    import time
    
    results = []
    correct = 0
    t0 = time.time()
    
    for q in questions:
        start = time.time()
        
        out = answer_mcq(
            question=q["question"],
            options=q["options"],
            retrieve_chunks=retrieve_chunks,
            filters=filters,
        )
        
        latency_ms = int((time.time() - start) * 1000)
        
        is_correct = out["selected_answer"] == q["correct_answer"]
        if is_correct:
            correct += 1
        
        kw_found = 0
        kw_total = len(q.get("expected_keywords", []))
        if kw_total > 0:
            reasoning = (out.get("reasoning") or "").lower()
            for kw in q.get("expected_keywords", []):
                if kw.lower() in reasoning:
                    kw_found += 1
        
        results.append({
            "id": q.get("id", ""),
            "category": q.get("category", ""),
            "correct_answer": q["correct_answer"],
            "selected_answer": out["selected_answer"],
            "is_correct": is_correct,
            "confidence": out.get("confidence", 0),
            "reasoning": out.get("reasoning", "")[:200],
            "keyword_match": kw_found / max(1, kw_total) if kw_total > 0 else 1.0,
            "latency_ms": latency_ms,
        })
    
    elapsed_ms = int((time.time() - t0) * 1000)
    accuracy = correct / max(1, len(questions))
    
    by_cat = {}
    for r in results:
        cat = r.get("category", "general")
        by_cat.setdefault(cat, []).append(r)
    
    cat_accuracy = {
        c: round(sum(1 for x in xs if x["is_correct"]) / len(xs) * 100, 1)
        for c, xs in by_cat.items()
    }
    
    return {
        "total_questions": len(questions),
        "correct": correct,
        "accuracy_percent": round(accuracy * 100, 1),
        "avg_confidence": round(sum(r["confidence"] for r in results) / max(1, len(results)), 2),
        "avg_latency_ms": int(sum(r["latency_ms"] for r in results) / max(1, len(results))),
        "elapsed_ms": elapsed_ms,
        "category_accuracy": cat_accuracy,
        "results": results,
    }
