from pydantic import BaseModel, Field
from typing import Literal, Optional, List


Mode = Literal["clinic", "deep_dive"]
Domain = Literal["aesthetic_medicine", "dental_medicine", "general_medicine"]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=2000)
    mode: Mode = "clinic"
    domain: Domain = "aesthetic_medicine"
    language: Optional[Literal["auto", "en", "fr"]] = "auto"


class Citation(BaseModel):
    source_id: str
    title: str
    year: Optional[int] = None
    organization_or_journal: Optional[str] = None
    page_or_section: Optional[str] = None
    evidence_level: Optional[str] = None
    snippet: Optional[str] = None  # short supporting excerpt (QA)


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    related_questions: List[str] = []
    refusal: bool = False
    refusal_reason: Optional[str] = None
    request_id: Optional[str] = None
    latency_ms: Optional[int] = None
