"""Unit tests for the HGMD gold builder (pure transform; no live DB).

All PMIDs/accessions here are SYNTHETIC (PMIDs >= 99000000, ``SYN…`` accessions) — the
builder is a pure transform, so synthetic inputs exercise it identically, and the licence
firewall forbids committing any real HGMD variant→PMID→accession selection. DM/DM? are the
public tag *filter criteria* the builder selects on, not curated content.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# datasets/ is not an importable package path; load the module by file path.
_SPEC = importlib.util.spec_from_file_location(
    "build_hgmd_gold", Path(__file__).resolve().parent.parent / "datasets" / "build_hgmd_gold.py"
)
build_hgmd_gold = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_hgmd_gold)


def test_row_to_record_builds_gold_schema():
    rec = build_hgmd_gold._row_to_record(
        "NM_000540.3:c.1840C>T", "RYR1", ["SYN0001"], ["DM"],
        ["99000010", "99000011", "99000012"], ["99000011"],
    )
    assert rec["id"] == "NM_000540.3:c.1840C>T"
    assert rec["input_text"] == "NM_000540.3:c.1840C>T"
    assert rec["gold_reference"] == ["99000010", "99000011", "99000012"]
    assert rec["metadata"]["gene"] == "RYR1"
    assert rec["metadata"]["source"] == "hgmd"
    assert rec["metadata"]["hgmd_accs"] == ["SYN0001"]
    assert rec["metadata"]["primary_pmids"] == ["99000011"]
    assert rec["metadata"]["tags"] == ["DM"]
    assert rec["metadata"]["n_pmids"] == 3


def test_row_to_record_merges_multiple_accessions():
    # Two HGMD accessions describing the SAME canonical variant collapse to one
    # record with a unique id and unioned PMIDs (loader requires unique ids).
    rec = build_hgmd_gold._row_to_record(
        "NM_000540.3:c.14667C>G", "RYR1", ["SYN0011", "SYN0012"], ["DM", "DM?"],
        ["99000021", "99000022", "99000023"], ["99000021", "99000022"],
    )
    assert rec["id"] == "NM_000540.3:c.14667C>G"
    assert rec["metadata"]["hgmd_accs"] == ["SYN0011", "SYN0012"]
    assert rec["metadata"]["tags"] == ["DM", "DM?"]
    assert rec["gold_reference"] == ["99000021", "99000022", "99000023"]


def test_row_to_record_handles_no_primary():
    rec = build_hgmd_gold._row_to_record(
        "NM_000540.3:c.1A>T", "RYR1", ["SYN0031"], ["DM"], ["99000031"], None
    )
    assert rec["metadata"]["primary_pmids"] == []
    assert rec["gold_reference"] == ["99000031"]


def test_fetch_gold_records_uses_cursor():
    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows
            self.executed = None
        def execute(self, sql, params):
            self.executed = params
        def fetchall(self):
            return self._rows

    cur = _FakeCursor([
        ("NM_000540.3:c.1840C>T", "RYR1", ["SYN0001"], ["DM"], ["99000010", "99000011"], ["99000010"]),
        ("NM_000540.3:c.7300G>A", "RYR1", ["SYN0002"], ["DM?"], ["99000013"], ["99000013"]),
    ])
    records = build_hgmd_gold.fetch_gold_records(cur, ["RYR1"], ["DM", "DM?"])
    assert cur.executed == {"genes": ["RYR1"], "tags": ["DM", "DM?"]}
    assert [r["id"] for r in records] == ["NM_000540.3:c.1840C>T", "NM_000540.3:c.7300G>A"]
    assert records[0]["metadata"]["hgmd_accs"] == ["SYN0001"]
