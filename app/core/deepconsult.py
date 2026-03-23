"""
AesthetiCite — DeepConsult Upgrade Pack (ALL 3 features)
========================================================
Implements:
A) Automatic routing (/qa → /deepconsult) when query is complex multi-study analysis
B) Citation-grade PDF export (ReportLab) for DeepConsult results
C) Literature disagreement detector (flags conflicts across sources)

PhD-level multi-study analysis for complex research questions.
"""

from __future__ import annotations

import os
import re
import io
import json
import time
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

logger = logging.getLogger(__name__)

DEEP_MODEL = os.getenv("OPENAI_MODEL_DEEP", "gpt-4.1")
FAST_MODEL = os.getenv("OPENAI_MODEL_FAST", "gpt-4.1-mini")


def llm_text_deep(system: str, user: str, temperature: float = 0.1) -> str:
    """Use the slower, more rigorous model for deep analysis."""
    from app.openai_wiring import llm_text as _llm_text
    return _llm_text(system, user, temperature=temperature, model=DEEP_MODEL)


def llm_json_deep(system: str, user: str, temperature: float = 0.1) -> dict:
    """Parse JSON from deep model response."""
    txt = llm_text_deep(system, user, temperature=temperature).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        txt = m.group(0)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {txt[:300]}")
        return {}


def _st(c: dict) -> str:
    """Get normalized source type."""
    return (c.get("source_type") or "other").lower().strip()


def _uniq_sources(chunks: List[dict]) -> List[dict]:
    """Deduplicate sources by DOI/title."""
    seen = set()
    out = []
    for c in chunks:
        key = c.get("doi") or c.get("url") or c.get("title") or c.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def format_citations(chunks: List[dict], max_items: int = 25) -> List[dict]:
    """Format citations for output."""
    out = []
    for c in _uniq_sources(chunks)[:max_items]:
        out.append({
            "title": c.get("title"),
            "year": c.get("year"),
            "source_type": c.get("source_type"),
            "doi": c.get("doi"),
            "url": c.get("url"),
        })
    return out


STUDY_QUALITY = {
    "meta_analysis": 1.0,
    "systematic_review": 0.95,
    "guideline": 0.90,
    "rct": 0.85,
    "cohort": 0.70,
    "case_control": 0.65,
    "case_series": 0.55,
    "case_report": 0.45,
    "review": 0.50,
    "pi": 0.80,
    "textbook": 0.40,
    "other": 0.30,
}


def quality_score(c: dict) -> float:
    return STUDY_QUALITY.get(_st(c), 0.30)


@dataclass
class RoutingThresholds:
    """Thresholds for automatic routing to DeepConsult."""
    keyword_trigger: bool = True
    min_high_level_sources: int = 2
    min_total_sources: int = 10
    query_length_trigger: int = 140
    complexity_score_trigger: float = 0.62


DEEP_KEYWORDS = [
    "systematic review", "meta-analysis", "meta analysis", "multiple studies",
    "compare studies", "conflicting", "heterogeneity", "bias", "risk of bias",
    "evidence synthesis", "literature", "what does the evidence say", "overall evidence",
    "guideline comparison", "pooled analysis", "compare the research"
]


def classify_need_deepconsult(
    query: str,
    chunks: List[dict],
    th: RoutingThresholds = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Deterministic router to decide if query needs DeepConsult.
    Returns (use_deep, routing_metadata).
    """
    th = th or RoutingThresholds()
    q = (query or "").lower()
    u = _uniq_sources(chunks)
    total = len(u)

    hi = sum(1 for c in u if _st(c) in ("meta_analysis", "systematic_review", "guideline", "rct"))
    kw = any(k in q for k in DEEP_KEYWORDS) if th.keyword_trigger else False
    longq = len(query) >= th.query_length_trigger

    score = 0.0
    score += 0.35 if kw else 0.0
    score += 0.20 if longq else 0.0
    score += 0.30 * min(1.0, hi / max(1, th.min_high_level_sources))
    score += 0.15 * min(1.0, total / max(1, th.min_total_sources))

    use_deep = (
        (score >= th.complexity_score_trigger) or
        (kw and hi >= 1) or
        (hi >= th.min_high_level_sources and total >= th.min_total_sources)
    )

    return use_deep, {
        "router_score": round(score, 3),
        "has_deep_keywords": kw,
        "query_length": len(query),
        "high_level_sources": hi,
        "unique_sources": total,
        "threshold": th.complexity_score_trigger,
    }


class DisagreementResult(BaseModel):
    """Result from literature disagreement detector."""
    conflict_found: bool
    conflict_score: float
    interpretation: str  # Clear label: "No Conflict", "Uncertain/Mixed", "Conflicting"
    topics: List[str]
    conflicting_claims: List[dict]
    notes: str


def interpret_conflict_score(score: float, llm_conflict: bool) -> Tuple[bool, str]:
    """
    Three-level interpretation of disagreement signals.
    Returns (conflict_found, interpretation_label).
    
    Thresholds (academic reviewer language):
    - < 0.35: No meaningful disagreement detected
    - 0.35-0.70: Mixed/uncertain evidence signals
    - >= 0.70 + LLM confirms: True conflict (directionally different conclusions)
    """
    # Only declare conflict if both high score AND LLM confirms
    if score >= 0.70 and llm_conflict:
        return True, "Conflicting findings detected across sources (directionally different conclusions)."
    elif score >= 0.35:
        return False, "Mixed/uncertain evidence signals (variation or limitations), but no direct contradiction identified."
    else:
        return False, "No meaningful disagreement detected."


def disagreement_detector(query: str, chunks: List[dict]) -> DisagreementResult:
    """
    Detect literature disagreement across sources.
    Uses hybrid approach: heuristics + LLM extraction.
    """
    u = _uniq_sources(chunks)
    texts = [(c.get("text") or "")[:1800] for c in u[:18]]
    joined = "\n\n---\n\n".join(texts).lower()

    cues = [
        "conflict", "inconsistent", "mixed results", "heterogeneity",
        "no difference", "significant", "increased risk", "decreased risk",
        "not significant", "however", "whereas", "controversial",
        "disputed", "debate", "contradictory"
    ]
    cue_hits = sum(1 for w in cues if w in joined)
    conflict_score = min(1.0, cue_hits / 10.0)

    # Low score: skip LLM call, no meaningful disagreement
    if conflict_score < 0.35:
        return DisagreementResult(
            conflict_found=False,
            conflict_score=round(conflict_score, 2),
            interpretation="No meaningful disagreement detected.",
            topics=[],
            conflicting_claims=[],
            notes="No strong disagreement signals detected in retrieved evidence."
        )

    system = (
        "You are a biomedical research analyst. Detect literature disagreement across studies.\n"
        "Return STRICT JSON only with schema:\n"
        "{\n"
        "  \"conflict_found\": boolean,\n"
        "  \"topics\": [string],\n"
        "  \"conflicting_claims\": [\n"
        "    {\"claim_a\": string, \"supporting_source_a\": string,\n"
        "     \"claim_b\": string, \"supporting_source_b\": string,\n"
        "     \"why_conflict\": string, \"possible_explanations\": [string]}\n"
        "  ],\n"
        "  \"notes\": string\n"
        "}\n"
        "Rules:\n"
        "- Be conservative: only mark conflict if claims truly diverge.\n"
        "- Cite sources by title/year when possible.\n"
        "- If evidence is just 'uncertain' rather than conflicting, say so.\n"
    )

    evidence_rows = []
    for c in u[:18]:
        evidence_rows.append({
            "title": c.get("title"),
            "year": c.get("year"),
            "type": _st(c),
            "snippet": (c.get("text") or "")[:420],
        })

    user = f"Question: {query}\n\nEvidence snippets:\n{json.dumps(evidence_rows, ensure_ascii=False)}"

    try:
        obj = llm_json_deep(system, user, temperature=0.1)
        llm_conflict = bool(obj.get("conflict_found"))
        # Use consistent interpretation
        found, interp = interpret_conflict_score(conflict_score, llm_conflict)
        return DisagreementResult(
            conflict_found=found,
            conflict_score=round(conflict_score, 2),
            interpretation=interp,
            topics=obj.get("topics") or [],
            conflicting_claims=obj.get("conflicting_claims") or [],
            notes=obj.get("notes") or ""
        )
    except Exception as e:
        logger.warning(f"Disagreement detector error: {e}")
        _, interp = interpret_conflict_score(conflict_score, False)
        return DisagreementResult(
            conflict_found=False,
            conflict_score=round(conflict_score, 2),
            interpretation=interp,
            topics=[],
            conflicting_claims=[],
            notes=f"Error during conflict analysis: {str(e)}"
        )


DEEPCONSULT_SYSTEM = """You are DeepConsult, a PhD-level biomedical research analyst specializing in evidence synthesis for aesthetic medicine.

Your task is to provide rigorous, academic-quality analysis of medical literature.

RULES:
- No guessing or extrapolation beyond the provided evidence
- Explicitly compare and contrast studies
- Discuss bias, heterogeneity, and methodological limitations
- If evidence conflicts, explain possible reasons why
- Maintain conservative, academic tone throughout
- Never provide specific dosing recommendations without PI/guideline support
- If evidence is insufficient, say so clearly

OUTPUT STRUCTURE (use these exact section headers):

## 1. Research Question
Restate the clinical/research question clearly.

## 2. Evidence Summary Table
| Study | Year | Type | N | Key Finding | Quality |
|-------|------|------|---|-------------|---------|

## 3. Study-by-Study Analysis
Detailed analysis of each key study, including methods, findings, and limitations.

## 4. Synthesis & Consensus
What do the studies agree on? Where is there disagreement? What is the overall direction of evidence?

## 5. Limitations & Bias
Publication bias, heterogeneity, methodological concerns, gaps in the literature.

## 6. Practical Implications
Conservative clinical takeaways supported by the evidence.

## 7. References
Numbered list of all cited sources.

Remember: This is academic-level analysis. Be thorough but honest about uncertainty."""


def run_deepconsult(
    question: str,
    retrieve_chunks: Callable[[str, Optional[dict], Optional[int]], List[dict]],
    filters: Optional[dict] = None,
    max_sources: int = 40,
    min_meta_analyses: int = 1,
    min_rcts: int = 3,
    include_disagreement: bool = True,
) -> Dict[str, Any]:
    """
    Run PhD-level deep analysis on a research question.
    """
    start = time.time()

    chunks = retrieve_chunks(question, filters, max_sources) or []
    u = _uniq_sources(chunks)

    if len(u) < 6:
        return {
            "refused": True,
            "reason": "Insufficient literature for multi-study synthesis (found fewer than 6 unique sources)",
            "citations": format_citations(u),
            "evidence_table": [],
            "analysis": None,
            "meta": {"sources_found": len(u)},
        }

    metas = [c for c in u if _st(c) in ("meta_analysis", "systematic_review")]
    rcts = [c for c in u if _st(c) == "rct"]
    guidelines = [c for c in u if _st(c) in ("guideline", "pi")]

    evidence_table = []
    for c in u[:max_sources]:
        evidence_table.append({
            "title": c.get("title"),
            "year": c.get("year"),
            "type": _st(c),
            "quality": quality_score(c),
            "doi": c.get("doi"),
            "url": c.get("url"),
            "snippet": (c.get("text") or "")[:520],
        })
    evidence_table.sort(key=lambda x: (-x["quality"], -(x.get("year") or 0)))

    user_prompt = (
        f"Research question:\n{question}\n\n"
        f"Evidence table ({len(evidence_table)} sources):\n"
        f"{json.dumps(evidence_table, indent=2, default=str)}"
    )

    analysis = llm_text_deep(DEEPCONSULT_SYSTEM, user_prompt, temperature=0.1)

    elapsed_ms = int((time.time() - start) * 1000)

    result = {
        "refused": False,
        "analysis": analysis,
        "evidence_table": evidence_table,
        "citations": format_citations(u, max_items=25),
        "meta": {
            "model": DEEP_MODEL,
            "sources_used": len(evidence_table),
            "meta_analyses": len(metas),
            "rcts": len(rcts),
            "guidelines": len(guidelines),
            "elapsed_ms": elapsed_ms,
        },
    }

    if include_disagreement:
        disagreement = disagreement_detector(question, chunks)
        result["disagreement"] = disagreement.model_dump()

    return result


def _escape_xml(s: str) -> str:
    """Escape XML special characters for ReportLab."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_sections_as_paragraphs(text: str, styles) -> List:
    """
    Converts numbered headings into PDF-friendly paragraphs:
      '## 1. Research Question' etc.
    """
    blocks = []
    lines = (text or "").splitlines()
    buf = []

    heading_re = re.compile(r"^\s*(?:##\s*)?(\d+)\.\s+(.+)\s*$")

    def flush():
        nonlocal buf
        if buf:
            content = _escape_xml("\n".join(buf)).replace("\n", "<br/>")
            blocks.append(Paragraph(content, styles["Body"]))
            blocks.append(Spacer(1, 10))
            buf = []

    for line in lines:
        m = heading_re.match(line.strip())
        if m:
            flush()
            heading = f"{m.group(1)}. {m.group(2)}"
            blocks.append(Paragraph(_escape_xml(heading), styles["H2"]))
        else:
            buf.append(line)
    flush()
    return blocks


def make_citation_pdf(
    *,
    title: str,
    subtitle: str,
    body_text: str,
    citations: List[dict],
    evidence_table: Optional[List[dict]] = None,
    conflict: Optional[DisagreementResult] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Creates a journal-style, citation-grade PDF with proper tables.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title=title,
        author="AesthetiCite"
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="H1",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=16,
        leading=20,
        spaceAfter=10
    ))
    styles.add(ParagraphStyle(
        name="H2",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name="Body",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=11,
        leading=14
    ))

    story = []

    # Title
    story.append(Paragraph(_escape_xml(title), styles["H1"]))
    story.append(Paragraph(f"<b>Research question:</b> {_escape_xml(subtitle)}", styles["Body"]))
    story.append(Spacer(1, 10))

    # Meta box (if provided)
    if meta:
        meta_table = [
            ["Model", str(meta.get("model", "")), "Sources Used", str(meta.get("sources_used", ""))],
            ["Guidelines/PI", str(meta.get("guidelines", "")), "Elapsed", f"{meta.get('elapsed_ms', 0)/1000:.1f}s"],
        ]
        t = Table(meta_table, colWidths=[1.3*inch, 2.7*inch, 1.3*inch, 2.0*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("BOX", (0,0), (-1,-1), 0.7, colors.black),
            ("INNERGRID", (0,0), (-1,-1), 0.3, colors.black),
            ("FONTNAME", (0,0), (-1,-1), "Times-Roman"),
            ("FONTSIZE", (0,0), (-1,-1), 10),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Disagreement box (if present)
    if conflict:
        interp = getattr(conflict, 'interpretation', 'Unknown')
        topics_str = ", ".join(conflict.topics[:5]) if conflict.topics else "N/A"
        dis_table = [
            ["Disagreement", interp, "Score", str(conflict.conflict_score)],
            ["Topics", topics_str[:100], "Status", "Conflicting" if conflict.conflict_found else "No Conflict"],
        ]
        dt = Table(dis_table, colWidths=[1.3*inch, 2.7*inch, 1.3*inch, 2.0*inch])
        dt.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F2F2F2")),
            ("BOX", (0,0), (-1,-1), 0.7, colors.black),
            ("INNERGRID", (0,0), (-1,-1), 0.3, colors.black),
            ("FONTNAME", (0,0), (-1,-1), "Times-Roman"),
            ("FONTSIZE", (0,0), (-1,-1), 10),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.append(dt)
        story.append(Spacer(1, 14))

    # Evidence Summary Table (proper table, not bullets)
    if evidence_table:
        story.append(Paragraph("Evidence Summary Table", styles["H2"]))
        header = ["Study", "Year", "Type", "Key Finding", "Quality"]
        rows = [header]

        for r in (evidence_table or [])[:12]:
            rows.append([
                _escape_xml((r.get("title") or "")[:50]),
                str(r.get("year") or ""),
                (r.get("type") or "").upper(),
                _escape_xml((r.get("snippet") or "")[:120]),
                str(r.get("quality") or "")
            ])

        et = Table(rows, colWidths=[1.8*inch, 0.5*inch, 0.8*inch, 3.0*inch, 0.5*inch])
        et.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EDEDED")),
            ("FONTNAME", (0,0), (-1,0), "Times-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 9),
            ("FONTNAME", (0,1), (-1,-1), "Times-Roman"),
            ("FONTSIZE", (0,1), (-1,-1), 8),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("GRID", (0,0), (-1,-1), 0.25, colors.black),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.whitesmoke]),
        ]))
        story.append(et)
        story.append(Spacer(1, 12))

    # Analysis (sections 1..7)
    story.append(Paragraph("DeepConsult Analysis", styles["H2"]))
    story.extend(_render_sections_as_paragraphs(body_text, styles))

    # References
    story.append(PageBreak())
    story.append(Paragraph("References", styles["H2"]))
    for i, ref in enumerate((citations or [])[:30], start=1):
        yr = ref.get("year") or ""
        st = ref.get("source_type") or ""
        doi = ref.get("doi") or ""
        url = ref.get("url") or ""
        ref_text = f"[{i}] {_escape_xml(ref.get('title') or 'Untitled')} ({yr}). {_escape_xml(st)}. {_escape_xml(doi)} {_escape_xml(url)}"
        story.append(Paragraph(ref_text, styles["Body"]))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()
