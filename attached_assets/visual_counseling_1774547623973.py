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
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


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

    # Validate it's actually an image
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


VISUAL_SYSTEM = """You are AesthetiCite, a clinical safety AI for aesthetic injectable medicine.

A clinician has uploaded a clinical photo and is asking a question about it.

RULES:
1. Describe only what is visually visible.
2. Focus on post-procedure complications: vascular compromise, infection, swelling, asymmetry, Tyndall effect, ptosis.
3. If you see signs of vascular occlusion (blanching, livedo, mottling) — state this prominently and urgently.
4. Every clinical statement must be followed by a citation marker [S1], [S2] etc.
5. Do NOT diagnose. Use language like "pattern consistent with" or "features suggesting".
6. If image quality is poor, say so.
7. End with: Suggested follow-up questions (3 questions relevant to this presentation).
"""


async def _stream_visual_answer(
    question: str,
    visual_id: str,
    lang: str = "en",
):
    image_bytes = load_image(visual_id)
    if not image_bytes:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Visual ID {visual_id!r} not found.'})}\n\n"
        return

    b64 = base64.b64encode(image_bytes).decode("utf-8")

    client = _get_client()
    try:
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": VISUAL_SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    }},
                    {"type": "text", "text": question or "Describe what you see in this clinical photo."},
                ]},
            ],
            max_tokens=1500,
            temperature=0.15,
            stream=True,
        )
        for chunk in stream:
            token = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if token:
                yield f"data: {json.dumps({'type': 'content', 'data': token})}\n\n"
    except Exception as e:
        logger.error(f"[VisualStream] Error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:120]})}\n\n"

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
