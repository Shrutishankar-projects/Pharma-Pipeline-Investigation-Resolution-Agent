<!-- synthetic demo document -->
# SOP-202: Data Quality Thresholds for Clinical Trial Datasets

**Document ID:** SOP-202
**Version:** 2.1
**Owner:** Data Quality & Governance

## 1. Purpose
Defines the mandatory data-quality gate thresholds applied to CLINTRIAL_ETL
and related clinical trial data processing pipelines before the
`data_transformation` stage.

## 2. Thresholds
Section 2.1 — Null rate threshold: no required column may exceed a **2%
null rate**. `record_id`, `site_id`, and `subject_id` are required columns.

Section 2.2 — Duplicate rate threshold: duplicate `record_id` records may
not exceed **0.5%** of total records in a run.

Section 2.3 — Any breach of Section 2.1 or 2.2 is classified as a
**data_quality_validation FAIL** and the pipeline must halt before
transformation.

## 3. Root Cause Investigation
Section 3.1 — Null-rate breaches on `site_id` are most commonly caused by an
upstream site-reference-data synchronization failure between the Clinical
Trial Management System (CTMS) and the EDC export. Data Engineering should
check the site-mapping sync job before assuming a data-entry defect at the
site level.

Section 3.2 — Duplicate `record_id` breaches are most commonly caused by an
EDC export retry/resubmission mechanism re-sending the same query batch.
Check the EDC export job's idempotency key configuration.

## 4. Remediation Path
Section 4.1 — A data-quality gate failure does not require an
infrastructure fix. Recommended next step is to correct the upstream data
issue and rerun once thresholds are re-verified as passing. Reruns
following a data-quality failure remain a high-impact action requiring
approval per SOP-404.
