"""Skill 1 -- Pipeline Investigation (CLAUDE.md section 11).

Input: pipeline/run identifier.
Output: status, logs, failed stage, error evidence.

Independently testable/callable without any agent -- see test_core.py.
"""
from __future__ import annotations

from typing import Any

from tools import pipeline_tools


def run(run_id: str) -> dict[str, Any]:
    status = pipeline_tools.get_pipeline_status(run_id)
    if not status.get("found"):
        return {"found": False, "run_id": run_id, "error": status.get("error")}

    logs = pipeline_tools.get_pipeline_logs(run_id)

    return {
        "found": True,
        "run_id": run_id,
        "pipeline_id": status["pipeline_id"],
        "status": status["status"],
        "failed_stage": status.get("failed_stage"),
        "start_time": status.get("start_time"),
        "end_time": status.get("end_time"),
        "log_line_count": logs.get("line_count", 0),
        "error_evidence": logs.get("error_lines", []),
        "raw_log_available": logs.get("found", False),
    }
