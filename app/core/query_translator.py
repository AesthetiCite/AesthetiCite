from __future__ import annotations

import os
import time
import logging
from typing import Optional, Dict, Tuple
from cachetools import TTLCache
import threading

logger = logging.getLogger(__name__)

WEAK_RETRIEVAL_LANGS = {"ja", "zh", "ru", "tr", "bn", "ta", "gu"}

MIXED_RETRIEVAL_LANGS = {
    "hi", "it", "id", "ur", "mr", "pl", "ro", "sv", "da", "nl",
    "fr", "es", "de", "pt", "ar", "ko", "th",
    "te", "pa", "sw", "ha", "fa", "vi",
}

STRONG_RETRIEVAL_LANGS = {"en"}

_translation_cache: TTLCache = TTLCache(maxsize=500, ttl=600)
_cache_lock = threading.Lock()
_cache_stats = {"hits": 0, "misses": 0}


def needs_translation(lang: str) -> str:
    lang = (lang or "en").lower().strip()
    if lang == "en":
        return "native"
    if lang in WEAK_RETRIEVAL_LANGS:
        return "translate"
    return "dual"


def translate_to_english(text: str, source_lang: str = "auto") -> str:
    if not text or not text.strip():
        return text

    cache_key = f"{source_lang}:{text.strip()[:200]}"
    with _cache_lock:
        cached = _translation_cache.get(cache_key)
        if cached is not None:
            _cache_stats["hits"] += 1
            logger.info(f"Translation cache HIT (lang={source_lang}, hits={_cache_stats['hits']})")
            return cached

    _cache_stats["misses"] += 1

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
        )

        from app.core.lang import LANGUAGE_LABELS
        lang_name = LANGUAGE_LABELS.get(source_lang, source_lang)

        t0 = time.perf_counter()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a medical query translator. Translate the following medical/clinical query "
                    f"from {lang_name} to English. Preserve all medical terminology, drug names, "
                    "anatomical terms, and dosing information exactly. Output ONLY the English translation, "
                    "nothing else."
                )},
                {"role": "user", "content": text.strip()},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        translated = (resp.choices[0].message.content or "").strip()
        elapsed = (time.perf_counter() - t0) * 1000

        if translated and len(translated) > 5:
            logger.info(
                f"Translated query ({source_lang}→en, {elapsed:.0f}ms): "
                f"'{text.strip()[:60]}' → '{translated[:60]}'"
            )
            with _cache_lock:
                _translation_cache[cache_key] = translated
            return translated
        else:
            logger.warning(f"Translation returned empty/short result, using original")
            return text.strip()

    except Exception as e:
        logger.warning(f"Translation failed ({source_lang}→en): {e}")
        return text.strip()


def get_retrieval_query(original_query: str, detected_lang: str) -> Tuple[str, Optional[str]]:
    strategy = needs_translation(detected_lang)

    if strategy == "native":
        return original_query, None

    translated = translate_to_english(original_query, source_lang=detected_lang)

    if translated == original_query.strip():
        return original_query, None

    if strategy == "translate":
        return translated, None

    return translated, original_query


def get_translation_cache_stats() -> Dict:
    with _cache_lock:
        total = _cache_stats["hits"] + _cache_stats["misses"]
        hit_rate = (_cache_stats["hits"] / total * 100) if total > 0 else 0.0
        return {
            "hits": _cache_stats["hits"],
            "misses": _cache_stats["misses"],
            "hit_rate_pct": round(hit_rate, 1),
            "cache_size": len(_translation_cache),
        }
