"""
Pilot Dependencies
==================
FastAPI dependencies for extracting case context from requests.
"""

from typing import Optional
from fastapi import Request

CASE_ID_HEADER = "x-case-id"


def get_case_id(request: Request) -> Optional[str]:
    """
    Extract case_id from request headers.
    
    Frontend should send: X-Case-Id: case_abc123...
    when clinician is working on an active case.
    """
    case_id = request.headers.get(CASE_ID_HEADER)
    return case_id.strip() if case_id else None


def get_case_id_from_body(body: dict) -> Optional[str]:
    """
    Extract case_id from request body as fallback.
    """
    case_id = body.get("case_id") or body.get("caseId")
    return case_id.strip() if case_id else None
