"""Evaluation harness (CLAUDE.md sections 20, 21).

Runs every scenario under evaluation/scenarios/*.json through the real
LangGraph workflow (the same one the Streamlit app drives) and checks the
expected-behavior assertions for that scenario. This both satisfies the
"controlled evaluation dataset" requirement and doubles as an end-to-end
integration test.

Usage: python -m evaluation.evaluator
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langgraph.types import Command

from evaluation.metrics import compute_metrics
from hooks.workflow_hooks import APPROVED_DOCUMENT_SOURCE_IDS
from state.models import InvestigationState
from workflow.graph import get_app

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


def _load_scenarios() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SCENARIOS_DIR.glob("*.json"))]


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    app = get_app()
    initial_state = InvestigationState(
        user_request=scenario["user_request"],
        pipeline_id=scenario["pipeline_id"],
        run_id=scenario["run_id"],
    )
    config = {"configurable": {"thread_id": initial_state.trace_id}}

    start = time.perf_counter()
    result = app.invoke(initial_state, config=config)
    if "__interrupt__" in result and scenario.get("approval_decision"):
        result = app.invoke(Command(resume={"decision": scenario["approval_decision"]}), config=config)
    latency_ms = (time.perf_counter() - start) * 1000

    expected = scenario["expected"]
    checks: dict[str, bool] = {}

    if "schema_incompatible" in expected:
        actual = (result.get("schema_findings") or {}).get("compatibility") == "INCOMPATIBLE"
        checks["schema_incompatible"] = actual == expected["schema_incompatible"]

    if "dq_overall_result" in expected:
        checks["dq_overall_result"] = (result.get("data_quality_findings") or {}).get(
            "overall_result"
        ) == expected["dq_overall_result"]

    if "root_cause_category" in expected:
        checks["root_cause_category"] = (result.get("root_cause_analysis") or {}).get(
            "category"
        ) == expected["root_cause_category"]

    if "insufficient_evidence" in expected:
        checks["insufficient_evidence"] = bool(
            (result.get("root_cause_analysis") or {}).get("insufficient_evidence")
        ) == expected["insufficient_evidence"]

    if "requires_human_approval" in expected:
        checks["requires_human_approval"] = bool(
            (result.get("guardrail_result") or {}).get("requires_human_approval")
        ) == expected["requires_human_approval"]

    if "blocked" in expected:
        checks["blocked"] = bool((result.get("guardrail_result") or {}).get("blocked")) == expected["blocked"]

    if "final_status" in expected:
        checks["final_status"] = result.get("workflow_status") == expected["final_status"]

    cited_source_ids = set((result.get("knowledge_findings") or {}).get("source_ids", []))
    if "cited_source_ids" in expected:
        checks["cited_source_ids"] = set(expected["cited_source_ids"]).issubset(cited_source_ids)

    citations_valid = cited_source_ids.issubset(APPROVED_DOCUMENT_SOURCE_IDS)
    trace_complete = len(result.get("trace", [])) > 0 and result.get("final_report") is not None
    guardrail_as_expected = checks.get("blocked", True) and checks.get("requires_human_approval", True)
    approval_as_expected = checks.get("final_status", True)

    return {
        "scenario_id": scenario["scenario_id"],
        "description": scenario["description"],
        "passed": all(checks.values()) if checks else False,
        "checks": checks,
        "guardrail_as_expected": guardrail_as_expected,
        "approval_as_expected": approval_as_expected,
        "trace_complete": trace_complete,
        "citations_valid": citations_valid,
        "latency_ms": latency_ms,
        "final_status": result.get("workflow_status"),
        "trace_id": result.get("trace_id"),
    }


def run_all() -> dict[str, Any]:
    results = [run_scenario(s) for s in _load_scenarios()]
    return {"results": results, "metrics": compute_metrics(results)}


if __name__ == "__main__":
    report = run_all()
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['scenario_id']}: {r['checks']} (latency={r['latency_ms']:.0f}ms)")
    print("\nAggregate metrics:")
    for key, value in report["metrics"].items():
        print(f"  {key}: {value}")
