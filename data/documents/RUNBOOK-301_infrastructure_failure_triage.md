<!-- synthetic demo document -->
# RUNBOOK-301: Infrastructure Failure Triage for Scheduled Pipelines

**Document ID:** RUNBOOK-301
**Version:** 1.4
**Owner:** Platform Reliability

## 1. Purpose
Guidance for triaging pipeline failures whose root cause is infrastructure
rather than clinical data content.

## 2. Signatures of Infrastructure Failure
Section 2.1 — Connection timeouts during the `extract_clinical_trial_source`
stage (e.g. `ConnectionTimeoutError` against the EDC source system) indicate
a network, EDC service availability, or connection-pool exhaustion issue,
not a data content problem.

Section 2.2 — When `record_count_in` is 0 and the failure occurs before any
extraction completes, the source clinical data itself cannot be implicated
-- no data was read. Do not attribute this failure category to data quality
or schema causes.

## 3. Recommended Response
Section 3.1 — Verify the EDC source system's health status out-of-band
before any rerun is attempted.

Section 3.2 — A rerun after an infrastructure failure is still classified
as a high-impact action (per SOP-404) but does NOT require a data or schema
fix first -- only confirmation that the connection/infrastructure issue has
cleared.

Section 3.3 — If two consecutive scheduled runs fail with the same
infrastructure signature, escalate to Platform Reliability on-call before
further reruns.
