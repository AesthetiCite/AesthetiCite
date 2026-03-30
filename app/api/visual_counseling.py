"""
app/api/visual_counseling.py
============================
Visual counseling FastAPI router.
Upload endpoint now writes images to disk — survives server restarts.
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image

from app.api.visual_store import register_visual, load_image, delete_visual

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visual", tags=["Visual Counseling"])

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
ALLOWED_MIME  = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _detect_mime_fallback(data: bytes) -> str:
    """Magic byte check — server-side MIME detection without libmagic dependency."""
    if data[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    return "application/octet-stream"


# ─────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_visual(
    file: UploadFile = File(...),
    conversation_id: str = Form(default=""),
    kind: str = Form(default="photo"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Upload a clinical photo.
    Image is written to disk immediately — persists across server restarts.
    Returns a visual_id to reference in subsequent analysis calls.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Accepted: jpeg, png, webp, gif.",
        )

    image_bytes = await file.read()

    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(image_bytes):,} bytes). Maximum: 20 MB.",
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    # Server-side magic bytes validation (independent of client-sent Content-Type)
    detected_mime = _detect_mime_fallback(image_bytes)
    if detected_mime not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match an allowed image type (detected: {detected_mime}).",
        )

    # Validate it's actually a decodable image using PIL
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid image.")

    visual_id = str(uuid.uuid4())
    content_type = file.content_type or "image/jpeg"

    # Write to disk — persists across restarts
    disk_path = register_visual(visual_id, image_bytes, content_type)
    logger.info(
        f"[VisualUpload] visual_id={visual_id} "
        f"size={len(image_bytes):,}b kind={kind} path={disk_path}"
    )

    return {
        "ok": True,
        "visual_id": visual_id,
        "kind": kind,
        "conversation_id": conversation_id,
        "size_bytes": len(image_bytes),
        "content_type": content_type,
    }


# ─────────────────────────────────────────────────────────────────
# Preview (thumbnail with optional annotation overlay)
# ─────────────────────────────────────────────────────────────────

@router.post("/preview")
async def visual_preview(payload: dict):
    """
    Return a PNG thumbnail of the uploaded image.
    Optionally overlays a brightness/contrast adjustment via intensity_0_1.
    """
    visual_id = payload.get("visual_id", "")
    intensity = float(payload.get("intensity_0_1", 0.5))

    image_bytes = load_image(visual_id)
    if not image_bytes:
        raise HTTPException(
            status_code=404,
            detail=f"Visual ID '{visual_id}' not found.",
        )

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Resize to thumbnail
        img.thumbnail((800, 800), Image.LANCZOS)

        # Apply intensity as brightness enhancement
        from PIL import ImageEnhance
        factor = 0.6 + (intensity * 0.8)  # range: 0.6 – 1.4
        img = ImageEnhance.Brightness(img).enhance(factor)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/png")

    except Exception as e:
        logger.error(f"[VisualPreview] Failed for {visual_id}: {e}")
        raise HTTPException(status_code=500, detail="Preview generation failed.")


# ─────────────────────────────────────────────────────────────────
# Delete (ephemeral mode)
# ─────────────────────────────────────────────────────────────────

@router.delete("/delete/{visual_id}")
async def delete_visual_endpoint(visual_id: str):
    """
    Delete image from disk and memory.
    Called when ephemeral mode is enabled or when the clinician
    explicitly removes the image after analysis.
    """
    deleted = delete_visual(visual_id)
    return {
        "visual_id": visual_id,
        "deleted": deleted,
        "message": (
            "Image deleted from server. No image data is retained."
            if deleted else
            "Visual ID not found — may have already been deleted."
        ),
    }


# ─────────────────────────────────────────────────────────────────
# Streaming visual Q&A
# Proxies to the VeriDoc engine with image context attached.
# ─────────────────────────────────────────────────────────────────

import base64
import json
import os
from fastapi.responses import StreamingResponse
from openai import OpenAI


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )


from app.engine.vision_quality import (
    INJECTABLE_SAFETY_SYSTEM,
    build_injectable_safety_prompt,
    extract_visual_scores,
)


async def _stream_visual_answer(
    question: str,
    visual_id: str,
    lang: str = "en",
):
    from app.engine.vision_protocol_bridge import detect_protocols_from_vision_text, build_protocol_alert_sse

    image_bytes = load_image(visual_id)
    if not image_bytes:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Visual ID {visual_id!r} not found.'})}\n\n"
        return

    b64 = base64.b64encode(image_bytes).decode("utf-8")

    client = _get_client()
    full_analysis = ""
    user_prompt = build_injectable_safety_prompt(
        question or "Describe what you see in this clinical photo.",
    )
    try:
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": INJECTABLE_SAFETY_SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    }},
                    {"type": "text", "text": user_prompt},
                ]},
            ],
            max_tokens=1500,
            temperature=0.15,
            stream=True,
        )
        for chunk in stream:
            token = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if token:
                full_analysis += token
                yield f"data: {json.dumps({'type': 'content', 'data': token})}\n\n"
    except Exception as e:
        logger.error(f"[VisualStream] Error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:120]})}\n\n"
        return

    # ── Structured scores (Improvement 2) ──────────────────────────────────
    try:
        scores = extract_visual_scores(full_analysis)
        yield f"data: {json.dumps({'type': 'visual_scores', 'data': scores.dict()})}\n\n"
    except Exception as _se:
        logger.warning(f"[VisualStream] Score extraction error (non-fatal): {_se}")

    # ── Vision Protocol Bridge ──────────────────────────────────────────────
    try:
        triggered = detect_protocols_from_vision_text(full_analysis, query=question)
        if triggered:
            alert = build_protocol_alert_sse(triggered)
            yield f"data: {json.dumps(alert)}\n\n"
    except Exception as _pe:
        logger.warning(f"[VisualStream] Protocol bridge error (non-fatal): {_pe}")

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/stream")
async def visual_stream(payload: dict):
    """
    Streaming visual Q&A endpoint.
    Loads image from disk (persistent) and streams a clinical answer.
    """
    question   = payload.get("q", "")
    visual_id  = payload.get("visual_id", "")
    lang       = payload.get("lang", "en")

    if not visual_id:
        raise HTTPException(status_code=400, detail="visual_id is required.")

    return StreamingResponse(
        _stream_visual_answer(question, visual_id, lang),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection":    "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
