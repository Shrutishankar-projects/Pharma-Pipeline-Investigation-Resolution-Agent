"""Validation Agent (CLAUDE.md section 10.5).

Validates the result after an approved, controlled/simulated action.
Clearly states PASS/FAIL for each check rather than a single opaque
boolean.
"""
from __future__ import annotations

from typing import Any

from observability import tracer
from tools import validation_tools

AGENT_NAME = "validation_agent"


def validate(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    execution_result = state.get("execution_result") or {}

    validation_result = validation_tools.validate_simulated_rerun(execution_result)

    event = tracer.record(
        trace_id,
        node=AGENT_NAME,
        event="validation_agent.completed",
        agent=AGENT_NAME,
        status="OK" if validation_result["overall_result"] == "PASS" else "BLOCKED",
        detail=validation_result["overall_result"],
    )

    return {
        "validation_result": validation_result,
        "trace": [event],
        "current_step": "validation_complete",
    }
