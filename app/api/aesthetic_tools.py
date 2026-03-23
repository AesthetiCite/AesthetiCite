"""
AesthetiCite Aesthetic Medicine Safety Tools

Deterministic clinical decision support tools for aesthetic medicine:
- Local anesthetic safety (lidocaine/articaine/bupivacaine/ropivacaine) max dose calculator
- Epinephrine concentration helper + max dose guidance
- Acetaminophen safety check (adult)
- Botulinum toxin dilution helper (multi-brand)
- Vascular occlusion emergency checklist
- HSV prophylaxis suggestion (evidence-sensitive)
- Contraindication/risk flagger
- Local interaction checker

Design: Safety-first with hard bounds, warnings, and evidence hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, List, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator


router = APIRouter(prefix="/tools/aesthetic", tags=["aesthetic-tools"])


# -----------------------------------------------------------------------------
# Shared response shapes
# -----------------------------------------------------------------------------

class ToolStatus(str, Enum):
    ok = "ok"
    refuse = "refuse"
    error = "error"


class EvidenceItem(BaseModel):
    source_id: str = Field(..., description="Internal evidence id or corpus doc id")
    label: str = Field(..., description="Short label")
    note: Optional[str] = Field(None, description="Optional note about relevance")


class ToolResult(BaseModel):
    status: ToolStatus
    name: str
    output: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    refusals: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    disclaimer: str = "Clinical decision support only. Verify with local protocols and authoritative sources. AesthetiCite does not replace clinical judgment."


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------

def _round(x: float, nd: int = 2) -> float:
    try:
        return float(round(float(x), nd))
    except Exception:
        return x  # type: ignore


def _require(condition: bool, message: str, *, name: str) -> None:
    if not condition:
        raise HTTPException(status_code=422, detail=f"{name}: {message}")


# -----------------------------------------------------------------------------
# Tool: Local anesthetic maximum dose calculator
# -----------------------------------------------------------------------------

class LocalAnestheticAgent(str, Enum):
    lidocaine = "lidocaine"
    articaine = "articaine"
    bupivacaine = "bupivacaine"
    ropivacaine = "ropivacaine"


@dataclass(frozen=True)
class LocalAnestheticRule:
    mg_per_kg_no_epi: float
    max_mg_no_epi: float
    mg_per_kg_with_epi: float
    max_mg_with_epi: float
    common_mg_per_ml: Tuple[float, ...]
    evidence_ids: Tuple[str, ...]


LOCAL_ANESTHETIC_RULES: Dict[LocalAnestheticAgent, LocalAnestheticRule] = {
    LocalAnestheticAgent.lidocaine: LocalAnestheticRule(
        mg_per_kg_no_epi=4.5,
        max_mg_no_epi=300.0,
        mg_per_kg_with_epi=7.0,
        max_mg_with_epi=500.0,
        common_mg_per_ml=(10.0, 20.0),
        evidence_ids=("EVID_LIDO_SMPC", "EVID_LOCAL_ANESTH_SAFETY"),
    ),
    LocalAnestheticAgent.articaine: LocalAnestheticRule(
        mg_per_kg_no_epi=7.0,
        max_mg_no_epi=500.0,
        mg_per_kg_with_epi=7.0,
        max_mg_with_epi=500.0,
        common_mg_per_ml=(40.0,),
        evidence_ids=("EVID_ARTI_SMPC",),
    ),
    LocalAnestheticAgent.bupivacaine: LocalAnestheticRule(
        mg_per_kg_no_epi=2.0,
        max_mg_no_epi=175.0,
        mg_per_kg_with_epi=3.0,
        max_mg_with_epi=225.0,
        common_mg_per_ml=(2.5, 5.0),
        evidence_ids=("EVID_BUPI_SMPC",),
    ),
    LocalAnestheticAgent.ropivacaine: LocalAnestheticRule(
        mg_per_kg_no_epi=3.0,
        max_mg_no_epi=200.0,
        mg_per_kg_with_epi=3.0,
        max_mg_with_epi=200.0,
        common_mg_per_ml=(2.0, 5.0, 7.5, 10.0),
        evidence_ids=("EVID_ROPI_SMPC",),
    ),
}


class LocalAnestheticDoseArgs(BaseModel):
    agent: LocalAnestheticAgent
    weight_kg: float = Field(..., gt=0, le=300)
    with_epinephrine: bool = False
    concentration_mg_per_ml: Optional[float] = Field(None, description="If omitted, returns table for common concentrations.")
    hepatic_impairment: bool = False
    cardiac_disease: bool = False
    elderly: bool = False
    pregnancy: bool = False

    @field_validator("weight_kg")
    @classmethod
    def _reasonable_weight(cls, v: float) -> float:
        return v


@router.post("/local-anesthetic/max-dose")
def local_anesthetic_max_dose(args: LocalAnestheticDoseArgs) -> ToolResult:
    """Calculate maximum safe dose of local anesthetic based on weight and risk factors."""
    name = "local_anesthetic_max_dose"
    rule = LOCAL_ANESTHETIC_RULES[args.agent]

    mg_per_kg = rule.mg_per_kg_with_epi if args.with_epinephrine else rule.mg_per_kg_no_epi
    cap_mg = rule.max_mg_with_epi if args.with_epinephrine else rule.max_mg_no_epi

    reduction = 1.0
    risk_flags = []
    if args.hepatic_impairment:
        reduction *= 0.7
        risk_flags.append("hepatic_impairment")
    if args.cardiac_disease:
        reduction *= 0.8
        risk_flags.append("cardiac_disease")
    if args.elderly:
        reduction *= 0.85
        risk_flags.append("elderly")
    if args.pregnancy:
        reduction *= 0.85
        risk_flags.append("pregnancy")

    calc_mg = mg_per_kg * args.weight_kg
    max_mg = min(calc_mg, cap_mg) * reduction

    warnings: List[str] = []
    if reduction < 1.0:
        warnings.append(f"Conservative reduction applied ({int((1-reduction)*100)}%): {', '.join(risk_flags)}.")
    warnings.append("Always aspirate, dose incrementally, and monitor for LAST (local anesthetic systemic toxicity).")
    warnings.append("If symptoms suggest LAST, follow your institutional lipid emulsion protocol and escalate care.")

    output: Dict[str, Any] = {
        "agent": args.agent.value,
        "with_epinephrine": args.with_epinephrine,
        "weight_kg": _round(args.weight_kg, 2),
        "mg_per_kg_reference": mg_per_kg,
        "absolute_cap_mg_reference": cap_mg,
        "computed_mg_before_cap": _round(calc_mg, 2),
        "max_recommended_total_mg": _round(max_mg, 2),
    }

    if args.concentration_mg_per_ml is not None:
        _require(args.concentration_mg_per_ml > 0, "concentration_mg_per_ml must be > 0", name=name)
        max_ml = max_mg / args.concentration_mg_per_ml
        output["concentration_mg_per_ml"] = args.concentration_mg_per_ml
        output["max_volume_ml"] = _round(max_ml, 2)
    else:
        table = []
        for c in rule.common_mg_per_ml:
            table.append({
                "concentration_mg_per_ml": c,
                "max_volume_ml": _round(max_mg / c, 2),
            })
        output["volume_table_common_concentrations"] = table

    evidence = [EvidenceItem(source_id=eid, label="Local anesthetic dosing reference", note=None) for eid in rule.evidence_ids]
    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: Epinephrine helper
# -----------------------------------------------------------------------------

class EpinephrineArgs(BaseModel):
    dilution: Optional[str] = Field(None, description="Examples: '1:100000', '1:200000'")
    concentration_mg_per_ml: Optional[float] = Field(None, gt=0)
    planned_volume_ml: Optional[float] = Field(None, gt=0)
    context: str = Field("local_anesthetic_admix")


def _parse_dilution(d: str) -> Optional[float]:
    d = d.strip().lower().replace(" ", "")
    if d.startswith("1:"):
        try:
            denom = float(d.split(":")[1].replace(",", ""))
            return 1.0 / (denom / 1000.0)
        except Exception:
            return None
    return None


@router.post("/epinephrine/helper")
def epinephrine_helper(args: EpinephrineArgs) -> ToolResult:
    """Calculate epinephrine dose from dilution/concentration."""
    name = "epinephrine_helper"
    warnings: List[str] = []
    evidence: List[EvidenceItem] = [
        EvidenceItem(source_id="EVID_EPI_LABELING", label="Epinephrine labeling / dilution conventions", note=None),
        EvidenceItem(source_id="EVID_ANAPHYLAXIS_GUIDANCE", label="Anaphylaxis emergency guidance", note=None),
    ]

    mg_per_ml = args.concentration_mg_per_ml
    if mg_per_ml is None and args.dilution:
        mg_per_ml = _parse_dilution(args.dilution)

    if mg_per_ml is None:
        return ToolResult(
            status=ToolStatus.refuse,
            name=name,
            refusals=["Provide dilution (e.g., 1:100000) or concentration_mg_per_ml to compute dose safely."],
            evidence=evidence,
        )

    output: Dict[str, Any] = {
        "context": args.context,
        "concentration_mg_per_ml": _round(mg_per_ml, 6),
        "concentration_mcg_per_ml": _round(mg_per_ml * 1000.0, 2),
        "common_dilutions_reference": [
            {"dilution": "1:1000", "mg_per_ml": 1.0, "mcg_per_ml": 1000.0},
            {"dilution": "1:10000", "mg_per_ml": 0.1, "mcg_per_ml": 100.0},
            {"dilution": "1:100000", "mg_per_ml": 0.01, "mcg_per_ml": 10.0},
            {"dilution": "1:200000", "mg_per_ml": 0.005, "mcg_per_ml": 5.0},
        ],
        "max_epinephrine_dose_guidance_mg": {
            "healthy_adult_commonly_cited": 0.2,
            "cardiac_disease_commonly_cited": 0.04,
        },
    }

    if args.planned_volume_ml is not None:
        total_mg = mg_per_ml * args.planned_volume_ml
        total_mcg = total_mg * 1000.0
        output["planned_volume_ml"] = _round(args.planned_volume_ml, 2)
        output["total_epinephrine_mg"] = _round(total_mg, 4)
        output["total_epinephrine_mcg"] = _round(total_mcg, 1)

        if total_mg > 0.2:
            warnings.append("Planned epinephrine amount exceeds 0.2 mg (commonly cited healthy adult threshold). Re-check.")
        if total_mg > 0.04:
            warnings.append("If cardiac disease is present, commonly cited max is 0.04 mg; consider heightened caution.")
    else:
        warnings.append("Add planned_volume_ml to compute total epinephrine dose.")

    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: Acetaminophen safety check
# -----------------------------------------------------------------------------

class AcetaminophenArgs(BaseModel):
    weight_kg: Optional[float] = Field(None, gt=0, le=300)
    total_daily_mg: float = Field(..., gt=0)
    chronic_alcohol_use: bool = False
    liver_disease: bool = False
    fasting_or_malnourished: bool = False


@router.post("/acetaminophen/safety")
def acetaminophen_safety(args: AcetaminophenArgs) -> ToolResult:
    """Check acetaminophen daily dose safety with risk factors."""
    name = "acetaminophen_safety"
    evidence = [EvidenceItem(source_id="EVID_ACET_LABELING", label="Acetaminophen labeling / safety guidance", note=None)]

    warnings: List[str] = []
    standard_max = 4000.0
    conservative_max = 3000.0

    high_risk = args.chronic_alcohol_use or args.liver_disease or args.fasting_or_malnourished
    max_allowed = conservative_max if high_risk else standard_max

    status = "within_limit" if args.total_daily_mg <= max_allowed else "exceeds_limit"
    output = {
        "total_daily_mg": _round(args.total_daily_mg, 0),
        "high_risk_factors": {
            "chronic_alcohol_use": args.chronic_alcohol_use,
            "liver_disease": args.liver_disease,
            "fasting_or_malnourished": args.fasting_or_malnourished,
        },
        "max_daily_mg_applied": max_allowed,
        "status": status,
        "notes": ["Include all sources of acetaminophen (combo cold/flu products)."],
    }

    if high_risk:
        warnings.append("High-risk factors present: conservative daily maximum applied.")
    if args.total_daily_mg > max_allowed:
        warnings.append("Daily total exceeds applied maximum; consider alternative analgesia or dose reduction.")
    if args.total_daily_mg > 6000:
        warnings.append("Markedly elevated daily dose; assess urgently for toxicity risk depending on timing/context.")

    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: Botulinum toxin dilution helper (multi-brand)
# -----------------------------------------------------------------------------

class ToxinBrand(str, Enum):
    onabotulinumtoxinA = "onabotulinumtoxinA"      # Botox
    incobotulinumtoxinA = "incobotulinumtoxinA"    # Xeomin
    abobotulinumtoxinA = "abobotulinumtoxinA"      # Dysport
    prabotulinumtoxinA = "prabotulinumtoxinA"      # Jeuveau
    daxibotulinumtoxinA = "daxibotulinumtoxinA"    # Daxxify


class ToxinDilutionArgs(BaseModel):
    brand: ToxinBrand
    vial_units: float = Field(..., gt=0, description="Units per vial (as labeled)")
    diluent_ml: float = Field(..., gt=0, description="Diluent volume added (mL)")
    report_units_per_0_1ml: bool = True


@router.post("/toxin/dilution")
def toxin_dilution(args: ToxinDilutionArgs) -> ToolResult:
    """Calculate botulinum toxin concentration after reconstitution."""
    name = "toxin_dilution"
    evidence = [EvidenceItem(source_id="EVID_TOXIN_LABELING", label="Botulinum toxin labeling / reconstitution", note=None)]
    
    units_per_ml = args.vial_units / args.diluent_ml
    output = {
        "brand": args.brand.value,
        "vial_units": args.vial_units,
        "diluent_ml": args.diluent_ml,
        "units_per_ml": _round(units_per_ml, 3),
    }
    if args.report_units_per_0_1ml:
        output["units_per_0_1ml"] = _round(units_per_ml * 0.1, 3)

    warnings = [
        "Units are product-specific and NOT interchangeable across brands.",
        "Follow labeling for storage, stability, and technique.",
    ]
    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: Vascular occlusion emergency checklist (filler)
# -----------------------------------------------------------------------------

class VascularOcclusionArgs(BaseModel):
    suspected: bool = True
    area: Optional[str] = Field(None, description="e.g. nose, nasolabial fold, glabella, lips")
    visual_symptoms_present: bool = False
    pain_out_of_proportion: bool = False


@router.post("/vascular-occlusion/checklist")
def vascular_occlusion_checklist(args: VascularOcclusionArgs) -> ToolResult:
    """Emergency checklist for suspected filler-induced vascular occlusion."""
    name = "vascular_occlusion_checklist"
    evidence = [EvidenceItem(source_id="EVID_Filler_VO_Guideline", label="Dermal filler vascular occlusion guideline", note=None)]

    if not args.suspected:
        return ToolResult(
            status=ToolStatus.refuse,
            name=name,
            refusals=["Checklist is intended for suspected occlusion; set suspected=true if clinically relevant."],
            evidence=evidence,
        )

    output = {
        "area": args.area,
        "red_flags": {
            "visual_symptoms_present": args.visual_symptoms_present,
            "pain_out_of_proportion": args.pain_out_of_proportion,
        },
        "immediate_actions_checklist": [
            "STOP injection immediately.",
            "Assess capillary refill, skin color changes (blanching/livedo), pain, and vision symptoms.",
            "If any visual symptoms: treat as emergency and arrange urgent ophthalmology/ED per protocol.",
            "Consider warm compresses and gentle massage per protocol (avoid delaying definitive measures).",
            "Prepare hyaluronidase protocol if HA filler suspected; follow locally approved dosing/technique.",
            "Escalate care if progression or uncertainty; document time of onset and steps taken.",
        ],
        "documentation_prompts": [
            "Record product, lot, amount injected, site(s), time(s), symptoms onset, photos if appropriate.",
            "Record who was contacted (ED/ophthalmology) and timing.",
        ],
        "notes": ["This tool intentionally avoids numeric dosing. Bind your local protocol as evidence for dosing specifics."],
    }

    warnings = [
        "Time-critical complication: follow your clinic's emergency protocol and local guidelines.",
        "If ocular symptoms occur, do not delay emergency escalation.",
    ]
    
    if args.visual_symptoms_present:
        warnings.insert(0, "URGENT: Visual symptoms present - this is an ophthalmologic emergency!")
        
    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: HSV prophylaxis suggestion
# -----------------------------------------------------------------------------

class HSVProphylaxisArgs(BaseModel):
    procedure: str = Field(..., description="e.g., laser_resurfacing, deep_peel, lip_filler")
    history_of_hsv: bool = True
    immunosuppressed: bool = False
    regimens_enabled: bool = Field(False, description="Set true only if vetted regimens + evidence sources configured.")


@router.post("/hsv-prophylaxis/check")
def hsv_prophylaxis(args: HSVProphylaxisArgs) -> ToolResult:
    """Check HSV prophylaxis recommendation for aesthetic procedures."""
    name = "hsv_prophylaxis"
    evidence = [EvidenceItem(source_id="EVID_HSV_AESTHETIC_GUIDANCE", label="HSV prophylaxis guidance (aesthetic procedures)", note=None)]

    if not args.history_of_hsv:
        return ToolResult(
            status=ToolStatus.ok,
            name=name,
            output={"recommended": False, "reason": "No HSV history indicated; assess clinician judgment and risk factors."},
            evidence=evidence,
        )

    if not args.regimens_enabled:
        return ToolResult(
            status=ToolStatus.refuse,
            name=name,
            refusals=["HSV prophylaxis regimens are not enabled in this deployment. Enable only after binding vetted dosing protocols with primary evidence."],
            evidence=evidence,
        )

    output = {
        "recommended": True,
        "procedure": args.procedure,
        "risk_modifiers": {"immunosuppressed": args.immunosuppressed},
        "regimen_options": [
            {"drug": "valacyclovir", "schedule": "CONFIG_REQUIRED", "note": "Bind exact dosing + duration to your local protocol evidence."},
            {"drug": "acyclovir", "schedule": "CONFIG_REQUIRED", "note": "Bind exact dosing + duration to your local protocol evidence."},
        ],
    }
    warnings = ["Use only regimens supported by your local protocol, renal function, and contraindications."]
    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: Contraindication / risk flagger
# -----------------------------------------------------------------------------

class RiskFlagArgs(BaseModel):
    procedure: str = Field(..., description="e.g., filler, botox, laser, peel, threads")
    pregnant: bool = False
    breastfeeding: bool = False
    anticoagulant_or_antiplatelet: bool = False
    isotretinoin_within_6_months: bool = False
    active_infection_at_site: bool = False
    history_keloid: bool = False
    autoimmune_disease: bool = False
    immunosuppressed: bool = False
    uncontrolled_diabetes: bool = False
    allergy_lidocaine: bool = False
    allergy_hyaluronidase: bool = False


@router.post("/risk-flags/check")
def aesthetic_risk_flags(args: RiskFlagArgs) -> ToolResult:
    """Check contraindications and risk factors for aesthetic procedures."""
    name = "aesthetic_risk_flags"
    evidence = [EvidenceItem(source_id="EVID_AESTHETIC_CONTRAINDICATIONS", label="Aesthetic procedure contraindications guidance", note=None)]

    flags = []
    cautions = []
    
    if args.active_infection_at_site:
        flags.append({"flag": "active_infection_at_site", "severity": "contraindication", "note": "Defer procedure until resolved."})
    if args.pregnant:
        flags.append({"flag": "pregnant", "severity": "contraindication", "note": "Most aesthetic procedures avoided during pregnancy."})
    if args.breastfeeding:
        cautions.append({"flag": "breastfeeding", "severity": "caution", "note": "Discuss risks; some procedures may be deferred."})
    if args.anticoagulant_or_antiplatelet:
        cautions.append({"flag": "anticoagulant_or_antiplatelet", "severity": "caution", "note": "Increased bruising risk; consider timing/liaison with prescriber."})
    if args.isotretinoin_within_6_months:
        flags.append({"flag": "isotretinoin_within_6_months", "severity": "contraindication", "note": "Wait 6-12 months post-isotretinoin for resurfacing/ablative procedures."})
    if args.history_keloid:
        cautions.append({"flag": "history_keloid", "severity": "caution", "note": "Increased risk of abnormal scarring; informed consent essential."})
    if args.autoimmune_disease:
        cautions.append({"flag": "autoimmune_disease", "severity": "caution", "note": "May affect healing; consider specialist consultation."})
    if args.immunosuppressed:
        cautions.append({"flag": "immunosuppressed", "severity": "caution", "note": "Increased infection risk; heightened vigilance."})
    if args.uncontrolled_diabetes:
        cautions.append({"flag": "uncontrolled_diabetes", "severity": "caution", "note": "Impaired healing; optimize control before procedure."})
    if args.allergy_lidocaine:
        flags.append({"flag": "allergy_lidocaine", "severity": "contraindication", "note": "Avoid lidocaine; use alternative anesthesia."})
    if args.allergy_hyaluronidase:
        cautions.append({"flag": "allergy_hyaluronidase", "severity": "caution", "note": "Emergency reversal of HA filler may be limited."})

    output = {
        "procedure": args.procedure,
        "contraindications": flags,
        "cautions": cautions,
        "clear_to_proceed": len(flags) == 0,
    }

    warnings = []
    if flags:
        warnings.append(f"{len(flags)} contraindication(s) identified. Review before proceeding.")
    if cautions:
        warnings.append(f"{len(cautions)} caution(s) identified. Consider informed consent discussion.")

    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Tool: Hyaluronidase dosing guidance (emergency reversal)
# -----------------------------------------------------------------------------

class HyaluronidaseArgs(BaseModel):
    indication: str = Field("filler_reversal", description="filler_reversal or vascular_occlusion")
    filler_volume_ml: Optional[float] = Field(None, gt=0)
    area: Optional[str] = Field(None, description="e.g., lips, nasolabial fold, glabella")


@router.post("/hyaluronidase/guidance")
def hyaluronidase_guidance(args: HyaluronidaseArgs) -> ToolResult:
    """Guidance for hyaluronidase use in filler reversal/vascular occlusion."""
    name = "hyaluronidase_guidance"
    evidence = [
        EvidenceItem(source_id="EVID_HYALURONIDASE_GUIDANCE", label="Hyaluronidase dosing and technique guidance", note=None),
        EvidenceItem(source_id="EVID_Filler_VO_Guideline", label="Vascular occlusion emergency protocol", note=None),
    ]

    warnings = []
    output: Dict[str, Any] = {
        "indication": args.indication,
        "area": args.area,
        "general_principles": [
            "Test dose recommended if history of allergy uncertain.",
            "Dilution varies by protocol; typical: 150-1500 units per vial reconstituted in 1-10 mL saline.",
            "Inject into and around the filler deposit.",
            "Massage gently post-injection to distribute.",
        ],
    }

    if args.indication == "vascular_occlusion":
        output["urgency"] = "EMERGENCY"
        output["guidance"] = [
            "In vascular occlusion, early and generous dosing is often recommended.",
            "Consider 200-600+ units in affected area, repeated as needed.",
            "Do not delay for patch test in true emergency.",
            "Escalate to ophthalmology/ED if visual symptoms present.",
        ]
        warnings.append("URGENT: Vascular occlusion requires immediate action. Follow your institutional emergency protocol.")
    else:
        output["guidance"] = [
            "For cosmetic reversal, lower doses may suffice (20-150 units depending on volume).",
            "Assess after 24-48 hours; repeat if needed.",
        ]

    if args.filler_volume_ml:
        output["filler_volume_ml"] = args.filler_volume_ml
        output["estimated_units_range"] = f"{int(args.filler_volume_ml * 30)}-{int(args.filler_volume_ml * 150)} units (rough estimate)"
        warnings.append("Dosing estimates are approximate; adjust based on clinical response and local protocols.")

    warnings.append("Bind local protocol and product labeling for specific dosing.")
    return ToolResult(status=ToolStatus.ok, name=name, output=output, warnings=warnings, evidence=evidence)


# -----------------------------------------------------------------------------
# Unified tool executor
# -----------------------------------------------------------------------------

class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)


TOOL_MAP = {
    "local_anesthetic_max_dose": (LocalAnestheticDoseArgs, local_anesthetic_max_dose),
    "epinephrine_helper": (EpinephrineArgs, epinephrine_helper),
    "acetaminophen_safety": (AcetaminophenArgs, acetaminophen_safety),
    "toxin_dilution": (ToxinDilutionArgs, toxin_dilution),
    "vascular_occlusion_checklist": (VascularOcclusionArgs, vascular_occlusion_checklist),
    "hsv_prophylaxis": (HSVProphylaxisArgs, hsv_prophylaxis),
    "aesthetic_risk_flags": (RiskFlagArgs, aesthetic_risk_flags),
    "hyaluronidase_guidance": (HyaluronidaseArgs, hyaluronidase_guidance),
}


@router.post("/execute")
def execute_tool(call: ToolCall) -> Dict[str, Any]:
    """Execute any aesthetic tool by name."""
    if call.name not in TOOL_MAP:
        raise HTTPException(status_code=404, detail=f"Tool '{call.name}' not found. Available: {list(TOOL_MAP.keys())}")
    
    args_cls, fn = TOOL_MAP[call.name]
    try:
        args = args_cls(**call.args)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid args for '{call.name}': {str(e)}")
    
    result = fn(args)
    return result.model_dump()


@router.get("/list")
def list_tools() -> Dict[str, Any]:
    """List all available aesthetic medicine tools."""
    return {
        "tools": [
            {"name": "local_anesthetic_max_dose", "description": "Calculate max safe dose of local anesthetics with risk adjustments"},
            {"name": "epinephrine_helper", "description": "Convert epinephrine dilutions and calculate total dose"},
            {"name": "acetaminophen_safety", "description": "Check acetaminophen daily dose safety"},
            {"name": "toxin_dilution", "description": "Calculate botulinum toxin concentration after reconstitution"},
            {"name": "vascular_occlusion_checklist", "description": "Emergency checklist for filler-induced vascular occlusion"},
            {"name": "hsv_prophylaxis", "description": "HSV prophylaxis recommendation check"},
            {"name": "aesthetic_risk_flags", "description": "Check contraindications and risk factors for procedures"},
            {"name": "hyaluronidase_guidance", "description": "Guidance for hyaluronidase use in filler reversal"},
        ]
    }
