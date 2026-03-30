"""
AesthetiCite Self-RAG Engine
==============================
Implements improvements #1, #3, #14 from the benchmark:
  #1  — Agentic/iterative RAG: retrieval reformulates when evidence is insufficient
  #3  — Clinical confidence calibration: embeds uncertainty language into answers
  #14 — Self-RAG pattern: grounding classifier reduces hallucination to ~5.8%

Architecture
------------
Standard VeriDoc retrieval → SelfRAGEvaluator checks sufficiency →
if insufficient: query reformulator creates sub-query → second retrieval →
merge + dedupe → answer synthesis with calibrated confidence language

Integration — call wrap_with_self_rag() in ask_v2.py before answer synthesis:

    from app.engine.self_rag import wrap_with_self_rag

    # After initial retrieval:
    enhanced_chunks, self_rag_meta = await wrap_with_self_rag(
        question=question,
        initial_chunks=chunks,
        retrieve_fn=retrieve_db,
        max_iterations=2,
    )
    # enhanced_chunks replaces chunks in the answer synthesis call
    # self_rag_meta contains iteration info to include in meta SSE event
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")

# ─── Tuneable constants ────────────────────────────────────────────────────────
MAX_SELF_RAG_ITERATIONS = int(os.environ.get("SELF_RAG_MAX_ITER", "2"))
SUFFICIENCY_THRESHOLD   = float(os.environ.get("SELF_RAG_THRESHOLD", "0.55"))
SELF_RAG_ENABLED        = os.environ.get("SELF_RAG_ENABLED", "true").lower() == "true"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sufficiency evaluator
#    Classifies whether retrieved chunks sufficiently ground the question.
#    Returns a score 0.0–1.0 and a reformulation hint if insufficient.
# ─────────────────────────────────────────────────────────────────────────────

_SUFFICIENCY_SYSTEM = """You are a medical evidence evaluator.
Given a clinical question and a list of retrieved document snippets,
assess whether the evidence is sufficient to answer the question confidently.

Respond ONLY with valid JSON:
{
  "sufficient": true | false,
  "confidence": 0.0-1.0,
  "gap": "brief description of what evidence is missing, or null if sufficient",
  "reformulation": "a more specific sub-query that would find the missing evidence, or null if sufficient",
  "calibration_note": "one sentence for the LLM to express in the answer about evidence quality"
}

Rules:
- sufficient=true only if there is at least one guideline, RCT, or systematic review directly relevant to the question.
- For complication/safety questions, require at least 2 sources.
- Be conservative: if evidence is old (>8 years) or only case reports, mark as insufficient or set confidence<0.6."""


async def _evaluate_sufficiency(
    question: str,
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Call GPT-4o-mini to assess if retrieved chunks are sufficient to answer.
    Falls back gracefully (returns sufficient=True) if the call fails.
    """
    snippets = []
    for i, ch in enumerate(chunks[:8]):
        t = (ch.get("title") or "")[:80]
        x = (ch.get("text") or "")[:200]
        et = ch.get("evidence_type") or ch.get("source_type") or "unknown"
        y = ch.get("year") or ""
        snippets.append(f"[{i+1}] ({et}, {y}) {t}: {x}")

    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved evidence ({len(snippets)} chunks):\n"
        + "\n".join(snippets)
    )

    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": _SUFFICIENCY_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                         "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"[SelfRAG] Sufficiency eval failed: {e}")
        return {
            "sufficient": True,
            "confidence": 0.5,
            "gap": None,
            "reformulation": None,
            "calibration_note": "Evidence quality could not be automatically assessed.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Calibration note injector
#    Improvement #3: embeds confidence language into the answer prompt
#    so the LLM expresses appropriate uncertainty.
# ─────────────────────────────────────────────────────────────────────────────

CALIBRATION_TEMPLATES = {
    "high": (
        "Evidence for this answer is strong (guideline or RCT level). "
        "State your answer with appropriate clinical confidence."
    ),
    "moderate": (
        "Evidence is moderate (observational studies or expert consensus). "
        "Qualify key claims with phrases like 'evidence suggests' or 'based on current data'."
    ),
    "low": (
        "Evidence is limited (case reports or extrapolation). "
        "Explicitly note this limitation: state 'Limited evidence exists for...' "
        "or 'This recommendation is based on expert opinion only.'"
    ),
    "insufficient": (
        "Retrieved evidence is insufficient to fully answer this question. "
        "Be explicit: state exactly which aspects lack evidence and what additional "
        "information a clinician should seek."
    ),
}


def build_calibration_block(
    eval_result: Dict[str, Any],
    aci_score: Optional[float] = None,
) -> str:
    """
    Builds the calibration instruction block to prepend to the answer synthesis prompt.
    This is Improvement #3: calibrated confidence embedded into prompts.
    """
    confidence = eval_result.get("confidence", 0.5)
    sufficient  = eval_result.get("sufficient", True)
    cal_note    = eval_result.get("calibration_note", "")

    if not sufficient or confidence < 0.3:
        level = "insufficient"
    elif aci_score is not None and aci_score >= 7.0:
        level = "high"
    elif confidence >= 0.65:
        level = "moderate"
    else:
        level = "low"

    template = CALIBRATION_TEMPLATES[level]
    block = f"\n\nEVIDENCE CALIBRATION INSTRUCTION:\n{template}"
    if cal_note:
        block += f"\nAdditional context: {cal_note}"
    block += "\n"
    return block


# ─────────────────────────────────────────────────────────────────────────────
# 3. Self-RAG main loop
#    Improvement #1 + #14: iterative retrieval with grounding check
# ─────────────────────────────────────────────────────────────────────────────

def _dedupe_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate chunks by source_id or title."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for ch in chunks:
        key = ch.get("source_id") or ch.get("id") or ch.get("title", "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(ch)
    return out


async def wrap_with_self_rag(
    question: str,
    initial_chunks: List[Dict[str, Any]],
    retrieve_fn: Callable,           # retrieve_db(query, k=N) → List[Dict]
    max_iterations: int = MAX_SELF_RAG_ITERATIONS,
    k_per_iteration: int = 8,
    aci_score: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Main Self-RAG wrapper. Call this after initial retrieval in ask_v2.py.

    Returns:
        (enhanced_chunks, meta) where:
          enhanced_chunks — merged, deduped chunks for answer synthesis
          meta            — dict with iteration info for the SSE meta event:
            {
              "self_rag_iterations": 1,
              "self_rag_sufficient": true,
              "self_rag_confidence": 0.78,
              "calibration_block": "...",
              "calibration_level": "moderate"
            }
    """
    if not SELF_RAG_ENABLED or not initial_chunks:
        return initial_chunks, {"self_rag_iterations": 0, "self_rag_sufficient": True,
                                 "calibration_block": "", "calibration_level": "moderate"}

    all_chunks = list(initial_chunks)
    iterations_run = 0
    final_eval: Dict[str, Any] = {}

    for iteration in range(max_iterations):
        t0 = time.perf_counter()
        eval_result = await _evaluate_sufficiency(question, all_chunks)
        t1 = time.perf_counter()

        logger.info(
            f"[SelfRAG] Iter {iteration+1}: sufficient={eval_result.get('sufficient')}, "
            f"confidence={eval_result.get('confidence', '?'):.2f}, "
            f"eval_ms={int((t1-t0)*1000)}"
        )

        final_eval = eval_result
        iterations_run = iteration + 1

        # If sufficient or no reformulation possible, stop
        if eval_result.get("sufficient", True):
            break

        reformulation = eval_result.get("reformulation")
        if not reformulation:
            break

        # Run additional retrieval on the reformulated sub-query
        try:
            extra = await asyncio.to_thread(retrieve_fn, reformulation, k=k_per_iteration)
            if extra:
                all_chunks.extend(extra)
                all_chunks = _dedupe_chunks(all_chunks)
                logger.info(
                    f"[SelfRAG] Iter {iteration+1}: added {len(extra)} chunks "
                    f"via '{reformulation[:60]}', total={len(all_chunks)}"
                )
        except Exception as e:
            logger.warning(f"[SelfRAG] Retrieval on reformulation failed: {e}")
            break

    calibration_block = build_calibration_block(final_eval, aci_score)

    # Derive calibration level label for frontend display
    confidence = final_eval.get("confidence", 0.5)
    if not final_eval.get("sufficient", True) or confidence < 0.3:
        level = "insufficient"
    elif aci_score and aci_score >= 7.0:
        level = "high"
    elif confidence >= 0.65:
        level = "moderate"
    else:
        level = "low"

    meta = {
        "self_rag_iterations": iterations_run,
        "self_rag_sufficient": final_eval.get("sufficient", True),
        "self_rag_confidence": round(final_eval.get("confidence", 0.5), 3),
        "self_rag_gap": final_eval.get("gap"),
        "calibration_block": calibration_block,
        "calibration_level": level,
    }

    return all_chunks, meta


# ─────────────────────────────────────────────────────────────────────────────
# 4. Integration patch for ask_v2.py
# ─────────────────────────────────────────────────────────────────────────────

INTEGRATION_GUIDE = """
In app/api/ask_v2.py (or ask_stream.py), after initial retrieval:

# ── BEFORE (existing) ──────────────────────────────────────────────────────
chunks = await retrieve_db(question, k=14)
# pass chunks to answer synthesis

# ── AFTER (add self-RAG) ───────────────────────────────────────────────────
from app.engine.self_rag import wrap_with_self_rag

chunks, self_rag_meta = await wrap_with_self_rag(
    question=question,
    initial_chunks=chunks,
    retrieve_fn=lambda q, k=8: retrieve_db(q, k=k),
    max_iterations=2,
    aci_score=precomputed_aci_score,   # pass if available, else None
)

# Inject calibration block into answer synthesis prompt:
calibration = self_rag_meta["calibration_block"]
prompt = build_single_call_prompt(question, chunks, ...) + calibration

# Add self_rag_meta to SSE meta event:
meta_payload["self_rag"] = {
    "iterations": self_rag_meta["self_rag_iterations"],
    "confidence": self_rag_meta["self_rag_confidence"],
    "calibration_level": self_rag_meta["calibration_level"],
}
"""
