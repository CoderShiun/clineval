import pytest

from clineval.core.metric import (
    EvalContext,
    Metric,
    get_metrics,
    macro_average,
    register_metric,
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
