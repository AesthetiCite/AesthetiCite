from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


# -----------------------------
# 1) Input schema matches your JSON 1:1
# -----------------------------
class DeepConsultPayload(BaseModel):
    refused: bool
    analysis: Optional[str] = None

    evidence_table: List[dict] = []
    citations: List[dict] = []
    meta: dict = {}
    disagreement: Optional[dict] = None


router = APIRouter()


# -----------------------------
# 2) PDF Builder (citation-grade)
# -----------------------------
def build_pdf_bytes_from_deepconsult(payload: Dict[str, Any]) -> bytes:
    """
    Expects payload EXACTLY like you posted.
    """
    if payload.get("refused"):
        raise ValueError("DeepConsult refused — cannot export PDF")

    title = "AesthetiCite DeepConsult Report"
    question = extract_question_from_analysis(payload.get("analysis") or "") or "DeepConsult Analysis"
    meta = payload.get("meta") or {}
    disagreement = payload.get("disagreement") or {}
    evidence_rows = payload.get("evidence_table") or []
    citations = payload.get("citations") or []
    analysis_md = payload.get("analysis") or ""

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
    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=10,
        leading=13
    ))

    story: List[Any] = []

    # Title
    story.append(Paragraph(title, styles["H1"]))
    story.append(Paragraph(f"<b>Research question:</b> {escape_xml(question)}", styles["Body"]))
    story.append(Spacer(1, 10))

    # Meta table (your keys)
    meta_table = [
        ["Model", str(meta.get("model", "")), "Sources used", str(meta.get("sources_used", ""))],
        ["Guidelines", str(meta.get("guidelines", "")), "Elapsed", f"{int(meta.get('elapsed_ms', 0))/1000:.1f}s" if meta.get("elapsed_ms") else ""],
        ["Meta-analyses", str(meta.get("meta_analyses", "")), "RCTs", str(meta.get("rcts", ""))],
    ]
    story.append(make_box_table(meta_table))
    story.append(Spacer(1, 10))

    # Disagreement box
    if disagreement:
        dis_table = [
            ["Disagreement", "Found" if disagreement.get("conflict_found") else "Not found",
             "Score", str(disagreement.get("conflict_score", ""))],
            ["Topics", ", ".join(disagreement.get("topics") or [])[:1200],
             "Interpretation", (disagreement.get("interpretation") or "")[:400]],
            ["Notes", (disagreement.get("notes") or "")[:1200], "", ""],
        ]
        story.append(make_box_table(dis_table, header_bg="#F2F2F2"))
        story.append(Spacer(1, 14))

    # Evidence Summary Table
    story.append(Paragraph("Evidence Summary Table", styles["H2"]))
    story.append(make_evidence_table(evidence_rows))
    story.append(Spacer(1, 12))

    # Analysis sections (Markdown "## 1. ..." headings)
    story.append(Paragraph("DeepConsult Analysis", styles["H2"]))
    story.extend(render_markdown_sections(analysis_md, styles))

    # References (from citations)
    story.append(PageBreak())
    story.append(Paragraph("References", styles["H2"]))
    for i, c in enumerate(citations[:40], start=1):
        yr = c.get("year") or ""
        st = c.get("source_type") or ""
        doi = c.get("doi") or ""
        url = c.get("url") or ""
        ref = f"[{i}] {c.get('title') or 'Untitled'} ({yr}). {st}. {doi} {url}".strip()
        story.append(Paragraph(escape_xml(ref), styles["Small"]))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()


def make_box_table(rows: List[List[str]], header_bg: str = "#FAFAFA") -> Table:
    t = Table(rows, colWidths=[1.2*inch, 2.8*inch, 1.2*inch, 2.0*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(header_bg)),
        ("BOX", (0,0), (-1,-1), 0.7, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.black),
        ("FONTNAME", (0,0), (-1,-1), "Times-Roman"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    return t


def make_evidence_table(evidence_rows: List[dict]) -> Table:
    header = ["Study", "Year", "Type", "Key Finding / Snippet", "Quality"]
    rows = [header]

    for r in (evidence_rows or [])[:14]:
        rows.append([
            escape_xml((r.get("title") or "")[:70]),
            str(r.get("year") or ""),
            (r.get("type") or "").upper(),
            escape_xml((r.get("snippet") or "")[:220]),
            str(r.get("quality") or ""),
        ])

    t = Table(rows, colWidths=[2.2*inch, 0.6*inch, 0.9*inch, 2.7*inch, 0.6*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EDEDED")),
        ("FONTNAME", (0,0), (-1,0), "Times-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("FONTNAME", (0,1), (-1,-1), "Times-Roman"),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.black),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.whitesmoke]),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    return t


def render_markdown_sections(md: str, styles) -> List[Any]:
    """
    Parses:
      ## 1. Research Question
      text...
      ## 2. Evidence Summary Table
      ...

    Produces H2 headings + body paragraphs.
    """
    blocks: List[Any] = []

    # Split by '## ' headings
    parts = re.split(r"\n(?=##\s+)", (md or "").strip())
    if not parts or len(parts) == 1:
        # fallback: render as one block
        blocks.append(Paragraph(escape_xml(md).replace("\n", "<br/>"), styles["Body"]))
        return blocks

    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p.startswith("##"):
            lines = p.splitlines()
            heading = lines[0].lstrip("#").strip()
            body = "\n".join(lines[1:]).strip()

            blocks.append(Paragraph(escape_xml(heading), styles["H2"]))
            if body:
                blocks.append(Paragraph(escape_xml(body).replace("\n", "<br/>"), styles["Body"]))
                blocks.append(Spacer(1, 10))
        else:
            blocks.append(Paragraph(escape_xml(p).replace("\n", "<br/>"), styles["Body"]))
            blocks.append(Spacer(1, 10))

    return blocks


def extract_question_from_analysis(analysis_md: str) -> Optional[str]:
    """
    Attempts to extract the research question line(s) under '## 1. Research Question'.
    If not found, returns None.
    """
    m = re.search(r"##\s*1\.\s*Research Question\s*(.+?)(\n##\s*2\.|\Z)", analysis_md, re.S | re.I)
    if not m:
        return None
    text = m.group(1).strip()
    # take first non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def escape_xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# -----------------------------
# 3) FastAPI endpoints
# -----------------------------

# Request model for from-query endpoint
class DeepConsultPDFQueryRequest(BaseModel):
    question: str
    filters: Optional[dict] = None
    max_sources: int = 40
    include_disagreement: bool = True


@router.post("/deepconsult/pdf/from-query")
async def deepconsult_pdf_from_query(req: DeepConsultPDFQueryRequest):
    """
    One-step endpoint: question → DeepConsult → PDF
    """
    from app.core.deepconsult import run_deepconsult
    from app.core.retrieve_wrapper import make_retrieve_fn
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            retrieve_fn = make_retrieve_fn(db)
            result = run_deepconsult(
                question=req.question,
                retrieve_chunks=retrieve_fn,
                filters=req.filters or {"domain": "aesthetic_medicine"},
                max_sources=req.max_sources,
                include_disagreement=req.include_disagreement,
            )

        if result.get("refused"):
            raise HTTPException(
                status_code=400,
                detail=f"DeepConsult refused: {result.get('reason', 'insufficient evidence')}"
            )

        pdf_bytes = build_pdf_bytes_from_deepconsult(result)

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=deepconsult_report.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {e}")


@router.post("/deepconsult/pdf")
async def deepconsult_pdf_endpoint(payload: DeepConsultPayload):
    if payload.refused:
        raise HTTPException(status_code=400, detail="DeepConsult refused; cannot export PDF.")
    try:
        pdf_bytes = build_pdf_bytes_from_deepconsult(payload.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {e}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=deepconsult_report.pdf"}
    )


class ChatExportPayload(BaseModel):
    question: str
    answer: str
    citations: List[dict] = []
    clinicalSummary: Optional[str] = None
    aciScore: Optional[float] = None
    evidenceBadge: Optional[str] = None


def build_chat_pdf(payload: Dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=6,
                                  textColor=colors.HexColor("#0d9488"))
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=9,
                                     textColor=colors.HexColor("#6b7280"), spaceAfter=14)
    heading_style = ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13, spaceAfter=6,
                                    textColor=colors.HexColor("#111827"))
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14,
                                 spaceAfter=8, textColor=colors.HexColor("#374151"))
    citation_style = ParagraphStyle("Citation", parent=styles["Normal"], fontSize=9, leading=12,
                                     textColor=colors.HexColor("#4b5563"), leftIndent=12)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9,
                                 textColor=colors.HexColor("#6b7280"))

    elements = []

    elements.append(Paragraph("AesthetiCite Clinical Report", title_style))
    import datetime
    elements.append(Paragraph(f"Generated {datetime.datetime.now().strftime('%B %d, %Y at %H:%M')}", subtitle_style))

    aci = payload.get("aciScore")
    badge = payload.get("evidenceBadge")
    if aci is not None or badge:
        meta_parts = []
        if aci is not None:
            meta_parts.append(f"ACI Score: {aci}/10")
        if badge:
            meta_parts.append(f"Evidence: {badge}")
        elements.append(Paragraph(" | ".join(meta_parts), meta_style))
        elements.append(Spacer(1, 8))

    elements.append(Paragraph("Clinical Question", heading_style))
    q = payload.get("question", "")
    elements.append(Paragraph(_safe(q), body_style))
    elements.append(Spacer(1, 6))

    summary = payload.get("clinicalSummary")
    if summary:
        elements.append(Paragraph("Clinical Summary", heading_style))
        elements.append(Paragraph(_safe(summary), body_style))
        elements.append(Spacer(1, 6))

    elements.append(Paragraph("Evidence-Based Answer", heading_style))
    answer = payload.get("answer", "")
    for para in answer.split("\n"):
        para = para.strip()
        if not para:
            continue
        if para.startswith("# "):
            elements.append(Paragraph(_safe(para[2:]), heading_style))
        elif para.startswith("## "):
            elements.append(Paragraph(_safe(para[3:]), heading_style))
        elif para.startswith("**") and para.endswith("**"):
            elements.append(Paragraph(f"<b>{_safe(para[2:-2])}</b>", body_style))
        elif para.startswith("- ") or para.startswith("* "):
            elements.append(Paragraph(f"\u2022 {_safe(para[2:])}", body_style))
        else:
            elements.append(Paragraph(_safe(para), body_style))

    citations = payload.get("citations") or []
    if citations:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("References", heading_style))
        for i, c in enumerate(citations):
            title = c.get("title", "Unknown")
            year = c.get("year", "")
            journal = c.get("organization_or_journal", "")
            tier = c.get("tier") or c.get("evidence_level") or ""
            line = f"[{i + 1}] {_safe(title)}"
            if journal:
                line += f" \u2014 {_safe(journal)}"
            if year:
                line += f" ({year})"
            if tier:
                line += f" [{_safe(tier)}]"
            elements.append(Paragraph(line, citation_style))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        "This report was generated by AesthetiCite for research and educational purposes. "
        "It is not a substitute for professional medical judgment.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8,
                       textColor=colors.HexColor("#9ca3af"), alignment=1)
    ))

    doc.build(elements)
    return buf.getvalue()


def _safe(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@router.post("/export/pdf")
async def chat_export_pdf(payload: ChatExportPayload):
    try:
        pdf_bytes = build_chat_pdf(payload.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {e}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=aestheticite_report.pdf"}
    )
