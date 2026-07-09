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


def test_parse_llm_output_extracts_ids():
    text = 'Terms: HP_0001250 (seizure), "HP:0000252". Also nonsense HP:99.'
    assert adapters.parse_llm_output(text) == ["HP:0001250", "HP:0000252"]


def test_normalize_record_in_place():
    rec = PredictionRecord(
        id="r", input_text="", gold_reference=["HP_0001250"], system_output=["hp:0000252"]
    )
    out = adapters.normalize_record(rec)
    assert out is rec
    assert rec.gold_reference == ["HP:0001250"]
    assert rec.system_output == ["HP:0000252"]
