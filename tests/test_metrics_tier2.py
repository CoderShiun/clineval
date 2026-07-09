from clineval.core.metric import EvalContext
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.metrics import Tier2SemanticMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


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
