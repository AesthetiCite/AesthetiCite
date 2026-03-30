"""
AesthetiCite — Clinical State Pydantic Schemas
app/schemas/clinical_state.py

Aligned with the v2 Clinical Safety State Engine spec.
All enum values match the DB TEXT columns (no strict DB enum type).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────

class CaseStatus(str, Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    closed = "closed"
    # legacy aliases accepted
    open = "open"
    escalated = "escalated"


class CaseMode(str, Enum):
    acute_complication = "acute_complication"
    pre_procedure_safety = "pre_procedure_safety"
    post_procedure_followup = "post_procedure_followup"
    # legacy aliases
    emergency = "emergency"
    standard = "standard"
    elective = "elective"
    training = "training"


class ClinicalPhase(str, Enum):
    intake = "intake"
    assessment = "assessment"
    intervention = "intervention"
    reassessment = "reassessment"
    disposition = "disposition"


class SeverityLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    critical = "critical"


class ProtocolRunStatus(str, Enum):
    in_progress = "in_progress"
    completed = "completed"
    aborted = "aborted"


class ProtocolStepStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    completed = "completed"
    skipped = "skipped"
    blocked = "blocked"


class InterventionCategory(str, Enum):
    assessment = "assessment"
    drug_administration = "drug_administration"
    escalation = "escalation"
    advice_given = "advice_given"
    referral = "referral"
    documentation = "documentation"
    observation = "observation"


class ClinicalDirection(str, Enum):
    improving = "improving"
    unchanged = "unchanged"
    worsening = "worsening"
    resolved = "resolved"


class DispositionType(str, Enum):
    managed_in_clinic_with_close_followup = "managed_in_clinic_with_close_followup"
    urgent_hospital_referral = "urgent_hospital_referral"
    ophthalmology_emergency_referral = "ophthalmology_emergency_referral"
    ambulance_transfer = "ambulance_transfer"
    resolved_and_discharged = "resolved_and_discharged"


class ReviewStatus(str, Enum):
    internal_draft = "internal_draft"
    clinical_review = "clinical_review"
    approved = "approved"
    retired = "retired"


# ─────────────────────────────────────────
# NESTED VALUE OBJECTS
# ─────────────────────────────────────────

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Allergy(BaseModel):
    substance: str
    reaction: Optional[str] = None
    severity: Optional[str] = None


class ProductUsed(BaseModel):
    product_name: str
    category: Optional[str] = None
    lot_number: Optional[str] = None
    volume_ml: Optional[float] = None


class Technique(BaseModel):
    device: Optional[str] = None
    gauge: Optional[str] = None
    plane: Optional[str] = None
    bolus_or_linear: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class SymptomEntry(BaseModel):
    name: str
    present: bool
    severity: Optional[int] = Field(default=None, ge=0, le=10)
    onset: Optional[str] = None
    distribution: Optional[str] = None


class VitalSigns(BaseModel):
    heart_rate: Optional[int] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    spo2: Optional[float] = None
    temperature_c: Optional[float] = None
    model_config = ConfigDict(extra="allow")


class VisualSymptoms(BaseModel):
    present: Optional[bool] = None
    symptoms: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class DiagnosisCandidate(BaseModel):
    code: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class ProtocolStepDefinition(BaseModel):
    step_code: str
    step_order: int
    title: str
    action_type: Optional[str] = None
    criticality: Optional[str] = None


class DoseSupport(BaseModel):
    calculator_id: Optional[str] = None
    suggested_range_units: List[float] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class RecommendedNextAction(BaseModel):
    action_code: Optional[str] = None
    urgency: Optional[str] = None
    rationale: Optional[str] = None
    model_config = ConfigDict(extra="allow")


# ─────────────────────────────────────────
# CASE SESSION
# ─────────────────────────────────────────

class CaseSessionCreate(BaseModel):
    clinic_id: Optional[uuid.UUID] = None
    status: CaseStatus = CaseStatus.draft
    mode: CaseMode = CaseMode.acute_complication
    chief_concern: Optional[str] = None
    language: str = "en"
    country: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_by_user_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class CaseSessionUpdate(BaseModel):
    clinic_id: Optional[uuid.UUID] = None
    status: Optional[CaseStatus] = None
    mode: Optional[CaseMode] = None
    chief_concern: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class CaseSessionRead(ORMModel):
    id: uuid.UUID
    clinic_id: Optional[uuid.UUID] = None
    chief_concern: Optional[str] = None
    status: str
    mode: str
    language: str = "en"
    country: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_by_user_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────
# PATIENT CONTEXT
# ─────────────────────────────────────────

class PatientContextCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    patient_ref: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0)
    sex: Optional[str] = None
    pregnancy_status: Optional[str] = None
    weight_kg: Optional[float] = None
    consent_status: Optional[str] = None
    known_allergies: List[Allergy] = Field(default_factory=list)
    relevant_history: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)


class PatientContextUpdate(BaseModel):
    patient_ref: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0)
    sex: Optional[str] = None
    pregnancy_status: Optional[str] = None
    weight_kg: Optional[float] = None
    consent_status: Optional[str] = None
    known_allergies: Optional[List[Allergy]] = None
    relevant_history: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None
    risk_flags: Optional[List[str]] = None


class PatientContextRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    patient_ref: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    pregnancy_status: Optional[str] = None
    weight_kg: Optional[float] = None
    consent_status: Optional[str] = None
    known_allergies: List[Any] = Field(default_factory=list)
    relevant_history: List[Any] = Field(default_factory=list)
    current_medications: List[Any] = Field(default_factory=list)
    risk_flags: List[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────
# PROCEDURE CONTEXT
# ─────────────────────────────────────────

class ProcedureContextCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    procedure_type: Optional[str] = None
    subtype: Optional[str] = None
    treatment_date_time: Optional[datetime] = None
    operator_role: Optional[str] = None
    anatomical_areas: List[str] = Field(default_factory=list)
    products_used: List[ProductUsed] = Field(default_factory=list)
    technique: Optional[Technique] = None
    procedure_notes: Optional[str] = None


class ProcedureContextUpdate(BaseModel):
    procedure_type: Optional[str] = None
    subtype: Optional[str] = None
    treatment_date_time: Optional[datetime] = None
    operator_role: Optional[str] = None
    anatomical_areas: Optional[List[str]] = None
    products_used: Optional[List[ProductUsed]] = None
    technique: Optional[Technique] = None
    procedure_notes: Optional[str] = None


class ProcedureContextRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    procedure_type: Optional[str] = None
    subtype: Optional[str] = None
    treatment_date_time: Optional[datetime] = None
    operator_role: Optional[str] = None
    anatomical_areas: List[str] = Field(default_factory=list)
    products_used: List[Any] = Field(default_factory=list)
    technique: Optional[Any] = None
    procedure_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────
# CLINICAL STATE SNAPSHOT
# ─────────────────────────────────────────

class ClinicalStateSnapshotCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    phase: Optional[ClinicalPhase] = None
    time_since_procedure_minutes: Optional[int] = None
    symptoms: List[SymptomEntry] = Field(default_factory=list)
    vital_signs: Optional[VitalSigns] = None
    red_flags: List[str] = Field(default_factory=list)
    airway_risk: bool = False
    visual_symptoms: Optional[VisualSymptoms] = None
    photos_attached: bool = False
    free_text_observations: Optional[str] = None
    recorded_by: Optional[str] = None


class ClinicalStateSnapshotRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    state_version: int
    phase: Optional[str] = None
    time_since_procedure_minutes: Optional[int] = None
    symptoms: List[Any] = Field(default_factory=list)
    vital_signs: Optional[Any] = None
    red_flags: List[str] = Field(default_factory=list)
    airway_risk: bool = False
    visual_symptoms: Optional[Any] = None
    photos_attached: bool = False
    free_text_observations: Optional[str] = None
    recorded_at: datetime
    created_at: datetime


# ─────────────────────────────────────────
# CLINICAL IMPRESSION
# ─────────────────────────────────────────

class ClinicalImpressionCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    derived_from_state_id: Optional[uuid.UUID] = None
    primary_diagnosis: DiagnosisCandidate
    differentials: List[DiagnosisCandidate] = Field(default_factory=list)
    severity_level: SeverityLevel = SeverityLevel.low
    severity_rationale: List[str] = Field(default_factory=list)
    vision_emergency: bool = False
    anaphylaxis_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    needs_immediate_action: bool = False
    generated_by: str = "system"
    reasoning: Optional[str] = None


class ClinicalImpressionRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    derived_from_state_id: Optional[uuid.UUID] = None
    primary_diagnosis: Dict[str, Any]
    differentials: List[Any] = Field(default_factory=list)
    severity_level: Optional[str] = None
    severity_rationale: List[str] = Field(default_factory=list)
    needs_immediate_action: bool = False
    vision_emergency: bool = False
    anaphylaxis_probability: Optional[float] = None
    generated_by: str = "system"
    reasoning: Optional[str] = None
    generated_at: datetime
    created_at: datetime


# ─────────────────────────────────────────
# PROTOCOL RUN
# ─────────────────────────────────────────

class ProtocolRunCreate(BaseModel):
    protocol_id: str


class ProtocolRunUpdate(BaseModel):
    status: Optional[ProtocolRunStatus] = None
    current_step_order: Optional[int] = None
    completed_at: Optional[datetime] = None
    outcome_notes: Optional[str] = None


class ProtocolRunRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    protocol_id: str
    status: str
    current_step_order: Optional[int] = None
    outcome_notes: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ─────────────────────────────────────────
# PROTOCOL RUN STEP
# ─────────────────────────────────────────

class ProtocolRunStepUpdate(BaseModel):
    status: Optional[ProtocolStepStatus] = None
    performed_by: Optional[str] = None
    notes: Optional[str] = None
    dose_support: Optional[DoseSupport] = None
    completed_at: Optional[datetime] = None


class ProtocolRunStepRead(ORMModel):
    id: uuid.UUID
    protocol_run_id: uuid.UUID
    step_code: str
    step_order: int
    title: str
    status: str
    performed_by: Optional[str] = None
    notes: Optional[str] = None
    dose_support: Optional[Any] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ─────────────────────────────────────────
# INTERVENTION EVENT
# ─────────────────────────────────────────

class InterventionEventCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    linked_run_step_id: Optional[uuid.UUID] = None
    category: InterventionCategory
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)
    performed_by: Optional[str] = None
    immediate_response: Optional[str] = None


class InterventionEventRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    linked_run_step_id: Optional[uuid.UUID] = None
    category: str
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)
    performed_by: Optional[str] = None
    immediate_response: Optional[str] = None
    performed_at: datetime
    created_at: datetime


# ─────────────────────────────────────────
# REASSESSMENT EVENT
# ─────────────────────────────────────────

class ReassessmentEventCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    findings: Dict[str, Any] = Field(default_factory=dict)
    clinical_direction: ClinicalDirection = ClinicalDirection.unchanged
    recommended_next_action: Optional[RecommendedNextAction] = None
    next_reassessment_due_in_minutes: Optional[int] = None
    time_since_last_intervention_minutes: Optional[int] = None
    performed_by: Optional[str] = None


class ReassessmentEventRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    findings: Dict[str, Any] = Field(default_factory=dict)
    clinical_direction: Optional[str] = None
    recommended_next_action: Optional[Any] = None
    next_reassessment_due_in_minutes: Optional[int] = None
    time_since_last_intervention_minutes: Optional[int] = None
    performed_by: Optional[str] = None
    performed_at: datetime
    created_at: datetime


# ─────────────────────────────────────────
# DISPOSITION PLAN
# ─────────────────────────────────────────

class DispositionPlanCreate(BaseModel):
    case_id: Optional[uuid.UUID] = None
    disposition: DispositionType
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    followup_plan: List[str] = Field(default_factory=list)
    patient_advice: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    decided_by: Optional[str] = None


class DispositionPlanRead(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    disposition: str
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    followup_plan: List[str] = Field(default_factory=list)
    patient_advice: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    decided_by: Optional[str] = None
    decision_time: datetime
    created_at: datetime


# ─────────────────────────────────────────
# LIVE VIEW SCHEMAS
# ─────────────────────────────────────────

class CaseHeaderLive(BaseModel):
    case_id: uuid.UUID
    chief_concern: Optional[str] = None
    status: str
    severity: Optional[str] = None


class PatientSummaryLive(BaseModel):
    age: Optional[int] = None
    risk_flags: List[Any] = Field(default_factory=list)


class ProcedureSummaryLive(BaseModel):
    procedure_type: Optional[str] = None
    area: List[str] = Field(default_factory=list)
    product: List[str] = Field(default_factory=list)


class CurrentImpressionLive(BaseModel):
    primary_diagnosis: Optional[str] = None
    confidence: Optional[float] = None
    needs_immediate_action: Optional[bool] = None


class CurrentProtocolLive(BaseModel):
    title: Optional[str] = None
    current_step_order: Optional[int] = None
    next_step: Optional[str] = None


class TimersLive(BaseModel):
    minutes_since_procedure: Optional[int] = None
    next_reassessment_due_in_minutes: Optional[int] = None


class AlertItemLive(BaseModel):
    type: str
    message: str


class EvidenceSummaryLive(BaseModel):
    aci_score: Optional[Any] = None
    confidence_label: Optional[str] = None
    top_sources: List[str] = Field(default_factory=list)


class CaseLiveView(BaseModel):
    case_header: CaseHeaderLive
    patient_summary: Optional[PatientSummaryLive] = None
    procedure_summary: Optional[ProcedureSummaryLive] = None
    current_impression: Optional[CurrentImpressionLive] = None
    current_protocol: Optional[CurrentProtocolLive] = None
    timers: TimersLive = Field(default_factory=TimersLive)
    alerts: List[AlertItemLive] = Field(default_factory=list)
    evidence_summary: Optional[EvidenceSummaryLive] = None
