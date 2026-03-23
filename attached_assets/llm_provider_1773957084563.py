"""
AesthetiCite — LLM Provider Abstraction  (Mistral AI-inspired)
==============================================================
Allows each org to use OpenAI, Mistral AI, Azure OpenAI, or a local model.
The rest of the app calls get_llm_client(org_id) and gets back a
unified async client regardless of provider.

Endpoints:
  GET  /api/llm/config/{org_id}         — get current provider config
  POST /api/llm/config/{org_id}         — set/update provider config
  POST /api/llm/test                    — test current config with a sample prompt
  GET  /api/llm/providers               — list supported providers + models
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/api/llm", tags=["LLM Provider"])

# ---------------------------------------------------------------------------
# Supported providers
# ---------------------------------------------------------------------------

PROVIDERS: Dict[str, Any] = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "base_url": None,
        "on_premise": False,
        "notes": "Default. Uses OPENAI_API_KEY from environment if no key provided.",
    },
    "mistral": {
        "name": "Mistral AI",
        "models": [
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
            "open-mistral-nemo",
        ],
        "base_url": "https://api.mistral.ai/v1",
        "on_premise": False,
        "notes": "GDPR-friendly. French infrastructure. Requires Mistral API key.",
    },
    "azure_openai": {
        "name": "Azure OpenAI",
        "models": ["gpt-4o", "gpt-4-turbo"],
        "base_url": None,
        "on_premise": False,
        "notes": "Enterprise Azure deployment. Base URL is your Azure endpoint.",
    },
    "local": {
        "name": "Local / On-Premise",
        "models": ["mistral-7b-instruct", "llama-3-8b", "custom"],
        "base_url": "http://localhost:11434/v1",
        "on_premise": True,
        "notes": "Fully air-gapped. No data leaves the clinic network. Use Ollama or vLLM.",
    },
}

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o"


# ---------------------------------------------------------------------------
# Unified async client builder
# ---------------------------------------------------------------------------


async def get_llm_client(org_id: Optional[str], db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Returns a dict with {client, model, provider} for the given org.
    Falls back to system default if no org config found.

    Usage:
        cfg = await get_llm_client(org_id, db)
        response = await cfg["client"].chat.completions.create(
            model=cfg["model"],
            messages=[...]
        )
    """
    import openai as _openai  # openai SDK works for both OpenAI and Mistral (OpenAI-compatible)

    config = None
    if org_id and db:
        row = db.execute(
            text("SELECT * FROM llm_provider_configs WHERE org_id = :oid"),
            {"oid": org_id},
        ).fetchone()
        if row:
            config = dict(row)

    if not config:
        # Use system environment defaults
        return {
            "client": _openai.AsyncOpenAI(
                api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
                base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL") or None,
            ),
            "model": DEFAULT_MODEL,
            "provider": DEFAULT_PROVIDER,
        }

    provider = config.get("provider", DEFAULT_PROVIDER)
    model = config.get("model", DEFAULT_MODEL)
    api_key = config.get("api_key_enc")  # In production: decrypt with KMS
    base_url = config.get("base_url")

    # Fallback to env if no key stored
    if not api_key:
        if provider == "openai":
            api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        elif provider == "mistral":
            api_key = os.environ.get("MISTRAL_API_KEY")
        elif provider == "azure_openai":
            api_key = os.environ.get("AZURE_OPENAI_KEY")
        elif provider == "local":
            api_key = "not-required"  # Ollama doesn't need a key

    # All providers use OpenAI-compatible SDK
    client = _openai.AsyncOpenAI(
        api_key=api_key or "placeholder",
        base_url=base_url,
    )

    return {"client": client, "model": model, "provider": provider}


# ---------------------------------------------------------------------------
# Helper: require org admin
# ---------------------------------------------------------------------------


def _require_org_admin(db: Session, user_id: str, org_id: str) -> None:
    row = db.execute(
        text("""
            SELECT role FROM memberships
            WHERE user_id = :uid AND org_id = :oid AND is_active = TRUE
              AND role IN ('super_admin', 'org_admin')
            LIMIT 1
        """),
        {"uid": user_id, "oid": org_id},
    ).fetchone()
    if not row:
        raise HTTPException(403, "Org admin role required.")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LLMConfigUpsert(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    on_premise: bool = False
    extra_params: Dict[str, Any] = {}


class LLMTestRequest(BaseModel):
    org_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/providers")
def list_providers() -> Dict[str, Any]:
    return {"providers": PROVIDERS}


@router.get("/config/{org_id}")
def get_config(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_org_admin(db, current_user["id"], org_id)
    row = db.execute(
        text("SELECT provider, model, base_url, on_premise, extra_params, updated_at FROM llm_provider_configs WHERE org_id = :oid"),
        {"oid": org_id},
    ).fetchone()
    if not row:
        return {
            "org_id": org_id,
            "provider": DEFAULT_PROVIDER,
            "model": DEFAULT_MODEL,
            "base_url": None,
            "on_premise": False,
            "configured": False,
            "note": "Using system default. Set a custom config to override.",
        }
    d = dict(row)
    d["org_id"] = org_id
    d["configured"] = True
    d["api_key"] = "***stored***" if True else None  # Never return key
    return d


@router.post("/config/{org_id}")
def upsert_config(
    org_id: str,
    payload: LLMConfigUpsert,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_org_admin(db, current_user["id"], org_id)

    if payload.provider not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider. Supported: {list(PROVIDERS.keys())}")

    # In production, encrypt payload.api_key with KMS before storing
    db.execute(
        text("""
            INSERT INTO llm_provider_configs
                (org_id, provider, model, api_key_enc, base_url, on_premise, extra_params)
            VALUES (:org_id, :provider, :model, :key, :url, :on_prem, :extra)
            ON CONFLICT (org_id) DO UPDATE SET
                provider = EXCLUDED.provider,
                model = EXCLUDED.model,
                api_key_enc = COALESCE(EXCLUDED.api_key_enc, llm_provider_configs.api_key_enc),
                base_url = EXCLUDED.base_url,
                on_premise = EXCLUDED.on_premise,
                extra_params = EXCLUDED.extra_params,
                updated_at = now()
        """),
        {
            "org_id": org_id,
            "provider": payload.provider,
            "model": payload.model,
            "key": payload.api_key,  # Encrypt in production
            "url": payload.base_url or PROVIDERS[payload.provider].get("base_url"),
            "on_prem": payload.on_premise,
            "extra": json.dumps(payload.extra_params),
        },
    )
    db.commit()

    return {
        "status": "saved",
        "org_id": org_id,
        "provider": payload.provider,
        "model": payload.model,
        "on_premise": payload.on_premise,
    }


@router.post("/test")
async def test_config(
    payload: LLMTestRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_org_admin(db, current_user["id"], payload.org_id)

    cfg = await get_llm_client(payload.org_id, db)
    try:
        response = await cfg["client"].chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": "You are AesthetiCite clinical safety AI."},
                {"role": "user", "content": "Reply with: OK — AesthetiCite LLM provider connected."},
            ],
            max_tokens=30,
            temperature=0,
        )
        reply = response.choices[0].message.content
        return {
            "status": "ok",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "response": reply,
        }
    except Exception as e:
        raise HTTPException(502, f"LLM provider test failed: {str(e)[:200]}")
