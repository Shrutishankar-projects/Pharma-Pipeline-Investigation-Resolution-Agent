"""MCP server exposing the approved resources/tools (CLAUDE.md section 13).

This is the ONLY place agents may reach pipeline data, logs, schemas,
data-quality checks, and approved documentation -- every tool here wraps a
Skill (skills/) which in turn wraps a read-only tools/*.py accessor over the
local synthetic data/ fixtures. No arbitrary shell execution, no writes, no
destructive operations are exposed, per section 13's explicit prohibitions.

NOTE ON NAMING: CLAUDE.md's suggested folder name for this layer is `mcp/`.
That literal name collides with the required `mcp` PyPI package (the actual
Model Context Protocol SDK imported below) once the project root is on
sys.path for the rest of the app's packages -- Python cannot have a local
package shadow the installed `mcp` library it needs to import. This
directory is therefore named `mcp_server/` instead; the responsibility
(section 13's MCP layer) is unchanged and documented in README.md.
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from skills.data_quality import core as data_quality_skill
from skills.document_retrieval import core as document_retrieval_skill
from skills.pipeline_investigation import core as pipeline_investigation_skill
from skills.schema_comparison import core as schema_comparison_skill
from tools import pipeline_tools

server = MCPServer(
    name="pharma-pipeline-investigator-mcp",
    description=(
        "Controlled access to synthetic pharmaceutical pipeline runs, logs, "
        "schemas, data-quality checks, and approved documentation."
    ),
)

# Maps each registered MCP tool name to the Skill it wraps, purely so the
# client layer (mcp_server/client.py) can record `skill=...` on the same
# trace event as `tool=...` -- one call, full Agent -> Skill -> Tool/MCP
# traceability (CLAUDE.md section 19).
TOOL_TO_SKILL: dict[str, str] = {}


def _register(name: str, skill_name: str | None, description: str):
    def decorator(fn):
        if skill_name:
            TOOL_TO_SKILL[name] = skill_name
        return server.tool(name=name, description=description)(fn)

    return decorator


@_register(
    "investigate_pipeline_run",
    "pipeline_investigation",
    "Retrieve pipeline run status, logs, failed stage, and error evidence for a run_id.",
)
def investigate_pipeline_run(run_id: str) -> dict[str, Any]:
    return pipeline_investigation_skill.run(run_id)


@_register(
    "get_pipeline_run_metadata",
    None,
    "Retrieve full raw metadata (record counts, timestamps, previous_run_id) for a run_id.",
)
def get_pipeline_run_metadata(run_id: str) -> dict[str, Any]:
    return pipeline_tools.get_run_metadata(run_id)


@_register(
    "get_previous_run_comparison",
    None,
    "Retrieve historical comparison against the immediately preceding run for a run_id.",
)
def get_previous_run_comparison(run_id: str) -> dict[str, Any]:
    return pipeline_tools.get_previous_run_comparison(run_id)


@_register(
    "run_data_quality_checks",
    "data_quality",
    "Execute data-quality checks (null rate, duplicate rate, type conformance) against SOP-202 thresholds for a run_id.",
)
def run_data_quality_checks(run_id: str) -> dict[str, Any]:
    return data_quality_skill.run(run_id)


@_register(
    "compare_schema",
    "schema_comparison",
    "Compare the actual extracted schema for a run against the registered expected schema for a pipeline_id.",
)
def compare_schema(pipeline_id: str, run_id: str) -> dict[str, Any]:
    return schema_comparison_skill.run(pipeline_id, run_id)


@_register(
    "search_approved_documents",
    "document_retrieval",
    "Hybrid (BM25 + dense + RRF) search over approved SOPs/runbooks for a natural-language investigation question.",
)
def search_approved_documents(question: str) -> dict[str, Any]:
    return document_retrieval_skill.run(question)
