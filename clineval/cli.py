"""ClinEval command-line interface."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

import clineval.tasks.hpo_extraction  # noqa: F401  (registers metrics on import)
from clineval.core.dataset import JSONLDatasetLoader
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
from clineval.core.ontology.hpo import Ontology
from clineval.core.report import render_report
from clineval.tasks.hpo_extraction import adapters
from clineval.tasks.hpo_extraction.datasets import GscPlusLoader
from clineval.tasks.hpo_extraction.extractor import (
    CachedExtractor,
    OpenAICompatibleExtractor,
)

app = typer.Typer(add_completion=False, help="ClinEval: evaluate clinical LLM outputs.")


@app.callback()
def main() -> None:
    """ClinEval: evaluate clinical LLM outputs.

    A no-op callback: it exists only so Typer keeps `run` as a named
    subcommand instead of collapsing a single-command app into a bare CLI
    (Typer's default when there is exactly one registered command).
    """


def _load_dataset(dataset: str):
    if dataset == "synthetic":
        return JSONLDatasetLoader("examples/data/synthetic_mini.jsonl").load()
    if dataset == "gsc":
        return GscPlusLoader().load()
    return JSONLDatasetLoader(dataset).load()


@app.command()
def run(
    task: str = typer.Option("hpo_extraction", help="Task name."),
    dataset: str = typer.Option("synthetic", help="'synthetic', 'gsc', or a JSONL path."),
    report: str = typer.Option("reports/report.md", help="Output Markdown path."),
    live: bool = typer.Option(False, "--live", help="Call LM Studio instead of the cache."),
    cache: str = typer.Option(
        "examples/data/cached_predictions.jsonl", help="Cached predictions path."
    ),
    base_url: str = typer.Option("http://localhost:1234/v1", help="OpenAI-compatible URL."),
    model: str = typer.Option("local-model", help="Model name for --live."),
    api_key: str = typer.Option("not-needed", help="API key for --live."),
) -> None:
    """Run an end-to-end evaluation and write a Markdown report."""
    records = _load_dataset(dataset)
    for rec in records:
        adapters.normalize_record(rec)

    if live:
        extractor: object = OpenAICompatibleExtractor(base_url, model, api_key)
        model_label = model
    else:
        extractor = CachedExtractor(cache)
        model_label = f"cached:{extractor.model}"

    for rec in records:
        rec.system_output = extractor.extract(rec)
        adapters.normalize_record(rec)

    ontology = Ontology()
    records, alignment = adapters.align_records(records, ontology)
    context = EvalContext(ontology=ontology, config={})

    result = evaluate(
        task,
        records,
        context,
        dataset=dataset,
        model=model_label,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        alignment=alignment,
    )

    output = render_report(result)
    out_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    typer.echo(f"Wrote {report}  (documents: {result.n_documents}, model: {model_label})")
