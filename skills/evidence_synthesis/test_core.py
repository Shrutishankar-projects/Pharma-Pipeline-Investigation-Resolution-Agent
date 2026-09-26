from skills.evidence_synthesis import core


def test_synthesizes_evidence_from_all_sources():
    pipeline = {"found": True, "failed_stage": "data_transformation", "error_evidence": ["CAST_ERROR"]}
    schema = {"found": True, "compatibility": "INCOMPATIBLE", "added_columns": ["lab_qualifier_code"], "changed_columns": [], "removed_columns": []}
    dq = {"found": True, "overall_result": "PASS", "anomalies": []}
    knowledge = {"found": True, "source_ids": ["SOP-101"], "results": [{"section": "3. Required Remediation"}]}

    result = core.run(pipeline, dq, schema, knowledge)
    assert len(result["evidence"]) == 4
    assert any("incompatible" in c.lower() for c in result["contradictions"])


def test_handles_missing_dataset_without_inventing_evidence():
    dq = {"found": False, "error": "No dataset extract available"}
    result = core.run(None, dq, None, None)
    assert any("No dataset extract" in str(e["detail"]) for e in result["evidence"])
