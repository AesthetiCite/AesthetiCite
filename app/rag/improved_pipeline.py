"""
Improved QA Pipeline for AesthetiCite
=====================================
Addresses benchmark accuracy issues with:
1. Wide retrieval → quality-weighted reranking
2. Evidence gating for high-stakes queries
3. Claim extraction + verification
4. Automatic answer downgrade when claims unsupported
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# -----------------------------
# Config knobs
# -----------------------------
WIDE_K = 50            # initial fetch size (from vector/BM25/hybrid)
FINAL_K = 18           # what you pass to the answer model
MIN_PI_OR_GUIDELINE = 1
MIN_TOTAL_SOURCES = 3  # unique sources
MAX_VERIFY_CLAIMS = 6

HIGH_STAKES_KEYWORDS = [
    "dose", "dosing", "units", "mg", "mcg", "ml", "maximum", "max dose",
    "vascular occlusion", "blindness", "necrosis", "anaphyl", "lidocaine",
    "hyaluronidase", "emergency", "complication", "adverse", "contraindic"
]


# -----------------------------
# Helpers
# -----------------------------
def is_high_stakes(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in HIGH_STAKES_KEYWORDS)


def uniq_sources(chunks: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def quality_weight(source_type: str) -> float:
    st = (source_type or "other").lower()
    if st == "pi":
        return 1.00
    if st == "guideline":
        return 0.95
    if st == "meta_analysis":
        return 0.85
    if st == "rct":
        return 0.80
    if st == "case_series":
        return 0.55
    if st == "review":
        return 0.50
    return 0.35


def rerank_simple(query: str, chunks: List[dict]) -> List[dict]:
    """
    Lightweight reranker: combines keyword overlap + quality weight.
    """
    q_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored = []
    for c in chunks:
        text = (c.get("text") or "").lower()
        overlap = sum(1 for t in q_terms if t in text)
        qw = quality_weight(c.get("source_type"))
        
        # Boost for PI and guideline sources
        pi_boost = 3.0 if c.get("source_type", "").lower() in ("pi", "guideline") else 0
        
        # Boost for recent publications
        year = c.get("year") or 0
        recency_boost = 0.5 if year >= 2020 else 0
        
        score = overlap * 1.0 + qw * 5.0 + pi_boost + recency_boost
        scored.append((score, c))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


def evidence_gate(query: str, chunks: List[dict]) -> Tuple[bool, str]:
    """
    Returns (ok_to_answer, reason_if_not).
    For high-stakes questions, require PI/guideline presence and enough unique sources.
    """
    u = uniq_sources(chunks)
    if not u:
        return False, "no_sources"

    if not is_high_stakes(query):
        if len(u) < 2:
            return False, "too_few_sources"
        return True, ""

    # High-stakes gating
    pi_guideline = sum(
        1 for c in u 
        if (c.get("source_type") or "").lower() in ("pi", "guideline")
    )
    if pi_guideline < MIN_PI_OR_GUIDELINE:
        return False, "no_pi_or_guideline_for_high_stakes"
    if len(u) < MIN_TOTAL_SOURCES:
        return False, "too_few_unique_sources_for_high_stakes"

    return True, ""


# -----------------------------
# Claim extraction + verification
# -----------------------------
def extract_critical_claims(query: str, draft_answer: str) -> List[str]:
    """
    Extract numeric/clinical claims that need verification.
    """
    claims = []
    for line in draft_answer.splitlines():
        line = line.strip()
        # Look for lines with numbers (doses, percentages, etc.)
        if re.search(r"\b(\d+(\.\d+)?)\s*(mg|ml|units|%|mcg|cc)\b", line, re.I):
            claims.append(line)
        # Look for dosing recommendations
        elif re.search(r"\b(dose|dosing|maximum|recommend|contraindic)\b", line, re.I):
            if len(line) > 20:
                claims.append(line)
    return claims[:MAX_VERIFY_CLAIMS]


def claim_supported(claim: str, evidence_texts: List[str]) -> bool:
    """
    Deterministic check: tries to find key numbers/phrases from claim in evidence text.
    """
    c = claim.lower()
    nums = re.findall(r"\b\d+(\.\d+)?\b", c)
    
    for ev in evidence_texts:
        evl = ev.lower()
        if nums:
            # All numbers in claim must appear somewhere (strict)
            if all(n in evl for n in nums):
                # Also require at least one medical keyword overlap
                kw = [w for w in re.findall(r"[a-z]{4,}", c) 
                      if w not in ("this", "that", "with", "from", "into", "should", "would", "could")]
                if any(k in evl for k in kw[:6]):
                    return True
        else:
            # Non-numeric claim: require 2+ key tokens present
            kw = [w for w in re.findall(r"[a-z]{4,}", c)]
            hit = sum(1 for k in set(kw[:10]) if k in evl)
            if hit >= 2:
                return True
    return False


def verify_or_downgrade_answer(
    draft_answer: str, 
    chunks: List[dict], 
    claims: List[str]
) -> Tuple[str, Dict[str, Any]]:
    """
    Verify claims against evidence. If unsupported, add disclaimer.
    """
    evidence_texts = [(c.get("text") or "") for c in chunks]
    supported = []
    unsupported = []
    
    for cl in claims:
        if claim_supported(cl, evidence_texts):
            supported.append(cl)
        else:
            unsupported.append(cl)

    if unsupported:
        revised = draft_answer.strip()
        revised += "\n\n**Evidence Check:**\n"
        revised += "Some specific details could not be directly verified in the retrieved sources. "
        revised += "Where uncertainty exists, follow the product prescribing information and local protocol."
        meta = {"claims_supported": supported, "claims_unsupported": unsupported}
        return revised, meta

    return draft_answer, {"claims_supported": supported, "claims_unsupported": []}


# -----------------------------
# MAIN: improved QA flow
# -----------------------------
def improved_qa_pipeline(
    query: str, 
    retrieve_fn, 
    llm_fn,
    filters: Optional[dict] = None,
    wide_k: int = WIDE_K,
    final_k: int = FINAL_K
) -> Dict[str, Any]:
    """
    Improved QA pipeline with evidence gating and claim verification.
    
    Args:
        query: User question
        retrieve_fn: Function(query, k) -> List[dict] of chunks
        llm_fn: Function(system, user, temperature) -> str
        filters: Optional retrieval filters
        wide_k: Initial retrieval size
        final_k: Final chunks after reranking
    
    Returns:
        Dict with answer, meta, citations
    """

    # 1) Wide retrieval
    wide = retrieve_fn(query, k=wide_k)
    if len(wide) > wide_k:
        wide = wide[:wide_k]

    # 2) Rerank + take top final_k
    reranked = rerank_simple(query, wide)
    top = reranked[:final_k]

    # 3) Evidence gate (refuse or proceed)
    ok, reason = evidence_gate(query, top)
    if not ok:
        return {
            "answer": (
                "**Clinical Summary:**\n"
                "Insufficient high-quality evidence was retrieved to provide a reliable, specific answer to this question.\n\n"
                "**Practical Steps:**\n"
                "- Use prescribing information / guidelines for the exact product and indication.\n"
                "- If this is a high-risk scenario, follow emergency and escalation protocols.\n\n"
                "**Evidence Notes:**\n"
                f"Refusal reason: {reason}."
            ),
            "meta": {
                "refused": True, 
                "reason": reason, 
                "wide_k": len(wide), 
                "final_k": len(top)
            },
            "citations": [
                {
                    "title": c.get("title"), 
                    "year": c.get("year"), 
                    "source_type": c.get("source_type"), 
                    "doi": c.get("doi"), 
                    "url": c.get("url")
                } 
                for c in uniq_sources(top)[:8]
            ],
        }

    # 4) Build evidence context
    evidence_pack = []
    for i, c in enumerate(uniq_sources(top)[:8], 1):
        src_type = c.get("source_type", "").upper() or "OTHER"
        year = c.get("year", "")
        title = c.get("title", "")[:100]
        text_snippet = (c.get("text") or "")[:800]
        evidence_pack.append(f"[S{i}] ({src_type}, {year}) {title}\n{text_snippet}")
    
    evidence_text = "\n\n---\n\n".join(evidence_pack)

    # 5) Generate draft answer
    system = (
        "You are AesthetiCite, clinician-facing decision support for aesthetic medicine.\n"
        "Be conservative. Prefer PI/guidelines over other sources. If uncertain, say 'insufficient evidence'.\n"
        "Include inline citations like [S1], [S2] referencing the sources.\n"
        "Return sections:\n"
        "- **Clinical Summary**: Brief overview\n"
        "- **Evidence-Based Answer**: Detailed response with citations\n"
        "- **Complications & Red Flags**: Safety considerations\n"
        "- **Evidence Notes**: Quality assessment"
    )
    user = f"Question: {query}\n\n**Evidence Pack:**\n{evidence_text}"
    draft = llm_fn(system, user, temperature=0.2)

    # 6) Claim verification (deterministic)
    claims = extract_critical_claims(query, draft)
    final_answer, verify_meta = verify_or_downgrade_answer(draft, top, claims)

    return {
        "answer": final_answer,
        "meta": {
            "refused": False,
            "wide_k": len(wide),
            "final_k": len(top),
            "high_stakes": is_high_stakes(query),
            "verification": verify_meta,
        },
        "citations": [
            {
                "id": i + 1,
                "title": c.get("title"), 
                "year": c.get("year"), 
                "source_type": c.get("source_type"), 
                "doi": c.get("doi"), 
                "url": c.get("url")
            } 
            for i, c in enumerate(uniq_sources(top)[:8])
        ],
    }
