"""
AesthetiCite — Audit Service
app/services/audit_service.py
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.clinical_state import AuditEvent


async def log_audit_event(
    db: AsyncSession,
    case_id: UUID,
    actor_type: str,
    event_type: str,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    actor_id: Optional[UUID] = None,
    change_summary: Optional[str] = None,
) -> None:
    event = AuditEvent(
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        change_summary=change_summary,
    )
    db.add(event)
    # Flush without commit — caller controls the transaction boundary
    await db.flush()
