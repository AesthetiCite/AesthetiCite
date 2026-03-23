"""
AesthetiCite — Clinical Reasoning Engine  (Glass Health-inspired)
=================================================================
Endpoint: POST /api/reasoning/stream   → SSE stream of structured reasoning
Endpoint: POST /api/reasoning          → Synchronous JSON (fallback / caching)
Endpoint: GET  /api/reasoning/cache    → Return cached result if available

Design:
  - The master /api/decide endpoint returns a fast deterministic skeleton (<300ms).
  - This module runs in PARALLEL via a separate fetch in the frontend.
  - When the reasoning finishes streaming, the UI section fills in.
  - Result: Zero added latency to workflow delivery.

The prompt returns strict JSON with:
  {
    "diagnosis":      string,
    "confidence":     "low" | "medium" | "high",
    "confidence_why": string,
    "reasoning":      [{ "step": int, "label": str, "content": str }],
    "key_signs":      [string],
    "against_signs":  [string],
    "differentials":  [{ "diagnosis": str, "exclude_reason": str, "likelihood": "low"|"medium"|"high" }],
    "red_flags":      [string],
    "limitations":    string,
    "evidence_refs":  [string]   ← titles of evidence used in reasoning
  }
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/reasoning", tags=["Clinical Reasoning"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM config (mirrors existing ask_v2.py pattern)
# ---------------------------------------------------------------------------

_AI_BASE = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://api.openai.com/v1")
_AI_KEY  = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
_AI_URL  = f"{_AI_BASE.rstrip('/')}/chat/completions"

REASONING_MODEL       = "gpt-4o"
REASONING_TEMPERATURE = 0.15
REASONING_MAX_TOKENS  = 1200

# ---------------------------------------------------------------------------
# Result cache (LRU-style, 10 min TTL)
# ---------------------------------------------------------------------------

_CACHE: Dict[str, tuple[float, Dict]] = {}
_CACHE_TTL = 600

def _cache_key(payload: Dict) -> str:
    s = json.dumps({
        "c": payload.get("complication_type", ""),
        "r": payload.get("region", ""),
        "s": sorted(payload.get("symptoms", [])),
        "t": payload.get("time_since_minutes"),
    }, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()

def _cache_get(key: str) -> Optional[Dict]:
    if key in _CACHE:
        ts, val = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return val
        del _CACHE[key]
    return None

def _cache_set(key: str, val: Dict) -> None:
    _CACHE[key] = (time.time(), val)
    if len(_CACHE) > 200:
        oldest = sorted(_CACHE.items(), key=lambda x: x[1][0])[:50]
        for k, _ in oldest:
            del _CACHE[k]

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are AesthetiCite, a specialist clinical safety assistant for aesthetic medicine.
Your task is to provide structured clinical reasoning for a complication presentation.

CRITICAL RULES:
1. Return ONLY valid JSON — no markdown, no preamble, no trailing text.
2. Be specific to aesthetic medicine. Reference known complication patterns.
3. Confidence must reflect the evidence: "high" only when signs are pathognomonic.
4. Differentials must explain WHY each is less likely — not just list them.
5. Red flags are absolute hard-stops that require immediate escalation.
6. Do not invent signs or symptoms not present in the case.
7. Limitations must be honest — acknowledge when evidence is sparse."""

def _build_prompt(
    complication_type: str,
    symptoms: List[str],
    region: Optional[str],
    procedure: Optional[str],
    product: Optional[str],
    time_since_minutes: Optional[int],
    injector_experience: Optional[str],
    evidence_context: str,
) -> str:
    case_parts = []

    if procedure:
        case_parts.append(f"Procedure: {procedure}")
    if region:
        case_parts.append(f"Region: {region}")
    if product:
        case_parts.append(f"Product: {product}")
    if time_since_minutes is not None:
        if time_since_minutes < 60:
            case_parts.append(f"Onset: {time_since_minutes} minutes post-injection")
        else:
            case_parts.append(f"Onset: {time_since_minutes // 60}h {time_since_minutes % 60}m post-injection")
    if injector_experience:
        case_parts.append(f"Injector experience: {injector_experience}")
    if symptoms:
        case_parts.append(f"Presenting signs/symptoms: {', '.join(symptoms)}")

    case_text = "\n".join(case_parts) if case_parts else "Limited case details provided."

    evidence_block = ""
    if evidence_context:
        evidence_block = f"""
Available evidence context (use to ground your reasoning):
---
{evidence_context[:1500]}
---"""

    return f"""You are a clinical safety assistant for aesthetic medicine.

Return structured clinical reasoning for the following case. Respond ONLY with valid JSON.

Case:
Suspected complication: {complication_type}
{case_text}
{evidence_block}

Return this exact JSON structure:
{{
  "diagnosis": "Most likely diagnosis — be specific (e.g. 'Vascular occlusion — HA filler, superficial labial artery')",
  "confidence": "low|medium|high",
  "confidence_why": "One sentence explaining the confidence level",
  "reasoning": [
    {{"step": 1, "label": "Presentation Pattern", "content": "..."}},
    {{"step": 2, "label": "Key Evidence", "content": "..."}},
    {{"step": 3, "label": "Mechanism", "content": "..."}},
    {{"step": 4, "label": "Risk Factors", "content": "..."}}
  ],
  "key_signs": ["Sign present that supports diagnosis", "..."],
  "against_signs": ["Sign absent or features that make this less likely", "..."],
  "differentials": [
    {{
      "diagnosis": "Alternative diagnosis",
      "exclude_reason": "Why this is less likely given the presentation",
      "likelihood": "low|medium|high"
    }}
  ],
  "red_flags": [
    "Specific feature that mandates immediate escalation if present"
  ],
  "limitations": "Honest statement of what cannot be determined from the information given",
  "evidence_refs": ["Referenced guideline or study title if applicable"]
}}"""


# ---------------------------------------------------------------------------
# Evidence context builder
# ---------------------------------------------------------------------------

def _build_evidence_context(
    db: Session,
    complication_type: str,
    region: Optional[str],
) -> str:
    try:
        from app.rag.retriever import retrieve_db
        query = f"{complication_type} management aesthetic medicine"
        if region:
            query += f" {region}"
        chunks = retrieve_db(db=db, question=query, domain="aesthetic", k=4)
        if not chunks:
            return ""
        parts = []
        for c in chunks[:3]:
            title = c.get("title", "")
            text = (c.get("text") or c.get("chunk_text") or "")[:400]
            year = c.get("year", "")
            parts.append(f"[{title} ({year})]: {text}")
        return "\n\n".join(parts)
    except Exception as e:
        logger.debug(f"Evidence context retrieval failed (non-critical): {e}")
        return ""


# ---------------------------------------------------------------------------
# LLM call — streaming
# ---------------------------------------------------------------------------

async def _stream_reasoning_llm(prompt: str) -> AsyncGenerator[str, None]:
    import httpx

    headers = {
        "Authorization": f"Bearer {_AI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": REASONING_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "temperature": REASONING_TEMPERATURE,
        "max_tokens":  REASONING_MAX_TOKENS,
        "stream": True,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", _AI_URL, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                    tok = obj["choices"][0].get("delta", {}).get("content")
                    if tok:
                        yield tok
                except Exception:
                    continue


async def _call_reasoning_llm_sync(prompt: str) -> Dict[str, Any]:
    full = ""
    async for tok in _stream_reasoning_llm(prompt):
        full += tok

    clean = re.sub(r"```(?:json)?", "", full).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", clean)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        logger.warning(f"Reasoning LLM returned unparseable JSON: {clean[:200]}")
        return _fallback_reasoning(prompt)


def _fallback_reasoning(prompt: str) -> Dict[str, Any]:
    m = re.search(r"Suspected complication: (.+)", prompt)
    comp = m.group(1).strip() if m else "Complication"
    return {
        "diagnosis": comp,
        "confidence": "low",
        "confidence_why": "Automated reasoning unavailable — manual clinical assessment required.",
        "reasoning": [
            {"step": 1, "label": "Clinical Assessment", "content": "Automated reasoning temporarily unavailable. Use clinical judgement and refer to protocol."},
        ],
        "key_signs": [],
        "against_signs": [],
        "differentials": [],
        "red_flags": ["Escalate immediately if any deterioration"],
        "limitations": "Automated reasoning failed. This is a fallback response.",
        "evidence_refs": [],
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ReasoningRequest(BaseModel):
    complication_type: str = Field(..., min_length=2)
    symptoms: List[str] = []
    region: Optional[str] = None
    procedure: Optional[str] = None
    product: Optional[str] = None
    time_since_minutes: Optional[int] = None
    injector_experience: Optional[str] = None
    include_evidence_context: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/stream")
async def stream_reasoning(
    payload: ReasoningRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    SSE stream of clinical reasoning.
    Emits events:
      {type: "start"}
      {type: "token", content: "..."}
      {type: "reasoning", data: {...}}
      {type: "done"}
      {type: "error", message: "..."}
    """
    key = _cache_key(payload.dict())
    cached = _cache_get(key)

    async def generate() -> AsyncGenerator[str, None]:
        def sse(obj: Dict) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        yield sse({"type": "start"})

        if cached:
            yield sse({"type": "reasoning", "data": cached, "cache_hit": True})
            yield sse({"type": "done"})
            return

        evidence_ctx = ""
        if payload.include_evidence_context:
            try:
                evidence_ctx = _build_evidence_context(db, payload.complication_type, payload.region)
            except Exception:
                pass

        prompt = _build_prompt(
            complication_type=payload.complication_type,
            symptoms=payload.symptoms,
            region=payload.region,
            procedure=payload.procedure,
            product=payload.product,
            time_since_minutes=payload.time_since_minutes,
            injector_experience=payload.injector_experience,
            evidence_context=evidence_ctx,
        )

        full_text = ""
        try:
            async for tok in _stream_reasoning_llm(prompt):
                full_text += tok
                yield sse({"type": "token", "content": tok})
        except Exception as e:
            logger.error(f"Reasoning stream error: {e}")
            yield sse({"type": "error", "message": "Reasoning engine temporarily unavailable."})
            result = _fallback_reasoning(prompt)
            yield sse({"type": "reasoning", "data": result, "cache_hit": False})
            yield sse({"type": "done"})
            return

        clean = re.sub(r"```(?:json)?", "", full_text).strip()
        try:
            result = json.loads(clean)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", clean)
            result = json.loads(m.group(0)) if m else _fallback_reasoning(prompt)

        _cache_set(key, result)
        yield sse({"type": "reasoning", "data": result, "cache_hit": False})
        yield sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("")
async def get_reasoning(
    payload: ReasoningRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Synchronous JSON endpoint — for contexts where SSE is not available."""
    key = _cache_key(payload.dict())
    cached = _cache_get(key)
    if cached:
        return {**cached, "cache_hit": True, "latency_ms": 0}

    t0 = time.perf_counter()

    evidence_ctx = ""
    if payload.include_evidence_context:
        try:
            evidence_ctx = _build_evidence_context(db, payload.complication_type, payload.region)
        except Exception:
            pass

    prompt = _build_prompt(
        complication_type=payload.complication_type,
        symptoms=payload.symptoms,
        region=payload.region,
        procedure=payload.procedure,
        product=payload.product,
        time_since_minutes=payload.time_since_minutes,
        injector_experience=payload.injector_experience,
        evidence_context=evidence_ctx,
    )

    result = await _call_reasoning_llm_sync(prompt)
    _cache_set(key, result)
    return {
        **result,
        "cache_hit": False,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@router.get("/cache")
async def check_cache(
    complication_type: str,
    region: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Check if reasoning is cached for a complication."""
    key = _cache_key({"complication_type": complication_type, "region": region, "symptoms": []})
    cached = _cache_get(key)
    return {"cached": cached is not None, "data": cached}
