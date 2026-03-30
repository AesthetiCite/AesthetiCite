"""
AesthetiCite — Clinical State ORM Models
app/models/clinical_state.py

Covers all 15 tables in the clinical safety state schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean, ForeignKey, Integer, Numeric, String, Text,
    TIMESTAMP, ARRAY, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    cases: Mapped[List["CaseSession"]] = relationship("CaseSession", back_populates="clinic")


class ProtocolDefinition(Base):
    __tablename__ = "protocol_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    condition_code: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    applicable_when: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    contraindications: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    required_inputs: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(String, nullable=False, default="internal_draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    step_definitions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("condition_code", "version"),)

    runs: Mapped[List["ProtocolRun"]] = relationship("ProtocolRun", back_populates="protocol_definition")


class CaseSession(Base):
    __tablename__ = "case_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True)
    chief_concern: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    mode: Mapped[str] = mapped_column(String, nullable=False, default="acute_complication")
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    clinic: Mapped[Optional["Clinic"]] = relationship("Clinic", back_populates="cases")
    patient_context: Mapped[Optional["PatientContext"]] = relationship("PatientContext", back_populates="case", uselist=False)
    procedure_context: Mapped[Optional["ProcedureContext"]] = relationship("ProcedureContext", back_populates="case", uselist=False)
    state_snapshots: Mapped[List["ClinicalStateSnapshot"]] = relationship("ClinicalStateSnapshot", back_populates="case")
    impressions: Mapped[List["ClinicalImpression"]] = relationship("ClinicalImpression", back_populates="case")
    protocol_runs: Mapped[List["ProtocolRun"]] = relationship("ProtocolRun", back_populates="case")
    interventions: Mapped[List["InterventionEvent"]] = relationship("InterventionEvent", back_populates="case")
    reassessments: Mapped[List["ReassessmentEvent"]] = relationship("ReassessmentEvent", back_populates="case")
    dispositions: Mapped[List["DispositionPlan"]] = relationship("DispositionPlan", back_populates="case")
    audit_events: Mapped[List["AuditEvent"]] = relationship("AuditEvent", back_populates="case")
    evidence_bundles: Mapped[List["EvidenceBundle"]] = relationship("EvidenceBundle", back_populates="case")
    documentation_bundles: Mapped[List["DocumentationBundle"]] = relationship("DocumentationBundle", back_populates="case")


class PatientContext(Base):
    __tablename__ = "patient_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    patient_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sex: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pregnancy_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    consent_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # New canonical columns
    known_allergies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    relevant_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    current_medications: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Legacy columns (kept for backward compat)
    medical_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    medications: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    allergies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="patient_context")


class ProcedureContext(Base):
    __tablename__ = "procedure_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    procedure_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    treatment_date_time: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    operator_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    anatomical_areas: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    products_used: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    technique: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    procedure_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Legacy columns
    injection_technique: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    estimated_total_volume_ml: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    time_since_injection_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="procedure_context")


class ClinicalStateSnapshot(Base):
    __tablename__ = "clinical_state_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    phase: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    time_since_procedure_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # New canonical columns
    symptoms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    vital_signs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    visual_symptoms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    photos_attached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    free_text_observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    airway_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    red_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Legacy columns
    vitals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recorded_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="state_snapshots")
    impressions: Mapped[List["ClinicalImpression"]] = relationship("ClinicalImpression", back_populates="derived_from_state")


class ClinicalImpression(Base):
    __tablename__ = "clinical_impressions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    derived_from_state_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_state_snapshots.id", ondelete="SET NULL"), nullable=True)
    primary_diagnosis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    differentials: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    severity_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    severity_rationale: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    needs_immediate_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vision_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anaphylaxis_probability: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    # Legacy columns
    differential_diagnoses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    generated_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="impressions")
    derived_from_state: Mapped[Optional["ClinicalStateSnapshot"]] = relationship("ClinicalStateSnapshot", back_populates="impressions")


class ProtocolRun(Base):
    __tablename__ = "protocol_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    protocol_id: Mapped[str] = mapped_column(String, ForeignKey("protocol_definitions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="in_progress")
    current_step_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=1)
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="protocol_runs")
    protocol_definition: Mapped["ProtocolDefinition"] = relationship("ProtocolDefinition", back_populates="runs")
    steps: Mapped[List["ProtocolRunStep"]] = relationship("ProtocolRunStep", back_populates="run", order_by="ProtocolRunStep.step_order")


class ProtocolRunStep(Base):
    __tablename__ = "protocol_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("protocol_runs.id", ondelete="CASCADE"), nullable=False)
    step_code: Mapped[str] = mapped_column(String, nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    performed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dose_support: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    run: Mapped["ProtocolRun"] = relationship("ProtocolRun", back_populates="steps")
    interventions: Mapped[List["InterventionEvent"]] = relationship("InterventionEvent", back_populates="linked_run_step")


class InterventionEvent(Base):
    __tablename__ = "intervention_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    linked_run_step_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("protocol_run_steps.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    performed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    immediate_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Legacy columns
    drug_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dose_amount: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    dose_unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    route: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    anatomical_area: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="interventions")
    linked_run_step: Mapped[Optional["ProtocolRunStep"]] = relationship("ProtocolRunStep", back_populates="interventions")


class ReassessmentEvent(Base):
    __tablename__ = "reassessment_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    findings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    clinical_direction: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    recommended_next_action: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    next_reassessment_due_in_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_since_last_intervention_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Legacy
    performed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    performed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="reassessments")


class DispositionPlan(Base):
    __tablename__ = "disposition_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    disposition: Mapped[str] = mapped_column(String, nullable=False)
    escalation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followup_plan: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    patient_advice: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    owner: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decision_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    # Legacy
    escalation_target: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    follow_up_instructions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decided_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="dispositions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    object_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    object_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="audit_events")


class EvidenceBundle(Base):
    __tablename__ = "evidence_bundles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    linked_to: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    claim: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_strength_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uncertainties: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Legacy
    query_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="evidence_bundles")


class DocumentationBundle(Base):
    __tablename__ = "documentation_bundles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_sessions.id", ondelete="CASCADE"), nullable=False)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    audit_trail_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    export_formats: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    case: Mapped["CaseSession"] = relationship("CaseSession", back_populates="documentation_bundles")
