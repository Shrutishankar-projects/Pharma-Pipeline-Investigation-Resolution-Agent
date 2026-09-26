from skills.document_retrieval import core


def test_schema_change_query_surfaces_sop_101():
    result = core.run("What should we do when a column type changes like lab_result_value?")
    assert result["found"] is True
    assert "SOP-101" in result["source_ids"]
    assert all(r["passage"] for r in result["results"])


def test_data_quality_query_surfaces_sop_202():
    result = core.run("What are the null rate and duplicate thresholds for data quality?")
    assert "SOP-202" in result["source_ids"]


def test_results_never_fabricate_a_source_id():
    result = core.run("infrastructure timeout")
    known_ids = {"SOP-101", "SOP-202", "RUNBOOK-301", "SOP-404", "SOP-500"}
    assert set(result["source_ids"]).issubset(known_ids)
