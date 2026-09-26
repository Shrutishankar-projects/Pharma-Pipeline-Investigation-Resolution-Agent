from skills.schema_comparison import core


def test_detects_type_change_and_added_column():
    result = core.run("CLINTRIAL_ETL", "2026-10-30-001")
    assert result["found"] is True
    assert "lab_qualifier_code" in result["added_columns"]
    changed = {c["column"]: c for c in result["changed_columns"]}
    assert changed["lab_result_value"]["expected_type"] == "FLOAT"
    assert changed["lab_result_value"]["actual_type"] == "STRING"
    assert result["compatibility"] == "INCOMPATIBLE"


def test_matching_schema_is_compatible():
    result = core.run("CLINTRIAL_ETL", "2026-10-23-001")
    assert result["compatibility"] == "COMPATIBLE"
    assert result["added_columns"] == []
    assert result["changed_columns"] == []


def test_unknown_pipeline_reports_not_found():
    result = core.run("UNKNOWN_PIPELINE", "2026-10-23-001")
    assert result["found"] is False
