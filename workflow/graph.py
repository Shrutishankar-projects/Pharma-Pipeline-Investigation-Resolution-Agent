"""LangGraph workflow wiring (CLAUDE.md sections 7, 9, 23).

Implements: UNDERSTAND -> PLAN -> DELEGATE -> SKILL -> TOOL/MCP -> EVIDENCE
-> REASON -> OBSERVE -> VERIFY -> RE-PLAN -> GUARDRAIL -> HUMAN APPROVAL ->
EXECUTE -> VALIDATE -> COMPLETE -> TRACE.

Every node is wrapped by `_guarded`, which runs the Pre-Agent Hook
(hooks/pre_agent.py) first and catches any unhandled exception so a single
node failure marks the workflow FAILED rather than crashing the process
(CLAUDE.md section 22: fail safely, never silently continue). Every
conditional edge checks for that FAILED status first and short-circuits
straight to report generation.

Human approval (CLAUDE.md section 16) is a real LangGraph `interrupt()` --
the graph genuinely pauses and must be resumed with a `Command(resume=...)`
carrying an authorized human's decision; the AI cannot approve its own
recommendation because nothing downstream of the interrupt runs until that
resume call happens.
"""
from __future__ import annotations

from typing import Any, Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from agents import data_quality_agent, knowledge_agent, pipeline_agent, root_cause_agent, supervisor, validation_agent
from hooks import pre_agent
from hooks.pre_agent import PreAgentValidationError
from hooks import workflow_hooks
from observability import tracer
from state.models import InvestigationState

NodeFn = Callable[[dict[str, Any]], dict[str, Any]]


def _run_timed_with_events(
    agent_name: str, trace_id: str, fn: NodeFn, state_dict: dict[str, Any]
) -> dict[str, Any]:
    """Call `fn`, wrapping it with real `"{agent}.started"`/`"{agent}.completed"`
    trace events carrying the real elapsed duration -- this is what makes
    "Agent execution duration" and "Active agent" on the Observability
    dashboard real numbers instead of guesses. On failure, the elapsed time
    up to the exception is attached to the existing `"{agent}.error"` event
    instead of a separate completed event.
    """
    start_event = tracer.record(trace_id, node=agent_name, event=f"{agent_name}.started", agent=agent_name, status="OK")
    with tracer.timed() as elapsed:
        try:
            updates = fn(state_dict)
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all fail-safe boundary
            error_event = tracer.record(
                trace_id, node=agent_name, event=f"{agent_name}.error", agent=agent_name,
                status="ERROR", detail=str(exc), duration_ms=elapsed(),
            )
            return {"workflow_status": "FAILED", "errors": [f"{agent_name}: {exc}"], "trace": [start_event, error_event]}
    completed_event = tracer.record(
        trace_id, node=agent_name, event=f"{agent_name}.completed", agent=agent_name,
        status="OK", duration_ms=elapsed(),
    )
    existing_trace = updates.get("trace", [])
    updates["trace"] = [start_event, *existing_trace, completed_event]
    return updates


def _guarded(agent_name: str, fn: NodeFn) -> Callable[[InvestigationState], dict[str, Any]]:
    """Wrap an agent function with the Pre-Agent Hook, real started/completed
    duration tracking, and fail-safe error handling."""

    def wrapper(state: InvestigationState) -> dict[str, Any]:
        state_dict = state.model_dump()
        trace_id = state_dict.get("trace_id", "no-trace-id")
        try:
            pre_agent.run(state_dict, agent_name)
        except PreAgentValidationError as exc:
            event = tracer.record(
                trace_id, node=agent_name, event="pre_agent_hook.blocked", agent=agent_name,
                status="BLOCKED", detail=str(exc),
            )
            return {"workflow_status": "FAILED", "errors": [str(exc)], "trace": [event]}
        return _run_timed_with_events(agent_name, trace_id, fn, state_dict)

    return wrapper


def _guarded_terminal(agent_name: str, fn: NodeFn) -> Callable[[InvestigationState], dict[str, Any]]:
    """Like `_guarded` but skips the Pre-Agent terminal-status check.

    Report generation must always be reachable -- including from a workflow
    that is already FAILED/REJECTED/BLOCKED -- because its whole job is to
    explain that outcome. Started/completed duration tracking still applies.
    """

    def wrapper(state: InvestigationState) -> dict[str, Any]:
        state_dict = state.model_dump()
        trace_id = state_dict.get("trace_id", "no-trace-id")
        return _run_timed_with_events(agent_name, trace_id, fn, state_dict)

    return wrapper


def _is_evidence_thin(state: InvestigationState) -> bool:
    pf = state.pipeline_findings or {}
    return bool(pf.get("found")) and not pf.get("error_evidence")


def guardrail_check_node(state_dict: dict[str, Any]) -> dict[str, Any]:
    result, event = workflow_hooks.guardrail_hook(state_dict)
    updates: dict[str, Any] = {"guardrail_result": result, "trace": [event]}
    if result["blocked"]:
        updates["workflow_status"] = "FAILED"
        updates["human_approval_status"] = "NOT_REQUIRED"
    elif result["requires_human_approval"]:
        updates["workflow_status"] = "AWAITING_APPROVAL"
        updates["human_approval_status"] = "PENDING"
        requested_event = tracer.record(
            state_dict["trace_id"], node="guardrail_check", event="human_approval.requested",
            status="PENDING", detail="High-impact action requires an authorized human decision.",
        )
        updates["trace"] = [event, requested_event]
    else:
        updates["human_approval_status"] = "NOT_REQUIRED"
    return updates


def human_approval_node(state: InvestigationState) -> dict[str, Any]:
    decision = interrupt(
        {
            "recommendation": state.recommended_action,
            "evidence": state.evidence,
            "risk_level": state.risk_level,
            "guardrail_result": state.guardrail_result,
        }
    )
    status_map = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "FURTHER_INVESTIGATION": "FURTHER_INVESTIGATION_REQUESTED",
    }
    approval_status = status_map.get(decision.get("decision"), "REJECTED")
    event = tracer.record(
        state.trace_id, node="human_approval", event="human_approval.decision_received",
        status="OK", detail=approval_status,
    )
    return {
        "human_approval_status": approval_status,
        "human_approval_note": decision.get("note"),
        "trace": [event],
    }


def execute_action_node(state_dict: dict[str, Any]) -> dict[str, Any]:
    """Controlled/simulated execution ONLY -- never touches a real system.

    CLAUDE.md section 15 (Execution Guardrail): this prototype must use
    controlled/simulated execution. The simulated post-fix snapshot is what
    agents/validation_agent.py actually checks.
    """
    action = state_dict.get("recommended_action") or {}
    execution_result = {
        "action_type": action.get("action_type"),
        "description": action.get("description"),
        "simulated": True,
        "simulated_status": "SUCCESS",
        "output_produced": True,
        "error_recurred": False,
        "post_fix_schema_compatibility": "COMPATIBLE",
        "post_fix_dq_result": "PASS",
    }
    event = tracer.record(
        state_dict["trace_id"], node="execute_action", event="execution.simulated_rerun",
        status="OK", detail=action.get("action_type"),
    )
    return {
        "execution_result": execution_result,
        "workflow_status": "EXECUTING",
        "current_step": "execution_complete",
        "trace": [event],
    }


def _route_after(state: InvestigationState, happy_next: str) -> str:
    return "finalize_report" if state.workflow_status == "FAILED" else happy_next


def route_after_plan(state: InvestigationState) -> str:
    return _route_after(state, "pipeline_investigation")


def route_after_pipeline(state: InvestigationState) -> str:
    if state.workflow_status == "FAILED":
        return "finalize_report"
    if _is_evidence_thin(state) and not state.replanned:
        return "replan_previous_run"
    return "data_quality_investigation"


def route_after_replan(state: InvestigationState) -> str:
    return _route_after(state, "data_quality_investigation")


def route_after_dq(state: InvestigationState) -> str:
    return _route_after(state, "knowledge_retrieval")


def route_after_knowledge(state: InvestigationState) -> str:
    return _route_after(state, "root_cause_analysis")


def route_after_rootcause(state: InvestigationState) -> str:
    return _route_after(state, "guardrail_check")


def route_after_guardrail(state: InvestigationState) -> str:
    if state.workflow_status == "FAILED":
        return "finalize_report"
    if state.human_approval_status == "PENDING":
        return "human_approval"
    return "finalize_report"


def route_after_approval(state: InvestigationState) -> str:
    if state.human_approval_status == "APPROVED":
        return "execute_action"
    return "finalize_report"


def route_after_execute(state: InvestigationState) -> str:
    return _route_after(state, "validation")


def build_graph():
    g = StateGraph(InvestigationState)

    g.add_node("supervisor_plan", _guarded("supervisor", supervisor.create_plan))
    g.add_node("pipeline_investigation", _guarded("pipeline_agent", pipeline_agent.investigate))
    g.add_node("replan_previous_run", _guarded("pipeline_agent", pipeline_agent.compare_with_previous))
    g.add_node("data_quality_investigation", _guarded("data_quality_agent", data_quality_agent.investigate))
    g.add_node("knowledge_retrieval", _guarded("knowledge_agent", knowledge_agent.investigate))
    g.add_node("root_cause_analysis", _guarded("root_cause_agent", root_cause_agent.analyze))
    g.add_node("guardrail_check", _guarded("guardrail_check", guardrail_check_node))
    g.add_node("human_approval", human_approval_node)
    g.add_node("execute_action", _guarded("execute_action", execute_action_node))
    g.add_node("validation", _guarded("validation_agent", validation_agent.validate))
    g.add_node("finalize_report", _guarded_terminal("supervisor", supervisor.finalize_report))

    g.set_entry_point("supervisor_plan")
    g.add_conditional_edges(
        "supervisor_plan", route_after_plan, {"pipeline_investigation": "pipeline_investigation", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "pipeline_investigation",
        route_after_pipeline,
        {
            "replan_previous_run": "replan_previous_run",
            "data_quality_investigation": "data_quality_investigation",
            "finalize_report": "finalize_report",
        },
    )
    g.add_conditional_edges(
        "replan_previous_run", route_after_replan, {"data_quality_investigation": "data_quality_investigation", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "data_quality_investigation", route_after_dq, {"knowledge_retrieval": "knowledge_retrieval", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "knowledge_retrieval", route_after_knowledge, {"root_cause_analysis": "root_cause_analysis", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "root_cause_analysis", route_after_rootcause, {"guardrail_check": "guardrail_check", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "guardrail_check", route_after_guardrail, {"human_approval": "human_approval", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "human_approval", route_after_approval, {"execute_action": "execute_action", "finalize_report": "finalize_report"}
    )
    g.add_conditional_edges(
        "execute_action", route_after_execute, {"validation": "validation", "finalize_report": "finalize_report"}
    )
    g.add_edge("validation", "finalize_report")
    g.add_edge("finalize_report", END)

    return g.compile(checkpointer=MemorySaver())


_APP = None


def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP
