from clineval.core.schema import (
    EvaluationResult,
    MetricResult,
    OntologyAlignment,
    PredictionRecord,
)


def test_prediction_record_defaults():
    rec = PredictionRecord(id="r1", input_text="text", gold_reference=["HP:0001250"])
    assert rec.system_output == []
    assert rec.metadata == {}
    # defaults must be independent instances, not shared
    rec.system_output.append("HP:0000252")
    assert PredictionRecord(id="r2", input_text="", gold_reference=[]).system_output == []


def test_evaluation_result_holds_components():
    mr = MetricResult(name="tier1_exact", aggregate={"f1": 0.5})
    align = OntologyAlignment(
        hpo_version="2025-01-01", ic_basis="omim", alt_ids_resolved=1,
        obsolete_flagged=0, obsolete_ids=[], policy="p",
    )
    res = EvaluationResult(
        task="hpo_extraction", dataset="synthetic", n_documents=1, model="cached:x",
        timestamp="2026-07-09T00:00:00+00:00", metrics=[mr], alignment=align,
    )
    assert res.metrics[0].aggregate["f1"] == 0.5
    assert res.alignment.ic_basis == "omim"
