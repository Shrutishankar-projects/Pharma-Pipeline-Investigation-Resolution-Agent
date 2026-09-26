<!-- synthetic demo document -->
# SOP-404: Pipeline Rerun & Human Approval Policy

**Document ID:** SOP-404
**Version:** 4.0
**Owner:** Data Engineering Governance

## 1. Purpose
Defines which pipeline actions require human approval before execution.

## 2. High-Impact Actions
Section 2.1 — The following actions are classified as **high-impact** and
require explicit human approval before execution, regardless of
AI-assessed confidence:
- Rerunning a failed scheduled pipeline.
- Applying a schema mapping/adapter change.
- Any write operation against a production-designated clinical dataset.

Section 2.2 — The following actions are classified as **prohibited** for
any automated or AI agent, with no approval path: deleting pipeline
history, dropping or truncating tables, disabling monitoring/alerting, or
bypassing the data-quality gate.

## 3. Approval Process
Section 3.1 — An authorized human reviewer must review the investigation
summary, evidence, and recommended action, then respond with APPROVE,
REJECT, or REQUEST FURTHER INVESTIGATION.

Section 3.2 — An AI agent may never approve its own recommendation.
Approval must come from a human reviewer role.

Section 3.3 — If evidence is insufficient to support a recommendation, the
AI must report "insufficient evidence" rather than default to a rerun
recommendation.
