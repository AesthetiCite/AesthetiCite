"""
AesthetiCite Phase 2-5 API Routes
- Phase 2: Treatment Comparison, Protocols, Patient Handouts
- Phase 3: Citation Export (BibTeX/RIS)
- Phase 4: Personalized Alerts (email digests)
- Phase 5: Mobile/Tablet optimization
"""

from __future__ import annotations

import os
import re
import json
import time
import hashlib
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.rag.retriever import retrieve_db
from app.rag.llm_answer import synthesize_answer, _make_evidence_pack, _llm_openai
from app.rag.citations import to_citations
from app.rag.cache import cache_get, cache_set, make_cache_key
from app.core.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["phase2-5"])

DEFAULT_VIEW = "mobile"
MOBILE_MAX_CHARS = 1800
CACHE_TTL_SECONDS = 172800


class CompareRequest(BaseModel):
    treatments: List[str] = Field(..., min_length=2, max_length=4)
    context: Optional[str] = None
    view: Optional[str] = None


class ProtocolRequest(BaseModel):
    topic: str
    patient_profile: Optional[str] = None
    view: Optional[str] = None


class HandoutRequest(BaseModel):
    topic: str
    language: str = "en"
    reading_level: str = "middle_school"
    view: Optional[str] = None


class ExportCitationsRequest(BaseModel):
    citations: List[dict]
    format: str = "bibtex"


class InterestRequest(BaseModel):
    topics: List[str] = Field(default_factory=list)
    action: str = "add"


class AlertRequest(BaseModel):
    pass


def _view_mode(view: Optional[str]) -> str:
    v = (view or DEFAULT_VIEW).lower().strip()
    return "mobile" if v not in ("desktop", "mobile") else v


def _compact_answer(answer: str, max_chars: int = MOBILE_MAX_CHARS) -> str:
    ans = re.sub(r"\n{3,}", "\n\n", answer).strip()
    if len(ans) <= max_chars:
        return ans
    return ans[:max_chars].rsplit(" ", 1)[0] + "..."


def _extract_citations(chunks: List[dict], max_items: int = 8) -> List[dict]:
    seen = set()
    out = []
    for ch in chunks:
        key = ch.get("source_id") or ch.get("title") or str(ch.get("id"))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "title": ch.get("title"),
            "journal": ch.get("organization_or_journal"),
            "year": ch.get("year"),
            "doi": ch.get("doi"),
            "url": ch.get("url"),
            "authors": ch.get("authors", []),
            "first_author": ch.get("authors", [None])[0] if ch.get("authors") else None,
            "source_type": ch.get("document_type"),
            "evidence_level": ch.get("evidence_level"),
        })
        if len(out) >= max_items:
            break
    return out


def _safe(s: Optional[str]) -> str:
    return (s or "").strip()


def to_bibtex(items: List[dict]) -> str:
    out = []
    for i, c in enumerate(items, start=1):
        key = re.sub(r"[^a-zA-Z0-9]+", "", (_safe(str(c.get("first_author") or "")) + _safe(str(c.get("year") or "")))) or f"ref{i}"
        authors = " and ".join(c.get("authors") or ([c["first_author"]] if c.get("first_author") else []))
        title = _safe(c.get("title"))
        journal = _safe(c.get("journal"))
        year = _safe(str(c.get("year") or ""))
        doi = _safe(c.get("doi"))
        url = _safe(c.get("url"))
        fields = []
        if authors:
            fields.append(f"  author = {{{authors}}}")
        if title:
            fields.append(f"  title = {{{title}}}")
        if journal:
            fields.append(f"  journal = {{{journal}}}")
        if year:
            fields.append(f"  year = {{{year}}}")
        if doi:
            fields.append(f"  doi = {{{doi}}}")
        if url:
            fields.append(f"  url = {{{url}}}")
        out.append("@article{" + key + ",\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(out).strip()


def to_ris(items: List[dict]) -> str:
    lines = []
    for c in items:
        lines.append("TY  - JOUR")
        for a in (c.get("authors") or []):
            lines.append(f"AU  - {a}")
        if c.get("title"):
            lines.append(f"TI  - {c['title']}")
        if c.get("journal"):
            lines.append(f"JO  - {c['journal']}")
        if c.get("year"):
            lines.append(f"PY  - {c['year']}")
        if c.get("doi"):
            lines.append(f"DO  - {c['doi']}")
        if c.get("url"):
            lines.append(f"UR  - {c['url']}")
        lines.append("ER  - ")
        lines.append("")
    return "\n".join(lines).strip()


def _llm_json(system: str, user: str, temperature: float = 0.0) -> dict:
    messages = [
        {"role": "system", "content": system + "\n\nRespond ONLY with valid JSON."},
        {"role": "user", "content": user},
    ]
    try:
        response = _llm_openai(messages)
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        return {"raw_response": response}
    except Exception as e:
        logger.error(f"LLM JSON error: {e}")
        return {"error": str(e)}


def _llm_text(system: str, user: str, temperature: float = 0.2) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        return _llm_openai(messages)
    except Exception as e:
        logger.error(f"LLM text error: {e}")
        return f"Error generating response: {e}"


@router.post("/compare")
async def compare_treatments(req: CompareRequest, db: Session = Depends(get_db)):
    """Compare 2-4 treatments side by side with evidence."""
    view = _view_mode(req.view)
    cache_key = make_cache_key("compare", {"treatments": req.treatments, "context": req.context, "view": view})
    
    cached = cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return JSONResponse(cached)
    
    joined = ", ".join(req.treatments)
    query = f"Compare {joined} in aesthetic practice. Include dosing equivalence if applicable, onset, duration, diffusion/spread, contraindications, storage/handling, typical indications, adverse events."
    if req.context:
        query += f" Context: {req.context}"
    
    retrieved = retrieve_db(db=db, question=query, domain="aesthetic_medicine", k=12)
    citations = _extract_citations(retrieved)
    
    system = f"""You are {settings.APP_NAME}, a clinical decision support assistant for aesthetic medicine.
Output STRICT JSON only with this structure:
{{
  "comparison_table": [
    {{"attribute": "...", "values": {{"Treatment1": "...", "Treatment2": "..."}}}}
  ],
  "summary": "Brief practical summary",
  "key_differences": ["..."],
  "clinical_pearls": ["..."]
}}

Rules:
- Do not guess dosing equivalence; if uncertain, state 'insufficient evidence'
- Prefer prescribing information and guidelines over reviews
- Include inline citations like [1], [2] referring to the sources list"""
    
    sources_text = "\n".join([
        f"[{i+1}] {c.get('title')} ({c.get('year')}) - {c.get('journal') or ''}"
        for i, c in enumerate(citations)
    ])
    user = f"Treatments: {req.treatments}\nContext: {req.context or 'general aesthetic practice'}\n\nSources:\n{sources_text}"
    
    data = _llm_json(system, user, temperature=0.0)
    
    payload = {
        "comparison": data,
        "citations": citations,
        "view": view,
        "cached": False
    }
    cache_set(cache_key, payload)
    return JSONResponse(payload)


@router.post("/protocol")
async def get_protocol(req: ProtocolRequest, db: Session = Depends(get_db)):
    """Generate evidence-based treatment protocol."""
    view = _view_mode(req.view)
    cache_key = make_cache_key("protocol", {"topic": req.topic, "patient_profile": req.patient_profile, "view": view})
    
    cached = cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return JSONResponse(cached)
    
    query = f"Clinical protocol for: {req.topic}. Include dosing ranges, technique steps, follow-up schedule, contraindications, complications and management."
    if req.patient_profile:
        query += f" Patient profile: {req.patient_profile}"
    
    retrieved = retrieve_db(db=db, question=query, domain="aesthetic_medicine", k=12)
    citations = _extract_citations(retrieved)
    
    system = f"""You are {settings.APP_NAME}. Write a practical step-by-step treatment protocol.

Rules:
- Prefer PI/guidelines as primary sources
- If details are not supported by sources, label clearly as 'expert consensus' and keep conservative
- Include a 'complications & rescue' section
- Include inline citations [1], [2] referring to the sources
- Structure with clear sections: Indications, Contraindications, Preparation, Technique, Post-procedure, Follow-up, Complications & Management"""
    
    sources_text = "\n".join([
        f"[{i+1}] {c.get('title')} ({c.get('year')}) - {c.get('journal') or ''}"
        for i, c in enumerate(citations)
    ])
    user = f"Topic: {req.topic}\nPatient profile: {req.patient_profile or 'typical adult patient'}\n\nSources:\n{sources_text}"
    
    text = _llm_text(system, user, temperature=0.2)
    
    payload = {
        "protocol": _compact_answer(text) if view == "mobile" else text,
        "citations": citations,
        "view": view,
        "cached": False
    }
    cache_set(cache_key, payload)
    return JSONResponse(payload)


@router.post("/handout")
async def generate_handout(req: HandoutRequest, db: Session = Depends(get_db)):
    """Generate patient education handout."""
    view = _view_mode(req.view)
    cache_key = make_cache_key("handout", {"topic": req.topic, "language": req.language, "reading_level": req.reading_level, "view": view})
    
    cached = cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return JSONResponse(cached)
    
    query = f"Patient education handout: {req.topic}."
    retrieved = retrieve_db(db=db, question=query, domain="aesthetic_medicine", k=8)
    citations = _extract_citations(retrieved)
    
    reading_level_map = {
        "simple": "5th grade reading level, very simple words",
        "middle_school": "8th grade reading level, clear and accessible",
        "high_school": "12th grade reading level, more detailed"
    }
    level_desc = reading_level_map.get(req.reading_level, reading_level_map["middle_school"])
    
    system = f"""You are {settings.APP_NAME}. Create a patient education handout.
Language: {req.language}
Reading level: {level_desc}

Constraints:
- No fear-mongering or alarming language
- Include: what it is, benefits, common side effects, rare serious risks, aftercare instructions, when to call the clinic
- Avoid clinical jargon - use everyday language
- Be reassuring but honest
- Format with clear headings and bullet points for easy reading"""
    
    sources_text = "\n".join([
        f"- {c.get('title')} ({c.get('year')})"
        for c in citations
    ])
    user = f"Handout topic: {req.topic}\n\nBased on these sources:\n{sources_text}"
    
    text = _llm_text(system, user, temperature=0.2)
    
    payload = {
        "handout": _compact_answer(text, 2200) if view == "mobile" else text,
        "topic": req.topic,
        "language": req.language,
        "reading_level": req.reading_level,
        "citations": citations,
        "view": view,
        "cached": False
    }
    cache_set(cache_key, payload)
    return JSONResponse(payload)


@router.post("/export-citations")
async def export_citations(req: ExportCitationsRequest):
    """Export citations in BibTeX or RIS format."""
    fmt = req.format.lower().strip()
    if fmt not in ("bibtex", "ris"):
        raise HTTPException(status_code=400, detail="format must be 'bibtex' or 'ris'")
    
    if fmt == "bibtex":
        content = to_bibtex(req.citations)
        return PlainTextResponse(
            content,
            media_type="application/x-bibtex",
            headers={"Content-Disposition": "attachment; filename=citations.bib"}
        )
    else:
        content = to_ris(req.citations)
        return PlainTextResponse(
            content,
            media_type="application/x-research-info-systems",
            headers={"Content-Disposition": "attachment; filename=citations.ris"}
        )


@router.post("/interests")
async def manage_interests(
    req: InterestRequest, 
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Add or remove research interests for personalized alerts. Requires authentication."""
    from sqlalchemy import text
    
    user_id = user["id"]
    user_email = user.get("email", "")
    
    if req.action == "add":
        for topic in req.topics:
            db.execute(text("""
                INSERT INTO user_interests (user_id, topic, email, created_at)
                VALUES (:user_id, :topic, :email, :ts)
                ON CONFLICT (user_id, topic) DO UPDATE SET email = :email
            """), {"user_id": user_id, "topic": topic.strip().lower(), "email": user_email, "ts": int(time.time())})
        db.commit()
        return {"ok": True, "action": "added", "topics": req.topics}
    
    elif req.action == "remove":
        for topic in req.topics:
            db.execute(text("""
                DELETE FROM user_interests WHERE user_id = :user_id AND topic = :topic
            """), {"user_id": user_id, "topic": topic.strip().lower()})
        db.commit()
        return {"ok": True, "action": "removed", "topics": req.topics}
    
    elif req.action == "list":
        rows = db.execute(text("""
            SELECT topic, email, created_at FROM user_interests WHERE user_id = :user_id ORDER BY topic
        """), {"user_id": user_id}).fetchall()
        return {"ok": True, "interests": [{"topic": r[0], "email": r[1], "created_at": r[2]} for r in rows]}
    
    raise HTTPException(status_code=400, detail="action must be 'add', 'remove', or 'list'")


@router.post("/send-alert")
async def send_research_alert(
    req: AlertRequest, 
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Send personalized research alert email based on saved interests. Requires authentication."""
    from sqlalchemy import text
    
    user_id = user["id"]
    user_email = user.get("email", "")
    
    if not user_email:
        return {"ok": False, "error": "No email associated with account"}
    
    rows = db.execute(text("""
        SELECT topic FROM user_interests WHERE user_id = :user_id ORDER BY topic
    """), {"user_id": user_id}).fetchall()
    
    topics = [r[0] for r in rows]
    if not topics:
        return {"ok": True, "sent": False, "reason": "no topics saved"}
    
    alert_lines = [f"{settings.APP_NAME} - Research Alert\n", f"Topics: {', '.join(topics)}\n"]
    any_hits = False
    
    for topic in topics:
        query = f"Recent papers about: {topic}"
        retrieved = retrieve_db(db=db, question=query, domain="aesthetic_medicine", k=5)
        citations = _extract_citations(retrieved, max_items=5)
        
        if citations:
            any_hits = True
            alert_lines.append(f"\n== {topic.upper()} ==\n")
            for c in citations:
                title = c.get("title") or "Untitled"
                year = c.get("year") or ""
                journal = c.get("journal") or ""
                alert_lines.append(f"- {title} ({year}) {journal}")
    
    if not any_hits:
        alert_lines.append("\nNo new items found this week.\n")
    
    sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")
    if not sendgrid_api_key:
        return {"ok": False, "error": "Email not configured", "preview": "\n".join(alert_lines)}
    
    try:
        import httpx
        response = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {sendgrid_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "personalizations": [{"to": [{"email": user_email}]}],
                "from": {"email": "noreply@aestheticite.com", "name": settings.APP_NAME},
                "subject": f"{settings.APP_NAME} - Your Weekly Research Alert",
                "content": [{"type": "text/plain", "value": "\n".join(alert_lines)}]
            }
        )
        response.raise_for_status()
        return {"ok": True, "sent": True, "topics": topics}
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        return {"ok": False, "error": str(e), "preview": "\n".join(alert_lines)}


@router.get("/view-mode")
async def get_view_mode(view: Optional[str] = None):
    """Get optimized view settings for mobile or desktop."""
    mode = _view_mode(view)
    return {
        "view": mode,
        "settings": {
            "max_answer_chars": MOBILE_MAX_CHARS if mode == "mobile" else 4000,
            "compact_citations": mode == "mobile",
            "show_full_abstracts": mode == "desktop",
            "pagination_size": 5 if mode == "mobile" else 10
        }
    }
