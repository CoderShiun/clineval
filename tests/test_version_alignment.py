from clineval.core.ontology.hpo import TermResolution
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.adapters import _align_list, align_records


class FakeOntology:
    version = "test-1.0"
    ic_basis = "omim"
    library_version = "9.9.9"

    def resolve(self, hpo_id):
        table = {
            "HP:0000001": TermResolution("HP:0000001", "HP:0000001", "primary"),
            "HP:0000002": TermResolution("HP:0000002", "HP:0000100", "alt_id"),
            "HP:0000999": TermResolution("HP:0000999", None, "obsolete"),
            "HP:0000998": TermResolution("HP:0000998", None, "obsolete"),
            "HP:9999999": TermResolution("HP:9999999", None, "unknown"),
        }
        return table[hpo_id]


def test_align_resolves_alt_and_flags_obsolete():
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:0000002", "HP:0000999"],  # primary + alt + obsolete
            system_output=["HP:0000998"],                 # obsolete prediction -> retained
        )
    ]
    aligned, alignment = align_records(records, FakeOntology())
    assert aligned[0].gold_reference == ["HP:0000001", "HP:0000100"]  # alt resolved, obsolete dropped
    assert aligned[0].system_output == ["HP:0000998"]                # obsolete prediction kept (scores as error)
    assert alignment.alt_ids_resolved == 1
    assert alignment.obsolete_flagged == 2                            # unique ids across gold + pred
    assert alignment.obsolete_ids == ["HP:0000998", "HP:0000999"]
    assert alignment.unknown_flagged == 0
    assert alignment.unknown_ids == []
    assert alignment.hpo_version == "test-1.0"
    assert alignment.ic_basis == "omim"
    assert alignment.pyhpo_version == "9.9.9"


def test_align_counts_obsolete_and_unknown_separately():
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:0000999"],  # primary + obsolete (gold -> dropped)
            system_output=["HP:9999999"],                 # unknown (prediction -> kept)
        )
    ]
    aligned, alignment = align_records(records, FakeOntology())
    assert aligned[0].gold_reference == ["HP:0000001"]   # obsolete dropped from gold
    assert aligned[0].system_output == ["HP:9999999"]    # unknown prediction retained
    assert alignment.obsolete_flagged == 1
    assert alignment.obsolete_ids == ["HP:0000999"]
    assert alignment.unknown_flagged == 1
    assert alignment.unknown_ids == ["HP:9999999"]


def test_unresolvable_dropped_from_gold_but_kept_in_prediction():
    # The SAME unknown id: excluded from gold (nothing to score against an
    # unplaceable gold term) but retained in the prediction so it scores as a
    # hallucination instead of silently vanishing. Counted once (unique).
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:9999999"],   # unknown in gold -> dropped
            system_output=["HP:0000001", "HP:9999999"],    # unknown in pred -> kept
        )
    ]
    aligned, alignment = align_records(records, FakeOntology())
    assert aligned[0].gold_reference == ["HP:0000001"]
    assert aligned[0].system_output == ["HP:0000001", "HP:9999999"]
    assert alignment.unknown_flagged == 1                # deduped across gold + pred
    assert alignment.unknown_ids == ["HP:9999999"]


def test_align_list_keep_unresolvable_toggle():
    # Directly exercise the keep_unresolvable switch: False drops, True keeps.
    onto = FakeOntology()
    counters = {"alt": 0, "obsolete": 0, "obsolete_ids": [], "unknown": 0, "unknown_ids": []}
    dropped = _align_list(onto, ["HP:9999999"], counters, keep_unresolvable=False)
    kept = _align_list(onto, ["HP:9999999"], counters, keep_unresolvable=True)
    assert dropped == []
    assert kept == ["HP:9999999"]
