"""
Embedding cache for sub-3s latency.
Caches embeddings to avoid repeated embedding calls.
"""
from __future__ import annotations
import os
import hashlib
import json
import logging
from typing import List, Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = int(os.getenv("EMBED_CACHE_TTL", "172800"))
CACHE_MAX_SIZE = int(os.getenv("EMBED_CACHE_MAX_SIZE", "50000"))

embed_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cached_embedding(text: str) -> Optional[List[float]]:
    """Get embedding from cache if available."""
    key = _hash_text(text)
    return embed_cache.get(key)


def set_cached_embedding(text: str, embedding: List[float]) -> None:
    """Store embedding in cache."""
    key = _hash_text(text)
    embed_cache[key] = embedding


def get_embedding_with_cache(text: str, embed_fn) -> List[float]:
    """
    Get embedding, using cache if available.
    
    Args:
        text: Text to embed
        embed_fn: Function that takes text and returns embedding vector
    
    Returns:
        Embedding vector
    """
    cached = get_cached_embedding(text)
    if cached is not None:
        return cached
    
    embedding = embed_fn(text)
    set_cached_embedding(text, embedding)
    return embedding


def cache_stats() -> dict:
    """Return cache statistics."""
    return {
        "size": len(embed_cache),
        "max_size": CACHE_MAX_SIZE,
        "ttl_seconds": CACHE_TTL_SECONDS
    }
