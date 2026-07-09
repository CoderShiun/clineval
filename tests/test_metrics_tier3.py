from clineval.core.metric import EvalContext
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.metrics import Tier3ClinicalMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


def test_wrong_granularity_when_parent_predicted(ontology):
    # gold = perimembranous VSD; predicted its parent VSD -> wrong granularity.
    rec = _rec("r1", ["HP:0011682"], ["HP:0001629"])
    result = Tier3ClinicalMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.aggregate["wrong_granularity"] == 1.0
    assert result.aggregate["missed"] == 1.0  # gold not exactly present


def test_spurious_unrelated_fp(ontology):
    # gold = VSD; predicted an unrelated seizure -> spurious; gold missed.
    rec = _rec("r1", ["HP:0001629"], ["HP:0001250"])
    result = Tier3ClinicalMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.aggregate["spurious"] == 1.0
    assert result.aggregate["missed"] == 1.0


def test_wrong_term_for_sibling(ontology):
    # gold = muscular VSD; predicted sibling perimembranous VSD (related, not parent/child).
    # Siblings share the specific VSD parent, so their Lin is comfortably > 0.1;
    # a low tau keeps this robust to exact IC values while still excluding unrelated terms.
    rec = _rec("r1", ["HP:0011623"], ["HP:0011682"])
    result = Tier3ClinicalMetric().compute(
        [rec], EvalContext(ontology=ontology, config={"relatedness_tau": 0.1})
    )
    assert result.aggregate["wrong_term"] == 1.0


def test_missed_high_ic_flag(ontology):
    # A rare, specific gold term missed entirely should be flagged.
    rec = _rec("r1", ["HP:0011682"], [])
    result = Tier3ClinicalMetric().compute(
        [rec], EvalContext(ontology=ontology, config={"ic_high_threshold": 0.0})
    )
    types = {f["type"] for f in result.details["flags"]}
    assert "missed_high_ic" in types
