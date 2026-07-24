import pytest

import clineval.tasks.variant_retrieval  # noqa: F401  (registers the retrieval metric)
from clineval.core.metric import EvalContext, get_metrics
from clineval.core.schema import PredictionRecord
from clineval.tasks.variant_retrieval.metrics import RetrievalMetric


def _rec(rid, gold, pred, resolved=True):
    return PredictionRecord(
        id=rid, input_text=rid, gold_reference=gold, system_output=pred,
        metadata={"resolved": resolved},
    )


def test_retrieval_metric_per_doc_counts_and_macro():
    records = [
        _rec("v1", ["1", "2"], ["1", "2", "9"]),   # recall 1.0, precision 2/3, one extra
        _rec("v2", ["3", "4"], ["3"]),             # recall 0.5, precision 1.0, one missed
    ]
    result = RetrievalMetric().compute(records, EvalContext())
    v1 = result.per_document["v1"]
    assert v1["recall"] == 1.0 and v1["found_n"] == 2.0 and v1["extra_n"] == 1.0 and v1["missed_n"] == 0.0
    assert result.per_document["v2"]["missed_n"] == 1.0 and result.per_document["v2"]["precision"] == 1.0
    assert result.aggregate["recall"] == 0.75         # macro mean of 1.0 and 0.5
    assert result.aggregate["mean_yield"] == 2.0       # (3 + 1) / 2
    assert result.details["missed"]["v2"] == ["4"]     # the clinically important miss


def test_retrieval_metric_macro_precision_and_f1():
    # v1: perfect; v2: gold{3,4} pred{3,4,5,6} -> P=0.5, R=1.0, F1=2/3.
    records = [_rec("v1", ["1", "2"], ["1", "2"]), _rec("v2", ["3", "4"], ["3", "4", "5", "6"])]
    agg = RetrievalMetric().compute(records, EvalContext()).aggregate
    assert agg["precision"] == 0.75                    # (1.0 + 0.5) / 2
    assert agg["recall"] == 1.0                        # (1.0 + 1.0) / 2
    assert agg["f1"] == pytest.approx((1.0 + 2 / 3) / 2)


def test_retrieval_metric_empty_gold_and_pred_scores_one():
    # No known evidence AND nothing retrieved -> 1.0 (zero_division=0 convention), which
    # lifts the macro mean. Documented and pinned so the convention can't silently change.
    v = RetrievalMetric().compute([_rec("v", [], [])], EvalContext()).per_document["v"]
    assert v["recall"] == 1.0 and v["precision"] == 1.0 and v["f1"] == 1.0
    assert v["gold_n"] == 0.0 and v["retrieved_n"] == 0.0 and v["missed_n"] == 0.0


def test_retrieval_metric_micro_aggregates():
    records = [_rec("v1", ["1", "2"], ["1", "2", "9"]), _rec("v2", ["3", "4"], ["3"])]
    agg = RetrievalMetric().compute(records, EvalContext()).aggregate
    # pooled: tp=3 (1,2,3), fp=1 (9), fn=1 (4) -> micro P=R=F1=3/4
    assert agg["micro_precision"] == 0.75 and agg["micro_recall"] == 0.75 and agg["micro_f1"] == 0.75


def test_retrieval_metric_excludes_degraded_variants_from_scores():
    # A degraded variant (API failure / cache miss) is listed in details but NOT scored — its
    # zero would be a retrieval artifact, not evidence, so it must not deflate the aggregates.
    records = [
        _rec("v1", ["1", "2"], ["1", "2"]),                    # clean, perfect
        PredictionRecord(id="v2", input_text="v2", gold_reference=["3", "4"],
                         system_output=[], metadata={"retrieval_status": "degraded"}),
    ]
    result = RetrievalMetric().compute(records, EvalContext())
    assert result.details["degraded"] == ["v2"]
    assert "v2" not in result.per_document                     # excluded from per-doc
    assert result.aggregate["recall"] == 1.0                   # scored over v1 only, not 0.5
    assert result.aggregate["micro_recall"] == 1.0


def test_retrieval_metric_records_unresolved_variants():
    records = [_rec("v1", ["1"], ["1"]), _rec("v2", ["2"], [], resolved=False)]
    result = RetrievalMetric().compute(records, EvalContext())
    assert result.details["unresolved"] == ["v2"]


def test_retrieval_metric_all_missed():
    records = [_rec("v1", ["1"], []), _rec("v2", ["2", "3"], [])]   # nothing retrieved
    agg = RetrievalMetric().compute(records, EvalContext()).aggregate
    assert agg["recall"] == 0.0 and agg["mean_yield"] == 0.0
    assert agg["micro_precision"] == 0.0 and agg["micro_recall"] == 0.0 and agg["micro_f1"] == 0.0


def test_retrieval_metric_empty_records():
    result = RetrievalMetric().compute([], EvalContext())
    assert result.aggregate["recall"] == 0.0 and result.aggregate["mean_yield"] == 0.0
    assert result.aggregate["micro_f1"] == 0.0
    assert result.details["missed"] == {} and result.details["unresolved"] == []


def test_retrieval_metric_is_registered_for_task():
    assert "retrieval_prf" in [m.name for m in get_metrics("variant_retrieval")]
