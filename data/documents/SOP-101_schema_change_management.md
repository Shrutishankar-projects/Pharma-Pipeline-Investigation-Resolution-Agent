<!-- synthetic demo document -->
# SOP-101: Schema Change Management for Clinical Trial Data Pipelines

**Document ID:** SOP-101
**Version:** 3.2
**Owner:** Data Engineering Governance

## 1. Purpose
This SOP defines how upstream schema changes to clinical data capture systems
feeding the Clinical Trial Data Processing Pipeline (CLINTRIAL_ETL) must be
detected, evaluated, and remediated.

## 2. Detection
Section 2.1 — Every scheduled run must execute an automated schema validation
step (`data_quality_validation`) comparing the actual extracted schema to the
registered expected schema (`clinical_metrics_features_v2` and successors)
before the `data_transformation` stage executes.

Section 2.2 — A schema difference is classified as:
- **Additive** (new nullable column) — LOW risk, pipeline may proceed.
- **Type-changed** (a column's data type changed, e.g. FLOAT -> STRING) — HIGH
  risk. The transformation stage will typically fail on type coercion for
  existing consumers.
- **Removed column** — HIGH risk, must halt automatically.

## 3. Required Remediation for Type-Changed Columns
Section 3.1 — When a numeric result column type change is detected (such as
`lab_result_value` changing from FLOAT to STRING), Data Engineering must NOT
simply force-cast the column. A common cause is the source EDC (Electronic
Data Capture) system beginning to send **qualified/censored lab values** --
for example "BLQ" (below limit of quantification), "<0.05", or "ND" (not
detected) -- as free text in the numeric result field instead of using a
dedicated qualifier flag. Investigate the upstream lab-data feed change
first, since silent casting can corrupt downstream clinical metrics.

Section 3.2 — A pipeline rerun is only considered safe after either:
(a) the upstream EDC system reverts the offending column to the expected
numeric type and moves qualified-value flags into a dedicated qualifier
column (e.g. `lab_qualifier_code`), or
(b) an approved schema mapping/adapter is deployed to normalize the new
format before the `data_transformation` stage.

## 4. Approval Requirement
Section 4.1 — Any rerun of a pipeline that previously failed due to a schema
change is classified as a **high-impact action** and requires human approval
per the Human-in-the-Loop policy (see SOP-404).
