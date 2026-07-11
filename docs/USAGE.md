# ClinEval — Usage Guide

ClinEval is an **evaluator** for clinical LLM outputs — an inspection rig that scores how
well a system extracts **HPO (Human Phenotype Ontology)** terms from clinical text against a
gold standard, and writes a Markdown report with clinically-meaningful metrics plus a
regulatory-evidence mapping. It is *not* a model builder; the thing being evaluated (the
"system under test") is supplied to it.

Everything runs inside **Docker** — you do **not** install Python, uv, or any library on
your machine.

---

## 1. Prerequisites (the only thing you need)

- **Docker Desktop, running.** That's it. Confirm it's up:
  ```bash
  docker --version
  docker compose version
  docker info --format '{{.ServerVersion}}'   # a version here means the daemon is running
  ```
  If the last command errors, **start Docker Desktop** and retry.

No host Python / uv / pip is required or used. If you ever see a suggestion to `pip install`
or `uv sync` on your machine, you don't need it — all of that happens inside the image.

---

## 2. First run (about a minute)

```bash
# 1. Build the image once (installs Python 3.14 + all dependencies). Takes a few minutes.
docker compose build

# 2. Run the bundled offline demo and write a report.
docker compose run --rm clineval uv run clineval run --dataset synthetic --report reports/report.md
```

Open `reports/report.md`. On the bundled synthetic data you should see the headline result:

```
exact F1 0.617  →  semantic F1 0.730  (+0.113 gap)
```

The demo is **fully offline and deterministic** — it replays a committed set of model
predictions against a small bundled dataset. No network, no LLM, no setup. `reports/` is
git-ignored, so generated reports never get committed.

> **Tip — run commands without the long prefix.** Every command below starts with
> `docker compose run --rm clineval uv run …`. If you run several, you can open one shell in
> the container and drop the prefix inside it:
> ```bash
> docker compose run --rm clineval bash
> # now inside the container:
> uv run clineval run --dataset synthetic --report reports/report.md
> uv run pytest
> ```

---

## 3. What the report contains

The Markdown report has these sections (all from one run):

1. **Run metadata** — dataset, number of documents, model (with cache hit-rate for cached
   runs), HPO release, pyhpo version, IC basis, timestamp.
2. **Overall scores** — Tier 1 exact P/R/F1, Tier 2 semantic P/R/F1 (incl. IC-weighted) and
   set-based BMA, and the **exact-vs-semantic F1 gap** (the headline insight: a positive gap
   means many "errors" are clinical near-misses, not unrelated hallucinations).
3. **Per-document breakdown** — exact and semantic scores per document.
4. **Error taxonomy** — counts of `missed` / `wrong_granularity` / `wrong_term` / `spurious`.
5. **Clinical-significance flags** — missed high-IC (rare) phenotypes and high-IC spurious FPs.
6. **Ontology Alignment** — HPO release, pyhpo version, IC basis, and how many IDs were
   `alt_id`-resolved, flagged **obsolete** (real but deprecated), or flagged **unknown**
   (hallucinated / never-existed).
7. **Regulatory Evidence Mapping** — each metric mapped to EU AI Act / IVDR / ISO 15189:2022,
   with a disclaimer.

---

## 4. The `clineval run` command

```
clineval run [OPTIONS]
```

| Option | Default | Meaning |
|---|---|---|
| `--dataset` | `synthetic` | `synthetic` (bundled), `gsc` (downloaded — see §6), or a path to your own JSONL. |
| `--report` | `reports/report.md` | Where to write the Markdown report (parent dirs are created). |
| `--cache` | `examples/data/cached_predictions.jsonl` | Cached predictions to replay (offline default). |
| `--predictions-from-dataset` | off | Score the predictions already present in the dataset JSONL (`system_output` field) instead of a cache or live model. Cannot be combined with `--live`. |
| `--live` | off | Call a live local model instead of the cache (see §5). |
| `--base-url` | `http://localhost:1234/v1` | OpenAI-compatible endpoint for `--live`. From Docker, use `http://host.docker.internal:1234/v1`. |
| `--model` | `local-model` | Model name sent to the endpoint under `--live`. |
| `--api-key` | `not-needed` | API key for `--live` (LM Studio ignores it; real endpoints need a real key). |
| `--relatedness-tau` | `0.3` | Tier 3: Lin-similarity threshold that separates near-misses from spurious. |
| `--ic-high-threshold` | `3.0` | Tier 3: IC threshold for clinical-significance flags. |
| `--similarity-method` | `lin` | Semantic similarity: `lin`, `jc`, or `jaccard`. |
| `--task` | `hpo_extraction` | Evaluation task (only `hpo_extraction` exists today). |

See it live:
```bash
docker compose run --rm clineval uv run clineval run --help
```

---

## 5. Evaluating a live local model (LM Studio / Ollama / vLLM)

By default the demo replays cached predictions. To score a **live** model instead, run any
OpenAI-compatible server on your host (e.g. [LM Studio](https://lmstudio.ai/) on port 1234)
and point ClinEval at it. Because ClinEval runs inside Docker, reach the host with
`host.docker.internal`, **not** `localhost`:

```bash
docker compose run --rm clineval uv run clineval run \
    --dataset synthetic --report reports/report.md \
    --live --base-url http://host.docker.internal:1234/v1 --model my-model-name
```

The extractor prompts the model for HPO IDs, parses them out of the response, and scores
them — poor raw-LLM accuracy is expected and is exactly what the tool measures.

---

## 6. Choosing what to evaluate

### `--dataset synthetic` (bundled)
Ten small, clearly-synthetic clinical sentences with gold HPO annotations
(`examples/data/synthetic_mini.jsonl`). Fully offline; used by the quickstart and tests.

### `--dataset gsc` (the real GSC+ benchmark)
GSC+ / BiolarkGSC+ (228 PubMed abstracts). ClinEval does **not** bundle third-party corpora —
you fetch it with a script:
```bash
docker compose run --rm clineval uv run python datasets/download_gsc.py
docker compose run --rm clineval uv run clineval run --dataset gsc --report reports/gsc.md
```
> **Before you rely on this:** the download URL and the assumed on-disk format are marked
> "verify before use" in `datasets/download_gsc.py` and `datasets/README.md`. Confirm the
> current source and its **license** first, and adjust the script if the layout differs.

### `--dataset <your-file>.jsonl` (bring your own gold)
Point `--dataset` at your own JSON Lines file — **one JSON object per line**:

```json
{"id": "case-001", "input_text": "The patient has seizures and microcephaly.", "gold_reference": ["HP:0001250", "HP:0000252"]}
{"id": "case-002", "input_text": "Bilateral hearing impairment.", "gold_reference": ["HP:0000365"]}
```

Fields:
- `id` — **required**, unique per record (a string; numbers are coerced to strings). Keep
  ids unique — duplicate ids are a data error.
- `input_text` — the clinical text (optional; used only to show context and to feed a `--live` model).
- `gold_reference` — **required**, a JSON **list** of HPO IDs. May be empty (`[]`) for a
  document with no phenotypes.
- `metadata` — optional JSON object.

HPO IDs may use colons or underscores (`HP:0001250` or `HP_0001250`); ClinEval normalizes them.
Malformed lines (bad JSON, missing `id`/`gold_reference`, a non-list `gold_reference`) produce
a clear `Error: <file> line N: …` and a non-zero exit, not a stack trace.

---

## 7. Bring your own predictions (the cache file)

Predictions are supplied through the **extractor**: either a **cache file** (offline) or a
**live** model (§5). To score predictions you already computed elsewhere, put them in a cache
JSONL and pass `--cache`. The cache format is:

```json
{"_meta": true, "model": "my-extractor v1.2"}
{"id": "case-001", "system_output": ["HP:0001250", "HP:0000252"]}
{"id": "case-002", "system_output": ["HP:0000365"]}
```

- Line 1 is metadata: `{"_meta": true, "model": "<name>"}` — the model name appears in the
  report for provenance.
- Each subsequent line maps a record `id` (matching your `--dataset`) to its predicted HPO IDs.
- A record whose id isn't in the cache is treated as an empty prediction; ClinEval prints the
  **cache hit-rate** and warns if it's partial or zero (a mismatch would otherwise look like a
  bad model rather than a lookup miss).

```bash
docker compose run --rm clineval uv run clineval run \
    --dataset mine.jsonl --cache my_predictions.jsonl --report reports/mine.md
```

> Note: by default `clineval run` gets predictions from the extractor (cache or `--live`); a
> `system_output` field inside the **dataset** JSONL is ignored (with a warning) unless you
> pass `--predictions-from-dataset`, which scores those dataset-supplied predictions directly
> instead of consulting a cache or live model.

**Regenerating the bundled cache from a live model:** the committed
`examples/data/cached_predictions.jsonl` was produced by running the demo once with `--live`
against a local model and recording its outputs. You can regenerate your own the same way.

---

## 8. Tuning the scoring

Three flags control the clinical/semantic layer:

- `--relatedness-tau` (default `0.3`) — how close (Lin similarity) a predicted term must be to
  a gold term to count as a near-miss rather than spurious. Use a value in `(0, 1]`. The
  default is calibrated for `lin`; re-tune it if you switch similarity method.
- `--ic-high-threshold` (default `3.0`) — Information-Content cutoff above which a missed or
  spurious term is flagged as clinically significant (rare/specific).
- `--similarity-method` (default `lin`) — `lin`, `jc`, or `jaccard`. These are the normalized,
  self-similarity=1 measures; Resnik and friends are intentionally not selectable here because
  they would make semantic F1 fall below exact F1.

```bash
docker compose run --rm clineval uv run clineval run \
    --dataset synthetic --report reports/report.md \
    --relatedness-tau 0.4 --ic-high-threshold 2.5 --similarity-method jaccard
```

---

## 9. Running the tests, coverage, and lint

```bash
docker compose run --rm clineval uv run pytest        # full suite + enforced coverage gate
docker compose run --rm clineval uv run ruff check .  # lint
```

- The suite runs **fully offline and deterministically** (no live LLM, no network; the HPO
  ontology loads once per session).
- **Coverage is enforced at build time** via `--cov-fail-under` in `pyproject.toml` — a run
  that drops below the threshold fails. To see the per-file coverage report:
  ```bash
  docker compose run --rm clineval uv run pytest --cov=clineval --cov-report=term-missing
  ```

---

## 10. The notebook walkthrough

For a step-by-step, inspectable version of the same pipeline (loads data, runs the cached
extractor, evaluates, and renders the report inline):

```bash
docker compose run --rm clineval uv run --with jupyter \
    jupyter nbconvert --to notebook --execute examples/hpo_extraction_demo.ipynb \
    --output executed_demo.ipynb
```

Or open `examples/hpo_extraction_demo.ipynb` in your own Jupyter/VS Code and run the cells.

---

## 11. Where things live

```
clineval/
├── core/                 # task-agnostic engine (schema, dataset, metric registry, evaluator, report)
│   └── ontology/         #   the only code that touches PyHPO (IC, similarity, alignment)
├── tasks/hpo_extraction/ # Module A: metrics (Tier 1/2/3), extractor, adapters, dataset loader
├── regulatory/           # metric → EU AI Act / IVDR / ISO 15189:2022 mapping
├── templates/            # the Jinja report template
└── cli.py                # the `clineval run` entry point
datasets/                 # GSC+ download + convert script (data itself is git-ignored)
examples/                 # bundled synthetic data, cached predictions, and the demo notebook
tests/                    # the test suite
reports/                  # generated reports (git-ignored)
```

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `failed to connect to the docker API …` | Docker Desktop isn't running — start it, then retry. |
| `--live` errors with a connection failure | From Docker use `--base-url http://host.docker.internal:1234/v1` (not `localhost`), and make sure your local model server is running. |
| `Error: … not found … run: python datasets/download_gsc.py` | You used `--dataset gsc` without downloading GSC+ first (§6). |
| `--dataset gsc` report is all zeros | The converter found no annotations/documents (a format/path mismatch — the GSC+ layout is unverified; see §6). Re-check the download and the converter's assumed layout. |
| A report shows all-zero scores with `[0/N cache hits]` in the Model line | Your `--cache` file doesn't cover the dataset's record ids — align them, or use `--live`. |
| First `docker compose build` is slow | Expected — it installs Python 3.14 and dependencies once; later runs reuse the cached layer. |

---

## 13. Data & privacy

ClinEval is designed to run **fully on-prem**: no data leaves your machine on the default
(cached) path, and `--live` talks only to a model server *you* run. Use **public data only** —
**do not** put patient data / PHI into datasets, caches, or reports.

---

## Disclaimer

ClinEval is a general technical/educational tool, **not** legal or regulatory-compliance
advice. Dataset licenses, HPO versions, and regulatory clauses change; confirm dataset license
terms before use and consult qualified regulatory/quality professionals against the current
official texts before relying on any output as validation evidence.
