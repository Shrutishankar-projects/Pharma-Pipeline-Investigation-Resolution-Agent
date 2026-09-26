"""Streamlit UI for the Pharma Agentic Pipeline Investigator (CLAUDE.md section 27).

Eight pages backed by ONE real LangGraph workflow (workflow/graph.py):
Investigation -> Live Workflow -> Evidence -> Recommendation -> Human Approval
-> Trace -> Evaluation -> Observability & Traceability. All data shown
anywhere in this app is synthetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from langgraph.types import Command

from observability import dashboard
from state.models import InvestigationState
from workflow.graph import get_app

PIPELINES = ["CLINTRIAL_ETL"]
RUN_IDS = ["2026-10-30-001", "2026-10-16-001", "2026-10-09-001", "2026-10-02-001", "2026-10-23-001"]
DEFAULT_REQUEST = (
    "Investigate the failed Clinical Trial Data Processing Pipeline run {run_id}. Identify the "
    "likely cause, provide supporting evidence, check relevant documentation, and recommend the next action."
)

st.set_page_config(page_title="Pharma Agentic Pipeline Investigator", layout="wide")


@st.cache_resource
def _graph_app():
    return get_app()


def _init_session():
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("config", None)
    st.session_state.setdefault("history", [])


_init_session()


def _current() -> dict | None:
    return st.session_state.result


def _pending_approval() -> bool:
    result = _current()
    return bool(result and "__interrupt__" in result)


def _run_investigation(pipeline_id: str, run_id: str, user_request: str):
    app = _graph_app()
    state = InvestigationState(user_request=user_request, pipeline_id=pipeline_id, run_id=run_id)
    config = {"configurable": {"thread_id": state.trace_id}}
    result = app.invoke(state, config=config)
    st.session_state.config = config
    st.session_state.result = result


def _resume(decision: str, note: str = ""):
    app = _graph_app()
    config = st.session_state.config
    result = app.invoke(Command(resume={"decision": decision, "note": note}), config=config)
    st.session_state.result = result


st.sidebar.title("Pharma Agentic Pipeline Investigator")
st.sidebar.caption("Synthetic demo data only. No production systems are accessed.")
page = st.sidebar.radio(
    "Page",
    [
        "1. Investigation",
        "2. Live Workflow",
        "3. Evidence",
        "4. Recommendation",
        "5. Human Approval",
        "6. Trace",
        "7. Evaluation",
        "8. Observability & Traceability",
    ],
)

result = _current()
if result:
    st.sidebar.divider()
    st.sidebar.markdown(f"**Trace ID:** `{result.get('trace_id', 'n/a')}`")
    st.sidebar.markdown(f"**Workflow status:** `{result.get('workflow_status', 'n/a')}`")
    st.sidebar.markdown(f"**Human approval:** `{result.get('human_approval_status', 'n/a')}`")

# ---------------------------------------------------------------- Page 1 ----
if page == "1. Investigation":
    st.header("1. Investigation")
    st.write("Start a new pipeline investigation. All pipeline/run data below is synthetic demo data.")

    col1, col2 = st.columns(2)
    with col1:
        pipeline_id = st.selectbox("Pipeline", PIPELINES)
    with col2:
        run_id = st.selectbox("Run ID", RUN_IDS)

    user_request = st.text_area(
        "Investigation request",
        value=DEFAULT_REQUEST.format(run_id=run_id),
        height=100,
    )

    if st.button("Start Investigation", type="primary"):
        with st.spinner("Supervisor is planning and delegating to sub-agents..."):
            _run_investigation(pipeline_id, run_id, user_request)
        st.rerun()

    if result:
        st.success(f"Investigation `{result.get('trace_id')}` is at status `{result.get('workflow_status')}`.")
        if _pending_approval():
            st.info("This investigation is paused awaiting human approval -- see page 5.")

# ---------------------------------------------------------------- Page 2 ----
elif page == "2. Live Workflow":
    st.header("2. Live Workflow")
    if not result:
        st.warning("Start an investigation on page 1 first.")
    else:
        st.subheader("Current state")
        st.write(
            f"**Status:** {result.get('workflow_status')} &nbsp;&nbsp; "
            f"**Current step:** {result.get('current_step')} &nbsp;&nbsp; "
            f"**Re-planned:** {result.get('replanned', False)}"
        )
        st.subheader("Investigation plan")
        st.write(result.get("investigation_plan", []))

        st.subheader("Completed steps / tool calls (in order)")
        trace = result.get("trace", [])
        for event in trace:
            icon = {"OK": "✅", "ERROR": "❌", "BLOCKED": "🛑", "PENDING": "⏳"}.get(event.get("status"), "•")
            agent = event.get("agent") or event.get("node")
            skill = f" · skill={event['skill']}" if event.get("skill") else ""
            tool = f" · tool={event['tool']}" if event.get("tool") else ""
            duration = f" ({event['duration_ms']}ms)" if event.get("duration_ms") else ""
            st.write(f"{icon} `{event.get('event')}` — agent={agent}{skill}{tool}{duration}")

        if result.get("errors"):
            st.subheader("Errors")
            for err in result["errors"]:
                st.error(err)

# ---------------------------------------------------------------- Page 3 ----
elif page == "3. Evidence":
    st.header("3. Evidence")
    if not result:
        st.warning("Start an investigation on page 1 first.")
    else:
        st.subheader("Correlated evidence")
        for item in result.get("evidence", []):
            with st.expander(f"{item.get('source')}: {item.get('claim')}"):
                st.json(item.get("detail"))

        st.subheader("Data quality findings")
        st.json(result.get("data_quality_findings"))

        st.subheader("Schema findings")
        st.json(result.get("schema_findings"))

        st.subheader("Documentation findings (source-cited, hybrid BM25 + dense + RRF retrieval)")
        knowledge = result.get("knowledge_findings") or {}
        for r in knowledge.get("results", []):
            with st.expander(f"{r.get('source_id')} — {r.get('section')} (relevance={r.get('relevance_score')})"):
                st.write(r.get("passage"))

# ---------------------------------------------------------------- Page 4 ----
elif page == "4. Recommendation":
    st.header("4. Recommendation")
    if not result:
        st.warning("Start an investigation on page 1 first.")
    else:
        root_cause = result.get("root_cause_analysis") or {}
        if root_cause.get("insufficient_evidence"):
            st.warning("Insufficient evidence to conclude a root cause.")
        else:
            st.write(f"**Potential root cause:** {root_cause.get('potential_cause', 'N/A')}")
        st.write(f"**Confidence / uncertainty:** {root_cause.get('confidence_explanation', 'N/A')}")
        if root_cause.get("contradicting_evidence"):
            st.write("**Contradicting evidence:**")
            st.write(root_cause["contradicting_evidence"])

        st.subheader("Recommended action")
        st.json(result.get("recommended_action"))
        st.write(f"**Risk level:** {result.get('risk_level', 'N/A')}")

# ---------------------------------------------------------------- Page 5 ----
elif page == "5. Human Approval":
    st.header("5. Human Approval")
    if not result:
        st.warning("Start an investigation on page 1 first.")
    elif not _pending_approval():
        st.info(
            f"No approval currently pending. human_approval_status = "
            f"`{result.get('human_approval_status')}`."
        )
    else:
        payload = result["__interrupt__"][0].value
        st.subheader("Recommendation")
        st.json(payload.get("recommendation"))
        st.subheader("Evidence")
        st.json(payload.get("evidence"))
        st.subheader("Risk / Impact")
        st.write(payload.get("risk_level"))
        st.subheader("Guardrail result")
        st.json(payload.get("guardrail_result"))

        st.warning("The AI cannot approve its own recommendation. An authorized human must decide.")
        note = st.text_input("Approval note (optional)")
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ APPROVE", type="primary"):
            _resume("APPROVE", note)
            st.rerun()
        if c2.button("❌ REJECT"):
            _resume("REJECT", note)
            st.rerun()
        if c3.button("🔎 REQUEST FURTHER INVESTIGATION"):
            _resume("FURTHER_INVESTIGATION", note)
            st.rerun()

# ---------------------------------------------------------------- Page 6 ----
elif page == "6. Trace":
    st.header("6. Trace")
    if not result:
        st.warning("Start an investigation on page 1 first.")
    else:
        st.write(f"**Trace ID:** `{result.get('trace_id')}`")
        trace = result.get("trace", [])
        st.dataframe(
            [
                {
                    "step_id": e.get("step_id"),
                    "timestamp": e.get("timestamp"),
                    "node": e.get("node"),
                    "agent": e.get("agent"),
                    "skill": e.get("skill"),
                    "tool": e.get("tool"),
                    "event": e.get("event"),
                    "status": e.get("status"),
                    "duration_ms": e.get("duration_ms"),
                }
                for e in trace
            ],
            width="stretch",
        )
        if result.get("final_report"):
            st.subheader("Final report")
            st.json(result["final_report"])

# ---------------------------------------------------------------- Page 7 ----
elif page == "7. Evaluation":
    st.header("7. Evaluation")
    st.write("Runs the controlled evaluation dataset (evaluation/scenarios/*.json) against the real workflow.")
    if st.button("Run evaluation scenarios"):
        with st.spinner("Running all scenarios end-to-end..."):
            from evaluation.evaluator import run_all

            report = run_all()
        st.session_state["eval_report"] = report

    eval_report = st.session_state.get("eval_report")
    if eval_report:
        st.subheader("Per-scenario results")
        for r in eval_report["results"]:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            st.write(f"{status} — **{r['scenario_id']}** ({r['description']})")
            st.json(r["checks"])
        st.subheader("Aggregate metrics")
        st.json(eval_report["metrics"])

# ---------------------------------------------------------------- Page 8 ----
elif page == "8. Observability & Traceability":
    st.header("8. Observability & Traceability")
    if not result:
        st.warning("Start an investigation on page 1 first.")
    else:
        STATUS_ICON = {
            "DONE": "✅", "PASS": "✅", "OK": "✅",
            "PENDING": "⏳", "NOT_REQUIRED": "➖", "NOT_REACHED": "⬜",
            "BLOCKED": "🛑", "FAIL": "❌", "ERROR": "❌",
        }

        # --- 1. Observability summary ---
        st.subheader("Observability Summary")
        metrics = dashboard.summary_metrics(result)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trace ID", metrics["trace_id"])
        c1.metric("Active Agent", metrics["active_agent"] or "— (finished)")
        c2.metric("Workflow Status", metrics["workflow_status"])
        c2.metric("Human Approval", metrics["human_approval_status"])
        c3.metric("Total Duration", f"{metrics['total_duration_seconds']} sec" if metrics["total_duration_seconds"] is not None else "n/a")
        c3.metric("Agents", metrics["agent_count"])
        c4.metric("Tool / MCP Calls", metrics["tool_call_count"])
        c4.metric("Errors", metrics["error_count"])
        st.caption(
            f"Workflow started: `{metrics['workflow_started_at']}`  →  ended: `{metrics['workflow_ended_at']}`. "
            f"Completed agents: {', '.join(metrics['completed_agents']) or 'none'}. "
            "Tool Calls and MCP Calls are the same count in this architecture -- every tool access is dispatched through the MCP layer (mcp_server/client.py)."
        )

        # --- 2. Agent execution table ---
        st.subheader("Agent Execution Table")
        st.caption("Every row below is a real event emitted by the running workflow -- nothing here is pre-scripted.")
        st.dataframe(dashboard.agent_execution_rows(result), width="stretch")

        # --- 3. Tool / MCP observability ---
        st.subheader("Tool / MCP Observability")
        tool_rows = dashboard.tool_mcp_rows(result)
        if tool_rows:
            st.dataframe(tool_rows, width="stretch")
        else:
            st.info("No tool/MCP calls were made on this run.")

        # --- 4. Error and retry monitoring ---
        st.subheader("Error & Retry Monitoring")
        err = dashboard.error_retry_summary(result)
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Total Errors", err["total_errors"])
        e2.metric("Failed Tool Calls", err["failed_tool_call_count"])
        e3.metric("Retries", err["retries"])
        e4.metric("Workflow Interruptions", err["workflow_interruptions"])
        if not err["has_errors"]:
            st.success("No errors recorded.")
        else:
            for msg in err["error_messages"]:
                st.error(msg)
            st.write(f"Failed agents: {', '.join(err['failed_agents']) or 'none'}")
        st.caption("Retries are reported as 0 because this prototype implements no automatic retry logic -- a failed node marks the workflow FAILED rather than being silently retried.")

        # --- 5. Model / token observability ---
        st.subheader("Model / Token Observability")
        llm = dashboard.llm_observability(result)
        st.write(f"**Number of LLM/model calls:** {llm['call_count']}")
        if llm["calls"]:
            st.dataframe(llm["calls"], width="stretch")
        if llm["token_usage_available"]:
            st.write(f"**Total tokens:** {llm['total_tokens']}")
        else:
            st.info(llm["unavailable_message"] or "Token usage unavailable from provider")

        # --- 6. Traceability dashboard ---
        st.subheader("Traceability Dashboard")
        chain = dashboard.traceability_chain(result)
        chain_lines = [f"{STATUS_ICON.get(row['status'], '•')} {row['step']}  _(​{row['status']})_" for row in chain]
        st.markdown("\n\n↓\n\n".join(chain_lines))

        # --- 14. Capstone traceability requirement (reuses the same chain) ---
        required_chain = [r["step"] for r in chain]
        done_count = sum(1 for r in chain if r["status"] in {"DONE", "NOT_REQUIRED"})
        st.caption(
            f"Required chain coverage: {done_count}/{len(chain)} steps reached "
            "(User Request → Agent Plan → Agent/Sub-agent → Skill → Tool/MCP → Evidence/Data → "
            "Action → Guardrail Check → Human Approval → Final Output)."
        )

        # --- 13. Guardrail visibility ---
        st.subheader("Guardrail Visibility")
        g_rows = dashboard.guardrail_rows(result)
        if g_rows:
            st.dataframe(g_rows, width="stretch")
        else:
            st.info("No guardrail checks were recorded for this run.")

        # --- 7. Evidence trace ---
        st.subheader("Evidence Trace")
        for item in dashboard.evidence_trace(result):
            with st.expander(f"Conclusion: {item['conclusion']}"):
                st.write(f"**Source:** {item['source']}  |  **Agent:** {item['agent']}")
                st.write("**Supporting evidence:**")
                st.json(item["supporting_detail"])
                st.write("**Produced by (tool/MCP + timestamp):**")
                st.json(item["produced_by"])

        # --- 12. Human approval (AI vs human decisions) ---
        st.subheader("Human Approval Event")
        st.write(
            f"🤖 **AI-generated recommendation:** {(result.get('recommended_action') or {}).get('description', 'n/a')}"
        )
        st.write(f"🧑 **Human decision:** {metrics['human_approval_status']}"
                 + (f" — note: {metrics['human_approval_note']}" if metrics["human_approval_note"] else ""))

        # --- 9. Audit trail ---
        with st.expander("Audit Trail (chronological, full detail)"):
            for row in dashboard.audit_trail_rows(result):
                icon = "🧑" if row["actor"] == "HUMAN" else "🤖"
                st.write(
                    f"{icon} `{row['timestamp']}` **{row['friendly_label']}** "
                    f"(agent={row['agent']}, status={row['status']})"
                )
                if row["detail"] or row["metadata"]:
                    st.caption(f"detail={row['detail']}  metadata={row['metadata']}")

        # --- 10. Export ---
        st.subheader("Export")
        exp1, exp2 = st.columns(2)
        exp1.download_button(
            "⬇ Download trace/audit as JSON",
            data=dashboard.export_json(result),
            file_name=f"{metrics['trace_id']}_trace.json",
            mime="application/json",
        )
        exp2.download_button(
            "⬇ Download agent execution table as CSV",
            data=dashboard.export_csv(result),
            file_name=f"{metrics['trace_id']}_events.csv",
            mime="text/csv",
        )
