import pytest

from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext, Metric, register_metric
from clineval.core.schema import MetricResult, OntologyAlignment, PredictionRecord
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


def test_evaluate_raises_for_task_with_no_registered_metrics():
    alignment = OntologyAlignment("v", "omim", 0, 0, [], "policy")
    with pytest.raises(ValueError):
        evaluate(
            "no_such_task", [], EvalContext(),
            dataset="d", model="m", timestamp="t",
            alignment=alignment,
        )


def test_evaluate_without_alignment_carries_provenance():
    # A non-HPO task (no ontology) evaluates without an OntologyAlignment and
    # instead records task-agnostic run provenance (tool versions, cache stats).
    @register_metric("provenance_test_task")
    class _ProvMetric(Metric):
        name = "provenance_test_metric"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={"n": float(len(records))})

    rec = PredictionRecord(id="v1", input_text="", gold_reference=["1"])
    result = evaluate(
        "provenance_test_task", [rec], EvalContext(),
        dataset="ryr1", model="cached", timestamp="2026-07-20T00:00:00+00:00",
        provenance={"vvdb_version": "vvdb_2025_3"},
    )
    assert result.alignment is None
    assert result.provenance == {"vvdb_version": "vvdb_2025_3"}
    assert result.metric("provenance_test_metric").aggregate["n"] == 1.0


def test_evaluate_defaults_provenance_to_empty_dict():
    # When neither alignment nor provenance is supplied, provenance is an empty dict
    # (not None) so report renderers can iterate it unconditionally. Self-contained:
    # registers its own metric rather than depending on another test's registration.
    @register_metric("provenance_default_task")
    class _DefaultMetric(Metric):
        name = "provenance_default_metric"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={})

    alignment = OntologyAlignment("v", "omim", 0, 0, [], "policy")
    result = evaluate(
        "provenance_default_task", [], EvalContext(),
        dataset="d", model="m", timestamp="t", alignment=alignment,
    )
    assert result.provenance == {}
    assert result.alignment is alignment


def test_evaluate_minimal_retrieval_call_omits_both():
    # The minimal call a non-ontology (retrieval) task makes: neither alignment
    # nor provenance -> alignment None and provenance an empty dict.
    @register_metric("minimal_task")
    class _MinMetric(Metric):
        name = "minimal_metric"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={})

    result = evaluate(
        "minimal_task", [], EvalContext(), dataset="d", model="m", timestamp="t"
    )
    assert result.alignment is None
    assert result.provenance == {}
