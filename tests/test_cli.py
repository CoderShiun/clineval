from typer.testing import CliRunner

from clineval.cli import app

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
