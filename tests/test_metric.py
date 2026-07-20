import pytest

from clineval.core.metric import (
    EvalContext,
    Metric,
    get_metrics,
    harmonic,
    macro_average,
    register_metric,
    set_prf,
)
from clineval.core.schema import MetricResult


def test_macro_average():
    per_doc = {"a": {"f1": 1.0}, "b": {"f1": 0.0}}
    assert macro_average(per_doc, ["f1"]) == {"f1": 0.5}
    assert macro_average({}, ["f1"]) == {"f1": 0.0}


def test_register_and_get_metrics():
    @register_metric("unit_test_task")
    class Dummy(Metric):
        name = "dummy"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={"n": float(len(records))})

    metrics = get_metrics("unit_test_task")
    assert [m.name for m in metrics] == ["dummy"]
    result = metrics[0].compute([1, 2, 3], EvalContext())
    assert result.aggregate["n"] == 3.0


def test_register_metric_is_idempotent_for_the_same_class():
    @register_metric("idempotent_task")
    class Dummy(Metric):
        name = "idempotent_dummy"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={})

    # Re-decorating the exact same class object must be a silent no-op, not a
    # duplicate-name error and not a second registry entry.
    same_cls = register_metric("idempotent_task")(Dummy)
    assert same_cls is Dummy
    names = [m.name for m in get_metrics("idempotent_task")]
    assert names == ["idempotent_dummy"]


def test_register_metric_rejects_duplicate_name_different_class():
    @register_metric("dup_name_task")
    class First(Metric):
        name = "dup"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={})

    with pytest.raises(ValueError):

        @register_metric("dup_name_task")
        class Second(Metric):
            name = "dup"

            def compute(self, records, context):
                return MetricResult(name=self.name, aggregate={})


def test_set_prf_perfect_partial_and_empty():
    # Perfect overlap.
    assert set_prf(["a", "b"], ["a", "b"]) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    # Disjoint sets -> everything wrong.
    assert set_prf(["a"], ["b"]) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    # Both empty -> a correct "nothing here" prediction scores 1.0 (zero_division=0).
    assert set_prf([], []) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    # Partial: predicted one of two gold -> perfect precision, half recall.
    partial = set_prf(["a", "b"], ["a"])
    assert partial["precision"] == 1.0
    assert partial["recall"] == 0.5
    assert partial["f1"] == harmonic(1.0, 0.5)


def test_set_prf_one_sided_empty():
    # Only the BOTH-empty case earns 1.0. When one side is empty and the other is
    # not, every metric is 0.0 (zero_division=0) — a spurious prediction against an
    # empty gold, or a missed gold against an empty prediction, both score 0.
    assert set_prf([], ["a"]) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    assert set_prf(["a"], []) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_set_prf_dedupes_via_sets():
    # Duplicate ids collapse (set semantics); counts are not inflated.
    result = set_prf(["a", "a", "b"], ["a", "a"])
    assert result == {"precision": 1.0, "recall": 0.5, "f1": harmonic(1.0, 0.5)}


def test_harmonic_formula():
    # Pin the 2·p·r/(p+r) formula against literals so a dropped/altered factor
    # (e.g. p·r/(p+r) = 1/3) would fail rather than pass tautologically.
    assert harmonic(0.0, 0.0) == 0.0
    assert harmonic(1.0, 1.0) == 1.0
    assert harmonic(0.5, 0.5) == 0.5
    assert harmonic(1.0, 0.5) == pytest.approx(2 / 3)
