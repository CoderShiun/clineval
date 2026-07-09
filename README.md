# ClinEval

**Open-source, self-hostable evaluation toolkit for clinical LLM outputs.**

ClinEval is an *evaluator* — an inspection rig for clinical AI systems — not a system that
builds extraction or generation models. Point it at a system's outputs and a gold standard;
it produces clinically meaningful quality metrics **and** evidence mapped to medical-device
regulation (EU AI Act, IVDR, ISO 15189:2022).

**Module A (this MVP): HPO extraction evaluation.** Given clinical text, a system's
extracted [Human Phenotype Ontology](https://hpo.jax.org/) term IDs, and a gold standard,
ClinEval scores exact match, ontology-aware semantic similarity, and a clinical error
taxonomy, then renders a single Markdown report.

## The headline insight: exact match understates a clinical system

Naive precision/recall/F1 treats every mismatch the same — a wildly wrong term and a
sibling term one hop away in the ontology both count as pure failures. Clinically that's
not true: predicting a parent or closely related HPO term is a much smaller error than
predicting something unrelated. On the bundled 10-record synthetic demo:

| Metric | F1 |
|---|---|
| Tier 1 — exact match | **≈ 0.62** |
| Tier 2 — semantic (ontology-aware) | **≈ 0.73** |

The **+0.11 gap** is the signal: a sizeable share of the "errors" exact-match penalizes are
near-misses (parent/child/sibling HPO terms), not hallucinations. Reporting only exact F1
would make the same system look meaningfully worse than it clinically is — which is why
ClinEval always reports both, side by side, in every generated report.

## Three metric tiers

1. **Tier 1 — Exact match.** Precision / recall / F1 over normalized HPO IDs (`HP:0000000`
   form). The strict, standard baseline.
2. **Tier 2 — Semantic / hierarchy-aware.** Best-match [Lin similarity](https://hpo.jax.org/)
   over the HPO graph via [PyHPO](https://pypi.org/project/pyhpo/), an information-content
   (IC) weighted variant, and a set-level best-match-average (BMA) score. Rewards clinically
   sensible near-misses instead of penalizing them like unrelated errors.
3. **Tier 3 — Clinical error taxonomy.** Classifies every discrepancy as *missed*,
   *wrong granularity* (parent/child), *wrong term* (related, not parent/child), or
   *spurious* (unrelated false positive) — plus clinical-significance flags for missed
   high-information-content terms (the ones most likely to matter for diagnosis).

## Regulatory-evidence mapping

Every report ends with a table mapping each metric to the regulatory clause it can serve as
evidence for — turning a test run into an artifact usable in a technical file:

| ClinEval evidence | EU AI Act | IVDR | ISO 15189:2022 |
|---|---|---|---|
| Exact P/R/F1 | Art 15 (accuracy) | Annex XIII analytical performance | 7.3.2 verification of examination methods |
| Semantic F1 / IC-weighted | Art 15 (appropriate accuracy metrics; robustness) | performance evaluation | 7.3.3 validation of examination methods |
| Error taxonomy + significance flags | Art 15 (robustness) | performance / risk evidence | 7.3.7 ensuring validity of results + 7.5 nonconforming work |
| Ontology alignment / traceability | Art 12 (logging & traceability) | technical documentation | Clause 8 management system (records & documents) |

> **Disclaimer:** general technical/educational reference, not legal or
> regulatory-compliance advice. Clauses and timelines change — confirm dataset licenses
> before use and consult qualified regulatory/quality professionals against current
> official texts.

## Quickstart (Docker — no host installs)

Everything runs in the container; the only host prerequisite is Docker.

```bash
docker compose build
docker compose run --rm clineval uv run clineval run --dataset synthetic --report reports/report.md
```

This replays a committed set of cached model predictions against the bundled synthetic
dataset — fully offline, deterministic, zero setup — and writes a Markdown report to
`reports/report.md`.

To evaluate a **live** local model instead (e.g. [LM Studio](https://lmstudio.ai/) running
on the host), add `--live` and point at the host's OpenAI-compatible endpoint:

```bash
docker compose run --rm clineval uv run clineval run \
    --dataset synthetic --report reports/report.md \
    --live --base-url http://host.docker.internal:1234/v1
```

For a step-by-step, inspectable walkthrough of the same pipeline, see
[`examples/hpo_extraction_demo.ipynb`](examples/hpo_extraction_demo.ipynb).

## Architecture

ClinEval separates a **generic evaluation core** from **pluggable tasks**:

```
clineval/core/         schema, dataset loading, metric registry, evaluator,
                        ontology utilities (IC, similarity), Markdown report renderer
clineval/tasks/
    hpo_extraction/     Module A: adapters, extractors (cached + live), metrics,
                         dataset loaders — everything specific to HPO extraction
    report_generation/  Module B seam — intentionally empty. A future task adds
                         faithfulness/hallucination metrics for generated clinical
                         reports here, reusing the same core schema, evaluator, and
                         report machinery, without touching Module A.
clineval/regulatory/    the evidence-to-clause mapping table
clineval/templates/     the Jinja2 report template
```

Adding a new task means implementing a `DatasetLoader`, one or more `Metric`s registered
under a task name, and (optionally) an extractor — the core evaluator, alignment, and
report renderer are all reused unmodified.

## Datasets

- **Synthetic fixture** (`examples/data/synthetic_mini.jsonl` + committed
  `cached_predictions.jsonl`) — 10 hand-built records covering exact matches, parent/child
  near-misses, unrelated errors, and an empty-gold case. This is what `--dataset synthetic`
  (the default) runs, entirely offline.
- **GSC+ / BiolarkGSC+** — 228 PubMed abstracts annotated with HPO concepts (Lobo et al.,
  2017). Not committed to this repo. Fetch and convert it with
  `datasets/download_gsc.py` (`--dataset gsc`); see [`datasets/README.md`](datasets/README.md)
  for the license-confirmation step required before use.

No patient data — real or synthetic PHI — is bundled or required. See below.

## On-prem, public-data, no-PHI

ClinEval is designed to run entirely on infrastructure you control:

- **On-prem by default.** The Docker image has no external service dependency for the
  default (cached) run; `--live` only ever talks to a local, self-hosted OpenAI-compatible
  endpoint (LM Studio, Ollama, vLLM) that you point it at — no data leaves the host.
- **Public data only.** Bundled and documented datasets (the synthetic fixture, GSC+) are
  public research corpora, not real patient records. Nothing in this repo requires or
  processes PHI.
- **No PHI.** Do not feed real patient data into ClinEval without your own institution's
  data-governance and de-identification review — this project makes no claims about being
  suitable for that use case.

## License

MIT — see `LICENSE`.
