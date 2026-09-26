"""Structured workflow state for the Pharma Agentic Pipeline Investigator.

This is the single source of truth passed between every LangGraph node (see
workflow/graph.py). Per CLAUDE.md section 14, the system must not rely on
conversational history alone -- every field here can be inspected at any point
to explain what has already happened and what remains to be done.
"""
from __future__ import annotations

import operator
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

WorkflowStatus = Literal[
    "CREATED",
    "PLANNING",
    "INVESTIGATING",
    "AWAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "EXECUTING",
    "VALIDATING",
    "COMPLETED",
    "FAILED",
]

HumanApprovalStatus = Literal[
    "NOT_REQUIRED",
    "PENDING",
    "APPROVED",
    "REJECTED",
    "FURTHER_INVESTIGATION_REQUESTED",
]

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


def _new_trace_id() -> str:
    return f"trace-{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceEvent(BaseModel):
    """One entry in the end-to-end trace (CLAUDE.md section 19)."""

    trace_id: str
    step_id: str
    timestamp: str = Field(default_factory=now_iso)
    node: str
    agent: str | None = None
    skill: str | None = None
    tool: str | None = None
    event: str
    status: Literal["OK", "ERROR", "BLOCKED", "PENDING"] = "OK"
    detail: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] | None = None


class InvestigationState(BaseModel):
    """LangGraph state schema.

    Fields that must accumulate across nodes (evidence, trace, errors, plan)
    use an `operator.add` reducer so each node can return only the new items
    it produced rather than the whole growing list.
    """

    # --- identity / request ---
    trace_id: str = Field(default_factory=_new_trace_id)
    user_request: str = ""
    pipeline_id: str | None = None
    run_id: str | None = None

    # --- workflow control ---
    workflow_status: WorkflowStatus = "CREATED"
    investigation_plan: Annotated[list[str], operator.add] = Field(default_factory=list)
    current_step: str = "received_request"
    replanned: bool = False
    workflow_started_at: str | None = None
    workflow_ended_at: str | None = None

    # --- agent findings ---
    pipeline_findings: dict[str, Any] | None = None
    data_quality_findings: dict[str, Any] | None = None
    schema_findings: dict[str, Any] | None = None
    knowledge_findings: dict[str, Any] | None = None

    # --- evidence / analysis ---
    evidence: Annotated[list[dict[str, Any]], operator.add] = Field(default_factory=list)
    root_cause_analysis: dict[str, Any] | None = None
    recommended_action: dict[str, Any] | None = None
    risk_level: RiskLevel | None = None

    # --- guardrails / approval / execution ---
    guardrail_result: dict[str, Any] | None = None
    human_approval_status: HumanApprovalStatus = "NOT_REQUIRED"
    human_approval_note: str | None = None
    execution_result: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None

    # --- output ---
    final_report: dict[str, Any] | None = None

    # --- observability ---
    # Stored as plain dicts (validated against TraceEvent by observability/tracer.py
    # before being returned) so LangGraph's msgpack checkpointer never has to
    # serialize a custom pydantic type.
    trace: Annotated[list[dict[str, Any]], operator.add] = Field(default_factory=list)
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)

    def explain_progress(self) -> str:
        """Human-readable summary of what has happened and what remains."""
        done = [s for s in self.investigation_plan if s in {e.get("node") for e in self.trace}]
        remaining = [s for s in self.investigation_plan if s not in done]
        return (
            f"Status: {self.workflow_status}. Current step: {self.current_step}. "
            f"Completed plan steps: {done or 'none yet'}. Remaining: {remaining or 'none'}."
        )
