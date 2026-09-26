from state.models import InvestigationState


def test_state_initializes_with_defaults():
    state = InvestigationState(user_request="investigate x")
    assert state.workflow_status == "CREATED"
    assert state.human_approval_status == "NOT_REQUIRED"
    assert state.evidence == []
    assert state.trace == []
    assert state.trace_id.startswith("trace-")


def test_trace_id_is_unique_per_instance():
    a = InvestigationState()
    b = InvestigationState()
    assert a.trace_id != b.trace_id


def test_explain_progress_reports_remaining_steps():
    state = InvestigationState(investigation_plan=["step_a", "step_b"])
    summary = state.explain_progress()
    assert "step_a" in summary and "step_b" in summary
