"""Schema comparison over synthetic Clinical Trial Data Processing Pipeline
(CLINTRIAL_ETL) schema fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHEMAS_DIR = DATA_DIR / "schemas"


def _load_schema(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {col["name"]: col for col in payload["columns"]}


def compare_schema(pipeline_id: str, run_id: str) -> dict[str, Any]:
    expected_file = SCHEMAS_DIR / f"{pipeline_id}_expected.json"
    if not expected_file.exists():
        return {"found": False, "error": f"No expected schema registered for pipeline_id={pipeline_id}"}

    expected = _load_schema(expected_file)

    actual_file = SCHEMAS_DIR / f"{run_id}_actual.json"
    if actual_file.exists():
        actual = _load_schema(actual_file)
        actual_source = "observed"
    else:
        # No drift-specific fixture recorded for this run: treat schema as matching.
        actual = expected
        actual_source = "assumed_matching_no_fixture"

    added = [name for name in actual if name not in expected]
    removed = [name for name in expected if name not in actual]
    changed = [
        {"column": name, "expected_type": expected[name]["type"], "actual_type": actual[name]["type"]}
        for name in expected
        if name in actual and expected[name]["type"] != actual[name]["type"]
    ]

    if removed or changed:
        compatibility = "INCOMPATIBLE"
    elif added:
        compatibility = "COMPATIBLE_WITH_ADDITIONS"
    else:
        compatibility = "COMPATIBLE"

    return {
        "found": True,
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "actual_source": actual_source,
        "added_columns": added,
        "removed_columns": removed,
        "changed_columns": changed,
        "compatibility": compatibility,
    }
