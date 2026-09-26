"""Skill 2 -- Data Quality Analysis (CLAUDE.md section 11).

Input: dataset/run identifier.
Output: quality checks, thresholds, anomalies.
"""
from __future__ import annotations

from typing import Any

from tools import data_quality_tools


def run(run_id: str) -> dict[str, Any]:
    result = data_quality_tools.run_data_quality_checks(run_id)
    if not result.get("found"):
        return result

    anomalies = [c for c in result["checks"] if c["result"] == "FAIL"]
    return {
        **result,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "thresholds": {
            "null_rate": data_quality_tools.NULL_RATE_THRESHOLD,
            "duplicate_rate": data_quality_tools.DUPLICATE_RATE_THRESHOLD,
        },
    }
