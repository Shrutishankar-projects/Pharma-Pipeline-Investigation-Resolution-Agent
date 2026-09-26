from skills.report_generation import core


def test_report_contains_mandated_sections():
    state = {
        "trace_id": "trace-abc",
        "user_request": "Investigate run 2026-10-30-001",
        "pipeline_id": "CLINTRIAL_ETL",
        "run_id": "2026-10-30-001",
        "pipeline_findings": {"failed_stage": "data_transformation"},
        "evidence": [{"source": "pipeline_agent", "claim": "x"}],
        "root_cause_analysis": {"potential_cause": "Schema type change", "confidence_explanation": "Evidence indicates..."},
        "recommended_action": {"description": "Rerun after schema fix"},
        "risk_level": "HIGH",
        "guardrail_result": {"passed": True},
        "human_approval_status": "APPROVED",
        "workflow_status": "COMPLETED",
    }
    report = core.run(state)
    for field in [
        "trace_id", "investigation_summary", "pipeline_run", "observed_issue", "evidence",
        "potential_root_cause", "confidence_or_uncertainty", "recommended_action", "risk_impact",
        "guardrail_result", "human_approval", "final_status",
    ]:
        assert field in report


def test_insufficient_evidence_is_reported_not_papered_over():
    state = {"root_cause_analysis": {"insufficient_evidence": True}}
    report = core.run(state)
    assert "Insufficient evidence" in report["potential_root_cause"]
