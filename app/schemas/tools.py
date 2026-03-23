from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any, Union

# -------- Interactions --------
class InteractionRequest(BaseModel):
    drugs: List[str] = Field(..., min_length=2, max_length=12)

class InteractionFinding(BaseModel):
    severity: Optional[str] = None
    description: str
    source: Optional[str] = None

class InteractionSummary(BaseModel):
    overall: str
    counts: Dict[str, int]


class InteractionResponse(BaseModel):
    ok: bool
    drugs: List[str]
    findings: List[InteractionFinding]
    disclaimer: str
    summary: Optional[InteractionSummary] = None

# -------- Core calculators --------
class BMIRequest(BaseModel):
    weight_kg: float = Field(..., gt=0)
    height_cm: float = Field(..., gt=0)

class BSARequest(BaseModel):
    weight_kg: float = Field(..., gt=0)
    height_cm: float = Field(..., gt=0)
    method: Literal["mosteller"] = "mosteller"

class CockcroftGaultRequest(BaseModel):
    age_years: int = Field(..., ge=1, le=120)
    weight_kg: float = Field(..., gt=0)
    serum_creatinine_mg_dl: float = Field(..., gt=0)
    sex: Literal["male", "female"]

class EgfrCkdEpi2021Request(BaseModel):
    age_years: int = Field(..., ge=1, le=120)
    serum_creatinine_mg_dl: float = Field(..., gt=0)
    sex: Literal["male", "female"]

# -------- Units / concentrations --------
class UnitConvertRequest(BaseModel):
    value: float
    from_unit: Literal["mcg", "mg", "g", "iu", "units", "ml", "l", "percent"]
    to_unit: Literal["mcg", "mg", "g", "iu", "units", "ml", "l", "percent"]

class ConcentrationRequest(BaseModel):
    amount_mg: Optional[float] = None
    volume_ml: Optional[float] = None
    percent: Optional[float] = None

class DilutionRequest(BaseModel):
    stock_value: float
    stock_unit: Literal["mg_per_ml", "units_per_ml"]
    desired_value: float
    desired_unit: Literal["mg_per_ml", "units_per_ml"]
    final_volume_ml: float = Field(..., gt=0)

# -------- Dosing math --------
class MgKgDoseRequest(BaseModel):
    dose_mg_per_kg: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)

class McgKgMinInfusionRequest(BaseModel):
    dose_mcg_per_kg_min: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    concentration_mcg_per_ml: float = Field(..., gt=0)

# -------- Botox tools --------
class BotoxReconstitutionRequest(BaseModel):
    vial_units: float = Field(..., gt=0)
    diluent_ml: float = Field(..., gt=0)

class BotoxSessionTotalRequest(BaseModel):
    injection_points_units: List[float] = Field(..., min_length=1, max_length=200)

# -------- Steroid equivalents --------
class SteroidEquivalentRequest(BaseModel):
    value_mg: float = Field(..., gt=0)
    from_steroid: Literal["prednisone", "methylprednisolone", "dexamethasone", "hydrocortisone"]
    to_steroid: Literal["prednisone", "methylprednisolone", "dexamethasone", "hydrocortisone"]

# -------- Evidence-locked rules --------
class CreateDosingRuleRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    category: str = Field(..., min_length=3, max_length=80)
    rule_json: Dict[str, Any]
    source_id: Optional[str] = None
    source_excerpt: Optional[str] = None

class DosingRuleOut(BaseModel):
    id: str
    name: str
    category: str
    rule_json: Dict[str, Any]
    source_id: Optional[str] = None
    source_excerpt: Optional[str] = None
    updated_at: Optional[str] = None

class EvidenceLockedRequest(BaseModel):
    rule_id: str
    weight_kg: float = Field(..., gt=0)
    with_epinephrine: Optional[bool] = None

# -------- Generic response --------
class GenericCalcResponse(BaseModel):
    ok: bool
    result: Union[float, str, Dict[str, Any]]
    unit: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    disclaimer: str
