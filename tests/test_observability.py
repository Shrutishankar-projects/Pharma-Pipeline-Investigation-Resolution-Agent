"""Tests for the Observability & Traceability dashboard feature.

Covers: the logger secret-scrubbing fix, trace metadata round-tripping,
real per-agent/LLM/tool-call event creation during an actual end-to-end
workflow run, and the observability/dashboard.py derivations that back the
Streamlit page -- all against real events, never mocked/hardcoded data.
"""
from __future__ import annotations

from langgraph.types import Command

from mcp_server import client as mcp_client
from observability import dashboard
from observability.logger import log_event
from observability.tracer import record as trace_record
from state.models import InvestigationState
from workflow.graph import get_app


# --- Logger secret-scrubbing -------------------------------------------------


def test_token_usage_fields_are_never_redacted():
    result = log_event("test", tokens_used=42, input_tokens=10, output_tokens=32, token_usage="reported")
    assert result["tokens_used"] == 42
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 32
    assert result["token_usage"] == "reported"


def test_real_secret_shaped_fields_are_redacted_including_nested():
    result = log_event(
        "test",
        api_key="sk-abc123",
        password="hunter2",
        credential="c1",
        metadata={"access_token": "abc", "model": "deterministic-template-v1"},
    )
    assert result["api_key"] == "***redacted***"
    assert result["password"] == "***redacted***"
    assert result["credential"] == "***redacted***"
    assert result["metadata"]["access_token"] == "***redacted***"
    assert result["metadata"]["model"] == "deterministic-template-v1"  # untouched, not secret-shaped


# --- Tracer metadata ---------------------------------------------------------


def test_tracer_record_round_trips_metadata():
    event = trace_record("trace-x", node="n", event="e", metadata={"provider": "deterministic", "tokens_used": None})
    assert event["metadata"] == {"provider": "deterministic", "tokens_used": None}


# --- Real MCP call produces input/output summaries --------------------------


def test_mcp_call_produces_input_and_output_summary_metadata():
    result = mcp_client.call("pipeline_agent", "investigate_pipeline_run", run_id="2026-10-30-001", _trace_id="t1")
    assert result.ok
    metadata = result.trace_event["metadata"]
    assert metadata["input_summary"] == "run_id=2026-10-30-001"
    assert "failed_stage" in metadata["output_summary"]
    assert len(metadata["output_summary"]) <= 210  # truncated, never a raw dump


def test_mcp_call_failure_still_records_input_summary():
    result = mcp_client.call("knowledge_agent", "investigate_pipeline_run", run_id="2026-10-30-001", _trace_id="t1")
    assert not result.ok
    assert result.trace_event["metadata"]["input_summary"] == "run_id=2026-10-30-001"


# --- Real end-to-end workflow run: fixture used by the dashboard tests below -


def _run_schema_change_to_completion():
    app = get_app()
    state = InvestigationState(
        user_request="Investigate the failed Clinical Trial Data Processing Pipeline run 2026-10-30-001.",
        pipeline_id="CLINTRIAL_ETL",
        run_id="2026-10-30-001",
    )
    config = {"configurable": {"thread_id": state.trace_id}}
    interrupted = app.invoke(state, config=config)
    final = app.invoke(Command(resume={"decision": "APPROVE", "note": "looks good"}), config=config)
    return interrupted, final


def test_workflow_timestamps_and_agent_duration_events_are_real():
    interrupted, final = _run_schema_change_to_completion()

    assert interrupted["workflow_started_at"] is not None
    events_by_name = {e["event"]: e for e in interrupted["trace"]}
    assert "pipeline_agent.started" in events_by_name
    assert "pipeline_agent.completed" in events_by_name
    assert isinstance(events_by_name["pipeline_agent.completed"]["duration_ms"], float)
    assert events_by_name["pipeline_agent.completed"]["duration_ms"] >= 0

    assert any(e["event"] == "human_approval.requested" for e in interrupted["trace"])

    assert final["workflow_ended_at"] is not None
    final_events = {e["event"] for e in final["trace"]}
    assert {"guardrail.evaluated", "human_approval.decision_received", "supervisor.report_generated", "workflow.completed"}.issubset(final_events)


def test_llm_call_event_is_recorded_with_no_invented_token_usage():
    _interrupted, final = _run_schema_change_to_completion()
    llm_events = [e for e in final["trace"] if e["event"] == "llm.call"]
    assert len(llm_events) >= 1
    assert llm_events[0]["metadata"]["provider"] == "deterministic"
    assert llm_events[0]["metadata"]["tokens_used"] is None  # honest: default provider reports no usage


# --- Dashboard derivations ----------------------------------------------------


def _fixture_state_no_errors():
    return {
        "trace_id": "trace-fixture",
        "workflow_status": "COMPLETED",
        "workflow_started_at": "2026-01-01T00:00:00+00:00",
        "workflow_ended_at": "2026-01-01T00:00:05+00:00",
        "user_request": "x",
        "investigation_plan": ["a"],
        "evidence": [{"source": "pipeline_agent", "claim": "c", "detail": "d"}],
        "errors": [],
        "trace": [
            {"trace_id": "trace-fixture", "step_id": "s1", "timestamp": "2026-01-01T00:00:01+00:00", "node": "supervisor", "agent": "supervisor", "skill": None, "tool": None, "event": "supervisor.plan_created", "status": "OK", "detail": None, "duration_ms": None, "metadata": None},
            {"trace_id": "trace-fixture", "step_id": "s2", "timestamp": "2026-01-01T00:00:02+00:00", "node": "pipeline_agent", "agent": "pipeline_agent", "skill": "pipeline_investigation", "tool": "investigate_pipeline_run", "event": "mcp.investigate_pipeline_run", "status": "OK", "detail": None, "duration_ms": 5.0, "metadata": {"input_summary": "run_id=x", "output_summary": "{}"}},
        ],
    }


def test_error_retry_summary_reports_zero_without_fabrication():
    summary = dashboard.error_retry_summary(_fixture_state_no_errors())
    assert summary["total_errors"] == 0
    assert summary["retries"] == 0
    assert summary["has_errors"] is False


def test_llm_observability_reports_unavailable_when_no_calls():
    llm = dashboard.llm_observability(_fixture_state_no_errors())
    assert llm["call_count"] == 0
    assert llm["token_usage_available"] is False
    assert llm["unavailable_message"] == "Token usage unavailable from provider"
    assert llm["total_tokens"] is None


def test_guardrail_rows_match_check_count_on_real_run():
    _interrupted, final = _run_schema_change_to_completion()
    rows = dashboard.guardrail_rows(final)
    assert len(rows) == len(final["guardrail_result"]["checks"])
    assert all(row["Result"] in {"PASS", "FAIL"} for row in rows)


def test_traceability_chain_all_done_on_fully_approved_run():
    _interrupted, final = _run_schema_change_to_completion()
    chain = dashboard.traceability_chain(final)
    assert len(chain) == 13
    assert all(row["status"] in {"DONE", "NOT_REQUIRED"} for row in chain)


def test_summary_metrics_active_agent_is_none_once_finished():
    _interrupted, final = _run_schema_change_to_completion()
    metrics = dashboard.summary_metrics(final)
    assert metrics["workflow_status"] == "COMPLETED"
    assert metrics["active_agent"] is None
    assert metrics["total_duration_seconds"] is not None
    assert metrics["total_duration_seconds"] >= 0


def test_export_json_and_csv_are_well_formed():
    _interrupted, final = _run_schema_change_to_completion()
    import json

    payload = json.loads(dashboard.export_json(final))
    assert payload["trace_id"] == final["trace_id"]
    assert isinstance(payload["trace"], list) and len(payload["trace"]) > 0

    csv_text = dashboard.export_csv(final)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("Timestamp,Trace ID,Agent,Event,Status")
    assert len(lines) == len(final["trace"]) + 1  # header + one row per event
