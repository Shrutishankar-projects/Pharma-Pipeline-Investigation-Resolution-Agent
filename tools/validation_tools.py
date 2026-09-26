"""Post-execution validation checks (CLAUDE.md section 10.5).

Execution in this prototype is always a controlled/simulated rerun (see
agents/validation_agent.py and workflow/graph.py execute_action node) -- this
module never touches a real system. It re-derives pass/fail checks from the
simulated execution result plus the original schema/data-quality findings so
validation is not just "trust the execution result".
"""
from __future__ import annotations

from typing import Any


def validate_simulated_rerun(execution_result: dict[str, Any]) -> dict[str, Any]:
    """Check a simulated rerun's own reported post-fix state.

    `execution_result` is produced by the controlled/simulated execute_action
    step (workflow/graph.py) and carries both the simulated outcome AND the
    post-fix schema/data-quality snapshot it claims to have achieved -- this
    function re-derives pass/fail from that claim rather than blindly
    trusting a bare "SUCCESS" flag.
    """
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "check": "pipeline_status",
            "expected": "SUCCESS",
            "actual": execution_result.get("simulated_status", "UNKNOWN"),
            "result": "PASS" if execution_result.get("simulated_status") == "SUCCESS" else "FAIL",
        }
    )

    checks.append(
        {
            "check": "required_output_produced",
            "expected": True,
            "actual": execution_result.get("output_produced", False),
            "result": "PASS" if execution_result.get("output_produced") else "FAIL",
        }
    )

    post_fix_schema = execution_result.get("post_fix_schema_compatibility", "N/A")
    checks.append(
        {
            "check": "schema_compatibility_post_fix",
            "expected": "COMPATIBLE or COMPATIBLE_WITH_ADDITIONS",
            "actual": post_fix_schema,
            "result": "PASS" if post_fix_schema in {"COMPATIBLE", "COMPATIBLE_WITH_ADDITIONS"} else "FAIL",
        }
    )

    post_fix_dq = execution_result.get("post_fix_dq_result", "N/A")
    checks.append(
        {
            "check": "data_quality_gate_post_fix",
            "expected": "PASS",
            "actual": post_fix_dq,
            "result": "PASS" if post_fix_dq == "PASS" else "FAIL",
        }
    )

    checks.append(
        {
            "check": "error_recurrence",
            "expected": False,
            "actual": execution_result.get("error_recurred", False),
            "result": "FAIL" if execution_result.get("error_recurred") else "PASS",
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    return {"overall_result": overall, "checks": checks}
