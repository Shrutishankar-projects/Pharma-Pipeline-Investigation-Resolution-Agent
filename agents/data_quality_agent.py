"""Data Quality Agent (CLAUDE.md section 10.2).

Runs data-quality checks and schema comparison, both through the MCP layer.
Every check output carries expected/actual/result/evidence/severity as
mandated.
"""
from __future__ import annotations

from typing import Any

from mcp_server import client as mcp_client

AGENT_NAME = "data_quality_agent"


def investigate(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    run_id = state["run_id"]
    pipeline_id = state["pipeline_id"]

    dq_result = mcp_client.call(AGENT_NAME, "run_data_quality_checks", run_id=run_id, _trace_id=trace_id)
    schema_result = mcp_client.call(
        AGENT_NAME, "compare_schema", pipeline_id=pipeline_id, run_id=run_id, _trace_id=trace_id
    )

    dq_findings = dq_result.data if dq_result.ok else {"found": False, "error": dq_result.error}
    schema_findings = schema_result.data if schema_result.ok else {"found": False, "error": schema_result.error}

    evidence: list[dict[str, Any]] = []
    if dq_findings.get("found") and dq_findings.get("overall_result") == "FAIL":
        evidence.append(
            {
                "source": f"{AGENT_NAME}:quality_checks",
                "claim": "Data quality gate breached one or more SOP-202 thresholds",
                "detail": dq_findings.get("anomalies"),
            }
        )
    elif dq_findings.get("found"):
        evidence.append(
            {
                "source": f"{AGENT_NAME}:quality_checks",
                "claim": "Data quality checks passed against SOP-202 thresholds",
                "detail": "no anomalies",
            }
        )
    else:
        evidence.append(
            {
                "source": f"{AGENT_NAME}:quality_checks",
                "claim": "No dataset extract was available to check",
                "detail": dq_findings.get("error"),
            }
        )

    if schema_findings.get("found") and schema_findings.get("compatibility") == "INCOMPATIBLE":
        evidence.append(
            {
                "source": f"{AGENT_NAME}:schema_comparison",
                "claim": "Upstream schema changed in an incompatible way",
                "detail": {
                    "added": schema_findings.get("added_columns"),
                    "changed": schema_findings.get("changed_columns"),
                    "removed": schema_findings.get("removed_columns"),
                },
            }
        )

    return {
        "data_quality_findings": dq_findings,
        "schema_findings": schema_findings,
        "evidence": evidence,
        "trace": [dq_result.trace_event, schema_result.trace_event],
        "current_step": "data_quality_investigation_complete",
    }
