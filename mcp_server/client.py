"""Thin in-process MCP client wrapper (CLAUDE.md section 13).

This is the ONLY function agents call to reach data. It:
1. Runs the Pre-Tool Hook (authorization + input validation).
2. Dispatches the call through the real MCP protocol (`MCPServer.call_tool`,
   from the official `mcp` SDK) rather than importing skills/tools directly.
3. Runs the Post-Tool Hook to build the trace event + structured log line.

Every MCP operation is logged (section 13's "every MCP operation should be
logged" requirement) with no exceptions -- success and failure paths both
produce a TraceEvent.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from hooks import post_tool, pre_tool
from mcp_server.server import TOOL_TO_SKILL, server
from observability import tracer
from state.models import TraceEvent


class MCPCallResult:
    def __init__(self, data: dict[str, Any] | None, error: str | None, trace_event: TraceEvent):
        self.data = data
        self.error = error
        self.trace_event = trace_event

    @property
    def ok(self) -> bool:
        return self.error is None


def _parse_content(result) -> dict[str, Any]:
    if result.structured_content is not None:
        return result.structured_content
    for block in result.content:
        if hasattr(block, "text"):
            return json.loads(block.text)
    return {}


async def _call_async(tool_name: str, arguments: dict[str, Any]):
    return await server.call_tool(tool_name, arguments)


_SUMMARY_MAX_CHARS = 200


def _summarize_input(arguments: dict[str, Any]) -> str:
    """Short, safe preview of what was asked.

    Arguments here are always the already-hook-validated run_id/pipeline_id/
    question strings (hooks/pre_tool.py enforces this) -- never secret- or
    PII-bearing -- so a plain preview is safe to surface on the dashboard.
    """
    return ", ".join(f"{key}={value}" for key, value in arguments.items())[:_SUMMARY_MAX_CHARS]


def _summarize_output(data: dict[str, Any]) -> str:
    """Short, generic preview of what came back, truncated defensively."""
    preview = json.dumps(data, default=str)
    if len(preview) > _SUMMARY_MAX_CHARS:
        preview = preview[:_SUMMARY_MAX_CHARS] + "..."
    return preview


def call(agent_name: str, tool_name: str, **arguments: str) -> MCPCallResult:
    """Synchronous, hook-wrapped MCP tool call used by every agent."""
    skill_name = TOOL_TO_SKILL.get(tool_name)
    trace_id = arguments.pop("_trace_id", None) or "no-trace-id"
    input_summary = _summarize_input(arguments)

    with tracer.timed() as elapsed:
        try:
            pre_tool.run(agent_name, tool_name, arguments)
            result = asyncio.run(_call_async(tool_name, arguments))
            if result.is_error:
                error_text = "; ".join(getattr(b, "text", "") for b in result.content)
                event = post_tool.run(
                    trace_id, agent_name, tool_name, skill_name, "ERROR", elapsed(), error_text,
                    input_summary=input_summary,
                )
                return MCPCallResult(None, error_text or "Unknown MCP tool error", event)
            data = _parse_content(result)
            event = post_tool.run(
                trace_id, agent_name, tool_name, skill_name, "OK", elapsed(),
                input_summary=input_summary, output_summary=_summarize_output(data),
            )
            return MCPCallResult(data, None, event)
        except Exception as exc:  # authorization / validation / unexpected tool errors
            event = post_tool.run(
                trace_id, agent_name, tool_name, skill_name, "ERROR", elapsed(), str(exc),
                input_summary=input_summary,
            )
            return MCPCallResult(None, str(exc), event)
