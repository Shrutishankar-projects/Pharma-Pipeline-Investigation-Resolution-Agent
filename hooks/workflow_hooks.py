"""Guardrail Hook and Post-Workflow Hook (CLAUDE.md section 12)."""
from __future__ import annotations

from typing import Any

from guardrails import rules
from observability.logger import log_event
from observability import tracer
from state.models import TraceEvent

APPROVED_DOCUMENT_SOURCE_IDS = {"SOP-101", "SOP-202", "RUNBOOK-301", "SOP-404", "SOP-500"}


def guardrail_hook(state: dict[str, Any]) -> tuple[dict[str, Any], TraceEvent]:
    """Before any high-impact action: classify, check evidence, decide approval need."""
    recommended_action = state.get("recommended_action") or {}
    action_type = recommended_action.get("action_type", "no_action")

    result = rules.evaluate_all(
        action_type=action_type,
        root_cause_analysis=state.get("root_cause_analysis"),
        evidence=state.get("evidence", []),
        knowledge_findings=state.get("knowledge_findings"),
        approved_source_ids=APPROVED_DOCUMENT_SOURCE_IDS,
        report_text=str(state.get("root_cause_analysis", {})),
    )

    event = tracer.record(
        state["trace_id"],
        node="guardrail_check",
        event="guardrail.evaluated",
        status="OK" if result["passed"] else "BLOCKED",
        detail=f"requires_approval={result['requires_human_approval']} blocked={result['blocked']}",
    )
    return result, event


def post_workflow_hook(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record final status, validation/approval outcome, and trace id at workflow end.

    Returns (summary, trace_event) -- same pattern as `guardrail_hook` --
    so the caller (agents/supervisor.finalize_report) can append the event
    to the unified trace alongside logging it.
    """
    record = {
        "trace_id": state.get("trace_id"),
        "final_status": state.get("workflow_status"),
        "human_approval_status": state.get("human_approval_status"),
        "validation_result": (state.get("validation_result") or {}).get("overall_result"),
        "step_count": len(state.get("trace", [])),
    }
    log_event("workflow.completed", **record)
    event = tracer.record(
        state.get("trace_id", "no-trace-id"),
        node="post_workflow_hook",
        event="workflow.completed",
        status="OK",
        detail=f"final_status={record['final_status']} steps={record['step_count']}",
    )
    return record, event
