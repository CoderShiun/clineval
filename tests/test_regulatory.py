from clineval.regulatory import mapping


def test_mapping_rows_shape_and_iso_2022():
    rows = mapping.get_mapping_rows()
    assert len(rows) == 4
    for row in rows:
        assert set(row) == {"evidence", "ai_act", "ivdr", "iso15189"}
    # ISO clauses use 2022 numbering (7.3.x / Clause 8), not 2012 (5.5.x).
    iso_blob = " ".join(r["iso15189"] for r in rows)
    assert "7.3.2" in iso_blob and "7.3.3" in iso_blob
    assert "5.5" not in iso_blob


def test_disclaimer_present():
    assert "not legal" in mapping.DISCLAIMER.lower()
