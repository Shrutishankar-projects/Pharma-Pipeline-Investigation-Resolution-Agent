from skills.pipeline_investigation import core


def test_run_found_returns_error_evidence():
    result = core.run("2026-10-30-001")
    assert result["found"] is True
    assert result["status"] == "FAILED"
    assert result["failed_stage"] == "data_transformation"
    assert any("CAST_ERROR" in line for line in result["error_evidence"])


def test_run_not_found_reports_error_not_invented_data():
    result = core.run("does-not-exist")
    assert result["found"] is False
    assert "error" in result
