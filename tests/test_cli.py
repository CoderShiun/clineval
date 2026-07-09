from typer.testing import CliRunner

import clineval.cli
from clineval.cli import app
from clineval.core.schema import PredictionRecord

runner = CliRunner()


def test_cli_run_writes_report(tmp_path):
    data = tmp_path / "mini.jsonl"
    data.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n'
        '{"id": "r2", "input_text": "vsd", "gold_reference": ["HP:0011682"]}\n',
        encoding="utf-8",
    )
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        '{"id": "r1", "system_output": ["HP:0001250"]}\n'   # exact hit
        '{"id": "r2", "system_output": ["HP_0001629"]}\n',  # parent -> near-miss (underscore)
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["run", "--dataset", str(data), "--cache", str(cache), "--report", str(out)],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "# ClinEval Report" in text
    assert "cached:qwen-test" in text
    assert "Regulatory Evidence Mapping" in text


def test_cli_run_warns_on_cache_dataset_mismatch(tmp_path):
    data = tmp_path / "mini.jsonl"
    data.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        '{"id": "other-id", "system_output": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["run", "--dataset", str(data), "--cache", str(cache), "--report", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output


class FakeExtractor:
    """Stand-in for OpenAICompatibleExtractor: no network, fixed prediction."""

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.model = model

    def extract(self, record: PredictionRecord) -> list[str]:
        return ["HP:0001250"]


def test_cli_run_live_uses_live_extractor(tmp_path, monkeypatch):
    data = tmp_path / "mini.jsonl"
    data.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    monkeypatch.setattr(clineval.cli, "OpenAICompatibleExtractor", FakeExtractor)
    result = runner.invoke(
        app,
        [
            "run",
            "--dataset", str(data),
            "--report", str(out),
            "--live",
            "--model", "fake-live",
        ],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "# ClinEval Report" in text
    assert "fake-live" in text
    assert "cached:" not in text
