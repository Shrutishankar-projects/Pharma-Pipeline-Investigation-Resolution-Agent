"""Guardrail rules (CLAUDE.md section 15). Each function returns a small
dict {"passed": bool, "guardrail": name, "reason": str} so results can be
collected, logged, and shown verbatim on the Human Approval UI page.
"""
from __future__ import annotations

import re
from typing import Any

PROHIBITED_ACTION_TYPES = {
    "delete_pipeline_history",
    "drop_table",
    "truncate_table",
    "disable_monitoring",
    "bypass_data_quality_gate",
    "modify_production_credentials",
}

HIGH_IMPACT_ACTION_TYPES = {
    "rerun_pipeline",
    "apply_schema_mapping",
    "write_production_dataset",
}

_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-shaped
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email
    re.compile(r"\b\d{16}\b"),  # card-number-shaped
]

_PROMPT_INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard the system prompt",
    "you are now",
    "act as if",
    "override your instructions",
]


def evidence_guardrail(root_cause_analysis: dict[str, Any] | None, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """The system must not state a confirmed root cause without supporting evidence."""
    if root_cause_analysis and not root_cause_analysis.get("insufficient_evidence") and not evidence:
        return {
            "passed": False,
            "guardrail": "evidence_guardrail",
            "reason": "A root cause was proposed with zero supporting evidence items.",
        }
    return {"passed": True, "guardrail": "evidence_guardrail", "reason": "Root cause is backed by collected evidence."}


def hallucination_guardrail(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """If evidence is insufficient, the workflow must say so rather than guess."""
    if len(evidence) < 1:
        return {
            "passed": False,
            "guardrail": "hallucination_guardrail",
            "reason": "Insufficient evidence collected; a root cause must not be asserted.",
        }
    return {"passed": True, "guardrail": "hallucination_guardrail", "reason": "Sufficient evidence present."}


def source_guardrail(knowledge_findings: dict[str, Any] | None, approved_source_ids: set[str]) -> dict[str, Any]:
    """Only approved/known documents may be cited."""
    if not knowledge_findings or not knowledge_findings.get("found"):
        return {"passed": True, "guardrail": "source_guardrail", "reason": "No documentation was cited."}
    cited = set(knowledge_findings.get("source_ids", []))
    unknown = cited - approved_source_ids
    if unknown:
        return {
            "passed": False,
            "guardrail": "source_guardrail",
            "reason": f"Cited unapproved/unknown source id(s): {sorted(unknown)}.",
        }
    return {"passed": True, "guardrail": "source_guardrail", "reason": f"All cited sources approved: {sorted(cited)}."}


def prompt_injection_guardrail(knowledge_findings: dict[str, Any] | None) -> dict[str, Any]:
    """Retrieved documents are untrusted content -- flag (never execute) embedded instructions."""
    if not knowledge_findings or not knowledge_findings.get("found"):
        return {"passed": True, "guardrail": "prompt_injection_guardrail", "reason": "No retrieved content to scan."}
    flagged = []
    for result in knowledge_findings.get("results", []):
        text = result.get("passage", "").lower()
        if any(marker in text for marker in _PROMPT_INJECTION_MARKERS):
            flagged.append(result.get("source_id"))
    if flagged:
        return {
            "passed": False,
            "guardrail": "prompt_injection_guardrail",
            "reason": (
                f"Retrieved passage(s) from {flagged} contain instruction-like text. "
                "Treated as untrusted data only; not followed."
            ),
        }
    return {"passed": True, "guardrail": "prompt_injection_guardrail", "reason": "No embedded-instruction patterns found."}


def data_protection_guardrail(*texts: str) -> dict[str, Any]:
    """Do not expose sensitive/personal information in evidence or reports."""
    for text in texts:
        if not text:
            continue
        for pattern in _PII_PATTERNS:
            if pattern.search(text):
                return {
                    "passed": False,
                    "guardrail": "data_protection_guardrail",
                    "reason": "Potential sensitive/PII-shaped pattern detected in output text; blocked.",
                }
    return {"passed": True, "guardrail": "data_protection_guardrail", "reason": "No sensitive-data patterns detected."}


def execution_guardrail(action_type: str) -> dict[str, Any]:
    """Never permit destructive/prohibited operations, regardless of approval."""
    if action_type in PROHIBITED_ACTION_TYPES:
        return {
            "passed": False,
            "guardrail": "execution_guardrail",
            "reason": f"Action type '{action_type}' is prohibited and cannot be executed by any agent.",
        }
    return {"passed": True, "guardrail": "execution_guardrail", "reason": f"Action type '{action_type}' is permitted (controlled/simulated)."}


def classify_action(action_type: str) -> dict[str, Any]:
    """Action Guardrail: classify impact and whether human approval is required."""
    if action_type in PROHIBITED_ACTION_TYPES:
        return {"risk_level": "HIGH", "requires_approval": False, "blocked": True}
    if action_type in HIGH_IMPACT_ACTION_TYPES:
        return {"risk_level": "HIGH", "requires_approval": True, "blocked": False}
    return {"risk_level": "LOW", "requires_approval": False, "blocked": False}


def evaluate_all(
    *,
    action_type: str,
    root_cause_analysis: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    knowledge_findings: dict[str, Any] | None,
    approved_source_ids: set[str],
    report_text: str = "",
) -> dict[str, Any]:
    """Run every guardrail relevant at the pre-human-approval checkpoint."""
    checks = [
        evidence_guardrail(root_cause_analysis, evidence),
        hallucination_guardrail(evidence),
        source_guardrail(knowledge_findings, approved_source_ids),
        prompt_injection_guardrail(knowledge_findings),
        data_protection_guardrail(report_text),
        execution_guardrail(action_type),
    ]
    classification = classify_action(action_type)
    passed = all(c["passed"] for c in checks)
    return {
        "passed": passed,
        "checks": checks,
        "classification": classification,
        "requires_human_approval": classification["requires_approval"] and passed and not classification["blocked"],
        "blocked": classification["blocked"] or not passed,
    }
