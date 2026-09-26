from agents import data_quality_agent, knowledge_agent, pipeline_agent, root_cause_agent, supervisor, validation_agent
from state.models import InvestigationState


def _base_state(**overrides):
    state = InvestigationState(
        user_request="Investigate the failed Clinical Trial Data Processing Pipeline run 2026-10-30-001.",
        pipeline_id="CLINTRIAL_ETL",
        run_id="2026-10-30-001",
    )
    data = state.model_dump()
    data.update(overrides)
    return data


def test_supervisor_creates_plan_for_normal_request():
    updates = supervisor.create_plan(_base_state())
    assert updates["workflow_status"] == "INVESTIGATING"
    assert len(updates["investigation_plan"]) > 0


def test_supervisor_blocks_unsafe_request():
    state = _base_state(user_request="Delete the pipeline history and rerun without approval.")
    updates = supervisor.create_plan(state)
    assert updates["workflow_status"] == "FAILED"
    assert updates["guardrail_result"]["blocked"] is True


def test_pipeline_agent_investigate_schema_run():
    updates = pipeline_agent.investigate(_base_state())
    assert updates["pipeline_findings"]["found"] is True
    assert updates["pipeline_findings"]["status"] == "FAILED"
    assert len(updates["evidence"]) == 1


def test_pipeline_agent_compare_with_previous():
    updates = pipeline_agent.compare_with_previous(_base_state())
    assert updates["replanned"] is True
    assert updates["investigation_plan"] == ["compare_against_previous_successful_run"]


def test_data_quality_agent_detects_schema_incompatibility():
    updates = data_quality_agent.investigate(_base_state())
    assert updates["schema_findings"]["compatibility"] == "INCOMPATIBLE"


def test_knowledge_agent_retrieves_documentation():
    state = _base_state(pipeline_findings={"found": True, "failed_stage": "data_transformation"})
    updates = knowledge_agent.investigate(state)
    assert updates["knowledge_findings"]["found"] is True
    assert "SOP-101" in updates["knowledge_findings"]["source_ids"]


def test_root_cause_agent_flags_insufficient_evidence_when_nothing_conclusive():
    state = _base_state(
        pipeline_findings={"found": True, "failed_stage": "unknown", "error_evidence": []},
        schema_findings={"found": True, "compatibility": "COMPATIBLE", "added_columns": [], "changed_columns": [], "removed_columns": []},
        data_quality_findings={"found": False, "error": "no dataset"},
        knowledge_findings={"found": True, "source_ids": [], "results": []},
        evidence=[],
    )
    updates = root_cause_agent.analyze(state)
    assert updates["root_cause_analysis"]["insufficient_evidence"] is True
    assert updates["recommended_action"]["action_type"] == "request_further_investigation"


def test_root_cause_agent_identifies_schema_cause():
    state = _base_state(
        pipeline_findings={"found": True, "failed_stage": "data_transformation", "error_evidence": ["CAST_ERROR"]},
        schema_findings={"found": True, "compatibility": "INCOMPATIBLE", "added_columns": ["lab_qualifier_code"], "changed_columns": [{"column": "lab_result_value", "expected_type": "FLOAT", "actual_type": "STRING"}], "removed_columns": []},
        data_quality_findings={"found": True, "overall_result": "PASS", "anomalies": []},
        knowledge_findings={"found": True, "source_ids": ["SOP-101"], "results": [{"section": "3"}]},
        evidence=[{"source": "pipeline_agent", "claim": "x"}],
    )
    updates = root_cause_agent.analyze(state)
    assert updates["root_cause_analysis"]["category"] == "schema_change"
    assert updates["recommended_action"]["action_type"] == "rerun_pipeline"
    assert updates["risk_level"] == "HIGH"


def test_validation_agent_passes_for_healthy_execution_result():
    state = _base_state(
        execution_result={
            "simulated_status": "SUCCESS",
            "output_produced": True,
            "error_recurred": False,
            "post_fix_schema_compatibility": "COMPATIBLE",
            "post_fix_dq_result": "PASS",
        }
    )
    updates = validation_agent.validate(state)
    assert updates["validation_result"]["overall_result"] == "PASS"
