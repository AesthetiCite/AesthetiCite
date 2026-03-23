from pydantic import BaseModel, Field
from typing import Optional, Literal

DocType = Literal["guideline", "review", "rct", "consensus", "ifu", "textbook", "other"]
Domain = Literal["medicine", "dermatology", "aesthetic_medicine"]

class IngestMetadata(BaseModel):
    source_id: str = Field(..., min_length=3, max_length=200)
    title: str = Field(..., min_length=5, max_length=400)
    authors: Optional[str] = None
    organization_or_journal: Optional[str] = None
    year: Optional[int] = None
    document_type: DocType = "other"
    domain: Domain = "medicine"
    version: Optional[str] = None
    url: Optional[str] = None
