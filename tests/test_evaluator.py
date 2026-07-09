from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
from clineval.core.schema import OntologyAlignment, PredictionRecord
import clineval.tasks.hpo_extraction  # noqa: F401  (registers metrics)


def test_evaluate_runs_registered_metrics(ontology):
    records = [
        PredictionRecord(id="r1", input_text="", gold_reference=["HP:0001250"],
                         system_output=["HP:0001250"])
    ]
    alignment = OntologyAlignment("v", "omim", 0, 0, [], "policy")
    result = evaluate(
        "hpo_extraction", records, EvalContext(ontology=ontology),
        dataset="synthetic", model="cached:x", timestamp="2026-07-09T00:00:00+00:00",
        alignment=alignment,
    )
    assert result.n_documents == 1
    names = {m.name for m in result.metrics}
    assert {"tier1_exact", "tier2_semantic", "tier3_clinical"} <= names
    assert result.metric("tier1_exact").aggregate["f1"] == 1.0
