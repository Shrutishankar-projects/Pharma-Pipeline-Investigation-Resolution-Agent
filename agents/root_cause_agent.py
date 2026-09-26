"""Root Cause Analysis Agent (CLAUDE.md section 10.4).

Correlates findings from the other agents (via the Evidence Synthesis
skill) and proposes a potential root cause -- using the language mandated
by section 10.4 ("Evidence indicates...", "Potential cause...",
"Insufficient evidence to conclude...") rather than asserting certainty.

No MCP calls here: this agent only reasons over findings already collected
by pipeline_agent / data_quality_agent / knowledge_agent, which is why it
has zero tool permissions in guardrails/authorization.py.
"""
from __future__ import annotations

from typing import Any

from llm.provider import get_llm_provider
from observability import tracer
from skills.evidence_synthesis import core as evidence_synthesis_skill

AGENT_NAME = "root_cause_agent"

_INFRA_MARKERS = ("timeout", "connection", "oom", "unavailable", "out of memory")


def _classify(
    pipeline_findings: dict[str, Any] | None,
    schema_findings: dict[str, Any] | None,
    data_quality_findings: dict[str, Any] | None,
) -> dict[str, Any] | None:
    schema = schema_findings or {}
    dq = data_quality_findings or {}
    pf = pipeline_findings or {}

    if schema.get("found") and schema.get("compatibility") == "INCOMPATIBLE":
        return {
            "category": "schema_change",
            "cause": "Upstream schema change caused a column type mismatch at the load stage.",
            "action_type": "rerun_pipeline",
            "action_description": (
                "Apply an approved schema mapping/adapter for the changed column(s) (or wait for the "
                "upstream source to revert the type), then rerun the pipeline, per SOP-101 section 3."
            ),
        }

    if dq.get("found") and dq.get("overall_result") == "FAIL":
        return {
            "category": "data_quality",
            "cause": "A data-quality gate breach (null-rate and/or duplicate-rate threshold violation) halted the run.",
            "action_type": "rerun_pipeline",
            "action_description": (
                "Correct the upstream data issue (site reference-data sync / EDC export idempotency key) "
                "and rerun once thresholds pass, per SOP-202 section 4."
            ),
        }

    error_text = " ".join(pf.get("error_evidence", []) or []).lower()
    if any(marker in error_text for marker in _INFRA_MARKERS):
        return {
            "category": "infrastructure",
            "cause": "The failure signature indicates an infrastructure/connectivity issue, not a data content defect.",
            "action_type": "rerun_pipeline",
            "action_description": (
                "Confirm source system connectivity/health out-of-band, then rerun, per RUNBOOK-301 section 3. "
                "No source data or schema fix is implicated."
            ),
        }

    return None


def analyze(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    pipeline_findings = state.get("pipeline_findings")
    schema_findings = state.get("schema_findings")
    data_quality_findings = state.get("data_quality_findings")
    knowledge_findings = state.get("knowledge_findings")
    evidence = state.get("evidence", [])

    synthesis = evidence_synthesis_skill.run(
        pipeline_findings, data_quality_findings, schema_findings, knowledge_findings
    )
    classification = _classify(pipeline_findings, schema_findings, data_quality_findings)

    llm = get_llm_provider()

    if classification is None:
        with tracer.timed() as elapsed:
            response = llm.reason(
                task="root_cause_analysis",
                context={"evidence_count": len(evidence), "contradictions": synthesis["contradictions"]},
                instructions="Insufficient evidence to conclude a root cause. Request additional investigation.",
            )
        llm_duration_ms = elapsed()
        root_cause_analysis = {
            "insufficient_evidence": True,
            "potential_cause": None,
            "contradicting_evidence": synthesis["contradictions"],
            "confidence_explanation": response.text,
        }
        recommended_action = {
            "action_type": "request_further_investigation",
            "description": "Insufficient evidence to safely recommend a rerun. Escalate for manual investigation.",
        }
        risk_level = "LOW"
    else:
        with tracer.timed() as elapsed:
            response = llm.reason(
                task="root_cause_analysis",
                context={"category": classification["category"], "evidence_count": len(evidence)},
                instructions=f"Evidence indicates: {classification['cause']}",
            )
        llm_duration_ms = elapsed()
        root_cause_analysis = {
            "insufficient_evidence": False,
            "potential_cause": classification["cause"],
            "category": classification["category"],
            "supporting_evidence": evidence,
            "contradicting_evidence": synthesis["contradictions"],
            "confidence_explanation": response.text,
        }
        recommended_action = {
            "action_type": classification["action_type"],
            "description": classification["action_description"],
        }
        risk_level = "HIGH"

    llm_event = tracer.record(
        trace_id,
        node=AGENT_NAME,
        event="llm.call",
        agent=AGENT_NAME,
        status="OK",
        duration_ms=llm_duration_ms,
        metadata={
            "provider": response.provider,
            "model": response.model,
            "tokens_used": response.tokens_used,
            "task": "root_cause_analysis",
        },
    )
    event = tracer.record(
        trace_id,
        node=AGENT_NAME,
        event="root_cause_agent.completed",
        agent=AGENT_NAME,
        skill="evidence_synthesis",
        status="OK",
        detail=root_cause_analysis.get("potential_cause") or "insufficient_evidence",
    )

    return {
        "root_cause_analysis": root_cause_analysis,
        "recommended_action": recommended_action,
        "risk_level": risk_level,
        "trace": [llm_event, event],
        "current_step": "root_cause_analysis_complete",
    }
