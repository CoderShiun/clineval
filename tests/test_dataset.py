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
    with pytest.raises(KeyError):
        JSONLDatasetLoader(str(p)).load()
