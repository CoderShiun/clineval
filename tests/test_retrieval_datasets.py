import pytest

from clineval.tasks.variant_retrieval.datasets import HgmdGoldLoader, RYR1BenchmarkLoader


def test_ryr1_loader_reads_committed_gold():
    records = RYR1BenchmarkLoader().load()
    assert len(records) >= 3
    r0 = records[0]
    assert r0.id.startswith("NM_000540.3:c.")
    assert all(isinstance(p, str) for p in r0.gold_reference)
    assert r0.metadata["gene"] == "RYR1"
    # The whole committed fixture is synthetic, never HGMD-derived (licence firewall):
    # every row must carry the marker, so a stray HGMD-tagged row can't slip in unnoticed.
    assert all(r.metadata.get("source") == "synthetic_demo" for r in records)


def test_ryr1_loader_coerces_pmids_to_str(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(
        '{"id": "v", "input_text": "v", "gold_reference": [123, 456], "metadata": {}}\n',
        encoding="utf-8",
    )
    records = RYR1BenchmarkLoader(str(p)).load()
    assert records[0].gold_reference == ["123", "456"]   # numeric PMIDs -> strings


def test_hgmd_loader_missing_file_is_clear():
    with pytest.raises(FileNotFoundError) as e:
        HgmdGoldLoader(path="datasets/hgmd_gold/does_not_exist.jsonl").load()
    msg = str(e.value)
    assert "export" in msg.lower() and "does_not_exist.jsonl" in msg   # actionable path


def test_hgmd_loader_reads_when_present(tmp_path):
    p = tmp_path / "gold.jsonl"
    p.write_text(
        '{"id": "NM:c.1A>T", "gold_reference": ["1", "2"], "metadata": {"gene": "RYR1"}}\n',
        encoding="utf-8",
    )
    records = HgmdGoldLoader(str(p)).load()
    assert records[0].id == "NM:c.1A>T" and records[0].gold_reference == ["1", "2"]
