"""ClinEval command-line interface."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import openai
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
    DatasetExtractor,
    OpenAICompatibleExtractor,
)

app = typer.Typer(add_completion=False, help="ClinEval: evaluate clinical LLM outputs.")

# Only bounded, self-similarity=1.0 methods are safe as a semantic-scoring knob.
# Resnik and friends are unnormalized IC and would make semantic F1 fall BELOW
# exact F1, which is nonsensical for a "semantic near-miss credit" score.
_ALLOWED_SIMILARITY_METHODS = {"lin", "jc", "jaccard"}


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
    predictions_from_dataset: bool = typer.Option(
        False,
        "--predictions-from-dataset",
        help=(
            "Score predictions already present in the dataset JSONL (system_output "
            "field) instead of a cache or live model."
        ),
    ),
    base_url: str = typer.Option("http://localhost:1234/v1", help="OpenAI-compatible URL."),
    model: str = typer.Option("local-model", help="Model name for --live."),
    api_key: str = typer.Option("not-needed", help="API key for --live."),
    relatedness_tau: float = typer.Option(
        0.3, help="Tier 3: Lin-similarity threshold for 'related' classification."
    ),
    ic_high_threshold: float = typer.Option(
        3.0, help="Tier 3: IC threshold for clinical-significance flags."
    ),
    similarity_method: str = typer.Option(
        "lin", help="Semantic similarity method (lin, jc, or jaccard)."
    ),
) -> None:
    """Run an end-to-end evaluation and write a Markdown report."""
    if similarity_method not in _ALLOWED_SIMILARITY_METHODS:
        typer.echo("Error: --similarity-method must be one of: lin, jc, jaccard", err=True)
        raise typer.Exit(code=1)
    if not 0.0 < relatedness_tau <= 1.0:
        typer.echo("Error: --relatedness-tau must be in (0, 1].", err=True)
        raise typer.Exit(code=1)
    if ic_high_threshold < 0.0:
        typer.echo("Error: --ic-high-threshold must be >= 0.", err=True)
        raise typer.Exit(code=1)
    if live and predictions_from_dataset:
        typer.echo(
            "Error: --live and --predictions-from-dataset cannot be combined.", err=True
        )
        raise typer.Exit(1)
    try:
        records = _load_dataset(dataset)
        for rec in records:
            adapters.normalize_record(rec)
        dataset_has_predictions = any(rec.system_output for rec in records)
        if not live and not predictions_from_dataset and dataset_has_predictions:
            typer.echo(
                "WARNING: the dataset supplies predictions (system_output) for some "
                "records; they are ignored. Pass --predictions-from-dataset to score "
                "them.",
                err=True,
            )
        if live:
            extractor: object = OpenAICompatibleExtractor(base_url, model, api_key)
            model_label = model
        elif predictions_from_dataset:
            extractor = DatasetExtractor()
            model_label = "dataset"
        else:
            extractor = CachedExtractor(cache)
            model_label = f"cached:{extractor.model}"
        for rec in records:
            rec.system_output = extractor.extract(rec)
            adapters.normalize_record(rec)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except openai.OpenAIError as exc:
        typer.echo(
            f"Error: could not reach the LLM endpoint at {base_url} ({exc}). "
            "From inside Docker, use --base-url http://host.docker.internal:1234/v1.",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    hits: int | None = None
    if not live and not predictions_from_dataset:
        hits = sum(1 for rec in records if extractor.covers(rec.id))
        model_label = f"cached:{extractor.model} [{hits}/{len(records)} cache hits]"
        if hits == 0:
            typer.echo(
                f"WARNING: 0/{len(records)} records matched cache '{cache}' — the "
                "report will be all-zero. Check --dataset/--cache alignment or use --live.",
                err=True,
            )
        elif hits < len(records):
            typer.echo(
                f"WARNING: only {hits}/{len(records)} records matched cache '{cache}' — "
                "the report will contain all-zero scores for the unmatched records. "
                "Check --dataset/--cache alignment or use --live.",
                err=True,
            )

    ontology = Ontology()
    records, alignment = adapters.align_records(records, ontology)
    config = {
        "relatedness_tau": relatedness_tau,
        "ic_high_threshold": ic_high_threshold,
        "similarity_method": similarity_method,
    }
    context = EvalContext(ontology=ontology, config=config)

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
    summary = f"Wrote {report}  (documents: {result.n_documents}, model: {model_label})"
    if hits is not None:
        summary += f"  cache hits: {hits}/{len(records)}"
    typer.echo(summary)
