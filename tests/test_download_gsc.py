import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "download_gsc", str(Path("datasets/download_gsc.py"))
)
download_gsc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(download_gsc)


def test_convert_builds_normalized_jsonl(tmp_path):
    out = tmp_path / "gsc_plus.jsonl"
    count = download_gsc.convert("tests/fixtures/gsc_sample", str(out))
    assert count == 1
    line = out.read_text(encoding="utf-8").strip()
    assert '"id": "PMID_1"' in line
    assert "HP:0001250" in line and "HP:0000252" in line  # normalized to colon form
    assert "HP_" not in line


def test_convert_raises_when_docs_but_no_annotations(tmp_path):
    # A .txt doc with no parseable annotations must fail loudly, not emit empty gold.
    (tmp_path / "PMID_9.txt").write_text("some clinical text", encoding="utf-8")
    out = tmp_path / "gsc_plus.jsonl"
    with pytest.raises(ValueError, match="parsed 0 HPO annotations"):
        download_gsc.convert(str(tmp_path), str(out))


def test_convert_raises_when_no_txt_documents(tmp_path):
    # An empty (or wrongly-laid-out) raw dir must fail loudly, not silently
    # write a zero-record dataset that later looks like an all-zero report.
    out = tmp_path / "gsc_plus.jsonl"
    with pytest.raises(ValueError, match="no .txt documents"):
        download_gsc.convert(str(tmp_path), str(out))
