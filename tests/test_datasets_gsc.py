import pytest

from clineval.tasks.hpo_extraction.datasets import GscPlusLoader


def test_gsc_loader_reads_converted_jsonl(tmp_path):
    root = tmp_path / "gsc_plus"
    root.mkdir()
    (root / "gsc_plus.jsonl").write_text(
        '{"id": "PMID1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    records = GscPlusLoader(str(root)).load()
    assert records[0].id == "PMID1"
    assert records[0].gold_reference == ["HP:0001250"]


def test_gsc_loader_missing_gives_friendly_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_gsc"):
        GscPlusLoader(str(tmp_path / "absent")).load()


def test_gsc_loader_normalizes_underscore_gold_ids(tmp_path):
    root = tmp_path / "gsc_plus"
    root.mkdir()
    (root / "gsc_plus.jsonl").write_text(
        '{"id": "PMID2", "input_text": "seizures", "gold_reference": ["HP_0001250"]}\n',
        encoding="utf-8",
    )
    records = GscPlusLoader(str(root)).load()
    assert records[0].gold_reference == ["HP:0001250"]
