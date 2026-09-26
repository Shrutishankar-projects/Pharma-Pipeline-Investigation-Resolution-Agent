"""Knowledge / RAG Agent (CLAUDE.md section 10.3).

Retrieves approved documentation via hybrid (BM25 + dense + RRF) retrieval,
through the MCP layer. Never fabricates a document id, section, or citation
-- every result comes straight from skills/document_retrieval.
"""
from __future__ import annotations

from typing import Any

from mcp_server import client as mcp_client

AGENT_NAME = "knowledge_agent"


def _build_query(state: dict[str, Any]) -> str:
    pieces = [state.get("user_request", "")]
    failed_stage = (state.get("pipeline_findings") or {}).get("failed_stage")
    if failed_stage:
        pieces.append(f"failed stage {failed_stage}")
    schema = state.get("schema_findings") or {}
    if schema.get("compatibility") == "INCOMPATIBLE":
        pieces.append("schema column type change incompatible")
    dq = state.get("data_quality_findings") or {}
    if dq.get("overall_result") == "FAIL":
        pieces.append("data quality null duplicate threshold breach")
    return " ".join(p for p in pieces if p)


def investigate(state: dict[str, Any]) -> dict[str, Any]:
    trace_id = state["trace_id"]
    query = _build_query(state)

    result = mcp_client.call(AGENT_NAME, "search_approved_documents", question=query, _trace_id=trace_id)
    findings = result.data if result.ok else {"found": False, "error": result.error, "results": []}

    updates: dict[str, Any] = {
        "knowledge_findings": findings,
        "trace": [result.trace_event],
        "current_step": "knowledge_retrieval_complete",
    }
    if findings.get("found"):
        updates["evidence"] = [
            {
                "source": AGENT_NAME,
                "claim": f"Relevant documentation retrieved: {', '.join(findings.get('source_ids', []))}",
                "detail": [r["section"] for r in findings.get("results", [])],
            }
        ]
    return updates
