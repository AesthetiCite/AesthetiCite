"""
AesthetiCite Multilingual Support Module

Supports 25 languages covering ~90% of world population:
English, Chinese, Hindi, Spanish, French, Arabic, Bengali, Portuguese, Russian,
Urdu, Indonesian, German, Japanese, Swahili, Turkish, Vietnamese, Italian,
Korean, Thai, Persian, Hausa, Punjabi, Telugu, Marathi, Tamil

- Detects requested language from explicit `lang`, Accept-Language header, or text detection
- Translates query -> retrieval language and answer -> user language
- Never translates citations/snippets for defensibility
"""

from __future__ import annotations

import os
import re
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Literal

from fastapi import Request
from pydantic import BaseModel, Field

from app.core.glossaries import expand_query_with_glossary
from app.core.refusals_i18n import render_refusal, REFUSAL_TEMPLATES


# -------------------------
# Global language coverage (~90% world population)
# -------------------------

Lang = Literal[
    "en",  # English
    "zh",  # Chinese (Simplified)
    "hi",  # Hindi
    "es",  # Spanish
    "fr",  # French
    "ar",  # Arabic
    "bn",  # Bengali
    "pt",  # Portuguese
    "ru",  # Russian
    "ur",  # Urdu
    "id",  # Indonesian
    "de",  # German
    "ja",  # Japanese
    "sw",  # Swahili
    "tr",  # Turkish
    "vi",  # Vietnamese
    "it",  # Italian
    "ko",  # Korean
    "th",  # Thai
    "fa",  # Persian (Farsi)
    "ha",  # Hausa
    "pa",  # Punjabi
    "te",  # Telugu
    "mr",  # Marathi
    "ta",  # Tamil
]

SUPPORTED_LANGS: List[str] = [
    "en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ur",
    "id", "de", "ja", "sw", "tr", "vi", "it", "ko", "th", "fa",
    "ha", "pa", "te", "mr", "ta"
]

DEFAULT_LANG: Lang = "en"

# Languages prioritized for retrieval
# (because most high-quality medical evidence exists here)
RETRIEVAL_LANGS_PRIORITY: List[Lang] = [
    "en",
    "fr",
    "de",
    "es",
    "pt",
    "it"
]

LANGUAGE_NAMES = {
    "en": "English",
    "zh": "Chinese",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "ar": "Arabic",
    "bn": "Bengali",
    "pt": "Portuguese",
    "ru": "Russian",
    "ur": "Urdu",
    "id": "Indonesian",
    "de": "German",
    "ja": "Japanese",
    "sw": "Swahili",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "it": "Italian",
    "ko": "Korean",
    "th": "Thai",
    "fa": "Persian",
    "ha": "Hausa",
    "pa": "Punjabi",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
}


# -------------------------
# Request/Response contracts
# -------------------------

class AesthetiCiteQuery(BaseModel):
    query: str
    lang: Optional[str] = Field(None, description="Optional explicit language override (e.g., 'fr').")
    context: Optional[Dict[str, Any]] = None


class Citation(BaseModel):
    source_id: str
    title: Optional[str] = None
    url: Optional[str] = None
    snippet: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    source_language: Optional[str] = None


class AesthetiCiteAnswer(BaseModel):
    status: Literal["ok", "refuse", "error"]
    answer: Optional[str] = None
    refusal_reason: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    answer_language: Optional[str] = None
    retrieval_language: Optional[str] = None
    debug: Optional[Dict[str, Any]] = None


# -------------------------
# Language detection
# -------------------------

_ACCEPT_LANG_RE = re.compile(r"([a-zA-Z-]{2,8})(?:;q=([0-9.]+))?")


def parse_accept_language(header_val: str) -> List[Tuple[str, float]]:
    if not header_val:
        return []
    out = []
    for part in header_val.split(","):
        part = part.strip()
        m = _ACCEPT_LANG_RE.match(part)
        if not m:
            continue
        tag = m.group(1).lower()
        q = float(m.group(2) or 1.0)
        base = tag.split("-")[0]
        out.append((base, q))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def normalize_lang(lang: Optional[str]) -> Lang:
    if not lang:
        return DEFAULT_LANG
    base = lang.lower().strip().split("-")[0]
    if base in SUPPORTED_LANGS:
        return base  # type: ignore
    return DEFAULT_LANG


def naive_detect_lang(text: str) -> Lang:
    """Lightweight heuristic detection using script ranges and word markers."""
    t = text.strip()
    if not t:
        return DEFAULT_LANG

    # Script-based detection (most reliable for non-Latin scripts)
    
    # Chinese (CJK Unified Ideographs)
    if re.search(r"[\u4e00-\u9fff]", t):
        # Could be Chinese or Japanese - check for hiragana/katakana
        if re.search(r"[\u3040-\u30ff]", t):
            return "ja"
        return "zh"
    
    # Japanese (hiragana/katakana)
    if re.search(r"[\u3040-\u30ff]", t):
        return "ja"
    
    # Korean (Hangul)
    if re.search(r"[\uac00-\ud7af\u1100-\u11ff]", t):
        return "ko"
    
    # Arabic script (Arabic, Urdu, Persian, Hausa variants)
    if re.search(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]", t):
        # Distinguish between Arabic, Urdu, Persian
        if re.search(r"[پچژگ]", t):  # Persian/Urdu specific chars
            if re.search(r"[ٹڈڑں]", t):  # Urdu-specific
                return "ur"
            return "fa"
        return "ar"
    
    # Devanagari (Hindi, Marathi)
    if re.search(r"[\u0900-\u097F]", t):
        # Marathi-specific markers
        mr_markers = ["आहे", "असे", "होते", "आणि", "किंवा"]
        if any(m in t for m in mr_markers):
            return "mr"
        return "hi"
    
    # Bengali script
    if re.search(r"[\u0980-\u09FF]", t):
        return "bn"
    
    # Tamil script
    if re.search(r"[\u0B80-\u0BFF]", t):
        return "ta"
    
    # Telugu script
    if re.search(r"[\u0C00-\u0C7F]", t):
        return "te"
    
    # Gurmukhi (Punjabi)
    if re.search(r"[\u0A00-\u0A7F]", t):
        return "pa"
    
    # Thai script
    if re.search(r"[\u0E00-\u0E7F]", t):
        return "th"
    
    # Cyrillic (Russian)
    if re.search(r"[\u0400-\u04FF]", t):
        return "ru"
    
    # Vietnamese (Latin with diacritics)
    vi_markers = ["ơ", "ư", "ă", "đ", "ạ", "ả", "ấ", "ầ", "ẩ", "ẫ", "ậ", "ắ", "ằ", "ẳ", "ẵ", "ặ"]
    if any(m in t.lower() for m in vi_markers):
        return "vi"
    
    # Latin-script language detection by word markers
    t_lower = " " + t.lower() + " "
    
    # French
    fr_markers = [" le ", " la ", " les ", " des ", " est ", " avec ", " pour ", " quels ", " quel ", " quelle ", " quoi ", " comment ", " dans ", " cette ", " sont "]
    if sum(1 for m in fr_markers if m in t_lower) >= 2:
        return "fr"

    # Spanish
    es_markers = [" el ", " los ", " las ", " es ", " con ", " para ", " cual ", " cuales ", " como ", " esta ", " este ", " esos ", " pero ", " porque "]
    if sum(1 for m in es_markers if m in t_lower) >= 2:
        return "es"

    # German
    de_markers = [" der ", " die ", " das ", " und ", " ist ", " mit ", " von ", " bei ", " für ", " auf ", " nicht ", " werden "]
    if sum(1 for m in de_markers if m in t_lower) >= 2:
        return "de"

    # Italian
    it_markers = [" il ", " lo ", " gli ", " sono ", " con ", " per ", " che ", " della ", " degli ", " nelle ", " questo "]
    if sum(1 for m in it_markers if m in t_lower) >= 2:
        return "it"

    # Portuguese
    pt_markers = [" os ", " as ", " com ", " para ", " como ", " quando ", " está ", " não ", " mais ", " isso ", " dessa ", " pelo "]
    if sum(1 for m in pt_markers if m in t_lower) >= 2:
        return "pt"
    
    # Turkish
    tr_markers = [" bir ", " ve ", " için ", " ile ", " bu ", " olan ", " olan ", " değil ", " gibi ", " ancak "]
    if sum(1 for m in tr_markers if m in t_lower) >= 2:
        return "tr"
    
    # Indonesian
    id_markers = [" yang ", " dan ", " untuk ", " dengan ", " ini ", " itu ", " adalah ", " dalam ", " dari ", " tidak "]
    if sum(1 for m in id_markers if m in t_lower) >= 2:
        return "id"
    
    # Swahili
    sw_markers = [" na ", " ya ", " wa ", " kwa ", " ni ", " katika ", " hiyo ", " hii ", " yake ", " wao "]
    if sum(1 for m in sw_markers if m in t_lower) >= 2:
        return "sw"
    
    # Hausa (Latin script variant)
    ha_markers = [" da ", " shi ", " ya ", " ta ", " ba ", " don ", " su ", " ko ", " wanda ", " amma "]
    if sum(1 for m in ha_markers if m in t_lower) >= 2:
        return "ha"

    return DEFAULT_LANG


# -------------------------
# Translation provider interface + caching
# -------------------------

class TranslationProvider:
    def translate(self, *, text: str, source_lang: Lang, target_lang: Lang, purpose: str) -> str:
        raise NotImplementedError


class InMemoryTTLCache:
    def __init__(self, ttl_s: int = 3600, max_items: int = 10_000):
        self.ttl_s = ttl_s
        self.max_items = max_items
        self._store: Dict[str, Tuple[float, str]] = {}

    def get(self, key: str) -> Optional[str]:
        v = self._store.get(key)
        if not v:
            return None
        ts, val = v
        if time.time() - ts > self.ttl_s:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, val: str) -> None:
        if len(self._store) >= self.max_items:
            for k in list(self._store.keys())[: max(1, self.max_items // 10)]:
                self._store.pop(k, None)
        self._store[key] = (time.time(), val)


def _cache_key(text: str, source: str, target: str, purpose: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(source.encode("utf-8"))
    h.update(target.encode("utf-8"))
    h.update(purpose.encode("utf-8"))
    return h.hexdigest()


class SafeTranslator:
    """Wraps a TranslationProvider with caching and safety guardrails."""
    def __init__(self, provider: TranslationProvider):
        self.provider = provider
        self.cache = InMemoryTTLCache(ttl_s=24 * 3600)

    def translate(self, *, text: str, source_lang: Lang, target_lang: Lang, purpose: str) -> str:
        if source_lang == target_lang:
            return text
        if not text.strip():
            return text

        key = _cache_key(text, source_lang, target_lang, purpose)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        out = self.provider.translate(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            purpose=purpose,
        )

        if not out or not out.strip():
            out = text

        self.cache.set(key, out)
        return out


class OpenAICompatibleTranslator(TranslationProvider):
    """Uses an OpenAI-compatible chat completions endpoint for translation."""
    def __init__(self):
        self.base_url = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL", os.getenv("VERIDOC_TRANSLATE_BASE_URL", "")).rstrip("/")
        self.api_key = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", os.getenv("VERIDOC_TRANSLATE_API_KEY", ""))
        self.model = os.getenv("VERIDOC_TRANSLATE_MODEL", "gpt-4o-mini")
        
    def translate(self, *, text: str, source_lang: Lang, target_lang: Lang, purpose: str) -> str:
        if not self.base_url or not self.api_key:
            return text
            
        import httpx

        system = (
            "You are a translation engine for clinical decision support UI.\n"
            "Rules:\n"
            "- Translate faithfully.\n"
            "- Do NOT add, remove, or infer clinical facts.\n"
            "- Preserve numbers, units, and drug names.\n"
            "- Preserve formatting, bulleting, and section headers.\n"
            "- Preserve inline citation markers like [S1], [S2], etc.\n"
            "- If text is already in the target language, return it unchanged.\n"
        )

        user = (
            f"Translate from {LANGUAGE_NAMES.get(source_lang, source_lang)} to {LANGUAGE_NAMES.get(target_lang, target_lang)}.\n"
            f"Purpose: {purpose}\n\n"
            f"TEXT:\n{text}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/chat/completions"

        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except Exception:
            return text


class PassthroughTranslator(TranslationProvider):
    """No-op translator that returns text unchanged."""
    def translate(self, *, text: str, source_lang: Lang, target_lang: Lang, purpose: str) -> str:
        return text


# -------------------------
# Multilang orchestration helpers
# -------------------------

@dataclass
class MultiLangPlan:
    user_lang: Lang
    detected_lang: Lang
    retrieval_lang: Lang
    query_for_retrieval: str


def choose_retrieval_lang(user_lang: Lang) -> Lang:
    """Prefer same-language retrieval if your corpus supports it."""
    if user_lang in RETRIEVAL_LANGS_PRIORITY:
        return user_lang
    return RETRIEVAL_LANGS_PRIORITY[0]


def infer_user_language(request: Optional[Request], body_lang: Optional[str], query_text: str) -> Lang:
    if body_lang:
        return normalize_lang(body_lang)

    if request:
        al = parse_accept_language(request.headers.get("accept-language", ""))
        for lang, _q in al:
            nl = normalize_lang(lang)
            if nl in SUPPORTED_LANGS:
                return nl

    return normalize_lang(naive_detect_lang(query_text))


def prepare_multilang_query(
    *,
    request: Optional[Request],
    query_text: str,
    explicit_lang: Optional[str],
    translator: Optional[SafeTranslator],
) -> MultiLangPlan:
    user_lang = infer_user_language(request, explicit_lang, query_text)
    detected_lang = normalize_lang(naive_detect_lang(query_text))
    retrieval_lang = choose_retrieval_lang(user_lang)

    query_for_retrieval = query_text
    if translator is not None and detected_lang != retrieval_lang:
        query_for_retrieval = translator.translate(
            text=query_text,
            source_lang=detected_lang,
            target_lang=retrieval_lang,
            purpose="retrieval_query",
        )
    
    # Expand query with glossary terms for better retrieval
    query_for_retrieval = expand_query_with_glossary(query_for_retrieval, user_lang)

    return MultiLangPlan(
        user_lang=user_lang,
        detected_lang=detected_lang,
        retrieval_lang=retrieval_lang,
        query_for_retrieval=query_for_retrieval,
    )


def finalize_multilang_answer(
    *,
    plan: MultiLangPlan,
    answer_text: str,
    translator: Optional[SafeTranslator],
) -> Tuple[str, str, str]:
    """
    Translates only the final answer text, not citations/snippets.
    Returns (translated_answer, answer_language, retrieval_language)
    """
    if not answer_text:
        return answer_text, plan.user_lang, plan.retrieval_lang

    if translator is None:
        return answer_text, plan.user_lang, plan.retrieval_lang

    if plan.user_lang != plan.retrieval_lang:
        translated = translator.translate(
            text=answer_text,
            source_lang=plan.retrieval_lang,
            target_lang=plan.user_lang,
            purpose="final_answer",
        )
        return translated, plan.user_lang, plan.retrieval_lang
    
    return answer_text, plan.user_lang, plan.retrieval_lang


def get_translator() -> Optional[SafeTranslator]:
    """Get a configured translator if credentials are available."""
    base_url = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL", os.getenv("VERIDOC_TRANSLATE_BASE_URL", ""))
    api_key = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", os.getenv("VERIDOC_TRANSLATE_API_KEY", ""))
    
    if base_url and api_key:
        return SafeTranslator(OpenAICompatibleTranslator())
    return None


__all__ = [
    "SUPPORTED_LANGS",
    "DEFAULT_LANG",
    "LANGUAGE_NAMES",
    "Lang",
    "AesthetiCiteQuery",
    "AesthetiCiteAnswer",
    "Citation",
    "TranslationProvider",
    "SafeTranslator",
    "OpenAICompatibleTranslator",
    "PassthroughTranslator",
    "prepare_multilang_query",
    "finalize_multilang_answer",
    "get_translator",
    "naive_detect_lang",
    "normalize_lang",
    "MultiLangPlan",
    "expand_query_with_glossary",
    "render_refusal",
    "REFUSAL_TEMPLATES",
]
