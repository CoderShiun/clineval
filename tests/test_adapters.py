from clineval.core.ontology.hpo import TermResolution
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction import adapters


def test_normalize_underscore_and_case():
    assert adapters.normalize_hpo_id("HP_0000110") == "HP:0000110"
    assert adapters.normalize_hpo_id("hp:0000110") == "HP:0000110"
    assert adapters.normalize_hpo_id("  HP:0000110  ") == "HP:0000110"


def test_normalize_rejects_invalid():
    assert adapters.normalize_hpo_id("not-an-id") is None
    assert adapters.normalize_hpo_id("HP:123") is None  # too short
    assert adapters.normalize_hpo_id(None) is None


def test_normalize_ids_dedupes_and_drops_invalid():
    assert adapters.normalize_hpo_ids(["HP_0000110", "HP:0000110", "junk"]) == ["HP:0000110"]


def test_normalize_rejects_overlong_id():
    assert adapters.normalize_hpo_id("HP:00012501") is None  # not truncated to HP:0001250


def test_parse_llm_output_rejects_overlong_id():
    assert adapters.parse_llm_output("HP:12345678") == []


def test_parse_llm_output_extracts_ids():
    text = 'Terms: HP_0001250 (seizure), "HP:0000252". Also nonsense HP:99.'
    assert adapters.parse_llm_output(text) == ["HP:0001250", "HP:0000252"]


def test_parse_llm_output_empty_text_returns_empty():
    assert adapters.parse_llm_output("") == []
    assert adapters.parse_llm_output(None) == []


def test_parse_llm_output_dedupes_repeated_ids():
    text = "HP:0001250 appears here and again as HP_0001250."
    assert adapters.parse_llm_output(text) == ["HP:0001250"]


def test_normalize_record_in_place():
    rec = PredictionRecord(
        id="r", input_text="", gold_reference=["HP_0001250"], system_output=["hp:0000252"]
    )
    out = adapters.normalize_record(rec)
    assert out is rec
    assert rec.gold_reference == ["HP:0001250"]
    assert rec.system_output == ["HP:0000252"]


class _ConvergingOntology:
    """Two distinct raw ids that both resolve to the same primary id."""

    version = "test-1.0"
    ic_basis = "omim"
    library_version = "9.9.9"

    def resolve(self, hpo_id):
        table = {
            "HP:0000001": TermResolution("HP:0000001", "HP:0000001", "primary"),
            "HP:0000002": TermResolution("HP:0000002", "HP:0000001", "alt_id"),
        }
        return table[hpo_id]


def test_align_records_dedupes_when_two_ids_resolve_to_same_primary():
    # HP:0000001 (primary) and HP:0000002 (alt_id) both resolve to HP:0000001;
    # the aligned list must collapse them into a single entry.
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:0000002"],
            system_output=[],
        )
    ]
    aligned, alignment = adapters.align_records(records, _ConvergingOntology())
    assert aligned[0].gold_reference == ["HP:0000001"]
    assert alignment.alt_ids_resolved == 1
