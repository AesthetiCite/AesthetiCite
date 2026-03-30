from __future__ import annotations
import os
import math
import hashlib
import json
import httpx
import threading
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from cachetools import TTLCache

from app.db.session import get_db
from app.schemas.tools import (
    InteractionRequest, InteractionResponse, InteractionFinding,
    BMIRequest, BSARequest, CockcroftGaultRequest, EgfrCkdEpi2021Request,
    UnitConvertRequest, ConcentrationRequest, DilutionRequest,
    MgKgDoseRequest, McgKgMinInfusionRequest,
    BotoxReconstitutionRequest, BotoxSessionTotalRequest,
    SteroidEquivalentRequest,
    CreateDosingRuleRequest, DosingRuleOut, EvidenceLockedRequest, GenericCalcResponse
)
from app.core.admin_auth import require_admin

router = APIRouter(prefix="/tools", tags=["tools"])

DISCLAIMER = (
    "Clinical decision support only. Verify with local protocols and authoritative sources. "
    "AesthetiCite does not replace clinical judgment."
)

RXNAV_PUBLIC_BASE = "https://rxnav.nlm.nih.gov/REST"
RXNAV_LOCAL_BASE = os.getenv("RXNAV_LOCAL_BASE", "").rstrip("/")

CACHE_TTL_SECONDS = int(os.getenv("DDI_CACHE_TTL", "172800"))
interaction_cache = TTLCache(maxsize=50000, ttl=CACHE_TTL_SECONDS)
rxcui_cache = TTLCache(maxsize=10000, ttl=CACHE_TTL_SECONDS)

RXNAV_QPS = float(os.getenv("RXNAV_QPS", "10"))
_last_rxnav_call = 0.0
_rl_lock = threading.Lock()


def _rate_limit_rxnav():
    """Rate limit RxNav API calls."""
    global _last_rxnav_call
    if RXNAV_QPS <= 0:
        return
    min_interval = 1.0 / RXNAV_QPS
    with _rl_lock:
        now = time.time()
        wait = (_last_rxnav_call + min_interval) - now
        if wait > 0:
            time.sleep(wait)
        _last_rxnav_call = time.time()


def _cache_key(kind: str, obj: dict) -> str:
    raw = kind + ":" + json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _rxnorm_ids_for_name(name: str) -> List[str]:
    """Get RxNorm IDs for a drug name, with caching."""
    cache_key = _cache_key("rxcui", {"name": name.lower().strip()})
    cached = rxcui_cache.get(cache_key)
    if cached is not None:
        return cached
    
    base_url = RXNAV_LOCAL_BASE or RXNAV_PUBLIC_BASE
    url = f"{base_url}/approximateTerm.json"
    params = {"term": name, "maxEntries": 3}
    
    _rate_limit_rxnav()
    
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    
    ids = []
    for cand in data.get("approximateGroup", {}).get("candidate", []) or []:
        rid = cand.get("rxcui")
        if rid:
            ids.append(rid)
    
    rxcui_cache[cache_key] = ids
    return ids


async def _interactions_for_rxcuis(rxcuis: List[str]) -> List[InteractionFinding]:
    """Get drug interactions with caching."""
    sorted_rxcuis = sorted(set(rxcuis))
    cache_key = _cache_key("ddi", {"rxcuis": sorted_rxcuis})
    cached = interaction_cache.get(cache_key)
    if cached is not None:
        return cached
    
    base_url = RXNAV_LOCAL_BASE or RXNAV_PUBLIC_BASE
    url = f"{base_url}/interaction/list.json"
    params = {"rxcuis": "+".join(rxcuis)}
    
    _rate_limit_rxnav()
    
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url, params=params)
        if r.status_code == 404:
            # RxNorm returns 404 when no interaction data exists for these RxCUIs
            interaction_cache[cache_key] = []
            return []
        r.raise_for_status()
        data = r.json()
    
    findings: List[InteractionFinding] = []
    groups = data.get("fullInteractionTypeGroup", []) or []
    for g in groups:
        src = g.get("sourceName")
        for fit in g.get("fullInteractionType", []) or []:
            for pair in fit.get("interactionPair", []) or []:
                desc = pair.get("description") or ""
                sev = pair.get("severity") or None
                if desc:
                    findings.append(InteractionFinding(severity=sev, description=desc, source=src))
    
    interaction_cache[cache_key] = findings
    return findings


def _summarize_severity(findings: List[InteractionFinding]) -> Dict[str, Any]:
    """Summarize severity levels for UI display."""
    counts = {"contraindicated": 0, "major": 0, "moderate": 0, "minor": 0, "unknown": 0}
    for f in findings:
        sev = (f.severity or "unknown").lower()
        if "contra" in sev:
            counts["contraindicated"] += 1
        elif "major" in sev or "high" in sev:
            counts["major"] += 1
        elif "moder" in sev or "med" in sev:
            counts["moderate"] += 1
        elif "minor" in sev or "low" in sev:
            counts["minor"] += 1
        else:
            counts["unknown"] += 1
    
    if sum(counts.values()) == 0:
        overall = "none"
    elif counts["contraindicated"] > 0:
        overall = "contraindicated"
    elif counts["major"] > 0:
        overall = "major"
    elif counts["moderate"] > 0:
        overall = "moderate"
    elif counts["minor"] > 0:
        overall = "minor"
    else:
        overall = "unknown"
    
    return {"overall": overall, "counts": counts}


@router.post("/interactions", response_model=InteractionResponse)
async def interactions(payload: InteractionRequest):
    all_rxcuis: List[str] = []
    for d in payload.drugs:
        ids = await _rxnorm_ids_for_name(d)
        if ids:
            all_rxcuis.append(ids[0])
    if len(all_rxcuis) < 2:
        raise HTTPException(status_code=400, detail="Could not resolve enough drugs to RxNorm identifiers.")

    findings = await _interactions_for_rxcuis(all_rxcuis)
    seen = set()
    deduped = []
    for f in findings:
        key = (f.severity, f.description)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    return InteractionResponse(
        ok=True, 
        drugs=payload.drugs, 
        findings=deduped, 
        disclaimer=DISCLAIMER,
        summary=_summarize_severity(deduped)
    )

@router.post("/calculators/bmi", response_model=GenericCalcResponse)
def bmi(payload: BMIRequest):
    h_m = payload.height_cm / 100.0
    v = payload.weight_kg / (h_m * h_m)
    return GenericCalcResponse(ok=True, result=round(v, 2), unit="kg/m^2", disclaimer=DISCLAIMER)

@router.post("/calculators/bsa", response_model=GenericCalcResponse)
def bsa(payload: BSARequest):
    v = math.sqrt((payload.height_cm * payload.weight_kg) / 3600.0)
    return GenericCalcResponse(ok=True, result=round(v, 3), unit="m^2", details={"formula": "Mosteller"}, disclaimer=DISCLAIMER)

@router.post("/calculators/cockcroft-gault", response_model=GenericCalcResponse)
def cockcroft_gault(payload: CockcroftGaultRequest):
    crcl = ((140 - payload.age_years) * payload.weight_kg) / (72.0 * payload.serum_creatinine_mg_dl)
    if payload.sex == "female":
        crcl *= 0.85
    return GenericCalcResponse(ok=True, result=round(crcl, 1), unit="mL/min", details={"formula": "Cockcroft-Gault"}, disclaimer=DISCLAIMER)

@router.post("/calculators/egfr-ckd-epi-2021", response_model=GenericCalcResponse)
def egfr_ckd_epi_2021(payload: EgfrCkdEpi2021Request):
    Scr = payload.serum_creatinine_mg_dl
    age = payload.age_years
    female = payload.sex == "female"
    k = 0.7 if female else 0.9
    a = -0.241 if female else -0.302
    min_ratio = min(Scr / k, 1.0)
    max_ratio = max(Scr / k, 1.0)
    egfr = 142 * (min_ratio ** a) * (max_ratio ** -1.200) * (0.9938 ** age) * (1.012 if female else 1.0)
    return GenericCalcResponse(ok=True, result=round(egfr, 1), unit="mL/min/1.73m^2", details={"formula": "CKD-EPI 2021 (Cr)"}, disclaimer=DISCLAIMER)

@router.post("/calculators/unit-convert", response_model=GenericCalcResponse)
def unit_convert(payload: UnitConvertRequest):
    mass = {"mcg": 1e-6, "mg": 1e-3, "g": 1.0}
    vol = {"ml": 1e-3, "l": 1.0}
    iu = {"iu": 1.0, "units": 1.0}

    fu, tu = payload.from_unit, payload.to_unit
    v = payload.value

    if fu in mass and tu in mass:
        base_g = v * mass[fu]
        out = base_g / mass[tu]
        return GenericCalcResponse(ok=True, result=out, unit=tu, disclaimer=DISCLAIMER)

    if fu in vol and tu in vol:
        base_l = v * vol[fu]
        out = base_l / vol[tu]
        return GenericCalcResponse(ok=True, result=out, unit=tu, disclaimer=DISCLAIMER)

    if fu in iu and tu in iu:
        return GenericCalcResponse(ok=True, result=v, unit=tu, disclaimer=DISCLAIMER)

    if fu == "percent" and tu == "mg":
        raise HTTPException(status_code=400, detail="Percent must be converted with volume (use /calc/concentration).")

    raise HTTPException(status_code=400, detail="Incompatible units.")

@router.post("/calc/concentration", response_model=GenericCalcResponse)
def concentration(payload: ConcentrationRequest):
    if payload.percent is not None:
        mg_per_ml = payload.percent * 10.0
        return GenericCalcResponse(ok=True, result=mg_per_ml, unit="mg/mL", details={"assumption": "1% = 10 mg/mL"}, disclaimer=DISCLAIMER)
    if payload.amount_mg is None or payload.volume_ml is None or payload.volume_ml <= 0:
        raise HTTPException(status_code=400, detail="Provide (amount_mg and volume_ml) or percent.")
    mg_per_ml = payload.amount_mg / payload.volume_ml
    return GenericCalcResponse(ok=True, result=mg_per_ml, unit="mg/mL", disclaimer=DISCLAIMER)

@router.post("/calc/dilution", response_model=GenericCalcResponse)
def dilution(payload: DilutionRequest):
    if payload.final_volume_ml <= 0:
        raise HTTPException(status_code=400, detail="final_volume_ml must be > 0")
    if payload.stock_unit != payload.desired_unit:
        raise HTTPException(status_code=400, detail="Units must match (mg_per_ml or units_per_ml).")

    v1 = (payload.desired_value * payload.final_volume_ml) / payload.stock_value
    v2 = payload.final_volume_ml - v1
    if v1 < 0 or v2 < 0:
        raise HTTPException(status_code=400, detail="Invalid dilution values.")
    return GenericCalcResponse(
        ok=True,
        result={"stock_volume_ml": round(v1, 3), "diluent_volume_ml": round(v2, 3), "final_volume_ml": payload.final_volume_ml},
        unit="mL",
        details={"formula": "C1V1=C2V2"},
        disclaimer=DISCLAIMER
    )

@router.post("/dose/mgkg", response_model=GenericCalcResponse)
def dose_mgkg(payload: MgKgDoseRequest):
    total_mg = payload.dose_mg_per_kg * payload.weight_kg
    return GenericCalcResponse(ok=True, result=round(total_mg, 3), unit="mg", details={"dose_mg_per_kg": payload.dose_mg_per_kg, "weight_kg": payload.weight_kg}, disclaimer=DISCLAIMER)

@router.post("/dose/mcgkgmin-mlhr", response_model=GenericCalcResponse)
def mcgkgmin_to_mlhr(payload: McgKgMinInfusionRequest):
    mcg_per_min = payload.dose_mcg_per_kg_min * payload.weight_kg
    ml_per_min = mcg_per_min / payload.concentration_mcg_per_ml
    ml_per_hr = ml_per_min * 60.0
    return GenericCalcResponse(ok=True, result=round(ml_per_hr, 3), unit="mL/hr", details={"dose_mcg_per_kg_min": payload.dose_mcg_per_kg_min, "weight_kg": payload.weight_kg}, disclaimer=DISCLAIMER)

@router.post("/botox/reconstitution", response_model=GenericCalcResponse)
def botox_reconstitution(payload: BotoxReconstitutionRequest):
    units_per_ml = payload.vial_units / payload.diluent_ml
    units_per_0_1ml = units_per_ml * 0.1
    return GenericCalcResponse(
        ok=True,
        result={"units_per_ml": round(units_per_ml, 3), "units_per_0_1ml": round(units_per_0_1ml, 3)},
        unit="U/mL",
        details={"vial_units": payload.vial_units, "diluent_ml": payload.diluent_ml},
        disclaimer=DISCLAIMER
    )

@router.post("/botox/session-total", response_model=GenericCalcResponse)
def botox_session_total(payload: BotoxSessionTotalRequest):
    total = sum(payload.injection_points_units)
    return GenericCalcResponse(ok=True, result=round(total, 3), unit="Units", details={"points": len(payload.injection_points_units)}, disclaimer=DISCLAIMER)

_STEROID_EQ = {
    "prednisone": 5.0,
    "methylprednisolone": 4.0,
    "hydrocortisone": 20.0,
    "dexamethasone": 0.75
}

@router.post("/steroids/equivalent", response_model=GenericCalcResponse)
def steroid_equivalent(payload: SteroidEquivalentRequest):
    from_ref = _STEROID_EQ[payload.from_steroid]
    to_ref = _STEROID_EQ[payload.to_steroid]
    ref_units = payload.value_mg / from_ref
    out_mg = ref_units * to_ref
    return GenericCalcResponse(ok=True, result=round(out_mg, 3), unit="mg", details={"from_steroid": payload.from_steroid, "to_steroid": payload.to_steroid}, disclaimer=DISCLAIMER)

@router.post("/evidence/limit", response_model=GenericCalcResponse)
def evidence_locked_limit(payload: EvidenceLockedRequest, db: Session = Depends(get_db)):
    row = db.execute(text("""
      SELECT id::text, name, category, rule_json, source_id, source_excerpt
      FROM dosing_rules
      WHERE id = :id
    """), {"id": payload.rule_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Rule not found. (Evidence-locked calculator requires a stored rule.)")

    rule = row["rule_json"] or {}
    if row["category"] == "local_anesthetic":
        with_epi = bool(payload.with_epinephrine)
        key = "max_mg_per_kg_epi" if with_epi else "max_mg_per_kg_plain"
        if key not in rule:
            raise HTTPException(status_code=400, detail=f"Rule missing '{key}'.")
        max_mg = float(rule[key]) * payload.weight_kg
        details = {
            "rule_name": row["name"],
            "category": row["category"],
            "max_mg_per_kg": float(rule[key]),
            "with_epinephrine": with_epi,
            "source_id": row.get("source_id"),
            "source_excerpt": row.get("source_excerpt"),
        }
        return GenericCalcResponse(ok=True, result=round(max_mg, 2), unit="mg", details=details, disclaimer=DISCLAIMER)

    raise HTTPException(status_code=400, detail="Unsupported category for evidence/limit endpoint.")

admin_router = APIRouter(prefix="/admin/dosing-rules", tags=["admin-dosing"])

@admin_router.get("", response_model=List[DosingRuleOut])
def list_rules(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(text("""
      SELECT id::text, name, category, rule_json, source_id, source_excerpt, updated_at::text
      FROM dosing_rules
      ORDER BY updated_at DESC
      LIMIT 500;
    """)).mappings().all()
    return [dict(r) for r in rows]

@admin_router.post("", response_model=DosingRuleOut)
def create_rule(payload: CreateDosingRuleRequest, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    import json
    row = db.execute(text("""
      INSERT INTO dosing_rules (name, category, rule_json, source_id, source_excerpt, updated_at)
      VALUES (:name, :category, :rule_json::jsonb, :source_id, :source_excerpt, now())
      RETURNING id::text, name, category, rule_json, source_id, source_excerpt, updated_at::text;
    """), {
        "name": payload.name,
        "category": payload.category,
        "rule_json": json.dumps(payload.rule_json),
        "source_id": payload.source_id,
        "source_excerpt": payload.source_excerpt
    }).mappings().first()
    db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create dosing rule")
    return dict(row)

@admin_router.delete("/{rule_id}")
def delete_rule(rule_id: str, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM dosing_rules WHERE id = :id"), {"id": rule_id})
    db.commit()
    return {"ok": True}
