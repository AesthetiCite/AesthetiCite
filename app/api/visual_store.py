"""
app/api/visual_store.py
=======================
Persistent visual storage — replaces the in-memory _VISUAL_STORE dict
that existed across visual_differential.py, vision_analysis.py,
and visual_counseling.py.

Images are written to disk on upload and survive server restarts.
Memory cache is kept for same-session performance only.

Import this everywhere instead of the local _VISUAL_STORE dict:

    from app.api.visual_store import register_visual, load_image, delete_visual
"""

from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.environ.get("AESTHETICITE_UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_MEM_CACHE: dict[str, bytes] = {}
_MAX_MEM  = 50


def _ext(content_type: str) -> str:
    e = mimetypes.guess_extension(content_type, strict=False)
    if e in (".jpe", ".jpeg"):
        return ".jpg"
    return e or ".jpg"


def _disk_path(visual_id: str) -> Optional[str]:
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = os.path.join(UPLOAD_DIR, f"{visual_id}{ext}")
        if os.path.exists(p):
            return p
    return None


def _evict() -> None:
    if len(_MEM_CACHE) >= _MAX_MEM:
        del _MEM_CACHE[next(iter(_MEM_CACHE))]


def register_visual(visual_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Write image to disk and warm the memory cache. Returns disk path."""
    path = os.path.join(UPLOAD_DIR, f"{visual_id}{_ext(content_type)}")
    try:
        with open(path, "wb") as f:
            f.write(image_bytes)
    except Exception as e:
        logger.error(f"[VisualStore] write failed for {visual_id}: {e}")
    _evict()
    _MEM_CACHE[visual_id] = image_bytes
    return path


def load_image(visual_id: str) -> Optional[bytes]:
    """Load image bytes — memory first, disk fallback."""
    if visual_id in _MEM_CACHE:
        return _MEM_CACHE[visual_id]
    path = _disk_path(visual_id)
    if path:
        try:
            with open(path, "rb") as f:
                data = f.read()
            _evict()
            _MEM_CACHE[visual_id] = data
            return data
        except Exception as e:
            logger.error(f"[VisualStore] read failed for {visual_id}: {e}")
    return None


def delete_visual(visual_id: str) -> bool:
    """Remove from memory and disk. Returns True if anything was deleted."""
    deleted = bool(_MEM_CACHE.pop(visual_id, None))
    path = _disk_path(visual_id)
    if path:
        try:
            os.remove(path)
            deleted = True
        except Exception as e:
            logger.warning(f"[VisualStore] delete failed {path}: {e}")
    return deleted


def visual_exists(visual_id: str) -> bool:
    return visual_id in _MEM_CACHE or _disk_path(visual_id) is not None
