"""
Pilot Integration Module
========================
Provides event logging and rubric auto-fill for clinic pilot instrumentation.
"""

from app.pilot.client import log_event, draft_documentation
from app.pilot.deps import get_case_id
from app.pilot.rubric_autofill import autofill_rubric_from_note

__all__ = ["log_event", "draft_documentation", "get_case_id", "autofill_rubric_from_note"]
