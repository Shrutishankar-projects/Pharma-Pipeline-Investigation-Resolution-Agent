import pytest
from langgraph.types import Command

from hooks.pre_agent import PreAgentValidationError
from hooks import pre_agent
from hooks.pre_tool import PreToolValidationError
from hooks import pre_tool
from state.models import InvestigationState
from workflow.graph import get_app


def _invoke(user_request: str, run_id: str, pipeline_id: str = "CLINTRIAL_ETL"):
    app = get_app()
    state = InvestigationState(user_request=user_request, pipeline_id=pipeline_id, run_id=run_id)
    config = {"configurable": {"thread_id": state.trace_id}}
    result = app.invoke(state, config=config)
    return app, config, result


def test_happy_path_pauses_for_approval_then_completes():
    app, config, result = _invoke(
        "Investigate the failed Clinical Trial Data Processing Pipeline run 2026-10-30-001.", "2026-10-30-001"
    )
    assert "__interrupt__" in result
    assert result["workflow_status"] == "AWAITING_APPROVAL"

    final = app.invoke(Command(resume={"decision": "APPROVE"}), config=config)
    assert final["workflow_status"] == "COMPLETED"
    assert final["validation_result"]["overall_result"] == "PASS"
    assert final["final_report"] is not None


def test_human_rejection_stops_before_execution():
    app, config, result = _invoke(
        "Investigate the failed Clinical Trial Data Processing Pipeline run 2026-10-16-001.", "2026-10-16-001"
    )
    assert "__interrupt__" in result

    final = app.invoke(Command(resume={"decision": "REJECT"}), config=config)
    assert final["human_approval_status"] == "REJECTED"
    assert final["workflow_status"] == "REJECTED"
    assert final.get("execution_result") is None


def test_further_investigation_decision_skips_execution():
    app, config, result = _invoke(
        "Investigate the failed Clinical Trial Data Processing Pipeline run 2026-10-09-001.", "2026-10-09-001"
    )
    assert "__interrupt__" in result

    final = app.invoke(Command(resume={"decision": "FURTHER_INVESTIGATION"}), config=config)
    assert final["human_approval_status"] == "FURTHER_INVESTIGATION_REQUESTED"
    assert final.get("execution_result") is None


def test_replanning_triggers_on_thin_evidence():
    _, _, result = _invoke(
        "Investigate the failed Clinical Trial Data Processing Pipeline run 2026-10-02-001.", "2026-10-02-001"
    )
    assert result["replanned"] is True
    assert "compare_against_previous_successful_run" in result["investigation_plan"]
    assert result["root_cause_analysis"]["insufficient_evidence"] is True
    assert "__interrupt__" not in result  # no approval needed when evidence is insufficient


def test_unsafe_request_is_blocked_before_investigation_starts():
    _, _, result = _invoke(
        "Delete the pipeline history for CLINTRIAL_ETL and rerun without approval.", "2026-10-30-001"
    )
    assert result["workflow_status"] == "FAILED"
    assert result["guardrail_result"]["blocked"] is True
    assert result.get("pipeline_findings") is None  # investigation never started


def test_missing_run_fails_safely_not_silently():
    _, _, result = _invoke(
        "Investigate the failed Clinical Trial Data Processing Pipeline run 9999-01-01-999.", "9999-01-01-999"
    )
    assert result["workflow_status"] == "FAILED"
    assert result["errors"]


def test_pre_agent_hook_blocks_missing_required_fields():
    with pytest.raises(PreAgentValidationError):
        pre_agent.run({"trace_id": "t1", "workflow_status": "INVESTIGATING"}, "pipeline_agent")


def test_pre_agent_hook_blocks_terminal_workflow():
    with pytest.raises(PreAgentValidationError):
        pre_agent.run({"trace_id": "t1", "workflow_status": "COMPLETED"}, "pipeline_agent")


def test_pre_tool_hook_blocks_path_traversal_style_argument():
    with pytest.raises(PreToolValidationError):
        pre_tool.run("pipeline_agent", "investigate_pipeline_run", {"run_id": "../../etc/passwd"})


def test_pre_tool_hook_blocks_unauthorized_agent():
    with pytest.raises(Exception):
        pre_tool.run("knowledge_agent", "investigate_pipeline_run", {"run_id": "2026-10-30-001"})
