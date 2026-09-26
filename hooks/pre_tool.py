"""Pre-Tool Hook (CLAUDE.md section 12).

Runs before every MCP tool dispatch in mcp_server/client.py. Validates that
the calling agent is authorized for the tool (Authorization Guardrail),
that required arguments are present, and that any identifier argument is
within the approved character scope -- this specifically blocks path- or
injection-style values (e.g. "../secrets") from ever reaching the file
lookups in tools/*.py.
"""
from __future__ import annotations

import re
from typing import Any

from guardrails.authorization import check_authorization

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


class PreToolValidationError(ValueError):
    pass


def run(agent_name: str, tool_name: str, arguments: dict[str, Any]) -> None:
    check_authorization(agent_name, tool_name)

    if not arguments and tool_name != "search_approved_documents":
        raise PreToolValidationError(f"Tool '{tool_name}' called with no arguments.")

    for key, value in arguments.items():
        if not isinstance(value, str) or not value.strip():
            raise PreToolValidationError(f"Argument '{key}' for tool '{tool_name}' must be a non-empty string.")
        if key in {"run_id", "pipeline_id"} and not _SAFE_IDENTIFIER.match(value):
            raise PreToolValidationError(
                f"Argument '{key}'={value!r} is outside the approved scope (unsafe identifier)."
            )
