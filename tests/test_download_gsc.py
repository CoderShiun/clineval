import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "download_gsc", str(Path("datasets/download_gsc.py"))
)
download_gsc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(download_gsc)


def test_convert_builds_normalized_jsonl(tmp_path):
    # The fixture is a PubTator-style GSCplus_*_gold.tsv with 2 docs (one annotated,
    # one with no phenotypes).
    out = tmp_path / "gsc_plus.jsonl"
    count = download_gsc.convert("tests/fixtures/gsc_sample", str(out))
    assert count == 2
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert '"id": "PMID1"' in lines[0]
    assert "HP:0001250" in lines[0] and "HP:0000252" in lines[0]  # colon-normalized
    assert '"id": "PMID2"' in lines[1]
    assert '"gold_reference": []' in lines[1]  # a document with no annotations is kept


def test_convert_raises_when_docs_but_no_annotations(tmp_path):
    # A GSCplus file with documents but no parseable HPO annotations must fail loudly.
    (tmp_path / "GSCplus_bad_gold.tsv").write_text(
        "PMID9\nSome clinical text with no annotations.\n", encoding="utf-8"
    )
    out = tmp_path / "gsc_plus.jsonl"
    with pytest.raises(ValueError, match="parsed 0 HPO annotations"):
        download_gsc.convert(str(tmp_path), str(out))


def test_convert_raises_when_no_documents(tmp_path):
    # An empty (or wrongly-laid-out) raw dir must fail loudly, not silently write a
    # zero-record dataset that later looks like an all-zero report.
    out = tmp_path / "gsc_plus.jsonl"
    with pytest.raises(ValueError, match="no GSCplus_.*documents"):
        download_gsc.convert(str(tmp_path), str(out))


def test_parse_gscplus_file_extracts_text_and_gold():
    from clineval.tasks.hpo_extraction.adapters import normalize_hpo_id

    recs = download_gsc._parse_gscplus_file(
        Path("tests/fixtures/gsc_sample/GSCplus_sample_gold.tsv"), normalize_hpo_id
    )
    assert [r["id"] for r in recs] == ["PMID1", "PMID2"]
    assert recs[0]["input_text"] == "The patient had seizures and microcephaly."
    assert recs[0]["gold_reference"] == ["HP:0001250", "HP:0000252"]
    assert recs[1]["gold_reference"] == []
