import pytest

from clineval.core.metric import EvalContext
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.metrics import _SEM_KEYS, Tier2SemanticMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


def test_semantic_both_empty_is_all_ones(ontology):
    rec = _rec("r1", [], [])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.per_document["r1"] == {k: 1.0 for k in _SEM_KEYS}


def test_semantic_empty_gold_nonempty_pred_is_zero(ontology):
    # Predicting into a void (nothing gold) is fully wrong on both axes, same
    # convention as Tier 1's _exact_prf -- not vacuously "perfect precision".
    rec = _rec("r1", [], ["HP:0001250"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    doc = result.per_document["r1"]
    assert doc["sem_precision"] == 0.0
    assert doc["sem_precision_icw"] == 0.0
    assert doc["sem_recall"] == 0.0
    assert doc["sem_recall_icw"] == 0.0


def test_semantic_nonempty_gold_empty_pred_is_zero(ontology):
    # Missing everything (nothing predicted) is fully wrong on both axes.
    rec = _rec("r1", ["HP:0001250"], [])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    doc = result.per_document["r1"]
    assert doc["sem_recall"] == 0.0
    assert doc["sem_recall_icw"] == 0.0
    assert doc["sem_precision"] == 0.0
    assert doc["sem_precision_icw"] == 0.0


def test_semantic_gives_partial_credit_for_near_miss(ontology):
    # Predicted the parent VSD instead of the exact perimembranous VSD.
    rec = _rec("r1", ["HP:0011682"], ["HP:0001629"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    f1 = result.per_document["r1"]["sem_f1"]
    assert 0.0 < f1 < 1.0  # partial credit, not zero and not full


def test_semantic_exact_match_is_one(ontology):
    rec = _rec("r1", ["HP:0001250"], ["HP:0001250"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.per_document["r1"]["sem_f1"] == 1.0
    assert result.per_document["r1"]["bma"] == 1.0


def test_semantic_aggregate_keys_present(ontology):
    rec = _rec("r1", ["HP:0001250"], ["HP:0000252"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    for key in ["sem_precision", "sem_recall", "sem_f1",
                "sem_precision_icw", "sem_recall_icw", "sem_f1_icw", "bma"]:
        assert key in result.aggregate


def test_semantic_icw_recall_weights_toward_high_ic_match(ontology):
    # gold = [specific/high-IC term (exactly matched), broad/low-IC term (missed)].
    # IC-weighting should pull recall toward the correctly-matched high-IC term,
    # so icw recall must exceed the plain (unweighted) average recall.
    gold = ["HP:0011682", "HP:0000118"]
    pred = ["HP:0011682"]
    rec = _rec("r1", gold, pred)
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    doc = result.per_document["r1"]
    assert doc["sem_recall"] < 1.0  # the broad term is not an exact match
    assert doc["sem_recall_icw"] > doc["sem_recall"]


def test_semantic_bma_is_average_of_precision_and_recall_in_partial_case(ontology):
    # Predicted the parent VSD instead of the exact perimembranous VSD -> partial credit.
    rec = _rec("r1", ["HP:0011682"], ["HP:0001629"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    doc = result.per_document["r1"]
    assert 0.0 < doc["bma"] < 1.0
    assert doc["bma"] == pytest.approx((doc["sem_precision"] + doc["sem_recall"]) / 2)


def test_ic_weighted_perfect_match_of_zero_ic_term_is_one(ontology):
    # HP:0000001 (ontology root) has IC 0; a perfect match must not report icw 0.0.
    rec = _rec("r1", ["HP:0000001"], ["HP:0000001"])
    doc = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology)).per_document["r1"]
    assert doc["sem_f1_icw"] == 1.0


def test_semantic_invariant_holds_on_duplicated_predictions(ontology):
    from clineval.tasks.hpo_extraction.metrics import Tier1ExactMetric
    rec = _rec("r1", ["HP:0011682"], ["HP:0011682", "HP:0001250", "HP:0001250"])
    ctx = EvalContext(ontology=ontology)
    sem_f1 = Tier2SemanticMetric().compute([rec], ctx).per_document["r1"]["sem_f1"]
    exact_f1 = Tier1ExactMetric().compute([rec], ctx).per_document["r1"]["f1"]
    assert sem_f1 >= exact_f1
