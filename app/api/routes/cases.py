"""
AesthetiCite — Case & Protocol CRUD Routers
app/api/routes/cases.py

Covers:
  POST   /cases
  GET    /cases/{case_id}
  PATCH  /cases/{case_id}

  PUT    /cases/{case_id}/patient-context
  PUT    /cases/{case_id}/procedure-context

  POST   /cases/{case_id}/states
  POST   /cases/{case_id}/impressions

  POST   /cases/{case_id}/protocol-runs
  PATCH  /protocol-runs/{run_id}
  PATCH  /protocol-run-steps/{step_id}

  POST   /cases/{case_id}/interventions
  POST   /cases/{case_id}/reassessments
  POST   /cases/{case_id}/disposition

  GET    /cases/{case_id}/live-view

  GET    /protocols
  GET    /protocols/{protocol_id}
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update as sa_update

from app.db.session import get_async_db
from app.models.clinical_state import (
    CaseSession,
    PatientContext,
    ProcedureContext,
    ClinicalStateSnapshot,
    ClinicalImpression,
    ProtocolDefinition,
    ProtocolRun,
    ProtocolRunStep,
    InterventionEvent,
    ReassessmentEvent,
    DispositionPlan,
    AuditEvent,
)
from app.schemas.clinical_state import (
    CaseSessionCreate,
    CaseSessionRead,
    CaseSessionUpdate,
    PatientContextCreate,
    PatientContextRead,
    PatientContextUpdate,
    ProcedureContextCreate,
    ProcedureContextRead,
    ProcedureContextUpdate,
    ClinicalStateSnapshotCreate,
    ClinicalStateSnapshotRead,
    ClinicalImpressionCreate,
    ClinicalImpressionRead,
    ProtocolRunCreate,
    ProtocolRunRead,
    ProtocolRunUpdate,
    ProtocolRunStepUpdate,
    ProtocolRunStepRead,
    InterventionEventCreate,
    InterventionEventRead,
    ReassessmentEventCreate,
    ReassessmentEventRead,
    DispositionPlanCreate,
    DispositionPlanRead,
    CaseLiveView,
)
from app.services.live_view_service import build_live_view
from app.services.audit_service import log_audit_event
from app.services.protocol_engine import choose_protocol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clinical-cases", tags=["clinical-cases"])
protocol_router = APIRouter(prefix="/api", tags=["protocols"])


# ─────────────────────────────────────────
# DEPENDENCY: resolve case and verify ownership
# ─────────────────────────────────────────

async def get_case_or_404(
    case_id: UUID,
    db: AsyncSession = Depends(get_async_db),
) -> CaseSession:
    result = await db.execute(
        select(CaseSession).where(CaseSession.id == case_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


# ─────────────────────────────────────────
# CASES
# ─────────────────────────────────────────

@router.post("", response_model=CaseSessionRead, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseSessionCreate,
    db: AsyncSession = Depends(get_async_db),
):
    case = CaseSession(**payload.model_dump())
    db.add(case)
    await db.commit()
    await db.refresh(case)
    await log_audit_event(db, case.id, "system", "case_created", "case_session", str(case.id))
    await db.commit()
    return case


@router.get("", response_model=List[CaseSessionRead])
async def list_cases(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(CaseSession).order_by(CaseSession.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{case_id}", response_model=CaseSessionRead)
async def get_case(case: CaseSession = Depends(get_case_or_404)):
    return case


@router.patch("/{case_id}", response_model=CaseSessionRead)
async def update_case(
    payload: CaseSessionUpdate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(case, field, value)
    await db.commit()
    await db.refresh(case)
    await log_audit_event(db, case.id, "system", "case_updated", "case_session", str(case.id),
                          change_summary=str(list(update_data.keys())))
    await db.commit()
    return case


# ─────────────────────────────────────────
# PATIENT CONTEXT
# ─────────────────────────────────────────

@router.put("/{case_id}/patient-context", response_model=PatientContextRead)
async def upsert_patient_context(
    case_id: UUID,
    payload: PatientContextCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(PatientContext).where(PatientContext.case_id == case_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        for field, value in payload.model_dump(exclude={"case_id"}).items():
            setattr(existing, field, value)
        await db.commit()
        await db.refresh(existing)
        return existing

    patient_ctx = PatientContext(**{**payload.model_dump(), "case_id": case_id})
    db.add(patient_ctx)
    await db.commit()
    await db.refresh(patient_ctx)
    await log_audit_event(db, case_id, "system", "patient_context_upserted", "patient_context", str(patient_ctx.id))
    await db.commit()
    return patient_ctx


# ─────────────────────────────────────────
# PROCEDURE CONTEXT
# ─────────────────────────────────────────

@router.put("/{case_id}/procedure-context", response_model=ProcedureContextRead)
async def upsert_procedure_context(
    case_id: UUID,
    payload: ProcedureContextCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(ProcedureContext).where(ProcedureContext.case_id == case_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        for field, value in payload.model_dump(exclude={"case_id"}).items():
            setattr(existing, field, value)
        await db.commit()
        await db.refresh(existing)
        return existing

    proc_ctx = ProcedureContext(**{**payload.model_dump(), "case_id": case_id})
    db.add(proc_ctx)
    await db.commit()
    await db.refresh(proc_ctx)
    await log_audit_event(db, case_id, "system", "procedure_context_upserted", "procedure_context", str(proc_ctx.id))
    await db.commit()
    return proc_ctx


# ─────────────────────────────────────────
# CLINICAL STATE SNAPSHOTS
# Always append — never overwrite
# ─────────────────────────────────────────

@router.post("/{case_id}/states", response_model=ClinicalStateSnapshotRead, status_code=status.HTTP_201_CREATED)
async def append_clinical_state(
    case_id: UUID,
    payload: ClinicalStateSnapshotCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(ClinicalStateSnapshot.state_version)
        .where(ClinicalStateSnapshot.case_id == case_id)
        .order_by(ClinicalStateSnapshot.state_version.desc())
        .limit(1)
    )
    last_version = result.scalar_one_or_none() or 0

    data = payload.model_dump()
    data["case_id"] = case_id
    data["state_version"] = last_version + 1

    snapshot = ClinicalStateSnapshot(**data)
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    await log_audit_event(db, case_id, "system", "state_snapshot_appended",
                          "clinical_state_snapshot", str(snapshot.id),
                          change_summary=f"version={snapshot.state_version} phase={snapshot.phase}")
    await db.commit()
    return snapshot


# ─────────────────────────────────────────
# CLINICAL IMPRESSIONS
# ─────────────────────────────────────────

@router.post("/{case_id}/impressions", response_model=ClinicalImpressionRead, status_code=status.HTTP_201_CREATED)
async def create_impression(
    case_id: UUID,
    payload: ClinicalImpressionCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    data = payload.model_dump()
    data["case_id"] = case_id
    impression = ClinicalImpression(**data)
    db.add(impression)
    await db.commit()
    await db.refresh(impression)
    await log_audit_event(db, case_id, "system", "impression_created",
                          "clinical_impression", str(impression.id),
                          change_summary=f"severity={impression.severity_level}")
    await db.commit()
    return impression


# ─────────────────────────────────────────
# PROTOCOL RUNS
# ─────────────────────────────────────────

@router.post("/{case_id}/protocol-runs", response_model=ProtocolRunRead, status_code=status.HTTP_201_CREATED)
async def start_protocol_run(
    case_id: UUID,
    payload: ProtocolRunCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    protocol_result = await db.execute(
        select(ProtocolDefinition).where(ProtocolDefinition.id == payload.protocol_id)
    )
    protocol = protocol_result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail=f"Protocol {payload.protocol_id} not found")

    run = ProtocolRun(
        case_id=case_id,
        protocol_id=payload.protocol_id,
        status="in_progress",
        current_step_order=1,
    )
    db.add(run)
    await db.flush()

    for step_def in protocol.step_definitions:
        step = ProtocolRunStep(
            protocol_run_id=run.id,
            step_code=step_def["step_code"],
            step_order=step_def["step_order"],
            title=step_def["title"],
            status="pending" if step_def["step_order"] > 1 else "ready",
        )
        db.add(step)

    await db.commit()
    await db.refresh(run)
    await log_audit_event(db, case_id, "system", "protocol_run_started",
                          "protocol_run", str(run.id),
                          change_summary=f"protocol={payload.protocol_id}")
    await db.commit()
    return run


@router.post("/{case_id}/auto-start-protocol", response_model=ProtocolRunRead, status_code=status.HTTP_201_CREATED)
async def auto_start_protocol(
    case_id: UUID,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Inspects the latest procedure context and clinical state snapshot, feeds them
    to choose_protocol(), and starts the matched protocol run automatically.
    Returns 404 if no protocol matches the current clinical state.
    """
    # Fetch procedure context
    proc_result = await db.execute(
        select(ProcedureContext).where(ProcedureContext.case_id == case_id)
    )
    procedure: ProcedureContext | None = proc_result.scalar_one_or_none()

    # Fetch latest state snapshot
    state_result = await db.execute(
        select(ClinicalStateSnapshot)
        .where(ClinicalStateSnapshot.case_id == case_id)
        .order_by(ClinicalStateSnapshot.state_version.desc())
        .limit(1)
    )
    latest_state: ClinicalStateSnapshot | None = state_result.scalar_one_or_none()

    protocol_id = choose_protocol(
        procedure_type=procedure.procedure_type if procedure else None,
        subtype=procedure.subtype if procedure else None,
        symptoms=list(latest_state.symptoms or []) if latest_state else [],
        visual_symptoms=latest_state.visual_symptoms if latest_state else {},
    )

    if not protocol_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No protocol matched the current clinical state.",
        )

    # Verify protocol exists in DB
    proto_result = await db.execute(
        select(ProtocolDefinition).where(ProtocolDefinition.id == protocol_id)
    )
    protocol = proto_result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matched protocol '{protocol_id}' not found in protocol library.",
        )

    run = ProtocolRun(
        case_id=case_id,
        protocol_id=protocol_id,
        status="in_progress",
        current_step_order=1,
    )
    db.add(run)
    await db.flush()

    for step_def in protocol.step_definitions:
        step = ProtocolRunStep(
            protocol_run_id=run.id,
            step_code=step_def["step_code"],
            step_order=step_def["step_order"],
            title=step_def["title"],
            status="pending" if step_def["step_order"] > 1 else "ready",
        )
        db.add(step)

    await db.commit()
    await db.refresh(run)
    await log_audit_event(db, case_id, "system", "protocol_auto_started",
                          "protocol_run", str(run.id),
                          change_summary=f"protocol={protocol_id} auto_matched=true")
    await db.commit()
    return run


@protocol_router.patch("/protocol-runs/{run_id}", response_model=ProtocolRunRead)
async def update_protocol_run(
    run_id: UUID,
    payload: ProtocolRunUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(ProtocolRun).where(ProtocolRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Protocol run not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(run, field, value)
    await db.commit()
    await db.refresh(run)
    await log_audit_event(db, run.case_id, "system", "protocol_run_updated",
                          "protocol_run", str(run.id))
    await db.commit()
    return run


@protocol_router.patch("/protocol-run-steps/{step_id}", response_model=ProtocolRunStepRead)
async def update_protocol_step(
    step_id: UUID,
    payload: ProtocolRunStepUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(ProtocolRunStep).where(ProtocolRunStep.id == step_id))
    step = result.scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="Protocol step not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(step, field, value)

    if payload.status == "completed":
        next_result = await db.execute(
            select(ProtocolRunStep).where(
                ProtocolRunStep.protocol_run_id == step.protocol_run_id,
                ProtocolRunStep.step_order == step.step_order + 1,
            )
        )
        next_step = next_result.scalar_one_or_none()
        if next_step and next_step.status == "pending":
            next_step.status = "ready"

        run_result = await db.execute(
            select(ProtocolRun).where(ProtocolRun.id == step.protocol_run_id)
        )
        run = run_result.scalar_one_or_none()
        if run:
            run.current_step_order = step.step_order + 1

    await db.commit()
    await db.refresh(step)
    return step


# ─────────────────────────────────────────
# INTERVENTIONS
# ─────────────────────────────────────────

@router.post("/{case_id}/interventions", response_model=InterventionEventRead, status_code=status.HTTP_201_CREATED)
async def log_intervention(
    case_id: UUID,
    payload: InterventionEventCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    data = payload.model_dump()
    data["case_id"] = case_id
    event = InterventionEvent(**data)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    await log_audit_event(db, case_id, "system", "intervention_logged",
                          "intervention_event", str(event.id),
                          change_summary=f"category={event.category} action={event.action}")
    await db.commit()
    return event


# ─────────────────────────────────────────
# REASSESSMENTS
# ─────────────────────────────────────────

@router.post("/{case_id}/reassessments", response_model=ReassessmentEventRead, status_code=status.HTTP_201_CREATED)
async def log_reassessment(
    case_id: UUID,
    payload: ReassessmentEventCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    data = payload.model_dump()
    data["case_id"] = case_id
    event = ReassessmentEvent(**data)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    await log_audit_event(db, case_id, "system", "reassessment_logged",
                          "reassessment_event", str(event.id),
                          change_summary=f"direction={event.clinical_direction}")
    await db.commit()
    return event


# ─────────────────────────────────────────
# DISPOSITION
# ─────────────────────────────────────────

@router.post("/{case_id}/disposition", response_model=DispositionPlanRead, status_code=status.HTTP_201_CREATED)
async def create_disposition(
    case_id: UUID,
    payload: DispositionPlanCreate,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    data = payload.model_dump()
    data["case_id"] = case_id
    plan = DispositionPlan(**data)
    db.add(plan)

    case.status = "closed"

    await db.commit()
    await db.refresh(plan)
    await log_audit_event(db, case_id, "system", "disposition_set",
                          "disposition_plan", str(plan.id),
                          change_summary=f"disposition={plan.disposition} escalation={plan.escalation_required}")
    await db.commit()
    return plan


# ─────────────────────────────────────────
# LIVE VIEW
# ─────────────────────────────────────────

@router.get("/{case_id}/live-view", response_model=CaseLiveView)
async def get_live_view(
    case_id: UUID,
    case: CaseSession = Depends(get_case_or_404),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await build_live_view(db, case_id)
    except Exception as exc:
        logger.error("Live view failed for case %s: %s", case_id, exc)
        raise HTTPException(status_code=500, detail="Could not build live view")


# ─────────────────────────────────────────
# PROTOCOL DEFINITIONS (read-only public)
# ─────────────────────────────────────────

@protocol_router.get("/protocols", response_model=List[dict])
async def list_protocols(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(
            ProtocolDefinition.id,
            ProtocolDefinition.condition_code,
            ProtocolDefinition.title,
            ProtocolDefinition.review_status,
            ProtocolDefinition.version,
        )
    )
    rows = result.mappings().all()
    return [dict(row) for row in rows]


@protocol_router.get("/protocols/{protocol_id}", response_model=dict)
async def get_protocol(protocol_id: str, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(
        select(ProtocolDefinition).where(ProtocolDefinition.id == protocol_id)
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return {
        "id": protocol.id,
        "condition_code": protocol.condition_code,
        "title": protocol.title,
        "step_definitions": protocol.step_definitions,
        "applicable_when": protocol.applicable_when,
        "contraindications": protocol.contraindications,
        "required_inputs": protocol.required_inputs,
        "review_status": protocol.review_status,
        "version": protocol.version,
    }
