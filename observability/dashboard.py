"""Pure-function derivations for the Observability & Traceability dashboard.

Every function here takes a plain investigation state dict (the same shape
produced everywhere else in this codebase -- `InvestigationState(...).model_dump()`
or a LangGraph `.invoke()`/`.get_state()` result) and returns plain data. No
Streamlit import here on purpose: these are independently unit-testable
(see tests/test_observability.py) and reused verbatim by app/streamlit_app.py.

Nothing here invents data. Where the underlying mechanism genuinely has no
information (no retry logic exists in this prototype; the default LLM
provider reports no token usage), that is reported explicitly rather than
faked -- per the capstone's Hallucination/Evidence guardrails applied to
the dashboard itself.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

_ACTIVE_STATUSES = {"CREATED", "PLANNING", "INVESTIGATING", "AWAITING_APPROVAL", "APPROVED", "EXECUTING", "VALIDATING"}

_CHAIN_STEPS = [
    "User Request",
    "Agent Plan",
    "Supervisor",
    "Sub-Agent Investigation",
    "Skill",
    "Tool / MCP",
    "Evidence / Data",
    "Analysis (Root Cause)",
    "Guardrail Check",
    "Human Approval",
    "Action (Execution)",
    "Validation",
    "Final Output",
]

_FRIENDLY_EVENT_LABELS = {
    "supervisor.plan_created": "Plan Created",
    "supervisor.unsafe_request_blocked": "Unsafe Request Blocked",
    "supervisor.report_generated": "Final Output Generated",
    "pre_agent_hook.blocked": "Pre-Agent Hook Blocked",
    "guardrail.evaluated": "Guardrail Checked",
    "human_approval.requested": "Human Approval Requested",
    "human_approval.decision_received": "Human Approval Received",
    "execution.simulated_rerun": "Action Executed (Simulated)",
    "validation_agent.completed": "Validation Completed",
    "workflow.completed": "Workflow Completed",
    "llm.call": "LLM/Model Call",
}


def _trace(state: dict[str, Any]) -> list[dict[str, Any]]:
    return state.get("trace") or []


def _friendly_label(event_name: str) -> str:
    if event_name in _FRIENDLY_EVENT_LABELS:
        return _FRIENDLY_EVENT_LABELS[event_name]
    if event_name.endswith(".started"):
        return f"{event_name[:-len('.started')].replace('_', ' ').title()} Started"
    if event_name.endswith(".completed"):
        return f"{event_name[:-len('.completed')].replace('_', ' ').title()} Completed"
    if event_name.endswith(".error"):
        return f"{event_name[:-len('.error')].replace('_', ' ').title()} Error"
    if event_name.startswith("mcp."):
        return f"MCP Call: {event_name[len('mcp.'):]}"
    return event_name


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def summary_metrics(state: dict[str, Any]) -> dict[str, Any]:
    trace = _trace(state)
    started_at = state.get("workflow_started_at")
    ended_at = state.get("workflow_ended_at")

    duration_seconds = None
    start_dt, end_dt = _parse_iso(started_at), _parse_iso(ended_at)
    if start_dt and end_dt:
        duration_seconds = round((end_dt - start_dt).total_seconds(), 3)

    completed_agents = sorted({e["agent"] for e in trace if e.get("agent")})
    workflow_status = state.get("workflow_status")

    active_agent = None
    if workflow_status in _ACTIVE_STATUSES:
        for event in reversed(trace):
            if event.get("agent"):
                active_agent = event["agent"]
                break

    tool_mcp_call_count = sum(1 for e in trace if e.get("tool"))
    error_count = len(state.get("errors") or [])

    return {
        "trace_id": state.get("trace_id"),
        "workflow_status": workflow_status,
        "workflow_started_at": started_at,
        "workflow_ended_at": ended_at,
        "total_duration_seconds": duration_seconds,
        "active_agent": active_agent,
        "completed_agents": completed_agents,
        "agent_count": len(completed_agents),
        "tool_call_count": tool_mcp_call_count,
        "mcp_call_count": tool_mcp_call_count,  # same underlying calls -- every tool access in this architecture is dispatched via MCP
        "error_count": error_count,
        "human_approval_status": state.get("human_approval_status"),
        "human_approval_note": state.get("human_approval_note"),
    }


def agent_execution_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Timestamp": e.get("timestamp"),
            "Trace ID": e.get("trace_id"),
            "Agent": e.get("agent") or e.get("node"),
            "Event": e.get("event"),
            "Status": e.get("status"),
            "Duration (ms)": e.get("duration_ms"),
            "Details": e.get("detail"),
        }
        for e in _trace(state)
    ]


def tool_mcp_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for e in _trace(state):
        if not e.get("tool"):
            continue
        metadata = e.get("metadata") or {}
        rows.append(
            {
                "Timestamp": e.get("timestamp"),
                "Agent": e.get("agent"),
                "Tool / MCP": e.get("tool"),
                "Purpose (Skill)": e.get("skill"),
                "Input Summary": metadata.get("input_summary"),
                "Status": e.get("status"),
                "Duration (ms)": e.get("duration_ms"),
                "Output Summary": metadata.get("output_summary"),
            }
        )
    return rows


def error_retry_summary(state: dict[str, Any]) -> dict[str, Any]:
    trace = _trace(state)
    errors = state.get("errors") or []
    failed_tool_calls = [e for e in trace if e.get("tool") and e.get("status") == "ERROR"]
    failed_agents = sorted(
        {e["agent"] for e in trace if e.get("agent") and e.get("status") in {"ERROR", "BLOCKED"}}
    )
    workflow_interruptions = 1 if any(e.get("event") == "human_approval.requested" for e in trace) else 0

    return {
        "total_errors": len(errors),
        "error_messages": errors,
        "failed_tool_call_count": len(failed_tool_calls),
        "failed_tool_calls": failed_tool_calls,
        "failed_agents": failed_agents,
        # This prototype implements no automatic retry logic anywhere in the
        # workflow (a failed node marks the workflow FAILED and routes
        # straight to report generation) -- reported as 0, never fabricated.
        "retries": 0,
        "workflow_interruptions": workflow_interruptions,
        "has_errors": len(errors) > 0,
    }


def llm_observability(state: dict[str, Any]) -> dict[str, Any]:
    calls = []
    for e in _trace(state):
        if e.get("event") != "llm.call":
            continue
        metadata = e.get("metadata") or {}
        calls.append(
            {
                "timestamp": e.get("timestamp"),
                "agent": e.get("agent"),
                "provider": metadata.get("provider"),
                "model": metadata.get("model"),
                "tokens_used": metadata.get("tokens_used"),
                "duration_ms": e.get("duration_ms"),
                "task": metadata.get("task"),
            }
        )

    token_values = [c["tokens_used"] for c in calls if c["tokens_used"] is not None]
    token_usage_available = len(token_values) > 0

    return {
        "call_count": len(calls),
        "calls": calls,
        "token_usage_available": token_usage_available,
        "total_tokens": sum(token_values) if token_usage_available else None,
        "unavailable_message": None if token_usage_available else "Token usage unavailable from provider",
    }


def traceability_chain(state: dict[str, Any]) -> list[dict[str, Any]]:
    trace = _trace(state)
    evidence = state.get("evidence") or []
    guardrail_result = state.get("guardrail_result")
    human_approval_status = state.get("human_approval_status", "NOT_REQUIRED")

    has_supervisor = any(e.get("agent") == "supervisor" for e in trace)
    has_sub_agent = bool(
        state.get("pipeline_findings") or state.get("data_quality_findings") or state.get("knowledge_findings")
    )
    has_skill = any(e.get("skill") for e in trace)
    has_tool = any(e.get("tool") for e in trace)

    def status_for(done: bool) -> str:
        return "DONE" if done else "NOT_REACHED"

    approval_status = "NOT_REQUIRED"
    if human_approval_status == "PENDING":
        approval_status = "PENDING"
    elif human_approval_status in {"APPROVED", "REJECTED", "FURTHER_INVESTIGATION_REQUESTED"}:
        approval_status = "DONE"
    elif human_approval_status == "NOT_REQUIRED" and guardrail_result is None:
        approval_status = "NOT_REACHED"

    guardrail_status = "NOT_REACHED"
    if guardrail_result is not None:
        guardrail_status = "BLOCKED" if guardrail_result.get("blocked") else "DONE"

    rows = [
        ("User Request", status_for(bool(state.get("user_request")))),
        ("Agent Plan", status_for(bool(state.get("investigation_plan")))),
        ("Supervisor", status_for(has_supervisor)),
        ("Sub-Agent Investigation", status_for(has_sub_agent)),
        ("Skill", status_for(has_skill)),
        ("Tool / MCP", status_for(has_tool)),
        ("Evidence / Data", status_for(len(evidence) > 0)),
        ("Analysis (Root Cause)", status_for(state.get("root_cause_analysis") is not None)),
        ("Guardrail Check", guardrail_status),
        ("Human Approval", approval_status),
        ("Action (Execution)", status_for(state.get("execution_result") is not None)),
        ("Validation", status_for(state.get("validation_result") is not None)),
        ("Final Output", status_for(state.get("final_report") is not None)),
    ]
    return [{"step": name, "status": status} for name, status in rows]


def guardrail_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    guardrail_result = state.get("guardrail_result") or {}
    checks = guardrail_result.get("checks") or []
    timestamp = None
    for e in _trace(state):
        if e.get("event") == "guardrail.evaluated":
            timestamp = e.get("timestamp")
            break

    rows = [
        {
            "Guardrail": check.get("guardrail"),
            "Result": "PASS" if check.get("passed") else "FAIL",
            "Reason": check.get("reason"),
            "Timestamp": timestamp,
        }
        for check in checks
    ]

    # The blocked/unsafe-request path (agents/supervisor.create_plan) sets a
    # guardrail_result with no per-check list -- still surface it as a row,
    # using the blocking event's own timestamp since guardrail_check_node
    # never runs on that path.
    if not rows and guardrail_result:
        if timestamp is None:
            for e in _trace(state):
                if e.get("event") == "supervisor.unsafe_request_blocked":
                    timestamp = e.get("timestamp")
                    break
        rows.append(
            {
                "Guardrail": "action_guardrail",
                "Result": "FAIL" if not guardrail_result.get("passed", True) else "PASS",
                "Reason": guardrail_result.get("reason"),
                "Timestamp": timestamp,
            }
        )
    return rows


def evidence_trace(state: dict[str, Any]) -> list[dict[str, Any]]:
    trace = _trace(state)
    rows = []
    for item in state.get("evidence") or []:
        source = item.get("source") or ""
        agent_prefix = source.split(":")[0] if source else None
        produced_by = [
            {"tool": e.get("tool"), "skill": e.get("skill"), "timestamp": e.get("timestamp")}
            for e in trace
            if e.get("agent") == agent_prefix and (e.get("tool") or e.get("skill"))
        ]
        rows.append(
            {
                "conclusion": item.get("claim"),
                "supporting_detail": item.get("detail"),
                "source": source,
                "agent": agent_prefix,
                "produced_by": produced_by,
            }
        )
    return rows


def audit_trail_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for e in _trace(state):
        actor = "HUMAN" if e.get("event") == "human_approval.decision_received" else "AI / SYSTEM"
        rows.append(
            {
                "timestamp": e.get("timestamp"),
                "trace_id": e.get("trace_id"),
                "actor": actor,
                "agent": e.get("agent") or e.get("node"),
                "event": e.get("event"),
                "friendly_label": _friendly_label(e.get("event", "")),
                "status": e.get("status"),
                "detail": e.get("detail"),
                "metadata": e.get("metadata"),
            }
        )
    return rows


def export_json(state: dict[str, Any]) -> str:
    """Full trace/state export. No secrets are possible here -- none exist
    anywhere in InvestigationState -- but the exported set is still curated
    to exactly what's needed to reconstruct the workflow."""
    payload = {
        "trace_id": state.get("trace_id"),
        "user_request": state.get("user_request"),
        "pipeline_id": state.get("pipeline_id"),
        "run_id": state.get("run_id"),
        "workflow_status": state.get("workflow_status"),
        "workflow_started_at": state.get("workflow_started_at"),
        "workflow_ended_at": state.get("workflow_ended_at"),
        "investigation_plan": state.get("investigation_plan"),
        "evidence": state.get("evidence"),
        "root_cause_analysis": state.get("root_cause_analysis"),
        "recommended_action": state.get("recommended_action"),
        "risk_level": state.get("risk_level"),
        "guardrail_result": state.get("guardrail_result"),
        "human_approval_status": state.get("human_approval_status"),
        "human_approval_note": state.get("human_approval_note"),
        "execution_result": state.get("execution_result"),
        "validation_result": state.get("validation_result"),
        "final_report": state.get("final_report"),
        "errors": state.get("errors"),
        "trace": _trace(state),
    }
    return json.dumps(payload, indent=2, default=str)


def export_csv(state: dict[str, Any]) -> str:
    rows = agent_execution_rows(state)
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return buffer.getvalue()
