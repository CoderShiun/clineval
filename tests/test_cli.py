import openai
from typer.testing import CliRunner

import clineval.cli
from clineval.cli import app
from clineval.core.schema import PredictionRecord

runner = CliRunner()


def test_cli_run_default_synthetic_dataset_shows_cache_hit_rate(tmp_path):
    # No --dataset/--cache given: exercises the "synthetic" branch of
    # _load_dataset and the default cached_predictions.jsonl, and the
    # success-path "cache hits: N/M" summary line (hits > 0).
    out = tmp_path / "report.md"
    result = runner.invoke(app, ["run", "--report", str(out)])
    assert result.exit_code == 0, result.output
    assert "cache hits:" in result.output
    hits_str = result.output.split("cache hits:")[1].strip().split("\n")[0].strip()
    assert hits_str == "10/10"
    assert out.read_text(encoding="utf-8").startswith("# ClinEval Report")


def test_cli_run_live_openai_error_is_friendly(tmp_path, monkeypatch):
    data = tmp_path / "mini.jsonl"
    data.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "report.md"

    class BoomExtractor:
        def __init__(self, base_url, model, api_key):
            raise openai.OpenAIError("connection refused")

    monkeypatch.setattr(clineval.cli, "OpenAICompatibleExtractor", BoomExtractor)
    result = runner.invoke(
        app,
        ["run", "--dataset", str(data), "--report", str(out), "--live"],
    )
    assert result.exit_code == 1
    assert "Error" in result.output
    assert "could not reach the LLM endpoint" in result.output
    assert "host.docker.internal" in result.output


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


def test_cli_run_warns_on_partial_cache_hit(tmp_path):
    # Two records, cache only covers one: exercises the 0 < hits < len(records)
    # partial-miss warning branch (distinct from the zero-hits branch above).
    data = tmp_path / "mini.jsonl"
    data.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n'
        '{"id": "r2", "input_text": "vsd", "gold_reference": ["HP:0011682"]}\n',
        encoding="utf-8",
    )
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen-test"}\n'
        '{"id": "r1", "system_output": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["run", "--dataset", str(data), "--cache", str(cache), "--report", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "WARNING: only 1/2 records matched cache" in result.output
    assert "all-zero scores for the unmatched records" in result.output
    assert "cache hits: 1/2" in result.output


def test_cli_run_missing_dataset_is_friendly_error(tmp_path):
    out = tmp_path / "report.md"
    missing = tmp_path / "nope.jsonl"
    result = runner.invoke(
        app,
        ["run", "--dataset", str(missing), "--report", str(out)],
    )
    assert result.exit_code == 1
    assert "Error" in result.output
    assert str(missing) in result.output


def test_cli_run_gsc_without_data_is_friendly_error(tmp_path, monkeypatch):
    out = tmp_path / "report.md"
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["run", "--dataset", "gsc", "--report", str(out)],
    )
    assert result.exit_code == 1
    assert "download_gsc" in result.output


def test_cli_run_missing_cache_is_friendly_error(tmp_path):
    data = tmp_path / "mini.jsonl"
    data.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "run",
            "--dataset", str(data),
            "--cache", str(tmp_path / "nope-cache.jsonl"),
            "--report", str(out),
        ],
    )
    assert result.exit_code == 1
    assert "Error" in result.output


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


def test_cli_run_rejects_unbounded_similarity_method(tmp_path):
    # Resnik/etc. are unnormalized IC, not bounded to [0, 1] with
    # self-similarity == 1.0: allowing them would let semantic F1 fall below
    # exact F1, which is nonsensical for a "near-miss credit" score.
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["run", "--report", str(out), "--similarity-method", "resnik"],
    )
    assert result.exit_code == 1
    assert "--similarity-method must be one of: lin, jc, jaccard" in result.output
    assert not out.exists()


def test_cli_run_accepts_tier3_config_flags(tmp_path):
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "run",
            "--report", str(out),
            "--relatedness-tau", "0.5",
            "--ic-high-threshold", "5.0",
            "--similarity-method", "jaccard",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").startswith("# ClinEval Report")


def test_cli_run_report_shows_pyhpo_version_and_cache_hits(tmp_path):
    out = tmp_path / "report.md"
    result = runner.invoke(app, ["run", "--report", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "pyhpo version" in text.lower()
    assert "cache hits" in text.lower()
