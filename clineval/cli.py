"""ClinEval command-line interface."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import openai
import typer

import clineval.tasks.hpo_extraction  # noqa: F401  (registers metrics on import)
import clineval.tasks.variant_retrieval  # noqa: F401  (registers retrieval metric)
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
from clineval.tasks.variant_retrieval.datasets import HgmdGoldLoader, RYR1BenchmarkLoader
from clineval.tasks.variant_retrieval.report import render_retrieval_report
from clineval.tasks.variant_retrieval.retriever import (
    CachedRetriever,
    DatasetRetriever,
    PipelineRetriever,
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


def _load_retrieval_dataset(dataset: str):
    if dataset == "ryr1":
        return RYR1BenchmarkLoader().load()
    if dataset == "hgmd":
        return HgmdGoldLoader().load()
    return RYR1BenchmarkLoader(dataset).load()  # treat anything else as a path to a gold JSONL


def _build_pipeline_retriever(genome_build: str, request_cache: str) -> PipelineRetriever:
    """Wire the live Stage 1->2 pipeline over free public APIs (no HGMD)."""
    from clineval.pipeline.cache import RequestCache
    from clineval.pipeline.clients.eutils import EutilsClient
    from clineval.pipeline.clients.http import HttpClient
    from clineval.pipeline.clients.litvar import LitVarClient
    from clineval.pipeline.clients.myvariant_client import MyVariantClient
    from clineval.pipeline.clients.variantvalidator import VariantValidatorClient
    from clineval.pipeline.normalize import normalize_and_expand
    from clineval.pipeline.retrieve import retrieve
    from clineval.pipeline.throttle import RateLimiter

    http = HttpClient(cache=RequestCache(request_cache), limiter=RateLimiter(3.0))
    vv, mv = VariantValidatorClient(http), MyVariantClient()
    litvar = LitVarClient(http)
    eutils = EutilsClient(http, api_key=os.environ.get("NCBI_API_KEY"))
    return PipelineRetriever(
        normalize_fn=lambda hgvs: normalize_and_expand(hgvs, genome_build, vv=vv, mv=mv),
        retrieve_fn=lambda forms: retrieve(forms, litvar=litvar, eutils=eutils),
    )


@app.command("retrieval-eval")
def retrieval_eval(
    dataset: str = typer.Option("ryr1", help="'ryr1', 'hgmd', or a path to a gold JSONL."),
    report: str = typer.Option("reports/retrieval.md", help="Output Markdown path."),
    source: str = typer.Option(
        "cached", help="'cached' (offline), 'live' (real pipeline), or 'dataset'."
    ),
    cache: str = typer.Option(
        "examples/data/cached_retrieval.jsonl", help="Cached retrieval outputs (source=cached)."
    ),
    request_cache: str = typer.Option(
        ".cache/requests.sqlite", help="SQLite request cache (source=live)."
    ),
    genome_build: str = typer.Option("GRCh38", help="Genome build for normalization."),
) -> None:
    """Run the variant retrieval evaluation and write a Markdown report."""
    if source not in {"cached", "live", "dataset"}:
        typer.echo("Error: --source must be cached, live, or dataset.", err=True)
        raise typer.Exit(1)
    try:
        records = _load_retrieval_dataset(dataset)
        if source == "cached":
            retriever: object = CachedRetriever(cache)
            model_label = "cached"
        elif source == "dataset":
            retriever = DatasetRetriever()
            model_label = "dataset"
        else:
            retriever = _build_pipeline_retriever(genome_build, request_cache)
            model_label = "live-pipeline"
        for rec in records:
            rec.system_output = retriever.extract(rec)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    # Note: a live per-variant API/normalization failure does NOT raise here — the pipeline
    # marks that variant's retrieval "degraded" (excluded + surfaced below), so one bad
    # variant never aborts the batch.

    provenance: dict[str, str] = {}
    if source == "cached":
        hits = sum(1 for rec in records if retriever.covers(rec.id))
        provenance["cache_hit_rate"] = f"{hits}/{len(records)}"
        if hits < len(records):
            typer.echo(
                f"WARNING: {hits}/{len(records)} variants matched cache '{cache}' — "
                "unmatched variants score zero. Check --dataset/--cache "
                "alignment or use --source live.",
                err=True,
            )
    elif source == "live":
        provenance["genome_build"] = genome_build   # which build normalization used
        # Lift the pipeline's tool/DB-version evidence snapshot from the records into the
        # run-level provenance so the report actually renders what the regulatory table claims.
        sources: dict[str, None] = {}
        vvdb_version = ""
        for rec in records:
            snap = rec.metadata.get("provenance", {})
            vvdb_version = snap.get("vvdb_version", "") or vvdb_version
            sources.update(dict.fromkeys(snap.get("sources", [])))
        if vvdb_version:
            provenance["vvdb_version"] = vvdb_version
        if sources:
            provenance["sources"] = ",".join(sources)

    # A variant whose retrieval was degraded (API failure) or uncovered (cache miss) scores
    # zero, but that zero is NOT evidence of "no literature" — surface it, never hide it.
    degraded = [r for r in records if r.metadata.get("retrieval_status", "ok") != "ok"]
    if degraded:
        provenance["degraded_variants"] = f"{len(degraded)}/{len(records)}"
        typer.echo(
            f"WARNING: {len(degraded)}/{len(records)} variant(s) had degraded retrieval "
            "(API failure or cache miss); their empty results are flagged, not 'no evidence'.",
            err=True,
        )

    result = evaluate(
        "variant_retrieval",
        records,
        EvalContext(),   # the retrieval metric needs no ontology/config
        dataset=dataset,
        model=model_label,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        provenance=provenance,
    )
    output = render_retrieval_report(result)
    out_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    typer.echo(f"Wrote {report}  (variants: {result.n_documents}, source: {model_label})")
