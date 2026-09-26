"""Skill 6 -- Business Report Generation (CLAUDE.md sections 11, 33).

Input: completed investigation state (as a plain dict, e.g. via
InvestigationState.model_dump()).
Output: structured investigation report matching the mandated section list
in CLAUDE.md section 33. Never claims certainty beyond the evidence -- if
root_cause_analysis carries an "insufficient_evidence" flag, the report
says so explicitly rather than picking a cause.
"""
from __future__ import annotations

from typing import Any


def run(state: dict[str, Any]) -> dict[str, Any]:
    root_cause = state.get("root_cause_analysis") or {}
    recommended_action = state.get("recommended_action") or {}
    guardrail_result = state.get("guardrail_result") or {}
    execution_result = state.get("execution_result") or {}
    validation_result = state.get("validation_result") or {}

    if root_cause.get("insufficient_evidence"):
        potential_cause = "Insufficient evidence to conclude a root cause."
        confidence = "LOW -- additional investigation required before any corrective action."
    else:
        potential_cause = root_cause.get("potential_cause", "Not determined.")
        confidence = root_cause.get("confidence_explanation", "Not stated.")

    return {
        "trace_id": state.get("trace_id"),
        "investigation_summary": state.get("user_request"),
        "pipeline_run": {"pipeline_id": state.get("pipeline_id"), "run_id": state.get("run_id")},
        "observed_issue": (state.get("pipeline_findings") or {}).get("failed_stage", "N/A"),
        "evidence": state.get("evidence", []),
        "data_quality_findings": state.get("data_quality_findings"),
        "documentation_findings": state.get("knowledge_findings"),
        "potential_root_cause": potential_cause,
        "confidence_or_uncertainty": confidence,
        "recommended_action": recommended_action.get("description", "N/A"),
        "risk_impact": state.get("risk_level", "UNKNOWN"),
        "guardrail_result": guardrail_result,
        "human_approval": state.get("human_approval_status"),
        "execution_result": execution_result,
        "validation_result": validation_result,
        "final_status": state.get("workflow_status"),
        "generated_from_synthetic_data": True,
    }
