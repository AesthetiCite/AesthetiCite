"""
AesthetiCite — Live View Builder Service
app/services/live_view_service.py

Assembles a CaseLiveView from all child tables in a single async pass.
Designed for the GET /cases/{case_id}/live-view endpoint.
All queries run as individual selects rather than one giant join,
keeping the logic readable and each piece independently cacheable.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.clinical_state import (
    CaseSession,
    PatientContext,
    ProcedureContext,
    ClinicalStateSnapshot,
    ClinicalImpression,
    ProtocolRun,
    ProtocolRunStep,
    ReassessmentEvent,
    EvidenceBundle,
)
from app.schemas.clinical_state import (
    CaseLiveView,
    CaseHeaderLive,
    PatientSummaryLive,
    ProcedureSummaryLive,
    CurrentImpressionLive,
    CurrentProtocolLive,
    TimersLive,
    AlertItemLive,
    EvidenceSummaryLive,
)

logger = logging.getLogger(__name__)


async def build_live_view(db: AsyncSession, case_id: UUID) -> CaseLiveView:
    """
    Builds a complete CaseLiveView for the given case_id.
    Returns a structured snapshot suitable for the live complication view UI.
    """

    # ── 1. Case header ──────────────────────────────────────────────────────
    case_result = await db.execute(
        select(CaseSession).where(CaseSession.id == case_id)
    )
    case = case_result.scalar_one_or_none()
    if not case:
        raise ValueError(f"Case {case_id} not found")

    # ── 2. Latest clinical impression ────────────────────────────────────────
    impression_result = await db.execute(
        select(ClinicalImpression)
        .where(ClinicalImpression.case_id == case_id)
        .order_by(ClinicalImpression.generated_at.desc())
        .limit(1)
    )
    impression: Optional[ClinicalImpression] = impression_result.scalar_one_or_none()

    # ── 3. Patient context ───────────────────────────────────────────────────
    patient_result = await db.execute(
        select(PatientContext).where(PatientContext.case_id == case_id)
    )
    patient: Optional[PatientContext] = patient_result.scalar_one_or_none()

    # ── 4. Procedure context ─────────────────────────────────────────────────
    procedure_result = await db.execute(
        select(ProcedureContext).where(ProcedureContext.case_id == case_id)
    )
    procedure: Optional[ProcedureContext] = procedure_result.scalar_one_or_none()

    # ── 5. Latest state snapshot (for timers) ────────────────────────────────
    state_result = await db.execute(
        select(ClinicalStateSnapshot)
        .where(ClinicalStateSnapshot.case_id == case_id)
        .order_by(ClinicalStateSnapshot.state_version.desc())
        .limit(1)
    )
    latest_state: Optional[ClinicalStateSnapshot] = state_result.scalar_one_or_none()

    # ── 6. Active protocol run ───────────────────────────────────────────────
    run_result = await db.execute(
        select(ProtocolRun)
        .where(
            ProtocolRun.case_id == case_id,
            ProtocolRun.status == "in_progress",
        )
        .order_by(ProtocolRun.started_at.desc())
        .limit(1)
    )
    active_run: Optional[ProtocolRun] = run_result.scalar_one_or_none()

    next_step_title: Optional[str] = None
    if active_run and active_run.current_step_order:
        next_step_result = await db.execute(
            select(ProtocolRunStep)
            .where(
                ProtocolRunStep.protocol_run_id == active_run.id,
                ProtocolRunStep.step_order == active_run.current_step_order,
                ProtocolRunStep.status == "ready",
            )
            .limit(1)
        )
        next_step = next_step_result.scalar_one_or_none()
        if next_step:
            next_step_title = next_step.title

    # ── 7. Latest reassessment (for next reassessment timer) ─────────────────
    reassess_result = await db.execute(
        select(ReassessmentEvent)
        .where(ReassessmentEvent.case_id == case_id)
        .order_by(ReassessmentEvent.performed_at.desc())
        .limit(1)
    )
    latest_reassessment: Optional[ReassessmentEvent] = reassess_result.scalar_one_or_none()

    # ── 8. Latest evidence bundle ────────────────────────────────────────────
    evidence_result = await db.execute(
        select(EvidenceBundle)
        .where(EvidenceBundle.case_id == case_id)
        .order_by(EvidenceBundle.created_at.desc())
        .limit(1)
    )
    evidence: Optional[EvidenceBundle] = evidence_result.scalar_one_or_none()

    # ── 9. Build alerts ──────────────────────────────────────────────────────
    alerts: list[AlertItemLive] = []

    if impression:
        if impression.vision_emergency:
            alerts.append(AlertItemLive(
                type="critical",
                message="⚠ Vision emergency suspected — ophthalmology referral required immediately",
            ))
        if impression.needs_immediate_action:
            alerts.append(AlertItemLive(
                type="urgent",
                message="Immediate action required — follow active protocol",
            ))
        if impression.anaphylaxis_probability and impression.anaphylaxis_probability >= 0.7:
            alerts.append(AlertItemLive(
                type="critical",
                message=f"Anaphylaxis probability: {impression.anaphylaxis_probability:.0%} — administer adrenaline",
            ))

    if latest_state:
        if latest_state.airway_risk:
            alerts.append(AlertItemLive(
                type="critical",
                message="Airway risk flagged — monitor and prepare for escalation",
            ))
        for flag in (latest_state.red_flags or []):
            alerts.append(AlertItemLive(type="warning", message=flag))

    # ── 10. Assemble ─────────────────────────────────────────────────────────
    return CaseLiveView(
        case_header=CaseHeaderLive(
            case_id=case.id,
            chief_concern=case.chief_concern,
            status=case.status,
            severity=impression.severity_level if impression else None,
        ),
        patient_summary=PatientSummaryLive(
            age=patient.age if patient else None,
            risk_flags=list(patient.risk_flags) if patient else [],
        ) if patient else None,
        procedure_summary=ProcedureSummaryLive(
            procedure_type=procedure.procedure_type if procedure else None,
            area=list(procedure.anatomical_areas) if procedure else [],
            product=[
                p.get("product_name", "") for p in (procedure.products_used or [])
            ] if procedure else [],
        ) if procedure else None,
        current_impression=CurrentImpressionLive(
            primary_diagnosis=impression.primary_diagnosis.get("label") if impression else None,
            confidence=impression.primary_diagnosis.get("confidence") if impression else None,
            needs_immediate_action=impression.needs_immediate_action if impression else None,
        ) if impression else None,
        current_protocol=CurrentProtocolLive(
            title=active_run.protocol_id if active_run else None,
            current_step_order=active_run.current_step_order if active_run else None,
            next_step=next_step_title,
        ) if active_run else None,
        timers=TimersLive(
            minutes_since_procedure=(
                latest_state.time_since_procedure_minutes if latest_state else None
            ),
            next_reassessment_due_in_minutes=(
                latest_reassessment.next_reassessment_due_in_minutes
                if latest_reassessment else None
            ),
        ),
        alerts=alerts,
        evidence_summary=EvidenceSummaryLive(
            aci_score=evidence.evidence_strength_summary.get("aci_score") if evidence else None,
            confidence_label=evidence.evidence_strength_summary.get("confidence_label") if evidence else None,
            top_sources=[
                item.get("citation_label", "")
                for item in (evidence.evidence_items or [])[:3]
            ] if evidence else [],
        ) if evidence else None,
    )
