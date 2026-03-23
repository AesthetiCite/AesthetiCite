# ---------- OpenAI wiring for AesthetiCite ----------
# Uses Replit AI Integrations or standard OpenAI API

import os
from typing import List
from openai import OpenAI

OPENAI_API_KEY = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL") or None

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_EMBED_DIM = int(os.getenv("OPENAI_EMBED_DIM", os.getenv("EMBED_DIM", "1536")))

_client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
)

def llm_text(system: str, user: str, temperature: float = 0.2, model: str = None) -> str:
    """
    Uses OpenAI Responses API.
    Returns plain text.
    Optionally specify a different model (e.g., 'gpt-4.1' for DeepConsult).
    """
    use_model = model or OPENAI_MODEL
    resp = _client.responses.create(
        model=use_model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )

    if hasattr(resp, "output_text") and resp.output_text:
        return resp.output_text

    try:
        parts = []
        for item in (resp.output or []):
            for c in (getattr(item, "content", None) or []):
                t = getattr(c, "text", None)
                if t:
                    parts.append(t)
        return "\n".join(parts).strip()
    except Exception:
        return str(resp)

def embed(text: str) -> List[float]:
    """
    Uses OpenAI Embeddings API.
    IMPORTANT: Your main patch must set EMBED_DIM to match the embedding model output:
      - text-embedding-3-small -> 1536 dims
      - text-embedding-3-large -> 3072 dims
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * OPENAI_EMBED_DIM

    emb = _client.embeddings.create(
        model=OPENAI_EMBED_MODEL,
        input=text,
    )

    vec = emb.data[0].embedding
    if len(vec) != OPENAI_EMBED_DIM:
        raise RuntimeError(
            f"Embedding dim mismatch: got {len(vec)} but OPENAI_EMBED_DIM={OPENAI_EMBED_DIM}. "
            f"Fix EMBED_DIM/OPENAI_EMBED_DIM or switch embedding model."
        )
    return vec
