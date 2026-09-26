"""Skill 5 -- Evidence Synthesis (CLAUDE.md section 11).

Input: multiple findings (pipeline, data quality, schema, knowledge).
Output: correlated evidence list, contradictions, investigation summary.

This skill only correlates -- it does not decide a root cause. That
judgment belongs to agents/root_cause_agent.py, which consumes this
skill's output. Keeping the split visible is part of demonstrating genuine
delegation rather than one large opaque step.
"""
from __future__ import annotations

from typing import Any


def run(
    pipeline_findings: dict[str, Any] | None,
    data_quality_findings: dict[str, Any] | None,
    schema_findings: dict[str, Any] | None,
    knowledge_findings: dict[str, Any] | None,
    previous_run_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    contradictions: list[str] = []

    if pipeline_findings and pipeline_findings.get("found"):
        evidence.append(
            {
                "source": "pipeline_agent",
                "claim": f"Run failed at stage '{pipeline_findings.get('failed_stage')}'",
                "detail": pipeline_findings.get("error_evidence") or "no explicit error lines captured",
            }
        )

    if schema_findings and schema_findings.get("found"):
        if schema_findings.get("compatibility") == "INCOMPATIBLE":
            evidence.append(
                {
                    "source": "data_quality_agent:schema_comparison",
                    "claim": "Upstream schema changed in an incompatible way",
                    "detail": {
                        "added": schema_findings.get("added_columns"),
                        "changed": schema_findings.get("changed_columns"),
                        "removed": schema_findings.get("removed_columns"),
                    },
                }
            )
        elif schema_findings.get("compatibility") == "COMPATIBLE_WITH_ADDITIONS":
            evidence.append(
                {
                    "source": "data_quality_agent:schema_comparison",
                    "claim": "Schema gained additive, non-breaking columns only",
                    "detail": schema_findings.get("added_columns"),
                }
            )

    if data_quality_findings and data_quality_findings.get("found"):
        if data_quality_findings.get("overall_result") == "FAIL":
            evidence.append(
                {
                    "source": "data_quality_agent:quality_checks",
                    "claim": "Data quality gate breached one or more thresholds",
                    "detail": data_quality_findings.get("anomalies"),
                }
            )
        else:
            evidence.append(
                {
                    "source": "data_quality_agent:quality_checks",
                    "claim": "Data quality checks passed against SOP-202 thresholds",
                    "detail": "no anomalies",
                }
            )
    elif data_quality_findings is not None and not data_quality_findings.get("found"):
        evidence.append(
            {
                "source": "data_quality_agent:quality_checks",
                "claim": "No dataset extract was available to check",
                "detail": data_quality_findings.get("error"),
            }
        )

    if knowledge_findings and knowledge_findings.get("found"):
        evidence.append(
            {
                "source": "knowledge_agent",
                "claim": f"Relevant documentation retrieved: {', '.join(knowledge_findings.get('source_ids', []))}",
                "detail": [r["section"] for r in knowledge_findings.get("results", [])],
            }
        )

    if previous_run_comparison and previous_run_comparison.get("found"):
        evidence.append(
            {
                "source": "pipeline_agent:previous_run_comparison",
                "claim": f"Previous run {previous_run_comparison.get('previous_run_id')} status was "
                f"{previous_run_comparison.get('previous_status')}",
                "detail": previous_run_comparison,
            }
        )

    # A simple, explicit contradiction check: schema says compatible but data
    # quality gate independently failed for schema-unrelated reasons, or vice
    # versa a schema break coexists with a clean DQ gate result.
    schema_incompatible = bool(schema_findings and schema_findings.get("compatibility") == "INCOMPATIBLE")
    dq_failed = bool(data_quality_findings and data_quality_findings.get("overall_result") == "FAIL")
    if schema_incompatible and not dq_failed and data_quality_findings and data_quality_findings.get("found"):
        contradictions.append(
            "Schema comparison found an incompatible change, but the data-quality gate on the same "
            "extract passed -- the failure is more likely load-stage type coercion than a data content defect."
        )

    summary = (
        f"{len(evidence)} evidence item(s) correlated across "
        f"{'pipeline, ' if pipeline_findings else ''}"
        f"{'schema, ' if schema_findings else ''}"
        f"{'data-quality, ' if data_quality_findings else ''}"
        f"{'knowledge' if knowledge_findings else ''} sources."
    )

    return {"evidence": evidence, "contradictions": contradictions, "summary": summary}
