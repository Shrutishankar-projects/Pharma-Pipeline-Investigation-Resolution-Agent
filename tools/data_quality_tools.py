"""Data-quality checks over synthetic Clinical Trial Data Processing Pipeline
(CLINTRIAL_ETL) datasets.

Thresholds are sourced from SOP-202 (null_rate <= 2%, duplicate_rate <= 0.5%
on required columns) -- see data/documents/SOP-202_data_quality_thresholds.md.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATASETS_DIR = DATA_DIR / "datasets"

REQUIRED_COLUMNS = ["record_id", "site_id", "subject_id"]
NULL_RATE_THRESHOLD = 0.02
DUPLICATE_RATE_THRESHOLD = 0.005


def _load_rows(run_id: str) -> list[dict[str, str]] | None:
    dataset_file = DATASETS_DIR / f"{run_id}.csv"
    if not dataset_file.exists():
        return None
    with dataset_file.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _is_float_parseable(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def run_data_quality_checks(run_id: str) -> dict[str, Any]:
    rows = _load_rows(run_id)
    if rows is None:
        return {
            "found": False,
            "run_id": run_id,
            "error": (
                f"No dataset extract available for run_id={run_id} "
                "(likely because extraction never completed)."
            ),
            "checks": [],
        }

    total = len(rows)
    checks: list[dict[str, Any]] = []

    for column in REQUIRED_COLUMNS:
        null_count = sum(1 for row in rows if not row.get(column, "").strip())
        null_rate = round(null_count / total, 4) if total else 0.0
        checks.append(
            {
                "check": f"null_rate:{column}",
                "expected": f"<= {NULL_RATE_THRESHOLD:.1%}",
                "actual": f"{null_rate:.1%}",
                "result": "PASS" if null_rate <= NULL_RATE_THRESHOLD else "FAIL",
                "evidence": f"{null_count}/{total} rows missing '{column}'",
                "severity": "HIGH" if null_rate > NULL_RATE_THRESHOLD else "NONE",
            }
        )

    record_ids = [row.get("record_id", "") for row in rows]
    duplicate_count = len(record_ids) - len(set(record_ids))
    duplicate_rate = round(duplicate_count / total, 4) if total else 0.0
    checks.append(
        {
            "check": "duplicate_rate:record_id",
            "expected": f"<= {DUPLICATE_RATE_THRESHOLD:.1%}",
            "actual": f"{duplicate_rate:.1%}",
            "result": "PASS" if duplicate_rate <= DUPLICATE_RATE_THRESHOLD else "FAIL",
            "evidence": f"{duplicate_count} duplicate record_id rows out of {total}",
            "severity": "HIGH" if duplicate_rate > DUPLICATE_RATE_THRESHOLD else "NONE",
        }
    )

    type_issue_count = sum(
        1 for row in rows if row.get("lab_result_value") and not _is_float_parseable(row["lab_result_value"])
    )
    if type_issue_count:
        checks.append(
            {
                "check": "type_conformance:lab_result_value",
                "expected": "FLOAT-parseable values",
                "actual": f"{type_issue_count} non-numeric values",
                "result": "FAIL",
                "evidence": "Qualified/censored lab result values (e.g. 'BLQ', '<0.05', 'ND') found in extract",
                "severity": "MEDIUM",
            }
        )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    return {
        "found": True,
        "run_id": run_id,
        "record_count": total,
        "overall_result": overall,
        "checks": checks,
    }
