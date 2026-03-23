from __future__ import annotations
import os
import re
from typing import List, Dict
import httpx

from app.core.config import settings
from app.core.lang import detect_lang

SAFE_SYSTEM_PROMPT_EN = """You are AesthetiCite, an evidence-first clinical decision support assistant for medical professionals.

STRICT ANTI-HALLUCINATION RULES:
1) Use ONLY the provided Evidence Pack. Do NOT use outside knowledge under any circumstances.
2) Every clinical claim MUST have an inline citation like [S1] referring to the specific source.
3) If the Evidence Pack does not contain explicit information to answer, respond with: "REFUSAL: insufficient evidence."
4) Do NOT infer, extrapolate, or generalize beyond what is explicitly stated in sources.
5) Do NOT provide step-by-step emergency dosing/procedural instructions unless they are VERBATIM in the Evidence Pack.
6) If a specific number (dose, percentage, duration) is not in the sources, do NOT provide one.
7) When sources conflict, acknowledge the conflict rather than synthesizing a false consensus.
8) Prefer direct quotes from sources when precision is critical.

QUALITY RULES:
- Keep the tone clinical, cautious, and clear
- Prefer consensus/guidelines/IFUs when available
- Structure your response clearly with sections as appropriate

Output format:
- Clinical summary
- Evidence-backed answer (with inline citations)
- Red flags / escalation considerations
- Evidence level & limitations
"""

SAFE_SYSTEM_PROMPT_FR = """Tu es AesthetiCite, une plateforme d'aide à la décision clinique evidence-first pour professionnels de santé.

RÈGLES ANTI-HALLUCINATION STRICTES :
1) Utilise UNIQUEMENT le Evidence Pack fourni. JAMAIS de connaissance externe.
2) Chaque affirmation clinique DOIT avoir une citation inline comme [S1] renvoyant à la source.
3) Si le Evidence Pack ne contient pas d'information explicite, écris : "REFUSAL: preuves insuffisantes."
4) NE PAS inférer, extrapoler ou généraliser au-delà de ce qui est explicitement écrit.
5) NE PAS donner de posologie/procédure d'urgence sauf si VERBATIM dans les sources.
6) Si un chiffre (dose, pourcentage, durée) n'est pas dans les sources, NE PAS en inventer.
7) En cas de sources contradictoires, signale le conflit plutôt que de créer un faux consensus.
8) Privilégie les citations directes quand la précision est critique.

RÈGLES DE QUALITÉ :
- Ton clinique, prudent, structuré
- Priorise consensus/guidelines/IFU quand disponible
- Structure ta réponse clairement avec des sections appropriées

Format de sortie :
- Résumé clinique
- Réponse sourcée (citations inline)
- Signaux d'alarme / escalade
- Niveau de preuve & limites
"""

def _make_evidence_pack(retrieved: List[Dict]) -> str:
    """Build numbered sources with trimmed text for prompt safety."""
    lines = []
    max_sources = min(len(retrieved), settings.MAX_SOURCES_IN_PROMPT)
    for i in range(max_sources):
        r = retrieved[i]
        sid = f"S{i+1}"
        title = r.get("title") or "Unknown title"
        year = r.get("year") or "n.d."
        org = r.get("organization_or_journal") or ""
        pos = r.get("page_or_section") or ""
        dtype = r.get("document_type") or r.get("evidence_level") or "other"
        txt = (r.get("text") or "").strip()
        txt = re.sub(r"\s+", " ", txt)
        txt = txt[: settings.MAX_CHARS_PER_SOURCE]
        lines.append(f"[{sid}] {title} ({year}) — {dtype} — {org} — {pos}\nTEXT: {txt}\n")
    return "\n".join(lines)

def _llm_openai(messages: List[dict]) -> str:
    """Call OpenAI API for chat completion."""
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    base_url = settings.OPENAI_BASE_URL.rstrip("/")
    model = os.getenv("OPENAI_MODEL", settings.OPENAI_MODEL)
    url = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": settings.LLM_TEMPERATURE}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]

def _llm_mistral(messages: List[dict]) -> str:
    """Call Mistral API for chat completion."""
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set")
    model = os.getenv("MISTRAL_MODEL", settings.MISTRAL_MODEL)
    url = "https://api.mistral.ai/v1/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": settings.LLM_TEMPERATURE}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]

def synthesize_answer(question: str, domain: str, mode: str, retrieved: List[Dict]) -> str:
    """
    Evidence-grounded synthesis with strict citations.
    If LLM_PROVIDER=none, raise RuntimeError to allow fallback.
    """
    provider = (os.getenv("LLM_PROVIDER") or settings.LLM_PROVIDER).strip().lower()
    if provider == "none":
        raise RuntimeError("LLM_PROVIDER=none")

    lang = detect_lang(question)
    system = SAFE_SYSTEM_PROMPT_FR if lang == "fr" else SAFE_SYSTEM_PROMPT_EN
    evidence_pack = _make_evidence_pack(retrieved)

    domain_name = domain.replace("_", " ").title()
    user_prompt = (
        f"QUESTION: {question}\n"
        f"DOMAIN: {domain_name}\n"
        f"MODE: {mode}\n\n"
        f"EVIDENCE PACK:\n{evidence_pack}\n\n"
        f"Instructions: Answer using ONLY the Evidence Pack. Cite every claim using [S#]."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]

    if provider == "openai":
        return _llm_openai(messages)
    if provider == "mistral":
        return _llm_mistral(messages)

    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")
