"""Pre-Agent Hook (CLAUDE.md section 12).

Runs before every agent node in workflow/graph.py. Validates required state
fields, that the workflow hasn't already reached a terminal status, and that
the request structure is well-formed -- fails fast and loud rather than
letting a downstream agent run against a malformed or already-finished
workflow.
"""
from __future__ import annotations

import re
from typing import Any

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_TERMINAL_STATUSES = {"COMPLETED", "REJECTED", "FAILED"}

REQUIRED_BEFORE_AGENT: dict[str, tuple[str, ...]] = {
    "pipeline_agent": ("trace_id", "pipeline_id", "run_id"),
    "data_quality_agent": ("trace_id", "pipeline_id", "run_id"),
    "knowledge_agent": ("trace_id", "user_request"),
    "root_cause_agent": ("trace_id",),
    "validation_agent": ("trace_id", "execution_result"),
    "supervisor": ("trace_id", "user_request"),
}


class PreAgentValidationError(ValueError):
    pass


def run(state: dict[str, Any], agent_name: str) -> None:
    if state.get("workflow_status") in _TERMINAL_STATUSES:
        raise PreAgentValidationError(
            f"Cannot run agent '{agent_name}': workflow already in terminal status "
            f"'{state.get('workflow_status')}'."
        )

    for field in REQUIRED_BEFORE_AGENT.get(agent_name, ()):
        if not state.get(field):
            raise PreAgentValidationError(
                f"Cannot run agent '{agent_name}': required state field '{field}' is missing/empty."
            )

    run_id = state.get("run_id")
    if run_id and not _RUN_ID_PATTERN.match(run_id):
        raise PreAgentValidationError(f"Invalid run_id format: {run_id!r}.")
