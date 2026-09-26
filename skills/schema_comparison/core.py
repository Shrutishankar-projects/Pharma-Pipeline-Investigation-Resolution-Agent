"""Skill 3 -- Schema Comparison (CLAUDE.md section 11).

Input: expected schema, actual schema (both resolved by pipeline/run id).
Output: added columns, removed columns, changed data types, compatibility assessment.
"""
from __future__ import annotations

from typing import Any

from tools import schema_tools


def run(pipeline_id: str, run_id: str) -> dict[str, Any]:
    return schema_tools.compare_schema(pipeline_id, run_id)
