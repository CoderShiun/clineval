from clineval.core.metric import EvalContext, get_metrics
from clineval.core.schema import PredictionRecord
import clineval.tasks.hpo_extraction  # noqa: F401  (triggers metric registration)
from clineval.tasks.hpo_extraction.metrics import Tier1ExactMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


def test_tier1_perfect_and_partial():
    records = [
        _rec("r1", ["HP:0001250", "HP:0000252"], ["HP:0001250", "HP:0000252"]),  # perfect
        _rec("r2", ["HP:0001250"], ["HP:0000252"]),  # all wrong
    ]
    result = Tier1ExactMetric().compute(records, EvalContext())
    assert result.per_document["r1"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert result.per_document["r2"]["f1"] == 0.0
    assert result.aggregate["f1"] == 0.5  # macro mean of 1.0 and 0.0


def test_tier1_empty_sets_are_perfect():
    result = Tier1ExactMetric().compute([_rec("r", [], [])], EvalContext())
    assert result.per_document["r"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_tier1_empty_gold_nonempty_pred_is_all_wrong():
    # Nothing to find, but the system predicted something anyway: fully wrong.
    result = Tier1ExactMetric().compute([_rec("r", [], ["HP:0001250"])], EvalContext())
    assert result.per_document["r"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_tier1_nonempty_gold_empty_pred_is_all_wrong():
    # Something to find, system predicted nothing: fully wrong (not "perfect").
    result = Tier1ExactMetric().compute([_rec("r", ["HP:0001250"], [])], EvalContext())
    assert result.per_document["r"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_tier1_macro_average_covers_precision_and_recall_too():
    records = [
        _rec("r1", ["HP:0001250", "HP:0000252"], ["HP:0001250", "HP:0000252"]),  # P=R=1.0
        _rec("r2", ["HP:0001250"], ["HP:0000252"]),  # P=R=0.0
    ]
    result = Tier1ExactMetric().compute(records, EvalContext())
    assert result.aggregate["precision"] == 0.5  # macro mean of 1.0 and 0.0
    assert result.aggregate["recall"] == 0.5
    assert result.aggregate["f1"] == 0.5


def test_tier1_is_registered_for_task():
    names = [m.name for m in get_metrics("hpo_extraction")]
    assert "tier1_exact" in names
