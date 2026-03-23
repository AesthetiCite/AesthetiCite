from __future__ import annotations
import re
import time
import uuid
import json
import os
import logging
from typing import Optional, AsyncGenerator, List, Dict, Any
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI

from app.schemas.ask import AskRequest
from app.core.config import settings
from app.core.safety import safety_screen
from app.core.limiter import limiter
from app.db.session import get_db
from app.rag.retriever import retrieve_db
from app.rag.citations import to_citations
from app.core.lang import detect_lang
from app.core.query_translator import get_retrieval_query, needs_translation
from app.rag.quality_guard import has_citations
from app.rag.cache import get_cached_answer, set_cached_answer, is_hot_question, HOT_QUESTION_TTL_SECONDS
from app.rag.interaction_detector import (
    detect_interaction_intent,
    get_structured_interactions,
    InteractionIntent
)
from app.rag.evidence_badge import compute_evidence_badge
from app.api.oe_upgrade import (
    classify_intent, extract_entities, build_subqueries,
    convert_retrieved_to_chunks, dedupe_chunks,
    VERIDOC_ENABLED, _veridoc_retrieve_adapter, _veridoc_llm_json, _veridoc_llm_text,
    _engine_cache,
    OE_TOP_K, OE_EVIDENCE_K, _llm_call, infer_tier, infer_study_type,
    SYSTEM_RELATED,
)
from app.engine.veridoc import AesthetiCiteEngine
from app.engine.improvements import (
    classify_chunk, DISPLAY_LABELS, evidence_rank_from_display,
    compute_aci_from_enriched, enrich_source_from_meta,
    protocol_followups, build_followup_hint,
)
from app.engine.quality_fusion import (
    retrieve_with_quality_fusion,
    source_to_citation_dict,
    Source as QFSource,
)

logger = logging.getLogger(__name__)

CITATION_RE = re.compile(r"\[S\d+\]")

HYBRID_ALPHA = float(os.environ.get("HYBRID_ALPHA", "0.65"))
GUIDELINE_BOOST = float(os.environ.get("GUIDELINE_BOOST", "0.12"))
SR_BOOST = float(os.environ.get("SR_BOOST", "0.08"))
RCT_BOOST = float(os.environ.get("RCT_BOOST", "0.05"))
OBS_PENALTY = float(os.environ.get("OBS_PENALTY", "0.03"))
CASE_PENALTY = float(os.environ.get("CASE_PENALTY", "0.06"))
NARR_PENALTY = float(os.environ.get("NARR_PENALTY", "0.08"))

_STUDY_TYPE_RANK = {
    "guideline": 1,
    "consensus": 2,
    "rct": 3,
    "systematic_review": 3,
    "meta_analysis": 3,
    "labeling": 2,
    "review": 5,
    "observational": 6,
    "case_report": 7,
    "expert": 8,
    "unknown": 9,
}

def _assign_evidence_rank(source: Dict[str, Any], db_session=None) -> int:
    if db_session:
        try:
            enriched_dict = enrich_source_from_meta(source, db_session)
            source.update(enriched_dict)
            return int(source.get("evidence_rank") or 9)
        except Exception:  # nosec B110
            pass
    enriched = classify_chunk(source)
    display_et = DISPLAY_LABELS.get(enriched.evidence_type, enriched.evidence_type)
    source["evidence_type"] = display_et
    source["evidence_type_raw"] = enriched.evidence_type
    source["evidence_tier"] = enriched.evidence_tier
    source["evidence_grade"] = enriched.evidence_grade
    return evidence_rank_from_display(display_et)


def evidence_rerank_inplace(sources: List[Dict[str, Any]], db_session=None) -> None:
    for s in sources:
        s["evidence_rank"] = _assign_evidence_rank(s, db_session=db_session)
    sources.sort(
        key=lambda s: (
            int(s.get("evidence_rank") or 9),
            -int(s.get("year") or 0),
        )
    )


def rewrite_query_rules(q: str) -> Dict[str, Any]:
    q0 = (q or "").strip()
    ql = q0.lower()

    complications_markers = [
        "vascular", "occlusion", "ischemia", "necrosis", "blindness", "embol", "artery", "hyaluronidase",
        "complication", "adverse", "safety", "contraindication"
    ]
    guideline_markers = ["guideline", "consensus", "recommendation", "position statement", "best practice"]
    dosing_markers = ["dose", "dosage", "units", "volume", "dilution", "reconstitution", "technique", "injection plane"]

    complications_mode = any(m in ql for m in complications_markers)
    guideline_first = complications_mode or any(m in ql for m in guideline_markers)

    hints = []
    if guideline_first:
        hints += ["guideline", "consensus", "recommendation", "position statement"]
    if complications_mode:
        hints += ["management", "algorithm", "emergency", "protocol"]

    q2 = q0
    if hints:
        q2 = f"{q0} ({' OR '.join(hints[:4])})"

    intent = "general"
    if complications_mode:
        intent = "complications"
    elif any(m in ql for m in dosing_markers):
        intent = "technique_or_dosing"
    elif guideline_first:
        intent = "guideline"

    return {"q2": q2, "intent": intent, "filters": {"guideline_first": guideline_first, "complications_mode": complications_mode}}


def hybrid_rerank_sources(enriched_sources: List[Dict[str, Any]]) -> None:
    import time as _time
    now_year = _time.gmtime().tm_year

    def _recency(year, now_yr):
        if not year or year < 1900 or year > now_yr:
            return 0.5
        age = max(0, now_yr - year)
        return 2 ** (-(age / 6.0))

    def boost_by_type(et: str) -> float:
        et_l = et.lower() if et else ""
        if "guideline" in et_l or "consensus" in et_l:
            return GUIDELINE_BOOST
        if "systematic" in et_l:
            return SR_BOOST
        if "random" in et_l or "rct" in et_l or "trial" in et_l:
            return RCT_BOOST
        if "observational" in et_l or "cohort" in et_l:
            return -OBS_PENALTY
        if "case" in et_l:
            return -CASE_PENALTY
        if "narrative" in et_l:
            return -NARR_PENALTY
        return 0.0

    for s in enriched_sources:
        et = s.get("evidence_type") or s.get("document_type") or "Other"
        y = s.get("year") if isinstance(s.get("year"), int) else None
        rec = _recency(y, now_year)

        vs = s.get("vector_score")
        fs = s.get("fts_score")

        if isinstance(vs, (int, float)) and isinstance(fs, (int, float)):
            blended = HYBRID_ALPHA * float(vs) + (1.0 - HYBRID_ALPHA) * float(fs)
            s["_rank_score"] = blended + boost_by_type(et) + 0.04 * rec
        else:
            s["_rank_score"] = -float(s.get("evidence_rank") or 9) + 0.06 * rec + boost_by_type(et)

    enriched_sources.sort(key=lambda s: float(s.get("_rank_score", -9999.0)), reverse=True)
    for s in enriched_sources:
        s.pop("_rank_score", None)


def validate_citations(answer: str) -> bool:
    if not CITATION_RE.search(answer or ""):
        return False
    m = re.search(
        r"Key Evidence-Based Points(.*?)(Safety Considerations|Limitations / Uncertainty|Suggested Follow-up Questions|Red Flags|Evidence Level|$)",
        answer,
        flags=re.S,
    )
    if m:
        block = m.group(1)
        bullets = re.findall(r"^\s*-\s+(.*)$", block, flags=re.M)
        for b in bullets:
            if not CITATION_RE.search(b):
                return False
    m2 = re.search(
        r"Evidence-Based Answer(.*?)(Red Flags|Safety Considerations|Evidence Level|Limitations|$)",
        answer,
        flags=re.S,
    )
    if m2:
        block = m2.group(1)
        bullets = re.findall(r"^\s*-\s+(.*)$", block, flags=re.M)
        uncited = sum(1 for b in bullets if not CITATION_RE.search(b))
        if bullets and uncited > len(bullets) * 0.5:
            return False
    return True


def citation_density(answer: str) -> float:
    if not answer:
        return 0.0
    cite_n = len(CITATION_RE.findall(answer))
    m = re.search(
        r"Key Evidence-Based Points(.*?)(Safety Considerations|Limitations / Uncertainty|Suggested Follow-up Questions|$)",
        answer,
        flags=re.S,
    )
    if m:
        bullets = re.findall(r"^\s*-\s+.*$", m.group(1), flags=re.M)
    else:
        bullets = re.findall(r"^\s*-\s+.*$", answer, flags=re.M)
    b_n = len(bullets)
    return (cite_n / b_n) if b_n else 0.0


CITATION_REFUSAL_ANSWER = (
    "**Clinical Summary**\n"
    "Evidence insufficient based on retrieved sources.\n\n"
    "**Key Evidence-Based Points**\n"
    "- Evidence insufficient based on retrieved sources. [S1]\n\n"
    "**Safety Considerations**\n"
    "If this topic involves vascular risk (e.g., fillers), use conservative technique and follow an occlusion response protocol.\n\n"
    "**Limitations / Uncertainty**\n"
    "Retrieved sources do not adequately support a grounded response at the requested specificity.\n\n"
    "**Suggested Follow-up Questions**\n"
    "- Can you narrow the question to a specific indication, product, and patient profile?\n"
    "- Should we restrict retrieval to guidelines/systematic reviews only?\n"
    "- Do you want dosing/technique omitted unless directly supported by retrieved sources?\n"
)

router = APIRouter(prefix="", tags=["ask-stream"])

def get_optional_user(request: Request, db: Session) -> Optional[dict]:
    """Get current user if auth is required, otherwise return None."""
    if not settings.REQUIRE_AUTH_FOR_ASK:
        return None
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")
    token = auth_header[7:]
    from app.core.auth import decode_token
    user_id = decode_token(token)
    row = db.execute(text("""
        SELECT id::text, email, is_active, role, created_at
        FROM users
        WHERE id = :id
    """), {"id": user_id}).mappings().first()
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return dict(row)


STREAM_SYSTEM_PROMPT_EN = """You are AesthetiCite, an evidence-first clinical decision support assistant for medical professionals.
You MUST obey these rules:
1) Use ONLY the provided Evidence Pack. Do not use outside knowledge.
2) Every clinical claim MUST have an inline citation like [S1] referring to the specific source.
3) If the Evidence Pack does not support an answer, say so explicitly.
4) Do NOT provide step-by-step emergency dosing/procedural instructions unless they are explicitly present in the Evidence Pack text.
5) Keep the tone clinical, cautious, and clear. Prefer consensus/guidelines/IFUs when available.
6) Format with markdown: **bold** for key points, bullet points for lists.
Output structure:
- **Clinical Summary**: Brief overview of the clinical context
- **Evidence-Based Answer**: Detailed response with inline [S#] citations for every claim
- **Red Flags / Considerations**: Safety notes and when to escalate
- **Evidence Level**: Quality assessment and limitations"""

STREAM_SYSTEM_PROMPT_FR = """Tu es AesthetiCite, une plateforme d'aide à la décision clinique evidence-first pour professionnels de santé.
Règles obligatoires :
1) Utilise UNIQUEMENT le "Evidence Pack" fourni. Pas de connaissance externe.
2) Chaque affirmation clinique doit avoir une citation inline comme [S1] renvoyant à la source correspondante.
3) Si le Evidence Pack ne permet pas de répondre, dis-le explicitement.
4) Ne donne pas de posologie ni de procédure d'urgence étape-par-étape sauf si elle est explicitement présente dans le Evidence Pack.
5) Ton clinique, prudent, structuré. Priorise consensus/guidelines/IFU quand disponible.
6) Formate avec markdown : **gras** pour les points clés, listes à puces.
Structure de sortie :
- **Résumé Clinique** : Aperçu du contexte clinique
- **Réponse Sourcée** : Réponse détaillée avec citations inline [S#] pour chaque affirmation
- **Signaux d'Alarme** : Notes de sécurité et quand escalader
- **Niveau de Preuve** : Évaluation de la qualité et limites"""

def build_streaming_prompt(question: str, mode: str, domain: str, retrieved: list, escalation_note: Optional[str] = None, query_intent: str = "general") -> str:
    """Build a prompt for streaming answer generation with strict citation rules."""
    context_parts = []
    for i, r in enumerate(retrieved[:8], 1):
        title = r.get("title", "Unknown")
        text_content = r.get("text", "")[:1400]
        year = r.get("year", "")
        journal = r.get("organization_or_journal", "")
        et = r.get("evidence_type") or r.get("document_type", "") or r.get("evidence_level", "")
        tier = r.get("evidence_tier") or ""
        tier_label = f" [Tier {tier}]" if tier else ""
        context_parts.append(f"[S{i}] {title} ({year}) — {et}{tier_label} — {journal}\nTEXT: {text_content}")
    
    context = "\n\n".join(context_parts)
    domain_name = domain.replace("_", " ").title()
    style = "concise clinical summary" if mode == "clinic" else "comprehensive evidence review"

    followup_hint = build_followup_hint(query_intent)
    
    prompt = f"""QUESTION: {question}
DOMAIN: {domain_name}
MODE: {style}

EVIDENCE PACK:
{context}

{f"SAFETY NOTE: {escalation_note}" if escalation_note else ""}

Instructions: Answer using ONLY the Evidence Pack. Cite every claim using [S#]. If evidence is insufficient, say so.
{followup_hint}"""
    
    return prompt


def generate_related_questions(question: str, domain: str) -> list:
    """Generate related questions based on the topic."""
    q_lower = question.lower()
    related = []
    
    if "hyaluronidase" in q_lower or "dissolve" in q_lower:
        related = [
            "What is the recommended hyaluronidase concentration for filler dissolution?",
            "How long should I wait between hyaluronidase injections?",
            "What are the signs of posthyaluronidase syndrome?",
        ]
    elif "vascular" in q_lower or "occlusion" in q_lower:
        related = [
            "What are the early signs of vascular occlusion?",
            "How quickly should treatment be initiated?",
            "What is the role of aspirin in vascular compromise?",
        ]
    elif "botox" in q_lower or "botulinum" in q_lower:
        related = [
            "What is the optimal dilution for botulinum toxin?",
            "How long until peak effect of botulinum toxin?",
            "What are contraindications for botulinum toxin?",
        ]
    else:
        related = [
            "What are the most common complications of dermal fillers?",
            "What are the high-risk zones for facial injection?",
            "What emergency equipment should be available?",
        ]
    
    return related[:3]


async def stream_answer(
    question: str,
    mode: str,
    domain: str,
    retrieved: list,
    citations: list,
    escalation_note: Optional[str],
    request_id: str,
    skip_meta: bool = False,
    query_intent: str = "general",
    precomputed_aci: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """Stream the answer using OpenAI API with strict citation enforcement."""

    has_high_level = any((s.get("evidence_rank") or 9) <= 3 for s in retrieved)

    evidence_badge = compute_evidence_badge(retrieved)
    if not has_high_level:
        evidence_badge["gaps"] = evidence_badge.get("gaps", [])
        evidence_badge["gaps"].append(
            "No guideline, systematic review, or randomized trial identified in top retrieved results"
        )

    if precomputed_aci is not None:
        aci = precomputed_aci
    else:
        aci = compute_aci_from_enriched(question, retrieved)

    meta_payload: Dict[str, Any] = {
        'type': 'meta',
        'request_id': request_id,
        'citations': [c.model_dump() for c in citations],
        'evidence_badge': evidence_badge,
        'aci_score': aci.get("score_0_to_10"),
        'aci_badge': aci.get("badge"),
        'aci_components': aci.get("components"),
        'aci_rationale': aci.get("rationale"),
    }

    if not skip_meta:
        yield f"data: {json.dumps(meta_payload)}\n\n"
    
    prompt = build_streaming_prompt(question, mode, domain, retrieved, escalation_note, query_intent=query_intent)
    
    lang = detect_lang(question)
    system_prompt = STREAM_SYSTEM_PROMPT_FR if lang == "fr" else STREAM_SYSTEM_PROMPT_EN
    
    client = OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )
    
    try:
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            stream=True,
            max_tokens=2000,
            temperature=0.2,
        )
        
        full_answer = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        
        is_refusal = full_answer.strip().lower().startswith("refusal:")

        if is_refusal:
            refusal_reason = "The evidence does not support a definitive answer."
            yield f"data: {json.dumps({'type': 'refusal', 'reason': refusal_reason})}\n\n"
            return

        if not validate_citations(full_answer):
            full_answer = CITATION_REFUSAL_ANSWER
            yield f"data: {json.dumps({'type': 'citation_replaced', 'reason': 'Original answer lacked inline citations; replaced with evidence-insufficient notice.'})}\n\n"

        cd = citation_density(full_answer)

        related = generate_related_questions(question, domain)
        yield f"data: {json.dumps({'type': 'related', 'questions': related})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'full_answer': full_answer, 'citation_density': round(cd, 2)})}\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


async def stream_answer_veridoc(
    question: str,
    db: Session,
    domain: str,
    request_id: str,
    escalation_note: Optional[str] = None,
    mode: str = "fast",
) -> AsyncGenerator[str, None]:
    """Stream answer using AesthetiCiteEngine v2 with FAST/DEEPCONSULT modes."""
    import asyncio

    retrieve_fn = _veridoc_retrieve_adapter(db, domain)
    engine = AesthetiCiteEngine(
        retrieve_fn=retrieve_fn,
        llm_json_fn=_veridoc_llm_json,
        llm_text_fn=_veridoc_llm_text,
        cache=_engine_cache,
    )

    result = await asyncio.to_thread(engine.answer, question, mode)

    strength = result.get("evidence_strength", {})
    grade = strength.get("grade", "Limited") if isinstance(strength, dict) else str(strength)

    if grade == "Insufficient":
        yield f"data: {json.dumps({'type': 'refusal', 'reason': result.get('clinical_answer', 'Insufficient evidence.')})}\n\n"
        return

    answer_text = result.get("clinical_answer")
    if not answer_text:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Answer generation failed.'})}\n\n"
        return

    ranked = result.get("ranked_chunks", [])
    for ch in ranked:
        enriched = classify_chunk(ch)
        display_et = DISPLAY_LABELS.get(enriched.evidence_type, enriched.evidence_type)
        ch["evidence_type"] = display_et
        ch["evidence_type_raw"] = enriched.evidence_type
        ch["evidence_tier"] = enriched.evidence_tier
        ch["evidence_grade"] = enriched.evidence_grade
        ch["evidence_rank"] = evidence_rank_from_display(display_et)

    citations_data = []
    for i, ch in enumerate(ranked, start=1):
        citations_data.append({
            "source_id": ch.get("source_id") or ch.get("id", ""),
            "title": ch.get("title"),
            "url": ch.get("url"),
            "year": ch.get("year"),
            "source_type": ch.get("source_type", "other"),
            "domain": ch.get("domain", ""),
            "label": f"S{i}",
            "evidence_type": ch.get("evidence_type"),
            "evidence_tier": ch.get("evidence_tier"),
            "evidence_grade": ch.get("evidence_grade"),
        })

    evidence_badge = {
        "level": grade,
        "label": f"Evidence: {grade}",
        "color": {"High": "green", "Moderate": "yellow", "Low": "orange"}.get(grade, "gray"),
    }

    det_aci = compute_aci_from_enriched(question, ranked)

    supported = result.get("supported_claims", [])
    excluded = result.get("excluded_claims", [])
    conflicts = result.get("conflicts", [])
    meta = result.get("meta", {})
    actions = result.get("actions", [])
    query_meta = result.get("query_meta", None)
    complication_protocol = result.get("complication_protocol", None)
    inline_tools = result.get("inline_tools", [])

    meta_payload = {
        'type': 'meta',
        'request_id': request_id,
        'citations': citations_data,
        'evidence_badge': evidence_badge,
        'engine': 'veridoc_v2',
        'mode': result.get('mode', ''),
        'grounded_claims': {
            'supported': len(supported),
            'excluded': len(excluded),
            'conflicts': len(conflicts),
        },
        'cache_hit': meta.get('cache_hit', False),
        'actions': actions,
        'aci_score': det_aci.get("score_0_to_10"),
        'aci_badge': det_aci.get("badge"),
        'aci_components': det_aci.get("components"),
        'aci_rationale': det_aci.get("rationale"),
    }
    if query_meta:
        meta_payload['query_meta'] = query_meta
    if complication_protocol:
        meta_payload['complication_protocol'] = complication_protocol
    if inline_tools:
        meta_payload['inline_tools'] = inline_tools

    yield f"data: {json.dumps(meta_payload)}\n\n"

    if not validate_citations(answer_text):
        answer_text = CITATION_REFUSAL_ANSWER
        yield f"data: {json.dumps({'type': 'citation_replaced', 'reason': 'Original answer lacked inline citations; replaced with evidence-insufficient notice.'})}\n\n"

    for i in range(0, len(answer_text), 12):
        token = answer_text[i:i+12]
        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    intent_pack = result.get("intent_pack", {})
    entities = intent_pack.get("entities", [])
    intent = result.get("intent", "other")
    try:
        related_prompt = (
            f"USER QUESTION:\n{question}\n\n"
            f"TOPIC: {intent}, entities: {', '.join(str(e) for e in entities[:5])}\n"
            "Return 4-6 safe follow-up questions."
        )
        rj_messages = [
            {"role": "system", "content": "You generate safe follow-up questions for clinicians.\nRules:\n- Questions must be evidence-based and not encourage unsafe actions.\n- Keep them short.\n- Return JSON only: {\"questions\": [..]}."},
            {"role": "user", "content": related_prompt},
        ]
        rj_raw = _llm_call(rj_messages, json_mode=True)
        rj = json.loads(rj_raw)
        related = [str(x)[:160] for x in rj.get("questions", [])][:6]
    except Exception:
        related = generate_related_questions(question, domain)

    yield f"data: {json.dumps({'type': 'related', 'questions': related})}\n\n"

    cd = citation_density(answer_text)
    yield f"data: {json.dumps({'type': 'done', 'full_answer': answer_text, 'citation_density': round(cd, 2)})}\n\n"


async def prepare_interaction_evidence(
    intent: InteractionIntent,
) -> tuple:
    """
    Prepare RxNav interaction data as Evidence Pack entries.
    
    Returns (rxnav_evidence_entry, interactions_list) where rxnav_evidence_entry 
    can be added to the retrieved evidence for LLM processing.
    """
    drug_names = [m.name for m in intent.detected_drugs[:5]]
    
    interactions = []
    if len(drug_names) >= 2:
        try:
            interactions = await get_structured_interactions(drug_names)
            logger.info(f"Found {len(interactions)} interactions for {len(drug_names)} agents")
        except Exception as e:
            logger.error(f"Failed to get interactions: {e}")
    
    if not interactions:
        return None, []
    
    # Format RxNav data as an Evidence Pack entry
    rxnav_text_parts = []
    for interaction in interactions:
        rxnav_text_parts.append(
            f"Drug Interaction: {interaction.drug_a} + {interaction.drug_b}. "
            f"Severity: {interaction.severity or 'Not specified'}. "
            f"Clinical Significance: {interaction.clinical_significance}. "
            f"Mechanism: {interaction.mechanism}. "
            f"Description: {interaction.description}. "
            f"Management: {interaction.management}."
        )
    
    rxnav_evidence = {
        "source_id": "rxnav_nih",
        "title": "NIH RxNav Drug Interaction Database",
        "year": 2024,
        "organization_or_journal": "National Library of Medicine",
        "document_type": "database",
        "domain": "drug_interactions",
        "page_or_section": "interaction_data",
        "evidence_level": "Level II",
        "text": " ".join(rxnav_text_parts),
    }
    
    return rxnav_evidence, interactions


@router.post("/ask/stream")
@limiter.limit(settings.RATE_LIMIT_ASK)
async def ask_stream(payload: AskRequest, request: Request, db: Session = Depends(get_db)):
    """Streaming version of the ask endpoint with caching and drug interaction support."""
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    
    user = get_optional_user(request, db) if settings.REQUIRE_AUTH_FOR_ASK else None
    user_id = user["id"] if user else (request.client.host if request.client else None)
    
    # Safety check
    safety = safety_screen(payload.question)
    if not safety.allowed:
        async def refusal_stream():
            yield f"data: {json.dumps({'type': 'refusal', 'reason': safety.refusal_reason or 'Request refused by safety policy.'})}\n\n"
        return StreamingResponse(refusal_stream(), media_type="text/event-stream")
    
    # Check answer cache for hot questions
    is_hot = is_hot_question(payload.question)
    cached_answer = get_cached_answer(payload.question)
    
    if cached_answer:
        logger.info(f"Cache hit for query: {payload.question[:50]}...")
        async def cached_stream():
            yield f"data: {json.dumps({'type': 'meta', 'request_id': request_id, 'citations': cached_answer.get('citations', []), 'cached': True})}\n\n"
            answer = cached_answer.get('answer', '')
            # Stream cached answer in chunks
            for i in range(0, len(answer), 100):
                yield f"data: {json.dumps({'type': 'token', 'content': answer[i:i+100]})}\n\n"
            related = generate_related_questions(payload.question, payload.domain)
            yield f"data: {json.dumps({'type': 'related', 'questions': related})}\n\n"
            cd = citation_density(answer)
            yield f"data: {json.dumps({'type': 'done', 'full_answer': answer, 'cached': True, 'citation_density': round(cd, 2)})}\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")
    
    # Detect drug interaction intent
    interaction_intent = detect_interaction_intent(payload.question)
    
    # Multilingual translation for weak/mixed retrieval languages
    _stream_detected_lang = detect_lang(payload.question)
    _stream_retrieval_q, _stream_native_q = get_retrieval_query(payload.question, _stream_detected_lang)
    if _stream_native_q:
        logger.info(f"[ask_stream] Multilingual: lang={_stream_detected_lang}, translated='{_stream_retrieval_q[:80]}'")

    # Rules-based query rewrite for retrieval precision
    rq = rewrite_query_rules(_stream_retrieval_q)
    q_for_retrieval = rq["q2"]
    query_intent = rq["intent"]

    # Retrieve evidence with subquery expansion for better coverage
    intent = classify_intent(payload.question)
    entities = extract_entities(payload.question)
    subqueries = build_subqueries(q_for_retrieval, intent, entities)
    
    all_retrieved = []
    seen_keys = set()
    for sq in subqueries:
        sq_results = retrieve_db(db=db, question=sq, domain=payload.domain, k=12)
        for r in sq_results:
            key = (r.get("source_id", ""), r.get("page_or_section", ""))
            if key not in seen_keys:
                seen_keys.add(key)
                all_retrieved.append(r)

    _stream_lang_strategy = needs_translation(_stream_detected_lang)
    if _stream_lang_strategy == "dual" and _stream_native_q:
        native_rq = rewrite_query_rules(_stream_native_q)
        native_subqueries = build_subqueries(native_rq["q2"], intent, entities)
        for sq in native_subqueries:
            sq_results = retrieve_db(db=db, question=sq, domain=payload.domain, k=8)
            for r in sq_results:
                key = (r.get("source_id", ""), r.get("page_or_section", ""))
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_retrieved.append(r)
        logger.info(f"[ask_stream] Dual retrieval: added native query results, total={len(all_retrieved)}")

    def _legacy_retrieve_adapter(query: str, k: int, filters=None) -> list:
        try:
            return retrieve_db(db=db, question=query, domain=payload.domain, k=k)
        except Exception:
            return []

    qf_aci_dict = None
    try:
        qf_bundle = retrieve_with_quality_fusion(
            _stream_retrieval_q,
            _legacy_retrieve_adapter,
            k_final=20,
            k_quality=15,
            k_general=20,
        )
        qf_sources: list = qf_bundle["sources"]
        _qf_aci = qf_bundle["aci"]
        qf_aci_dict = {
            "score_0_to_10": _qf_aci.score_0_to_10,
            "badge": _qf_aci.badge,
            "components": _qf_aci.components,
            "rationale": _qf_aci.rationale,
        }

        if qf_sources and len(qf_sources) >= 2:
            merged_by_key = {}
            for r in all_retrieved:
                k2 = (r.get("source_id", ""), r.get("title", ""))
                merged_by_key[k2] = r
            for s in qf_sources:
                k2 = (s.source_id or s.id, s.title)
                if k2 not in merged_by_key:
                    raw = s._raw if s._raw else {}
                    raw.update({
                        "title": s.title, "year": s.year, "journal": s.journal,
                        "source_id": s.source_id, "evidence_type": s.evidence_type,
                        "evidence_tier": s.evidence_tier, "publication_type": s.publication_type,
                        "chunk_text": s.chunk_text or raw.get("chunk_text", ""),
                    })
                    all_retrieved.append(raw)
            logger.info(
                f"Legacy quality fusion: {len(qf_sources)} sources, "
                f"tiers={sum(1 for s in qf_sources if s.evidence_tier == 'A')}A/"
                f"{sum(1 for s in qf_sources if s.evidence_tier == 'B')}B/"
                f"{sum(1 for s in qf_sources if s.evidence_tier == 'C')}C"
            )
    except Exception as e:
        logger.warning(f"Legacy quality fusion failed: {e}")

    retrieved = all_retrieved[:12]
    evidence_rerank_inplace(retrieved, db_session=db)
    hybrid_rerank_sources(retrieved)
    citations = to_citations(retrieved)
    
    # For interaction queries, fetch RxNav data and add to Evidence Pack
    rxnav_evidence = None
    interactions_data = []
    if interaction_intent.is_interaction_query and len(interaction_intent.detected_drugs) >= 2:
        logger.info(f"Interaction query detected with {len(interaction_intent.detected_drugs)} agent(s)")
        rxnav_evidence, interactions_data = await prepare_interaction_evidence(interaction_intent)
        
        # Add RxNav evidence to retrieved documents for LLM processing
        if rxnav_evidence:
            retrieved.insert(0, rxnav_evidence)  # Prepend as primary source
            # Regenerate citations with RxNav included
            citations = to_citations(retrieved)
    
    # Enforce standard citation requirements for all queries
    if len(citations) < settings.MIN_CITATIONS_REQUIRED:
        async def insufficient_stream():
            yield f"data: {json.dumps({'type': 'refusal', 'reason': 'Insufficient evidence retrieved to answer with citations.'})}\n\n"
        return StreamingResponse(insufficient_stream(), media_type="text/event-stream")
    
    # Log the query
    db.execute(text("""
      INSERT INTO queries (id, user_id, question, domain, mode, latency_ms, citations_count, refusal, refusal_reason)
      VALUES (:id, :user_id, :q, :domain, :mode, 0, :cc, false, NULL);
    """), {
        "id": request_id,
        "user_id": user_id,
        "q": payload.question,
        "domain": payload.domain,
        "mode": payload.mode,
        "cc": len(citations),
    })
    db.commit()
    
    # For interaction queries, add metadata about detected interactions but use standard LLM flow
    # This ensures all claims go through the Evidence Pack constraint
    if interaction_intent.is_interaction_query and interactions_data:
        async def interaction_stream_with_metadata():
            full_answer = ""
            
            # Stream the answer using standard RAG flow (RxNav is now in Evidence Pack)
            async for event in stream_answer(
                question=payload.question,
                mode=payload.mode,
                domain=payload.domain,
                retrieved=retrieved,
                citations=citations,
                escalation_note=safety.escalation_note,
                request_id=request_id,
                query_intent=query_intent,
                precomputed_aci=qf_aci_dict,
            ):
                yield event
                try:
                    if event.startswith("data: "):
                        data = json.loads(event[6:].strip())
                        if data.get('type') == 'token':
                            full_answer += data.get('content', '')
                except:  # nosec B110
                    pass
            
            # Emit structured interaction metadata after LLM response
            yield f"data: {json.dumps({'type': 'interactions', 'data': [{'drug_a': i.drug_a, 'drug_b': i.drug_b, 'severity': i.severity, 'description': i.description, 'source': i.source} for i in interactions_data]})}\n\n"
            
            # Cache hot question answers
            if is_hot and full_answer:
                set_cached_answer(
                    payload.question,
                    full_answer,
                    citations=[c.model_dump() for c in citations],
                    is_hot=True
                )
        
        return StreamingResponse(
            interaction_stream_with_metadata(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    # VeriDoc-powered stream (grounded, claim-verified)
    if VERIDOC_ENABLED:
        async def veridoc_stream_with_cache():
            full_answer = ""
            async for event in stream_answer_veridoc(
                question=payload.question,
                db=db,
                domain=payload.domain,
                request_id=request_id,
                escalation_note=safety.escalation_note,
            ):
                yield event
                try:
                    if event.startswith("data: "):
                        data = json.loads(event[6:].strip())
                        if data.get('type') == 'token':
                            full_answer += data.get('content', '')
                except:  # nosec B110
                    pass
            if is_hot and full_answer:
                set_cached_answer(
                    payload.question,
                    full_answer,
                    citations=[],
                    is_hot=True
                )

        return StreamingResponse(
            veridoc_stream_with_cache(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    # Standard RAG stream with caching (legacy)
    async def standard_stream_with_cache():
        full_answer = ""
        async for event in stream_answer(
            question=payload.question,
            mode=payload.mode,
            domain=payload.domain,
            retrieved=retrieved,
            citations=citations,
            escalation_note=safety.escalation_note,
            request_id=request_id,
            query_intent=query_intent,
            precomputed_aci=qf_aci_dict,
        ):
            yield event
            try:
                if event.startswith("data: "):
                    data = json.loads(event[6:].strip())
                    if data.get('type') == 'token':
                        full_answer += data.get('content', '')
            except:  # nosec B110
                pass
        if is_hot and full_answer:
            set_cached_answer(
                payload.question,
                full_answer,
                citations=[c.model_dump() for c in citations],
                is_hot=True
            )
    
    return StreamingResponse(
        standard_stream_with_cache(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
