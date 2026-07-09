import pytest

from clineval.core.dataset import JSONLDatasetLoader


def test_jsonl_loader_reads_records(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n'
        "\n"  # blank lines ignored
        '{"id": "r2", "input_text": "x", "gold_reference": [], '
        '"system_output": ["HP:0000252"], "metadata": {"src": "t"}}\n',
        encoding="utf-8",
    )
    records = JSONLDatasetLoader(str(p)).load()
    assert [r.id for r in records] == ["r1", "r2"]
    assert records[0].gold_reference == ["HP:0001250"]
    assert records[0].system_output == []
    assert records[0].metadata == {}
    assert records[1].system_output == ["HP:0000252"]
    assert records[1].metadata == {"src": "t"}


def test_jsonl_loader_requires_gold_reference(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "r1", "input_text": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="gold_reference"):
        JSONLDatasetLoader(str(p)).load()


def test_jsonl_loader_requires_id(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"input_text": "x", "gold_reference": []}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1.*'id'"):
        JSONLDatasetLoader(str(p)).load()


def test_jsonl_loader_reports_malformed_json_line(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(
        '{"id": "r1", "input_text": "x", "gold_reference": []}\n'
        "not json\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 2"):
        JSONLDatasetLoader(str(p)).load()


def test_jsonl_loader_rejects_scalar_gold_reference(tmp_path):
    # A scalar string for gold_reference (instead of a list) must not silently
    # explode into single characters via list("HP:0001250") -> raise cleanly.
    p = tmp_path / "bad.jsonl"
    p.write_text(
        '{"id": "r1", "input_text": "x", "gold_reference": "HP:0001250"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1.*gold_reference.*list"):
        JSONLDatasetLoader(str(p)).load()


def test_jsonl_loader_rejects_non_list_system_output(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(
        '{"id": "r1", "input_text": "x", "gold_reference": [], '
        '"system_output": "HP:0001250"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1.*system_output.*list"):
        JSONLDatasetLoader(str(p)).load()


def test_jsonl_loader_rejects_non_object_metadata(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(
        '{"id": "r1", "input_text": "x", "gold_reference": [], "metadata": "oops"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 1.*metadata.*object"):
        JSONLDatasetLoader(str(p)).load()


def test_jsonl_loader_rejects_non_object_line(tmp_path):
    # A whole-line bare scalar/array must fail cleanly, not raise a raw TypeError.
    p = tmp_path / "bad.jsonl"
    p.write_text("42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1.*must be a JSON object"):
        JSONLDatasetLoader(str(p)).load()
