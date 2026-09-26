from tools import data_quality_tools, pipeline_tools, schema_tools, validation_tools


def test_pipeline_tools_missing_run_reports_error_not_exception():
    result = pipeline_tools.get_run_metadata("no-such-run")
    assert result["found"] is False
    assert "error" in result


def test_pipeline_tools_previous_run_comparison():
    result = pipeline_tools.get_previous_run_comparison("2026-10-30-001")
    assert result["previous_run_id"] == "2026-10-23-001"
    assert result["previous_status"] == "SUCCESS"


def test_pipeline_tools_no_previous_run_on_record():
    result = pipeline_tools.get_previous_run_comparison("2026-10-02-001")
    assert result["previous_run_id"] is None


def test_data_quality_tools_missing_dataset_handled():
    result = data_quality_tools.run_data_quality_checks("2026-10-09-001")
    assert result["found"] is False


def test_schema_tools_missing_pipeline_handled():
    result = schema_tools.compare_schema("NOT_A_PIPELINE", "2026-10-23-001")
    assert result["found"] is False


def test_validation_tools_all_pass():
    execution_result = {
        "simulated_status": "SUCCESS",
        "output_produced": True,
        "error_recurred": False,
        "post_fix_schema_compatibility": "COMPATIBLE",
        "post_fix_dq_result": "PASS",
    }
    result = validation_tools.validate_simulated_rerun(execution_result)
    assert result["overall_result"] == "PASS"


def test_validation_tools_flags_failure():
    execution_result = {
        "simulated_status": "FAILED",
        "output_produced": False,
        "error_recurred": True,
        "post_fix_schema_compatibility": "INCOMPATIBLE",
        "post_fix_dq_result": "FAIL",
    }
    result = validation_tools.validate_simulated_rerun(execution_result)
    assert result["overall_result"] == "FAIL"
    assert all(c["result"] == "FAIL" for c in result["checks"])
