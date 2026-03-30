"""
Fix 2 — Disk persistence for visual store
==========================================
Replaces the in-memory _VISUAL_STORE dict in visual_differential.py
and vision_analysis.py with disk-backed storage.

Images are written to uploads/{visual_id}.{ext} on upload.
Reads fall through: memory → disk → 404.
Ephemeral delete removes both memory and disk.

INTEGRATION:
1. Drop this file into app/api/visual_store.py
2. In visual_differential.py and vision_analysis.py, replace:
       from app.api.visual_differential import _VISUAL_STORE, _load_image_bytes
   with:
       from app.api.visual_store import register_visual, load_image, delete_visual

3. In visual_counseling.py (upload endpoint), replace the in-memory store call:
       _VISUAL_STORE[visual_id] = image_bytes
   with:
       register_visual(visual_id, image_bytes, content_type)

No other changes needed — the API surface is identical.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.environ.get("AESTHETICITE_UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# In-memory cache — avoids re-reading disk for images used within the same
# request cycle. Not relied on for persistence.
_MEM_CACHE: dict[str, bytes] = {}
_MAX_MEM_CACHE = 50  # max images kept in memory simultaneously


# ─────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────

def _ext_from_content_type(content_type: str) -> str:
    ext = mimetypes.guess_extension(content_type, strict=False)
    if ext in (".jpe", ".jpeg"):
        ext = ".jpg"
    return ext or ".jpg"


def _find_disk_path(visual_id: str) -> Optional[str]:
    """Find the first matching file on disk for this visual_id."""
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        path = os.path.join(UPLOAD_DIR, f"{visual_id}{ext}")
        if os.path.exists(path):
            return path
    return None


def _evict_mem_cache() -> None:
    """Keep memory cache bounded."""
    if len(_MEM_CACHE) >= _MAX_MEM_CACHE:
        oldest_key = next(iter(_MEM_CACHE))
        del _MEM_CACHE[oldest_key]


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def register_visual(
    visual_id: str,
    image_bytes: bytes,
    content_type: str = "image/jpeg",
) -> str:
    """
    Persist image bytes to disk and cache in memory.
    Returns the disk path.

    Call this from the upload endpoint instead of:
        _VISUAL_STORE[visual_id] = image_bytes
    """
    ext = _ext_from_content_type(content_type)
    path = os.path.join(UPLOAD_DIR, f"{visual_id}{ext}")
    try:
        with open(path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"[VisualStore] Saved {visual_id} → {path} ({len(image_bytes):,} bytes)")
    except Exception as e:
        logger.error(f"[VisualStore] Failed to write {visual_id}: {e}")

    # Also keep in memory for immediate use in same request cycle
    _evict_mem_cache()
    _MEM_CACHE[visual_id] = image_bytes
    return path


def load_image(visual_id: str) -> Optional[bytes]:
    """
    Load image bytes for a visual_id.
    Checks memory first, then disk. Returns None if not found.

    Drop-in replacement for _load_image_bytes() and _load_image().
    """
    # 1. Memory cache
    if visual_id in _MEM_CACHE:
        return _MEM_CACHE[visual_id]

    # 2. Disk
    path = _find_disk_path(visual_id)
    if path:
        try:
            with open(path, "rb") as f:
                data = f.read()
            # Re-cache for subsequent access
            _evict_mem_cache()
            _MEM_CACHE[visual_id] = data
            return data
        except Exception as e:
            logger.error(f"[VisualStore] Failed to read {visual_id} from {path}: {e}")

    return None


def delete_visual(visual_id: str) -> bool:
    """
    Delete image from memory and disk.
    Called by the ephemeral delete endpoint and /api/visual/delete/{visual_id}.
    Returns True if anything was deleted.
    """
    deleted = False

    # Memory
    if visual_id in _MEM_CACHE:
        del _MEM_CACHE[visual_id]
        deleted = True

    # Disk
    path = _find_disk_path(visual_id)
    if path:
        try:
            os.remove(path)
            logger.info(f"[VisualStore] Deleted {visual_id} from disk: {path}")
            deleted = True
        except Exception as e:
            logger.warning(f"[VisualStore] Could not delete {path}: {e}")

    return deleted


def visual_exists(visual_id: str) -> bool:
    """Check if a visual is available without loading it."""
    return visual_id in _MEM_CACHE or _find_disk_path(visual_id) is not None


def list_visuals() -> list[dict]:
    """List all persisted visuals on disk (for admin/debug use)."""
    results = []
    try:
        for fname in os.listdir(UPLOAD_DIR):
            fpath = os.path.join(UPLOAD_DIR, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                stem, ext = os.path.splitext(fname)
                results.append({
                    "visual_id": stem,
                    "filename": fname,
                    "size_bytes": stat.st_size,
                    "in_memory": stem in _MEM_CACHE,
                })
    except Exception as e:
        logger.error(f"[VisualStore] list_visuals error: {e}")
    return results


# ─────────────────────────────────────────────────────────────────
# Updated upload endpoint helper
# Replace the upload logic in visual_counseling.py with this.
# ─────────────────────────────────────────────────────────────────

def process_upload(
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    conversation_id: str = "",
    kind: str = "photo",
) -> dict:
    """
    Process an uploaded image file.
    Returns the response dict for the upload endpoint.

    In visual_counseling.py, replace the upload handler body with:
        from app.api.visual_store import process_upload
        result = process_upload(
            file_bytes=file.read(),
            original_filename=file.filename,
            content_type=file.content_type,
            conversation_id=form_data.get("conversation_id", ""),
            kind=form_data.get("kind", "photo"),
        )
        return result
    """
    visual_id = str(uuid.uuid4())
    path = register_visual(visual_id, file_bytes, content_type)
    return {
        "ok": True,
        "visual_id": visual_id,
        "kind": kind,
        "size_bytes": len(file_bytes),
        "filename": original_filename,
        "persisted_path": path,
        "conversation_id": conversation_id,
    }
