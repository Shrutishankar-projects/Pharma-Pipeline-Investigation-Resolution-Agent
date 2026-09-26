"""Evaluation metrics (CLAUDE.md section 20)."""
from __future__ import annotations

from typing import Any


def compute_metrics(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scenario_results)
    if total == 0:
        return {"total_scenarios": 0}

    passed = [r for r in scenario_results if r["passed"]]
    guardrail_compliant = [r for r in scenario_results if r["guardrail_as_expected"]]
    approval_compliant = [r for r in scenario_results if r["approval_as_expected"]]
    trace_complete = [r for r in scenario_results if r["trace_complete"]]
    citation_correct = [r for r in scenario_results if r["citations_valid"]]
    latencies = [r["latency_ms"] for r in scenario_results]

    return {
        "total_scenarios": total,
        "task_completion_rate": len(passed) / total,
        "guardrail_compliance_rate": len(guardrail_compliant) / total,
        "human_approval_compliance_rate": len(approval_compliant) / total,
        "workflow_trace_completeness_rate": len(trace_complete) / total,
        "citation_correctness_rate": len(citation_correct) / total,
        "avg_response_latency_ms": round(sum(latencies) / total, 1) if latencies else None,
        "max_response_latency_ms": round(max(latencies), 1) if latencies else None,
    }
