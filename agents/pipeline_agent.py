"""Pipeline Investigation Agent (CLAUDE.md section 10.1).

Investigates pipeline execution information ONLY through the MCP layer
(mcp_server/client.py) -- it never reads data/ files directly, never
modifies anything, and never states a root cause itself (that belongs to
root_cause_agent).
"""
from __future__ import annotations

from typing import Any

from mcp_server import client as mcp_client

AGENT_NAME = "pipeline_agent"


def investigate(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    run_id = state["run_id"]

    result = mcp_client.call(AGENT_NAME, "investigate_pipeline_run", run_id=run_id, _trace_id=trace_id)
    findings = result.data if result.ok else {"found": False, "run_id": run_id, "error": result.error}

    updates: dict[str, Any] = {
        "pipeline_findings": findings,
        "trace": [result.trace_event],
        "current_step": "pipeline_investigation_complete",
    }
    if not findings.get("found"):
        updates["errors"] = [f"pipeline_agent: {findings.get('error')}"]
        updates["workflow_status"] = "FAILED"
    elif findings.get("status") == "FAILED":
        updates["evidence"] = [
            {
                "source": AGENT_NAME,
                "claim": f"Run failed at stage '{findings.get('failed_stage')}'",
                "detail": findings.get("error_evidence") or "no explicit error lines captured in log",
            }
        ]
    return updates


def compare_with_previous(state: dict[str, Any]) -> dict[str, Any]:
    """Re-planning step: compare against the previous successful/attempted run.

    Triggered by workflow/graph.py's conditional re-plan edge when the
    initial pipeline_findings carried no usable error evidence.
    """
    trace_id = state["trace_id"]
    run_id = state["run_id"]

    result = mcp_client.call(AGENT_NAME, "get_previous_run_comparison", run_id=run_id, _trace_id=trace_id)
    comparison = result.data if result.ok else {"found": False, "error": result.error}

    updates: dict[str, Any] = {
        "trace": [result.trace_event],
        "current_step": "previous_run_comparison_complete",
        "replanned": True,
        "investigation_plan": ["compare_against_previous_successful_run"],
    }
    if comparison.get("found") and comparison.get("previous_run_id"):
        updates["evidence"] = [
            {
                "source": f"{AGENT_NAME}:previous_run_comparison",
                "claim": (
                    f"Previous run {comparison.get('previous_run_id')} status was "
                    f"{comparison.get('previous_status')}"
                ),
                "detail": comparison,
            }
        ]
    return updates
