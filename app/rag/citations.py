from __future__ import annotations
from typing import List, Dict
from app.schemas.ask import Citation
from app.core.evidence import normalize_evidence_level

SNIPPET_MAX = 240  # keep short (QA only)

def _snippet(text: str | None) -> str | None:
    if not text:
        return None
    t = " ".join(text.split())
    if len(t) <= SNIPPET_MAX:
        return t
    return t[:SNIPPET_MAX].rstrip() + "…"

def to_citations(chunks: List[Dict]) -> List[Citation]:
    citations: List[Citation] = []
    seen = set()
    for c in chunks:
        key = (c.get("source_id"), c.get("page_or_section"))
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(
            source_id=c.get("source_id", ""),
            title=c.get("title", "Unknown source"),
            year=c.get("year"),
            organization_or_journal=c.get("organization_or_journal"),
            page_or_section=c.get("page_or_section"),
            evidence_level=normalize_evidence_level(c.get("evidence_level")),
            snippet=_snippet(c.get("text")),
        ))
    return citations
