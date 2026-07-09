import importlib.util
from pathlib import Path

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
