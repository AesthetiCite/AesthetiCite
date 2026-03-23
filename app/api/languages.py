"""
AesthetiCite Languages API

Provides endpoints for language detection and supported languages.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, List

from app.core.multilang import (
    SUPPORTED_LANGS, 
    LANGUAGE_NAMES, 
    DEFAULT_LANG,
    naive_detect_lang,
    normalize_lang,
)


router = APIRouter(prefix="/languages", tags=["languages"])


class LanguageInfo(BaseModel):
    code: str
    name: str
    is_default: bool


class DetectRequest(BaseModel):
    text: str


class DetectResponse(BaseModel):
    detected_language: str
    language_name: str
    confidence: str


@router.get("")
def list_supported_languages() -> Dict[str, List[LanguageInfo]]:
    """List all supported languages for AesthetiCite."""
    languages = []
    for code in SUPPORTED_LANGS:
        languages.append(LanguageInfo(
            code=code,
            name=LANGUAGE_NAMES.get(code, code),
            is_default=(code == DEFAULT_LANG)
        ))
    return {"languages": languages}


@router.post("/detect")
def detect_language(req: DetectRequest) -> DetectResponse:
    """Detect language of input text."""
    detected = naive_detect_lang(req.text)
    return DetectResponse(
        detected_language=detected,
        language_name=LANGUAGE_NAMES.get(detected, detected),
        confidence="heuristic"
    )
