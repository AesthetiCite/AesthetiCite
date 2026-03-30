"""
AesthetiCite × Haut.AI SkinGPT Integration
===========================================
Integrates the SkinGPT API into AesthetiCite Vision to simulate treatment
outcomes — specifically "treated vs untreated" scenarios for detected
complications (Tyndall effect, erythema, mottling, post-injection swelling).

Architecture
------------
1. SkinGPTClient   — low-level API wrapper (swap mock→live by setting HAUTAI_API_KEY)
2. ComplicationSimulator — maps AesthetiCite complication signals to SkinGPT scenarios
3. FastAPI router  — /visual/simulate-outcome, /visual/simulate-scenarios

Add to main.py:
    from app.api.skingpt_integration import router as skingpt_router
    app.include_router(skingpt_router)

Add to server/routes.ts:
    app.post("/api/visual/simulate-outcome",  (req, res) => proxyToFastAPI(req, res, "/visual/simulate-outcome"));
    app.post("/api/visual/simulate-scenarios",(req, res) => proxyToFastAPI(req, res, "/visual/simulate-scenarios"));
    app.get("/api/visual/simulation/:id",     (req, res) => proxyToFastAPI(req, res, `/visual/simulation/${req.params.id}`));

Environment variables:
    HAUTAI_API_KEY      — Haut.AI B2B API key (obtain from haut.ai/contact)
    HAUTAI_API_BASE     — defaults to https://api.haut.ai/v1
    HAUTAI_MOCK_MODE    — set "true" to run without a real API key (returns placeholder)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visual", tags=["SkinGPT Integration"])

# ─── Configuration ────────────────────────────────────────────────────────────
HAUTAI_API_KEY  = os.environ.get("HAUTAI_API_KEY", "")
HAUTAI_API_BASE = os.environ.get("HAUTAI_API_BASE", "https://api.haut.ai/v1")
MOCK_MODE       = os.environ.get("HAUTAI_MOCK_MODE", "true").lower() == "true"

EXPORT_DIR = os.environ.get("AESTHETICITE_EXPORT_DIR", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

# In-memory simulation cache (replace with Postgres for production)
_SIM_CACHE: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# SkinGPT Scenario definitions
# Maps AesthetiCite complication signals to SkinGPT simulation parameters
# ─────────────────────────────────────────────────────────────────────────────

# SkinGPT scenario library — each scenario has:
#   - skingpt_effect_id:  the effect type Haut.AI API accepts
#   - timeline_weeks:     simulation duration
#   - treated/untreated:  clinical outcome descriptions for UI display
SCENARIO_LIBRARY: Dict[str, Dict[str, Any]] = {
    "tyndall_effect": {
        "label": "Tyndall Effect",
        "skingpt_effect_id": "hyaluronic_acid_superficial",
        "description": "Blue-grey discolouration from superficially placed HA filler",
        "scenarios": [
            {
                "id": "tyndall_treated",
                "label": "After hyaluronidase (4 weeks)",
                "treatment": "hyaluronidase_dissolution",
                "timeline_weeks": 4,
                "prompt_modifier": "skin after hyaluronidase treatment of superficial HA filler, blue-grey discolouration resolving, natural skin tone returning",
                "expected_outcome": "Resolution of blue-grey discolouration with return to natural skin tone in 3–6 weeks"
            },
            {
                "id": "tyndall_untreated",
                "label": "Without treatment (4 weeks)",
                "treatment": "none",
                "timeline_weeks": 4,
                "prompt_modifier": "skin with persistent superficial HA filler Tyndall effect, unchanged blue-grey discolouration",
                "expected_outcome": "Persistent discolouration. HA filler does not self-resolve in superficial placement."
            }
        ]
    },
    "erythema": {
        "label": "Post-Injection Erythema",
        "skingpt_effect_id": "post_injection_erythema",
        "description": "Localised redness following injectable treatment",
        "scenarios": [
            {
                "id": "erythema_treated",
                "label": "With anti-inflammatory management (72h)",
                "treatment": "topical_anti_inflammatory",
                "timeline_weeks": 1,
                "prompt_modifier": "skin 72 hours after anti-inflammatory treatment for post-injection erythema, redness significantly reduced",
                "expected_outcome": "Significant reduction in erythema within 48–72h with appropriate management"
            },
            {
                "id": "erythema_untreated",
                "label": "Natural resolution (1 week)",
                "treatment": "observation",
                "timeline_weeks": 1,
                "prompt_modifier": "skin one week after injectable treatment, mild residual erythema, normal healing trajectory",
                "expected_outcome": "Most post-injection erythema self-resolves within 5–7 days"
            }
        ]
    },
    "swelling": {
        "label": "Post-Filler Swelling",
        "skingpt_effect_id": "post_filler_oedema",
        "description": "Oedema following filler injection",
        "scenarios": [
            {
                "id": "swelling_day3",
                "label": "Day 3 post-treatment",
                "treatment": "observation",
                "timeline_weeks": 0.5,
                "prompt_modifier": "face day 3 after dermal filler, initial swelling subsiding, early settling of filler",
                "expected_outcome": "Peak swelling typically at 24–48h, beginning to subside by day 3"
            },
            {
                "id": "swelling_week2",
                "label": "Week 2 — settled result",
                "treatment": "observation",
                "timeline_weeks": 2,
                "prompt_modifier": "face two weeks after dermal filler, swelling fully resolved, final settled result visible",
                "expected_outcome": "Swelling fully resolved by 2 weeks; final aesthetic result visible"
            }
        ]
    },
    "infection_signs": {
        "label": "Infection / Biofilm",
        "skingpt_effect_id": "inflammatory_nodule",
        "description": "Signs of infection or biofilm reaction",
        "scenarios": [
            {
                "id": "infection_treated",
                "label": "After antibiotic treatment (4 weeks)",
                "treatment": "antibiotics_and_hyaluronidase",
                "timeline_weeks": 4,
                "prompt_modifier": "skin after treatment of filler-associated infection with antibiotics and hyaluronidase, inflammation resolving",
                "expected_outcome": "With appropriate antibiotics ± hyaluronidase, most infections resolve within 4–6 weeks"
            },
            {
                "id": "infection_untreated",
                "label": "Without treatment (2 weeks)",
                "treatment": "none",
                "timeline_weeks": 2,
                "prompt_modifier": "skin with untreated filler-associated infection, progressive inflammation, erythema worsening",
                "expected_outcome": "Untreated infection may progress to abscess formation, tissue damage, or systemic spread"
            }
        ]
    },
    "blanching": {
        "label": "Vascular Compromise",
        "skingpt_effect_id": "vascular_compromise",
        "description": "Skin blanching suggesting vascular occlusion",
        "scenarios": [
            {
                "id": "vo_treated_early",
                "label": "Treated within 1h (hyaluronidase)",
                "treatment": "hyaluronidase_emergency",
                "timeline_weeks": 1,
                "prompt_modifier": "skin one week after successful treatment of HA filler vascular occlusion with hyaluronidase within 1 hour, normal perfusion restored, minimal residual change",
                "expected_outcome": "Early treatment (within 1h) with hyaluronidase significantly improves outcomes"
            },
            {
                "id": "vo_delayed_treatment",
                "label": "Delayed treatment (>6h)",
                "treatment": "hyaluronidase_delayed",
                "timeline_weeks": 4,
                "prompt_modifier": "skin four weeks after delayed treatment of filler vascular occlusion, residual scarring, hyperpigmentation, possible tissue damage",
                "expected_outcome": "Delayed treatment risks tissue necrosis, scarring, and permanent hyperpigmentation"
            }
        ]
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# SkinGPT API client
# ─────────────────────────────────────────────────────────────────────────────

class SkinGPTClient:
    """
    Thin async wrapper around the Haut.AI SkinGPT API.
    Swap HAUTAI_MOCK_MODE=false once you have the B2B API key.

    Haut.AI API contact: https://haut.ai/contact
    Expected endpoint structure based on their documentation pattern:
      POST /v1/simulate
      POST /v1/simulate/batch
    """

    BASE_URL = HAUTAI_API_BASE

    async def simulate(
        self,
        image_b64: str,
        effect_id: str,
        prompt_modifier: str,
        timeline_weeks: float,
        skin_tone_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Request a single skin simulation from SkinGPT.
        Returns: { simulation_id, image_b64, effect_applied, confidence, ... }
        """
        if MOCK_MODE or not HAUTAI_API_KEY:
            return await self._mock_simulate(effect_id, prompt_modifier, timeline_weeks)

        payload = {
            "image": image_b64,
            "effect": {
                "effect_id": effect_id,
                "timeline_weeks": timeline_weeks,
                "prompt_modifier": prompt_modifier,
            },
            "options": {
                "output_format": "base64",
                "resolution": "high",
                "skin_tone_hint": skin_tone_hint,
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/simulate",
                json=payload,
                headers={
                    "Authorization": f"Bearer {HAUTAI_API_KEY}",
                    "Content-Type": "application/json",
                    "X-Client": "AesthetiCite/1.0",
                },
            )
            if resp.status_code == 402:
                raise HTTPException(status_code=402, detail="SkinGPT API quota exceeded. Contact haut.ai for B2B plan.")
            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid SkinGPT API key. Set HAUTAI_API_KEY.")
            resp.raise_for_status()
            return resp.json()

    async def _mock_simulate(
        self,
        effect_id: str,
        prompt_modifier: str,
        timeline_weeks: float,
    ) -> Dict[str, Any]:
        """
        Mock response for development — returns the structure SkinGPT will return.
        Replace with live API once HAUTAI_API_KEY is set.
        """
        await asyncio.sleep(0.3)  # simulate network latency
        return {
            "simulation_id": f"mock_{uuid.uuid4().hex[:8]}",
            "image_b64": None,           # real API returns base64 image
            "effect_applied": effect_id,
            "confidence": 0.82,
            "timeline_weeks": timeline_weeks,
            "is_mock": True,
            "mock_message": (
                "SkinGPT mock mode active. Set HAUTAI_API_KEY + HAUTAI_MOCK_MODE=false "
                "to enable live photorealistic simulations. Contact haut.ai/contact for B2B pricing."
            ),
            "prompt_applied": prompt_modifier,
        }


_skingpt = SkinGPTClient()


# ─────────────────────────────────────────────────────────────────────────────
# Complication → Scenario mapper
# ─────────────────────────────────────────────────────────────────────────────

def map_signals_to_scenarios(detected_signals: List[str]) -> List[str]:
    """
    Maps AesthetiCite vision protocol bridge signals to SkinGPT scenario keys.
    Returns list of scenario_library keys that are relevant.
    """
    signal_to_scenario = {
        "tyndall_flag":        "tyndall_effect",
        "blue_gray_tyndall":   "tyndall_effect",
        "erythema":            "erythema",
        "swelling":            "swelling",
        "angioedema":          "swelling",
        "infection_signs":     "infection_signs",
        "fluctuance":          "infection_signs",
        "blanching":           "blanching",
        "mottling":            "blanching",
        "necrosis":            "blanching",
    }
    seen: set = set()
    result: List[str] = []
    for sig in detected_signals:
        scenario_key = signal_to_scenario.get(sig)
        if scenario_key and scenario_key not in seen:
            seen.add(scenario_key)
            result.append(scenario_key)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class SimulationScenario(BaseModel):
    scenario_id: str
    label: str
    treatment: str
    timeline_weeks: float
    expected_outcome: str
    image_b64: Optional[str] = None
    simulation_id: Optional[str] = None
    confidence: Optional[float] = None
    is_mock: bool = False
    mock_message: Optional[str] = None


class SimulationResult(BaseModel):
    complication_key: str
    complication_label: str
    complication_description: str
    scenarios: List[SimulationScenario]
    generated_at_utc: str


class SimulateOutcomeRequest(BaseModel):
    """Request a simulation for a specific complication on a specific patient image."""
    visual_id: Optional[str] = None         # existing uploaded image
    complication_key: str                   # key from SCENARIO_LIBRARY
    fitzpatrick_type: Optional[str] = None  # I–VI, improves simulation accuracy
    clinician_id: Optional[str] = None


class SimulateScenariosRequest(BaseModel):
    """Simulate all relevant scenarios based on detected vision signals."""
    visual_id: Optional[str] = None
    detected_signals: List[str] = Field(..., description="Signal list from vision protocol bridge")
    fitzpatrick_type: Optional[str] = None
    clinician_id: Optional[str] = None
    max_scenarios: int = Field(2, ge=1, le=4, description="Max complication types to simulate")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/simulate-outcome",
    response_model=SimulationResult,
    summary="Simulate treated vs untreated outcome for a detected complication",
)
async def simulate_outcome(req: SimulateOutcomeRequest) -> SimulationResult:
    """
    Core endpoint. Takes a complication key + patient image visual_id and
    returns SkinGPT simulations for treated vs untreated scenarios.

    Example: complication_key="tyndall_effect" →
      - Scenario A: skin after 4-week hyaluronidase treatment
      - Scenario B: skin without treatment at 4 weeks

    This is the unique feature: AesthetiCite detects the complication,
    SkinGPT shows the clinician and patient what happens either way.
    """
    scenario_def = SCENARIO_LIBRARY.get(req.complication_key)
    if not scenario_def:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown complication key: '{req.complication_key}'. "
                   f"Valid: {list(SCENARIO_LIBRARY.keys())}"
        )

    # Retrieve image bytes if visual_id provided
    image_b64 = await _get_image_b64(req.visual_id)

    scenarios_out: List[SimulationScenario] = []
    for sc in scenario_def["scenarios"]:
        try:
            sim = await _skingpt.simulate(
                image_b64=image_b64 or "",
                effect_id=scenario_def["skingpt_effect_id"],
                prompt_modifier=sc["prompt_modifier"],
                timeline_weeks=sc["timeline_weeks"],
                skin_tone_hint=req.fitzpatrick_type,
            )
            scenarios_out.append(SimulationScenario(
                scenario_id=sc["id"],
                label=sc["label"],
                treatment=sc["treatment"],
                timeline_weeks=sc["timeline_weeks"],
                expected_outcome=sc["expected_outcome"],
                image_b64=sim.get("image_b64"),
                simulation_id=sim.get("simulation_id"),
                confidence=sim.get("confidence"),
                is_mock=sim.get("is_mock", False),
                mock_message=sim.get("mock_message"),
            ))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[SkinGPT] Simulation failed for {sc['id']}: {e}")
            scenarios_out.append(SimulationScenario(
                scenario_id=sc["id"],
                label=sc["label"],
                treatment=sc["treatment"],
                timeline_weeks=sc["timeline_weeks"],
                expected_outcome=sc["expected_outcome"],
                is_mock=True,
                mock_message=f"Simulation unavailable: {str(e)[:100]}",
            ))

    result = SimulationResult(
        complication_key=req.complication_key,
        complication_label=scenario_def["label"],
        complication_description=scenario_def["description"],
        scenarios=scenarios_out,
        generated_at_utc=_now(),
    )

    # Cache for frontend retrieval
    cache_id = uuid.uuid4().hex[:12]
    _SIM_CACHE[cache_id] = result.dict()
    return result


@router.post(
    "/simulate-scenarios",
    summary="Auto-simulate all relevant scenarios from detected vision signals",
)
async def simulate_scenarios(req: SimulateScenariosRequest) -> Dict[str, Any]:
    """
    Takes the detected_signals list from the vision protocol bridge and
    automatically selects and runs the most relevant SkinGPT simulations.

    Typical call flow:
      1. Vision engine analyses photo → returns analysis_text + triggered_protocols
      2. Protocol bridge extracts detected_signals
      3. Call this endpoint with detected_signals
      4. Returns up to req.max_scenarios simulation results
    """
    scenario_keys = map_signals_to_scenarios(req.detected_signals)

    if not scenario_keys:
        return {
            "simulations": [],
            "message": "No simulatable complication signals detected in this image.",
            "detected_signals": req.detected_signals,
        }

    # Limit to max_scenarios
    scenario_keys = scenario_keys[:req.max_scenarios]

    simulations = []
    for key in scenario_keys:
        try:
            result = await simulate_outcome(SimulateOutcomeRequest(
                visual_id=req.visual_id,
                complication_key=key,
                fitzpatrick_type=req.fitzpatrick_type,
                clinician_id=req.clinician_id,
            ))
            simulations.append(result.dict())
        except Exception as e:
            logger.error(f"[SkinGPT] Batch simulation failed for {key}: {e}")

    return {
        "simulations": simulations,
        "signal_count": len(req.detected_signals),
        "scenarios_run": len(simulations),
        "generated_at_utc": _now(),
        "mock_mode": MOCK_MODE,
        "mock_notice": (
            "Live simulations require HAUTAI_API_KEY. "
            "Contact https://haut.ai/contact for B2B pricing."
        ) if MOCK_MODE else None,
    }


@router.get(
    "/available-scenarios",
    summary="List all available complication simulation scenarios",
)
def list_scenarios() -> Dict[str, Any]:
    """Returns all available scenarios with their descriptions."""
    return {
        "scenarios": [
            {
                "key": k,
                "label": v["label"],
                "description": v["description"],
                "scenario_count": len(v["scenarios"]),
                "scenario_options": [s["label"] for s in v["scenarios"]],
            }
            for k, v in SCENARIO_LIBRARY.items()
        ],
        "total": len(SCENARIO_LIBRARY),
        "mock_mode": MOCK_MODE,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: retrieve image bytes from visual store
# ─────────────────────────────────────────────────────────────────────────────

async def _get_image_b64(visual_id: Optional[str]) -> Optional[str]:
    """
    Attempts to retrieve base64 image from the Postgres visual store.
    Falls back gracefully — SkinGPT can run without source image in mock mode.
    """
    if not visual_id:
        return None
    try:
        from app.rag import async_retriever as _ar
        if _ar._pool is None:
            return None
        async with _ar._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT image_data FROM visuals WHERE id = $1",
                visual_id,
            )
            if row and row["image_data"]:
                raw = bytes(row["image_data"])
                return base64.b64encode(raw).decode()
    except Exception as e:
        logger.debug(f"[SkinGPT] Could not load image {visual_id}: {e}")
    return None
