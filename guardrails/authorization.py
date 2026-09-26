"""Authorization Guardrail (CLAUDE.md sections 15, 17): agents may only use
tools permitted for their role. Enforced by hooks/pre_tool.py on every
mcp_server/client.py call -- this is not decorative, a violation raises
before the MCP server is ever reached.
"""
from __future__ import annotations

AGENT_TOOL_PERMISSIONS: dict[str, set[str]] = {
    "supervisor": set(),
    "pipeline_agent": {
        "investigate_pipeline_run",
        "get_pipeline_run_metadata",
        "get_previous_run_comparison",
    },
    "data_quality_agent": {"run_data_quality_checks", "compare_schema"},
    "knowledge_agent": {"search_approved_documents"},
    "root_cause_agent": set(),
    "validation_agent": {"get_pipeline_run_metadata"},
}


class AuthorizationError(PermissionError):
    pass


def check_authorization(agent: str, tool_name: str) -> None:
    allowed = AGENT_TOOL_PERMISSIONS.get(agent)
    if allowed is None:
        raise AuthorizationError(f"Unknown agent '{agent}' has no registered tool permissions.")
    if tool_name not in allowed:
        raise AuthorizationError(
            f"Agent '{agent}' is not authorized to call tool '{tool_name}'. "
            f"Allowed tools: {sorted(allowed) or 'none'}."
        )
