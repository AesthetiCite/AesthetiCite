"""
aestheticite_oe_upgrade.py  –  Structured Answer Pipeline v2 + VeriDoc Engine
==============================================================================
Pipeline v2 (legacy):
  A-G steps for intent/entity/subquery/claim/ground/conflict/compose

VeriDoc Engine (new, activated via VERIDOC_ENABLED=1):
  Clean class-based AnswerEngine with LLM claim rewriting, per-claim numeric
  guards, pairwise conflict detection, and structured evidence grading.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Literal, Tuple
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import httpx

from app.db.session import get_db
from app.core.config import settings
from app.core.safety import safety_screen
from app.core.limiter import limiter
from app.rag.retriever import retrieve_db
from app.rag.embedder import embed_text
from app.engine.veridoc import AesthetiCiteEngine, TTLCache

VERIDOC_ENABLED = os.getenv("VERIDOC_ENABLED", "1") == "1"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["aestheticite-oe-upgrade"])

OE_TOP_K = int(os.getenv("OE_TOP_K", "20"))
OE_EVIDENCE_K = int(os.getenv("OE_EVIDENCE_K", "15"))

EvidenceTier = Literal["A", "B", "C", "UNKNOWN"]
StudyType = Literal["guideline", "rct", "labeling", "review", "observational", "expert", "unknown"]


class AskOERequest(BaseModel):
    query: str
    domain: Optional[str] = None
    lang: Optional[str] = None
    user_id: Optional[str] = None
    include_related_questions: bool = True
    include_inline_tools: bool = True


class CitationOE(BaseModel):
    source_id: str
    title: Optional[str] = None
    url: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    quote: Optional[str] = None
    year: Optional[int] = None
    tier: EvidenceTier = "UNKNOWN"
    study_type: StudyType = "unknown"
    score: Optional[float] = None
    source_language: Optional[str] = None
    organization: Optional[str] = None


class GroundedClaim(BaseModel):
    claim_id: str
    text: str
    status: Literal["SUPPORTED", "UNSUPPORTED"]
    citations: List[str] = Field(default_factory=list)
    original_text: Optional[str] = None


class InlineToolObject(BaseModel):
    name: str
    args: Dict[str, Any]
    output: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, str]] = Field(default_factory=list)


class AskOEResponse(BaseModel):
    status: Literal["ok", "refuse", "error"]
    answer: Optional[str] = None
    clinical_summary: Optional[str] = None
    refusal_reason: Optional[str] = None
    refusal_code: Optional[str] = None
    citations: List[CitationOE] = Field(default_factory=list)
    grounded_claims: List[GroundedClaim] = Field(default_factory=list)
    inline_tools: List[InlineToolObject] = Field(default_factory=list)
    related_questions: List[str] = Field(default_factory=list)
    evidence_strength: Optional[str] = None
    aci_score: Optional[float] = None
    next_search_terms: List[str] = Field(default_factory=list)
    debug: Optional[Dict[str, Any]] = None


@dataclass
class Chunk:
    source_id: str
    title: str
    text: str
    url: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    year: Optional[int] = None
    source_language: Optional[str] = None
    document_type: Optional[str] = None
    organization: Optional[str] = None


_TIER_KEYWORDS_A = ("fda", "ema", "smpc", "label", "prescribing information", "randomized", "rct", "guideline", "ifu", "instructions for use")
_TIER_KEYWORDS_B = ("consensus", "position statement", "practice guideline", "society", "expert panel")
_TIER_KEYWORDS_C = ("review", "narrative", "expert opinion", "case report", "case series")


def infer_study_type(chunk: Chunk) -> StudyType:
    t = (chunk.title + " " + (chunk.section or "") + " " + chunk.text[:300]).lower()
    if "prescribing information" in t or "smpc" in t or "label" in t or "ifu" in t:
        return "labeling"
    if "guideline" in t or "practice guideline" in t:
        return "guideline"
    if "randomized" in t or "rct" in t:
        return "rct"
    if "review" in t:
        return "review"
    if "cohort" in t or "case-control" in t or "observational" in t:
        return "observational"
    if "expert" in t or "opinion" in t:
        return "expert"
    return "unknown"


def infer_tier(chunk: Chunk) -> EvidenceTier:
    t = (chunk.title + " " + (chunk.section or "") + " " + chunk.text[:300]).lower()
    doc_type = (chunk.document_type or "").lower()
    if doc_type in ("guideline", "consensus", "ifu", "rct"):
        return "A"
    if any(k in t for k in _TIER_KEYWORDS_A):
        return "A"
    if any(k in t for k in _TIER_KEYWORDS_B):
        return "B"
    if any(k in t for k in _TIER_KEYWORDS_C):
        return "C"
    return "UNKNOWN"


def score_chunk(chunk: Chunk, query: str) -> float:
    tier = infer_tier(chunk)
    tier_score = {"A": 1.0, "B": 0.72, "C": 0.45, "UNKNOWN": 0.55}[tier]

    year_score = 0.0
    if chunk.year:
        age = max(0, time.gmtime().tm_year - chunk.year)
        year_score = max(0.0, 1.0 - (age / 15.0))

    q_terms = {w for w in re.findall(r"[a-zA-Z]{3,}", query.lower())}
    c_terms = set(re.findall(r"[a-zA-Z]{3,}", (chunk.title + " " + chunk.text[:900]).lower()))
    overlap = len(q_terms & c_terms) / max(1, len(q_terms))
    overlap_score = min(1.0, overlap)

    return round(0.55 * tier_score + 0.25 * year_score + 0.20 * overlap_score, 4)


def best_tier_available(chunks: List[Chunk]) -> EvidenceTier:
    tiers = [infer_tier(c) for c in chunks]
    if "A" in tiers: return "A"
    if "B" in tiers: return "B"
    if "C" in tiers: return "C"
    return "UNKNOWN"


def evidence_strength_label(best_tier: EvidenceTier, conflict: bool) -> str:
    if conflict:
        return "Limited"
    return {"A": "High", "B": "Moderate", "C": "Limited", "UNKNOWN": "Limited"}[best_tier]


def extract_section(text: str, header: str) -> Optional[str]:
    pattern = rf"{header}\s*:?\s*(.*?)(?:\n[A-Za-z &]+:\s*|\Z)"
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|μg|g|kg|ml|mL|L|iu|IU|units|U|%|mm|cm|mmHg)", re.IGNORECASE)


def extract_numbers(text: str) -> List[str]:
    return [f"{m.group(1)}{m.group(2).lower()}" for m in _NUM_RE.finditer(text or "")]


# ─── A) UNDERSTAND ────────────────────────────────────────────

INTENT_CATEGORIES = {
    "dosing": ["dose", "dosing", "dosage", "how much", "how many", "units", "mg", "ml", "maximum dose", "max dose", "concentration"],
    "safety": ["complication", "risk", "adverse", "side effect", "contraindic", "warning", "danger", "emergency", "vascular occlusion", "necrosis", "blindness"],
    "efficacy": ["effective", "efficacy", "outcome", "result", "success rate", "work", "benefit"],
    "procedure": ["technique", "procedure", "how to", "protocol", "injection", "method", "approach", "step"],
    "comparison": ["versus", "vs", "compared", "difference", "better", "prefer", "choice"],
    "mechanism": ["mechanism", "how does", "pathway", "pharmacology", "action"],
    "general": [],
}


def classify_intent(question: str) -> str:
    q = question.lower()
    scores: Dict[str, int] = {}
    for intent, keywords in INTENT_CATEGORIES.items():
        scores[intent] = sum(1 for kw in keywords if kw in q)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "general"


MEDICAL_ENTITIES_RE = re.compile(
    r'\b('
    r'botox|botulinum|dysport|xeomin|jeuveau|'
    r'juvederm|restylane|radiesse|sculptra|belotero|teosyal|'
    r'hyaluronidase|hyaluronic acid|'
    r'lidocaine|epinephrine|triamcinolone|'
    r'filler|toxin|pdo|thread|prp|'
    r'retinol|tretinoin|hydroquinone|'
    r'laser|ipl|rf|radiofrequency|ultrasound|hifu|'
    r'lip|nasolabial|marionette|glabella|forehead|crow|perioral|chin|jawline|temple|'
    r'cheek|tear trough|undereye|neck|decollet|'
    r'necrosis|occlusion|blindness|granuloma|nodule|biofilm|infection|'
    r'aspirin|nitroglycerin|hylenex'
    r')\b',
    re.IGNORECASE
)


def extract_entities(question: str) -> List[str]:
    matches = MEDICAL_ENTITIES_RE.findall(question)
    return list(dict.fromkeys(m.lower() for m in matches))


def build_subqueries(question: str, intent: str, entities: List[str]) -> List[str]:
    subqueries = [question]
    if entities:
        entity_str = " ".join(entities[:3])
        if intent == "dosing":
            subqueries.append(f"{entity_str} recommended dose maximum dose prescribing information")
        elif intent == "safety":
            subqueries.append(f"{entity_str} complications adverse events contraindications safety")
        elif intent == "efficacy":
            subqueries.append(f"{entity_str} clinical outcomes efficacy results evidence")
        elif intent == "comparison":
            subqueries.append(f"{entity_str} comparison clinical trial head to head")
        elif intent == "procedure":
            subqueries.append(f"{entity_str} technique protocol injection guidelines")
        elif intent == "mechanism":
            subqueries.append(f"{entity_str} mechanism of action pharmacology")
    return subqueries[:3]


# ─── B) RETRIEVE + DEDUPE + RERANK ────────────────────────────

def dedupe_chunks(chunks: List[Chunk]) -> List[Chunk]:
    seen: Dict[str, Chunk] = {}
    for ch in chunks:
        key = f"{ch.source_id}:{ch.section or ch.page or ''}"
        if key not in seen:
            seen[key] = ch
    return list(seen.values())


def rerank(question: str, chunks: List[Chunk], top_k: int = 15) -> List[Tuple[Chunk, float]]:
    scored = [(ch, score_chunk(ch, question)) for ch in chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


# ─── C) HARD GUARD ────────────────────────────────────────────

HIGH_STAKES_INTENTS = {"dosing", "safety"}


def evidence_coverage_low(ranked: List[Tuple[Chunk, float]], intent: str = "general") -> bool:
    if len(ranked) < 2:
        return True
    top_score = ranked[0][1] if ranked else 0
    if top_score < 0.15:
        return True
    unique_sources = len(set(ch.source_id for ch, _ in ranked))
    if unique_sources < 2:
        return True
    if intent in HIGH_STAKES_INTENTS:
        best = best_tier_available([ch for ch, _ in ranked])
        if best not in ("A", "B"):
            return True
        if unique_sources < 3:
            return True
    return False


def suggest_search_terms(intent: str, entities: List[str]) -> List[str]:
    suggestions = []
    if entities:
        suggestions.append(f"Try searching for: {', '.join(entities[:3])}")
    if intent == "dosing":
        suggestions.append("Search prescribing information or product labeling")
    elif intent == "safety":
        suggestions.append("Search complications + specific product name")
    elif intent == "comparison":
        suggestions.append("Search head-to-head trials or systematic reviews")
    return suggestions[:3]


# ─── D) CLAIM PLANNING + GROUNDING ────────────────────────────

SYSTEM_CLAIM_PLANNER = (
    "You are AesthetiCite Claim Planner.\n"
    "Given the user's question and retrieved evidence, list the atomic claims needed to answer safely.\n"
    "Each claim must be a single verifiable statement.\n"
    "Return STRICT JSON only (no markdown):\n"
    '{"claims": ["claim text 1", "claim text 2", ...]}\n'
    "Rules:\n"
    "- Every claim must be answerable from the provided evidence.\n"
    "- Keep claims specific and factual.\n"
    "- Include 3-8 claims for a typical question.\n"
    "- Do NOT invent facts or make claims beyond the evidence.\n"
)


def select_supporting_chunks(
    claim: str, ranked: List[Tuple[Chunk, float]], min_n: int = 1
) -> List[Tuple[Chunk, str]]:
    claim_lower = claim.lower()
    claim_tokens = set(re.findall(r"[a-z]{3,}", claim_lower))
    claim_nums = set(re.findall(r"\d+(?:\.\d+)?", claim))

    idx_map = {id(ch): i + 1 for i, (ch, _) in enumerate(ranked)}

    supported: List[Tuple[Chunk, str, float]] = []
    for ch, sc in ranked:
        txt_lower = ch.text.lower()
        txt_tokens = set(re.findall(r"[a-z]{3,}", txt_lower))
        overlap = len(claim_tokens & txt_tokens)
        if overlap < 2:
            continue
        num_match = 0
        if claim_nums:
            txt_nums = set(re.findall(r"\d+(?:\.\d+)?", ch.text))
            num_match = len(claim_nums & txt_nums)
        relevance = overlap + num_match * 3 + sc * 5
        sid = f"S{idx_map[id(ch)]}"
        supported.append((ch, sid, relevance))

    supported.sort(key=lambda x: x[2], reverse=True)

    if len(supported) < min_n:
        return []
    return [(ch, sid) for ch, sid, _ in supported[:3]]


# ─── E) CONFLICT DETECTION ────────────────────────────────────

def detect_conflict(chunks: List[Chunk]) -> bool:
    pos = 0
    neg = 0
    for ch in chunks[:12]:
        t = ch.text.lower()
        if any(x in t for x in ("recommended", "effective", "safe", "supports", "improves", "beneficial")):
            pos += 1
        if any(x in t for x in ("not recommended", "insufficient", "no evidence", "contraindicated", "avoid", "harmful")):
            neg += 1
    return pos >= 3 and neg >= 3


# ─── F) COMPOSE ───────────────────────────────────────────────

SYSTEM_COMPOSER = (
    "You are AesthetiCite Synthesizer.\n"
    "You will receive:\n"
    "1. The user's question\n"
    "2. A list of GROUNDED CLAIMS (each marked SUPPORTED with citation IDs)\n"
    "3. The Evidence Pack for reference\n\n"
    "Rules:\n"
    "- Use ONLY the SUPPORTED claims to write the answer.\n"
    "- Cite each claim with its citation markers like [S1], [S2].\n"
    "- If a claim is marked UNSUPPORTED, mention that evidence is limited for that aspect.\n"
    "- If there are conflict signals, note the disagreement objectively.\n"
    "- Keep tone professional, clinical, and cautious.\n"
    "- Output sections:\n"
    "  1) **Clinical Summary**: 3-5 bullet overview\n"
    "  2) **Evidence-Based Answer**: paragraphs with inline [S#] citations\n"
    "  3) **Safety & Contraindications**: if relevant\n"
    "  4) **Evidence Strength**: High/Moderate/Limited with justification\n"
)

SYSTEM_RELATED = (
    "You generate safe follow-up questions for clinicians.\n"
    "Rules:\n"
    "- Questions must be evidence-based and not encourage unsafe actions.\n"
    "- Keep them short.\n"
    "- Return JSON only: {\"questions\": [..]}."
)


def _llm_call(messages: List[dict], json_mode: bool = False) -> str:
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    base_url = settings.OPENAI_BASE_URL.rstrip("/")
    model = os.getenv("OPENAI_MODEL", settings.OPENAI_MODEL)
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=90) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


async def llm_json(system: str, user: str, schema_hint: str = "") -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user + ("\n\n" + schema_hint if schema_hint else "")},
    ]
    result = _llm_call(messages, json_mode=True)
    return json.loads(result)


async def llm_text(system: str, user: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return _llm_call(messages, json_mode=False)


def convert_retrieved_to_chunks(retrieved: List[Dict]) -> List[Chunk]:
    chunks = []
    for r in retrieved:
        chunks.append(Chunk(
            source_id=r.get("source_id", ""),
            title=r.get("title", ""),
            text=r.get("text", ""),
            url=r.get("url"),
            page=int(r["page_or_section"]) if r.get("page_or_section") and str(r["page_or_section"]).isdigit() else None,
            section=r.get("page_or_section") if r.get("page_or_section") and not str(r["page_or_section"]).isdigit() else None,
            year=r.get("year"),
            source_language=r.get("language"),
            document_type=r.get("document_type"),
            organization=r.get("organization_or_journal"),
        ))
    return chunks


def make_evidence_pack(scored: List[Tuple[Chunk, float]]) -> Tuple[str, List[CitationOE]]:
    citations: List[CitationOE] = []
    blocks: List[str] = []
    for i, (ch, sc) in enumerate(scored, start=1):
        sid = f"S{i}"
        tier = infer_tier(ch)
        stype = infer_study_type(ch)
        words = ch.text.strip().split()
        quote = " ".join(words[:25]) if words else None

        citations.append(CitationOE(
            source_id=ch.source_id,
            title=ch.title,
            url=ch.url,
            page=ch.page,
            section=ch.section,
            quote=quote,
            year=ch.year,
            tier=tier,
            study_type=stype,
            score=sc,
            source_language=ch.source_language,
            organization=ch.organization,
        ))
        blocks.append(
            f"[{sid}] (tier={tier}, type={stype}, year={ch.year})\n"
            f"TITLE: {ch.title}\n"
            f"TEXT: {ch.text}\n"
        )
    return "\n\n".join(blocks), citations


async def execute_clinical_tool(tool_name: str, query: str, chunks: List[Chunk]) -> Optional[InlineToolObject]:
    tool_name_lower = tool_name.lower().replace("_", "").replace("-", "")
    tool_map = {
        "bmicalculator": ("bmi_calculator", {}),
        "bsacalculator": ("bsa_calculator", {}),
        "egfrcalculator": ("egfr_calculator", {}),
        "unitconverter": ("unit_converter", {}),
        "dosingcalculator": ("dosing_calculator", {}),
        "interactioncheck": ("interaction_check", {}),
        "localanestheticmaxdose": ("local_anesthetic_max_dose", {}),
        "botoxdilution": ("botox_dilution", {}),
    }
    if tool_name_lower not in tool_map:
        return None
    endpoint_name, default_args = tool_map[tool_name_lower]
    evidence_refs = []
    for i, ch in enumerate(chunks[:3], start=1):
        if tool_name_lower in ch.text.lower() or any(kw in ch.text.lower() for kw in ["dose", "dosing", "mg", "unit"]):
            evidence_refs.append({"source_id": ch.source_id, "label": f"S{i}"})
    return InlineToolObject(
        name=endpoint_name,
        args=default_args,
        output={"status": "available", "note": f"Use clinical tools panel for {endpoint_name}"},
        warnings=[],
        evidence=evidence_refs,
    )


# ─── MAIN PIPELINE ────────────────────────────────────────────

async def answer_question(
    question: str,
    db: Session,
    domain: Optional[str] = None,
    lang: str = "en",
    include_related: bool = True,
    include_tools: bool = True,
) -> AskOEResponse:
    t0 = time.time()

    # ── A) UNDERSTAND ──────────────────────────────────
    intent = classify_intent(question)
    entities = extract_entities(question)
    subqueries = build_subqueries(question, intent, entities)
    logger.info(f"Intent={intent}, entities={entities}, subqueries={len(subqueries)}")

    # ── B) RETRIEVE ────────────────────────────────────
    all_chunks: List[Chunk] = []
    for sq in subqueries:
        retrieved = retrieve_db(db=db, question=sq, domain=domain, k=OE_TOP_K)
        all_chunks.extend(convert_retrieved_to_chunks(retrieved))

    all_chunks = dedupe_chunks(all_chunks)
    ranked = rerank(question, all_chunks, top_k=OE_EVIDENCE_K)

    if not ranked:
        return AskOEResponse(
            status="refuse",
            refusal_code="NO_EVIDENCE",
            refusal_reason="No relevant evidence was found in the knowledge base.",
            next_search_terms=suggest_search_terms(intent, entities),
        )

    # ── C) HARD GUARD ──────────────────────────────────
    if evidence_coverage_low(ranked, intent):
        selected = [c for c, _ in ranked]
        _, citations = make_evidence_pack(ranked)
        return AskOEResponse(
            status="refuse",
            refusal_code="LOW_COVERAGE",
            refusal_reason="Insufficient relevant evidence to answer reliably.",
            citations=citations,
            evidence_strength="Insufficient",
            next_search_terms=suggest_search_terms(intent, entities),
            debug={"intent": intent, "entities": entities, "chunks_found": len(all_chunks), "top_score": ranked[0][1] if ranked else 0},
        )

    selected_chunks = [c for c, _ in ranked]
    evidence_pack, citations = make_evidence_pack(ranked)
    conflict = detect_conflict(selected_chunks)
    best_tier = best_tier_available(selected_chunks)
    strength = evidence_strength_label(best_tier, conflict)

    # ── D) PLAN CLAIMS ─────────────────────────────────
    planner_prompt = (
        f"USER QUESTION:\n{question}\n\n"
        f"INTENT: {intent}\n"
        f"ENTITIES: {', '.join(entities) if entities else 'none detected'}\n\n"
        f"EVIDENCE PACK:\n{evidence_pack}\n\n"
        "List the atomic claims needed to answer this question safely.\n"
        "Every claim must be verifiable from the Evidence Pack."
    )

    try:
        plan_raw = await llm_json(SYSTEM_CLAIM_PLANNER, planner_prompt)
        raw_claims = plan_raw.get("claims", [])
        if not isinstance(raw_claims, list):
            raw_claims = []
    except Exception as e:
        logger.warning(f"Claim planner failed: {e}, proceeding with direct synthesis")
        raw_claims = []

    # ── E) GROUND EACH CLAIM ──────────────────────────
    grounded_claims: List[GroundedClaim] = []
    if raw_claims:
        for idx, claim_text in enumerate(raw_claims, 1):
            if not isinstance(claim_text, str):
                claim_text = str(claim_text)
            support = select_supporting_chunks(claim_text, ranked, min_n=1)
            if not support:
                grounded_claims.append(GroundedClaim(
                    claim_id=f"C{idx}",
                    text=claim_text,
                    status="UNSUPPORTED",
                    original_text=claim_text,
                ))
            else:
                cite_ids = [sid for _, sid in support]
                grounded_claims.append(GroundedClaim(
                    claim_id=f"C{idx}",
                    text=claim_text,
                    status="SUPPORTED",
                    citations=cite_ids,
                    original_text=claim_text,
                ))

    supported_count = sum(1 for gc in grounded_claims if gc.status == "SUPPORTED")
    unsupported_count = sum(1 for gc in grounded_claims if gc.status == "UNSUPPORTED")

    # ── F) COMPOSE FINAL RESPONSE ─────────────────────
    claims_block = ""
    if grounded_claims:
        parts = []
        for gc in grounded_claims:
            cite_str = ", ".join(gc.citations) if gc.citations else "no citation"
            parts.append(f"- [{gc.status}] {gc.text} ({cite_str})")
        claims_block = "\n".join(parts)

    conflict_note = ""
    if conflict:
        conflict_note = "\nCONFLICT SIGNAL: Some sources show contradictory findings. Note the disagreement objectively.\n"

    compose_prompt = (
        f"USER QUESTION:\n{question}\n\n"
        f"GROUNDED CLAIMS:\n{claims_block}\n{conflict_note}\n"
        f"EVIDENCE PACK (for reference, cite using [S1], [S2] etc.):\n{evidence_pack}\n\n"
        f"Evidence Strength: {strength}\n\n"
        "Write the clinical response now using ONLY the SUPPORTED claims. "
        "For UNSUPPORTED claims, briefly note that evidence is limited."
    )

    try:
        answer_text = await llm_text(SYSTEM_COMPOSER, compose_prompt)
    except Exception as e:
        logger.error(f"Composer failed: {e}")
        return AskOEResponse(
            status="error",
            refusal_reason="Answer generation failed. Please try again.",
            citations=citations,
            debug={"error": repr(e)},
        )

    if "INSUFFICIENT_EVIDENCE" in answer_text:
        return AskOEResponse(
            status="refuse",
            refusal_code="INSUFFICIENT_EVIDENCE",
            refusal_reason="Insufficient evidence to answer this question reliably.",
            citations=citations,
            grounded_claims=grounded_claims,
            next_search_terms=suggest_search_terms(intent, entities),
        )

    has_any_cite = bool(re.search(r"\[S\d+\]", answer_text or ""))
    if not has_any_cite:
        return AskOEResponse(
            status="refuse",
            refusal_code="MISSING_CITATIONS",
            refusal_reason="Generated answer contains no citations. Cannot publish uncited medical claims.",
            citations=citations,
            grounded_claims=grounded_claims,
        )

    # ── FINAL ENFORCEMENT: per-paragraph citation check ──
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", answer_text.strip()) if p.strip()]
    uncited_paras = []
    for p in paragraphs:
        if not re.search(r"\[S\d+\]", p):
            if len(p) > 50 and not p.lower().startswith(("clinical summary", "evidence strength", "**clinical summary", "**evidence strength", "**safety")):
                uncited_paras.append(p[:80])
    if uncited_paras:
        answer_text += "\n\n*Note: Some statements may not have direct source citations. Always verify with primary literature.*"

    # ── FINAL ENFORCEMENT: numeric consistency ──
    numeric_warning = None
    answer_nums = extract_numbers(answer_text)
    if answer_nums:
        corpus = " ".join(ch.text.lower() for ch in selected_chunks[:10])
        unverified = [n for n in answer_nums if n.lower() not in corpus]
        if unverified:
            numeric_warning = f"Unverified numeric values: {', '.join(unverified[:5])}"
            if len(unverified) > len(answer_nums) * 0.5:
                answer_text += "\n\n*Caution: Some numeric values could not be verified against the retrieved sources. Verify with prescribing information.*"

    if "Evidence Strength" not in answer_text:
        answer_text = answer_text.strip() + f"\n\n**Evidence Strength**: {strength}."

    clinical_summary = extract_section(answer_text, "Clinical Summary")

    # ── RELATED QUESTIONS ──────────────────────────────
    related_questions: List[str] = []
    if include_related:
        related_user = (
            f"USER QUESTION:\n{question}\n\n"
            f"TOPIC: {intent}, entities: {', '.join(entities[:5])}\n"
            "Return 4-6 safe follow-up questions."
        )
        try:
            rj = await llm_json(SYSTEM_RELATED, related_user, '{"questions":[...]}')
            qs = rj.get("questions", [])
            if isinstance(qs, list):
                related_questions = [str(x)[:160] for x in qs][:6]
        except Exception:
            related_questions = []

    # ── INLINE TOOLS ───────────────────────────────────
    inline_tools: List[InlineToolObject] = []
    if include_tools and intent == "dosing":
        for tool_name in ["dosingcalculator", "unitconverter"][:2]:
            try:
                tool_result = await execute_clinical_tool(tool_name, question, selected_chunks)
                if tool_result:
                    inline_tools.append(tool_result)
            except Exception:  # nosec B112
                continue

    dt_ms = int((time.time() - t0) * 1000)
    debug = {
        "latency_ms": dt_ms,
        "intent": intent,
        "entities": entities,
        "subqueries": len(subqueries),
        "chunks_retrieved": len(all_chunks),
        "chunks_ranked": len(ranked),
        "best_tier": best_tier,
        "conflict": conflict,
        "claims_supported": supported_count,
        "claims_unsupported": unsupported_count,
        "uncited_paragraphs": len(uncited_paras),
    }
    if numeric_warning:
        debug["numeric_warning"] = numeric_warning

    return AskOEResponse(
        status="ok",
        answer=answer_text,
        clinical_summary=clinical_summary,
        citations=citations,
        grounded_claims=grounded_claims,
        inline_tools=inline_tools,
        related_questions=related_questions,
        evidence_strength=strength,
        next_search_terms=suggest_search_terms(intent, entities) if unsupported_count > 0 else [],
        debug=debug,
    )


# ─── VERIDOC v2 ADAPTER (AesthetiCiteEngine) ─────────────────

_engine_cache = TTLCache(max_items=4096, ttl_s=3600)


def _veridoc_retrieve_adapter(db: Session, domain: Optional[str] = None):
    def _retrieve(query: str, k: int = 20) -> List[Dict[str, Any]]:
        rows = retrieve_db(db=db, question=query, domain=domain, k=k)
        chunks = []
        for r in rows:
            doc_type = (r.get("document_type") or "").lower()
            source_type = "other"
            dm = "journal"
            if doc_type in ("guideline", "consensus"):
                source_type = "guideline"
                dm = "society"
            elif doc_type in ("ifu", "instructions for use"):
                source_type = "ifu"
                dm = "manufacturer"
            elif doc_type in ("labeling", "prescribing information"):
                source_type = "ifu"
                dm = "manufacturer"
            elif doc_type == "rct":
                source_type = "rct"
            elif doc_type == "review":
                source_type = "review"
            elif doc_type in ("cohort", "observational"):
                source_type = "cohort"
            elif doc_type in ("case_report", "case_series"):
                source_type = "case_report"
            elif doc_type in ("expert", "opinion"):
                source_type = "other"
            else:
                txt = (r.get("title", "") + " " + r.get("text", "")[:300]).lower()
                if "guideline" in txt or "consensus" in txt:
                    source_type = "guideline"
                    dm = "society"
                elif "ifu" in txt or "instructions for use" in txt:
                    source_type = "ifu"
                    dm = "manufacturer"
                elif "randomized" in txt or "rct" in txt:
                    source_type = "rct"
                elif "review" in txt:
                    source_type = "review"

            org = r.get("organization_or_journal", "")
            if org:
                org_l = org.lower()
                if any(k in org_l for k in ("society", "academy", "college", "association")):
                    dm = "society"
                elif any(k in org_l for k in ("journal", "annals", "lancet", "jama", "nejm")):
                    dm = "journal"

            chunks.append({
                "id": r.get("source_id", ""),
                "source_id": r.get("source_id", ""),
                "title": r.get("title", ""),
                "text": r.get("text", ""),
                "url": r.get("url"),
                "year": r.get("year"),
                "source_type": source_type,
                "domain": dm,
                "page_or_section": r.get("page_or_section"),
                "organization": org,
                "language": r.get("language"),
                "document_type": r.get("document_type"),
            })
        return chunks
    return _retrieve


def _veridoc_llm_json(prompt: str) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "Return valid JSON only. No markdown fences."},
        {"role": "user", "content": prompt},
    ]
    result = _llm_call(messages, json_mode=True)
    return json.loads(result)


def _veridoc_llm_text(prompt: str) -> str:
    messages = [
        {"role": "system", "content": "You are AesthetiCite, an evidence-based clinical assistant for aesthetic medicine."},
        {"role": "user", "content": prompt},
    ]
    return _llm_call(messages, json_mode=False)


def _map_veridoc_to_response(
    result: Dict[str, Any],
    question: str,
    include_related: bool = True,
    include_tools: bool = True,
    dt_ms: int = 0,
) -> AskOEResponse:
    if result.get("status") == "error":
        meta = result.get("meta", {})
        return AskOEResponse(
            status="error",
            refusal_reason=result.get("clinical_answer", "An error occurred during evidence search."),
            evidence_strength="Insufficient",
            debug={
                "engine": "veridoc_v2",
                "mode": meta.get("mode", ""),
                "latency_ms": meta.get("latency_ms", dt_ms),
                "cache_hit": False,
                "error": meta.get("error", ""),
            },
        )

    strength_info = result.get("evidence_strength", {})
    strength_grade = strength_info.get("grade", "Limited") if isinstance(strength_info, dict) else str(strength_info)

    if strength_grade == "Insufficient":
        refs = result.get("references", [])
        citations = []
        for r in refs:
            citations.append(CitationOE(
                source_id=r.get("id", ""),
                title=r.get("title"),
                url=r.get("url"),
                year=r.get("year"),
                tier="UNKNOWN",
                study_type="unknown",
            ))
        raw_aci = result.get("aci_score")
        aci_float = raw_aci.get("overall_confidence_0_10") if isinstance(raw_aci, dict) else raw_aci
        return AskOEResponse(
            status="refuse",
            refusal_code="LOW_COVERAGE",
            refusal_reason=result.get("clinical_answer", "Insufficient evidence."),
            citations=citations,
            evidence_strength="Insufficient",
            aci_score=aci_float,
            next_search_terms=result.get("next_search_terms", []),
            debug={
                "intent": result.get("intent"),
                "engine": "veridoc_v2",
                "mode": result.get("mode", ""),
                "coverage": result.get("meta", {}).get("coverage"),
                "latency_ms": dt_ms,
                "cache_hit": result.get("meta", {}).get("cache_hit", False),
            },
        )

    answer_text = result.get("clinical_answer")
    if not answer_text:
        return AskOEResponse(
            status="error",
            refusal_reason="Answer generation failed. Please try again.",
        )

    ranked = result.get("ranked_chunks", [])
    citations: List[CitationOE] = []
    for i, ch in enumerate(ranked, start=1):
        chunk_obj = Chunk(
            source_id=ch.get("source_id") or ch.get("id", ""),
            title=ch.get("title", ""),
            text=ch.get("text", ""),
            url=ch.get("url"),
            year=ch.get("year"),
            source_language=ch.get("language"),
            document_type=ch.get("document_type") or ch.get("source_type"),
            organization=ch.get("organization"),
        )
        tier = infer_tier(chunk_obj)
        stype = infer_study_type(chunk_obj)
        words = ch.get("text", "").strip().split()
        quote = " ".join(words[:25]) if words else None

        citations.append(CitationOE(
            source_id=ch.get("source_id") or ch.get("id", ""),
            title=ch.get("title"),
            url=ch.get("url"),
            year=ch.get("year"),
            tier=tier,
            study_type=stype,
            quote=quote,
            source_language=ch.get("language"),
            organization=ch.get("organization"),
        ))

    grounded_claims: List[GroundedClaim] = []
    for idx, gc in enumerate(result.get("supported_claims", []), 1):
        grounded_claims.append(GroundedClaim(
            claim_id=f"C{idx}",
            text=gc.get("text", ""),
            status="SUPPORTED",
            citations=gc.get("citations", []),
        ))
    for idx2, gc in enumerate(result.get("excluded_claims", []), len(grounded_claims) + 1):
        grounded_claims.append(GroundedClaim(
            claim_id=f"C{idx2}",
            text=gc.get("text", ""),
            status="UNSUPPORTED",
            citations=gc.get("citations", []),
        ))

    has_any_cite = bool(re.search(r"\[", answer_text or ""))
    if not has_any_cite and len(result.get("supported_claims", [])) > 0:
        return AskOEResponse(
            status="refuse",
            refusal_code="MISSING_CITATIONS",
            refusal_reason="Generated answer contains no citations. Cannot publish uncited medical claims.",
            citations=citations,
            grounded_claims=grounded_claims,
        )

    clinical_summary = extract_section(answer_text, "Clinical Summary")

    supported_count = sum(1 for gc in grounded_claims if gc.status == "SUPPORTED")
    unsupported_count = sum(1 for gc in grounded_claims if gc.status == "UNSUPPORTED")

    intent_pack = result.get("intent_pack", {})
    entities = intent_pack.get("entities", [])
    intent = result.get("intent", "other")

    conflicts = result.get("conflicts", [])
    meta = result.get("meta", {})

    debug = {
        "latency_ms": dt_ms,
        "engine": "veridoc_v2",
        "mode": result.get("mode", ""),
        "intent": intent,
        "entities": entities,
        "claims_supported": supported_count,
        "claims_unsupported": unsupported_count,
        "chunks_ranked": len(ranked),
        "conflicts": len(conflicts),
        "evidence_grade": strength_grade,
        "evidence_why": strength_info.get("why", "") if isinstance(strength_info, dict) else "",
        "cache_hit": meta.get("cache_hit", False),
        "coverage": meta.get("coverage"),
        "actions": result.get("actions", []),
    }

    raw_aci_ok = result.get("aci_score")
    aci_float_ok = raw_aci_ok.get("overall_confidence_0_10") if isinstance(raw_aci_ok, dict) else raw_aci_ok
    return AskOEResponse(
        status="ok",
        answer=answer_text,
        clinical_summary=clinical_summary,
        citations=citations,
        grounded_claims=grounded_claims,
        evidence_strength=strength_grade,
        aci_score=aci_float_ok,
        related_questions=[],
        next_search_terms=result.get("next_search_terms", []) if unsupported_count > 0 else [],
        debug=debug,
    )


async def answer_question_veridoc(
    question: str,
    db: Session,
    domain: Optional[str] = None,
    lang: str = "en",
    include_related: bool = True,
    include_tools: bool = True,
    mode: str = "fast",
) -> AskOEResponse:
    import asyncio
    t0 = time.time()

    retrieve_fn = _veridoc_retrieve_adapter(db, domain)
    engine = AesthetiCiteEngine(
        retrieve_fn=retrieve_fn,
        llm_json_fn=_veridoc_llm_json,
        llm_text_fn=_veridoc_llm_text,
        cache=_engine_cache,
    )

    result = await asyncio.to_thread(engine.answer, question, mode)
    dt_ms = int((time.time() - t0) * 1000)

    response = _map_veridoc_to_response(
        result, question,
        include_related=include_related,
        include_tools=include_tools,
        dt_ms=dt_ms,
    )

    if include_related and response.status == "ok":
        intent_pack = result.get("intent_pack", {})
        entities = intent_pack.get("entities", [])
        intent = result.get("intent", "other")
        related_user = (
            f"USER QUESTION:\n{question}\n\n"
            f"TOPIC: {intent}, entities: {', '.join(str(e) for e in entities[:5])}\n"
            "Return 4-6 safe follow-up questions."
        )
        try:
            rj = await llm_json(SYSTEM_RELATED, related_user, '{"questions":[...]}')
            qs = rj.get("questions", [])
            if isinstance(qs, list):
                response.related_questions = [str(x)[:160] for x in qs][:6]
        except Exception:  # nosec B110
            pass

    return response


# ─── ENDPOINT ─────────────────────────────────────────────────

@router.post("/ask_oe", response_model=AskOEResponse)
@limiter.limit(settings.RATE_LIMIT_ASK)
async def ask_oe(request: Request, body: AskOERequest, db: Session = Depends(get_db)) -> AskOEResponse:
    query = body.query.strip()
    if not query:
        return AskOEResponse(status="refuse", refusal_code="EMPTY_QUERY", refusal_reason="Empty query.")

    safety = safety_screen(query)
    if not safety.allowed:
        return AskOEResponse(
            status="refuse",
            refusal_code="SAFETY_BLOCK",
            refusal_reason=safety.refusal_reason or "Request refused by safety policy.",
        )

    if VERIDOC_ENABLED:
        return await answer_question_veridoc(
            question=query,
            db=db,
            domain=body.domain,
            lang=(body.lang or "en").lower().split("-")[0],
            include_related=body.include_related_questions,
            include_tools=body.include_inline_tools,
        )

    return await answer_question(
        question=query,
        db=db,
        domain=body.domain,
        lang=(body.lang or "en").lower().split("-")[0],
        include_related=body.include_related_questions,
        include_tools=body.include_inline_tools,
    )


@router.get("/ask_oe/health")
def health() -> Dict[str, str]:
    engine = "veridoc_v2" if VERIDOC_ENABLED else "pipeline_v2"
    return {"status": "ok", "module": "aestheticite_oe_upgrade_v2", "engine": engine}
