"""Post-Tool Hook (CLAUDE.md section 12).

Runs after every MCP tool dispatch. Builds the TraceEvent (tool name, agent,
timestamp, status, duration, error info) that mcp_server/client.py attaches
to workflow state, and writes the matching structured log line.
"""
from __future__ import annotations

from observability import tracer
from state.models import TraceEvent


def run(
    trace_id: str,
    agent_name: str,
    tool_name: str,
    skill_name: str | None,
    status: str,
    duration_ms: float,
    error: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
) -> TraceEvent:
    metadata = {}
    if input_summary:
        metadata["input_summary"] = input_summary
    if output_summary:
        metadata["output_summary"] = output_summary

    return tracer.record(
        trace_id,
        node=agent_name,
        event=f"mcp.{tool_name}",
        agent=agent_name,
        skill=skill_name,
        tool=tool_name,
        status=status,
        detail=error,
        duration_ms=duration_ms,
        metadata=metadata or None,
    )
