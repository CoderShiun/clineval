from clineval.core.ontology.hpo import TermResolution
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.adapters import align_records


class FakeOntology:
    version = "test-1.0"
    ic_basis = "omim"

    def resolve(self, hpo_id):
        table = {
            "HP:0000001": TermResolution("HP:0000001", "HP:0000001", "primary"),
            "HP:0000002": TermResolution("HP:0000002", "HP:0000100", "alt_id"),
            "HP:0000999": TermResolution("HP:0000999", None, "obsolete"),
            "HP:9999999": TermResolution("HP:9999999", None, "unknown"),
        }
        return table[hpo_id]


def test_align_resolves_alt_and_flags_obsolete():
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:0000002"],  # primary + alt
            system_output=["HP:0000999"],                 # obsolete
        )
    ]
    aligned, alignment = align_records(records, FakeOntology())
    assert aligned[0].gold_reference == ["HP:0000001", "HP:0000100"]  # alt resolved
    assert aligned[0].system_output == []                             # obsolete dropped
    assert alignment.alt_ids_resolved == 1
    assert alignment.obsolete_flagged == 1
    assert alignment.obsolete_ids == ["HP:0000999"]
    assert alignment.unknown_flagged == 0
    assert alignment.unknown_ids == []
    assert alignment.hpo_version == "test-1.0"
    assert alignment.ic_basis == "omim"


def test_align_counts_obsolete_and_unknown_separately():
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:0000999"],  # primary + obsolete
            system_output=["HP:9999999"],                 # unknown
        )
    ]
    aligned, alignment = align_records(records, FakeOntology())
    assert aligned[0].gold_reference == ["HP:0000001"]  # obsolete dropped
    assert aligned[0].system_output == []                # unknown dropped
    assert alignment.obsolete_flagged == 1
    assert alignment.obsolete_ids == ["HP:0000999"]
    assert alignment.unknown_flagged == 1
    assert alignment.unknown_ids == ["HP:9999999"]
