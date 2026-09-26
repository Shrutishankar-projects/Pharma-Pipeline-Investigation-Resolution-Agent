"""Read-only access to synthetic pipeline run metadata and execution logs.

CLAUDE.md section 4/28: this ONLY ever reads local synthetic fixture files
under data/. It never touches a real production system and never performs a
write. All data here is explicitly synthetic (see the `_synthetic` marker in
each fixture file).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUNS_DIR = DATA_DIR / "pipeline_runs"
LOGS_DIR = DATA_DIR / "logs"


def get_run_metadata(run_id: str) -> dict[str, Any]:
    """Return full synthetic run metadata, or an explicit not-found result."""
    run_file = RUNS_DIR / f"{run_id}.json"
    if not run_file.exists():
        return {"found": False, "run_id": run_id, "error": f"No pipeline run found for run_id={run_id}"}
    metadata = json.loads(run_file.read_text(encoding="utf-8"))
    metadata["found"] = True
    return metadata


def get_pipeline_status(run_id: str) -> dict[str, Any]:
    metadata = get_run_metadata(run_id)
    if not metadata.get("found"):
        return metadata
    return {
        "found": True,
        "pipeline_id": metadata["pipeline_id"],
        "run_id": metadata["run_id"],
        "status": metadata["status"],
        "failed_stage": metadata.get("failed_stage"),
        "start_time": metadata.get("start_time"),
        "end_time": metadata.get("end_time"),
    }


def get_pipeline_logs(run_id: str) -> dict[str, Any]:
    """Return the raw and line-split synthetic execution log for a run."""
    log_file = LOGS_DIR / f"{run_id}.log"
    if not log_file.exists():
        return {"found": False, "run_id": run_id, "error": f"No log file found for run_id={run_id}", "lines": []}
    raw = log_file.read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if line.strip()]
    error_lines = [line for line in lines if " ERROR " in line or line.strip().startswith("ERROR")]
    return {
        "found": True,
        "run_id": run_id,
        "raw": raw,
        "lines": lines,
        "error_lines": error_lines,
        "line_count": len(lines),
    }


def get_previous_run_comparison(run_id: str) -> dict[str, Any]:
    """Compare a run's metadata against its immediately preceding run."""
    current = get_run_metadata(run_id)
    if not current.get("found"):
        return {"found": False, "run_id": run_id, "error": current.get("error")}
    previous_run_id = current.get("previous_run_id")
    if not previous_run_id:
        return {"found": True, "run_id": run_id, "previous_run_id": None, "comparison": "no previous run on record"}
    previous = get_run_metadata(previous_run_id)
    return {
        "found": True,
        "run_id": run_id,
        "previous_run_id": previous_run_id,
        "previous_status": previous.get("status") if previous.get("found") else "unknown",
        "current_status": current.get("status"),
        "record_count_in_delta": _safe_delta(current.get("record_count_in"), previous.get("record_count_in")),
        "record_count_out_delta": _safe_delta(current.get("record_count_out"), previous.get("record_count_out")),
    }


def _safe_delta(a: Any, b: Any) -> Any:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a - b
    return None
