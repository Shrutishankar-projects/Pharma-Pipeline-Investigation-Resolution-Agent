"""Supervisor / Orchestrator Agent (CLAUDE.md section 9).

Understands the request, creates the investigation plan, and produces the
final report. Delegation to specialized sub-agents happens in
workflow/graph.py -- the supervisor itself never calls MCP tools or reads
pipeline data directly (see its empty tool allowlist in
guardrails/authorization.py).
"""
from __future__ import annotations

from typing import Any

from hooks import workflow_hooks
from observability import tracer
from skills.report_generation import core as report_generation_skill
from state.models import now_iso

AGENT_NAME = "supervisor"

BASE_PLAN = [
    "inspect_pipeline_status",
    "retrieve_execution_logs",
    "perform_data_quality_checks",
    "compare_schemas",
    "search_documentation",
    "correlate_evidence",
]

# Simple, explicit unsafe-request detection (CLAUDE.md section 20, Scenario 5
# and section 15's Execution Guardrail). A production system would route this
# through a policy/intent classifier; a deterministic keyword check keeps
# this prototype's Unsafe-Request guardrail path fully explainable.
UNSAFE_REQUEST_MARKERS = (
    "delete the pipeline history",
    "delete pipeline history",
    "drop table",
    "drop the table",
    "truncate table",
    "truncate the table",
    "disable monitoring",
    "disable alerting",
    "bypass the data quality gate",
    "bypass data quality",
    "without approval",
    "skip approval",
    "skip human approval",
)


def detect_unsafe_request(user_request: str) -> str | None:
    lowered = user_request.lower()
    for marker in UNSAFE_REQUEST_MARKERS:
        if marker in lowered:
            return marker
    return None


def create_plan(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    user_request = state.get("user_request", "")

    unsafe_marker = detect_unsafe_request(user_request)
    if unsafe_marker:
        event = tracer.record(
            trace_id,
            node=AGENT_NAME,
            event="supervisor.unsafe_request_blocked",
            agent=AGENT_NAME,
            status="BLOCKED",
            detail=f"Request text matched prohibited-action marker: '{unsafe_marker}'",
        )
        return {
            "workflow_status": "FAILED",
            "current_step": "blocked_unsafe_request",
            "workflow_started_at": now_iso(),
            "guardrail_result": {
                "passed": False,
                "blocked": True,
                "reason": (
                    f"Request text matched a prohibited/unauthorized action pattern ('{unsafe_marker}'). "
                    "Per SOP-404 section 2.2, this action has no approval path and cannot be executed by "
                    "any agent. The investigation was not started."
                ),
            },
            "human_approval_status": "NOT_REQUIRED",
            "trace": [event],
            "errors": [f"supervisor: blocked unsafe request ('{unsafe_marker}')"],
        }

    event = tracer.record(
        trace_id,
        node=AGENT_NAME,
        event="supervisor.plan_created",
        agent=AGENT_NAME,
        status="OK",
        detail=f"plan={BASE_PLAN}",
    )
    return {
        "workflow_status": "INVESTIGATING",
        "current_step": "plan_created",
        "investigation_plan": list(BASE_PLAN),
        "workflow_started_at": now_iso(),
        "trace": [event],
    }


def finalize_report(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    report = report_generation_skill.run(state)

    final_status = "COMPLETED"
    if state.get("human_approval_status") == "REJECTED":
        final_status = "REJECTED"
    elif state.get("workflow_status") == "FAILED":
        final_status = "FAILED"

    event = tracer.record(
        trace_id,
        node=AGENT_NAME,
        event="supervisor.report_generated",
        agent=AGENT_NAME,
        skill="report_generation",
        status="OK",
        detail=final_status,
    )

    ended_at = now_iso()
    _summary, workflow_completed_event = workflow_hooks.post_workflow_hook(
        {**state, "workflow_status": final_status}
    )

    return {
        "final_report": report,
        "workflow_status": final_status,
        "current_step": "report_generated",
        "workflow_ended_at": ended_at,
        "trace": [event, workflow_completed_event],
    }
