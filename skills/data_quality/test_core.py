from skills.data_quality import core


def test_dq_failure_run_flags_null_and_duplicate_anomalies():
    result = core.run("2026-10-16-001")
    assert result["found"] is True
    assert result["overall_result"] == "FAIL"
    assert result["anomaly_count"] >= 2


def test_clean_run_passes():
    result = core.run("2026-10-23-001")
    assert result["found"] is True
    assert result["overall_result"] == "PASS"


def test_missing_dataset_reports_not_found_without_inventing_data():
    result = core.run("2026-10-09-001")
    assert result["found"] is False
    assert "error" in result
