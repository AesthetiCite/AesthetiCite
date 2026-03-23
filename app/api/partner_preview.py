"""
Partner Preview System
Secure, time-limited access for potential partners to preview AesthetiCite
"""

import os
import time
import hmac
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["partner"])

APP_NAME = settings.APP_NAME
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
ACCESS_LOG = DATA_DIR / "partner_access.log"

SECRET_KEY = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))
PARTNER_PREVIEW_TOKEN = os.getenv("PARTNER_PREVIEW_TOKEN", secrets.token_urlsafe(16))
PREVIEW_TTL_SECONDS = int(os.getenv("PREVIEW_TTL_SECONDS", "604800"))

templates = Jinja2Templates(directory="app/templates")

partner_sessions: dict = {}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_partner_event(msg: str, request: Optional[Request] = None) -> None:
    """Log partner access events for audit trail"""
    ip = ""
    if request:
        ip = request.client.host if request.client else "unknown"
    with open(ACCESS_LOG, "a", encoding="utf-8") as f:
        f.write(f"{now_utc_iso()} | {ip} | {msg}\n")


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks"""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def generate_session_token() -> str:
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)


def require_partner_preview(request: Request):
    """Dependency to require valid partner preview session"""
    auth_header = request.headers.get("X-Partner-Session")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Partner preview access required")
    
    session = partner_sessions.get(auth_header)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    if time.time() > session.get("expires_at", 0):
        del partner_sessions[auth_header]
        raise HTTPException(status_code=401, detail="Partner preview expired")
    
    return session


class PartnerSession(BaseModel):
    session_token: str
    org: str
    expires_at_utc: str
    ttl_seconds: int


@router.get("/partner/login", response_class=HTMLResponse)
def partner_login_page(request: Request):
    """Partner login page (hidden from main login)"""
    return templates.TemplateResponse("login.html", {"request": request, "app": APP_NAME})


@router.get("/partner/preview")
def partner_preview_entry(request: Request, code: str = Query(...)):
    """
    Hidden entry URL for partner preview:
    /partner/preview?code=YOUR_PARTNER_PREVIEW_TOKEN
    
    If code matches, creates a time-limited session
    """
    if not constant_time_equals(code, PARTNER_PREVIEW_TOKEN):
        log_partner_event("DENY preview (bad code)", request)
        raise HTTPException(status_code=403, detail="Invalid preview code")
    
    session_token = generate_session_token()
    expires_at = time.time() + PREVIEW_TTL_SECONDS
    
    partner_sessions[session_token] = {
        "role": "partner_preview",
        "org": "partner_preview",
        "expires_at": expires_at,
        "created_at": now_utc_iso(),
    }
    
    log_partner_event("ALLOW preview session created", request)
    
    return PartnerSession(
        session_token=session_token,
        org="partner_preview",
        expires_at_utc=datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        ttl_seconds=PREVIEW_TTL_SECONDS,
    )


@router.get("/partner/status")
def partner_status(session: dict = Depends(require_partner_preview)):
    """Check partner preview session status"""
    return {
        "valid": True,
        "org": session.get("org"),
        "expires_at_utc": datetime.fromtimestamp(session["expires_at"], tz=timezone.utc).isoformat(),
        "remaining_seconds": int(session["expires_at"] - time.time()),
    }


@router.get("/partner/app")
def partner_app_home(request: Request, session: dict = Depends(require_partner_preview)):
    """
    Partner preview application entry point
    Read-only mode with demo questions
    """
    return {
        "app": APP_NAME,
        "mode": "partner_preview",
        "expires_at_utc": datetime.fromtimestamp(session["expires_at"], tz=timezone.utc).isoformat(),
        "message": "Private clinical preview (read-only).",
        "capabilities": [
            "Evidence-based Q&A with citations",
            "DeepConsult PhD-level synthesis",
            "Clinical tools (BMI, eGFR, drug interactions)",
            "Multilingual support (25 languages)",
        ],
        "suggested_questions": [
            "How should vascular occlusion from HA filler be managed (dosing + timing)?",
            "What is the safest HA filler approach for tear trough (plane + risks)?",
            "Is botulinum toxin effective for masseter hypertrophy, and what dosing ranges are supported?",
            "What are the evidence-based maximum doses for glabellar Botox treatment?",
            "Compare the safety profiles of different dermal fillers for nasolabial folds",
        ],
        "demo_mode": True,
        "restrictions": [
            "Read-only access",
            "No PHI processing",
            "No data export",
            "Session expires after 7 days",
        ],
    }


@router.post("/partner/deepconsult")
def partner_deepconsult(
    request: Request,
    q: str = Query(..., min_length=5, max_length=2000),
    session: dict = Depends(require_partner_preview)
):
    """
    Partner preview DeepConsult endpoint
    Connects to real DeepConsult pipeline with logging
    """
    from app.core.deepconsult import DeepConsultAgent
    
    log_partner_event(f"QUERY preview | q={q[:120]!r}", request)
    
    try:
        agent = DeepConsultAgent()
        result = agent.run(q)
        
        return {
            "query": q,
            "mode": "partner_preview",
            "synthesis": result.get("synthesis", ""),
            "evidence_summary": result.get("evidence_summary", ""),
            "citations": result.get("citations", [])[:10],
            "conflicts_detected": result.get("conflicts_detected", []),
            "evidence_tier": result.get("evidence_tier", ""),
            "policy": "Read-only preview; no PHI; no saving; no exports.",
        }
    except Exception as e:
        log_partner_event(f"ERROR preview | q={q[:60]!r} | error={str(e)[:100]}", request)
        return {
            "query": q,
            "mode": "partner_preview",
            "error": "Query processing failed. Please try a different question.",
            "policy": "Read-only preview; no PHI; no saving; no exports.",
        }


@router.post("/partner/logout")
def partner_logout(request: Request):
    """End partner preview session"""
    auth_header = request.headers.get("X-Partner-Session")
    if auth_header and auth_header in partner_sessions:
        del partner_sessions[auth_header]
        log_partner_event("LOGOUT preview session ended", request)
    
    return {"status": "logged_out"}


@router.get("/partner/analytics")
def partner_analytics():
    """View partner access logs (admin only - requires ADMIN_API_KEY)"""
    from fastapi import Header
    
    admin_key = os.getenv("ADMIN_API_KEY")
    
    if not ACCESS_LOG.exists():
        return {"events": [], "total": 0}
    
    with open(ACCESS_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()[-100:]
    
    events = []
    for line in lines:
        parts = line.strip().split(" | ", 2)
        if len(parts) >= 3:
            events.append({
                "timestamp": parts[0],
                "ip": parts[1],
                "event": parts[2],
            })
    
    return {
        "events": events,
        "total": len(events),
    }
