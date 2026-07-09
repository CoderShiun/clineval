# ClinEval — Module A: HPO Extraction Evaluation — Design Spec

- **Status:** Approved (2026-07-09), pending implementation plan
- **Scope:** First MVP of the open-source `clineval` toolkit — Module A (HPO extraction evaluation) plus the generic, task-agnostic core it plugs into.
- **Positioning:** ClinEval is an **evaluator / validation rig** for clinical LLM outputs ("grader", not a model builder). Its core is generic ("clinical LLM output evaluation + regulatory validation evidence"); **HPO extraction is the first reference implementation**. The architecture must keep future tasks (e.g. Module B, report-generation eval) cheap to add.

> **Disclaimer:** This document is a general technical design and learning reference, **not** legal or regulatory-compliance advice. Dataset licenses, HPO versions, and regulatory clauses/timelines change. Confirm dataset license terms before bundling, and consult qualified regulatory/quality professionals against the current official texts before any real-world validation use.

---

## 1. Scope & Definition of Done

This build delivers **Module A: HPO Extraction Evaluation** and the **generic core** it plugs into.

**Definition of Done:** one command runs the full pipeline on ~10 documents and writes a Markdown report. The first commit = this pipeline working end-to-end and producing a report.

**In scope (this build):**
- Generic core: shared schema, dataset loader, metric base + task-keyed registry, evaluator, report generator.
- PyHPO-backed ontology layer: loading, Information Content, semantic similarity, version alignment.
- Metrics, Tiers 1–3 (exact; semantic/hierarchy-aware; clinical layer).
- GSC+ dataset loader + runtime downloader; committed synthetic fixture.
- System-under-test extractor: OpenAI-compatible (LM Studio) + cached-prediction replay.
- Markdown report including a Regulatory Evidence Mapping table and an Ontology Alignment section.
- Typer CLI + a notebook demo.
- pytest suite (offline, deterministic).
- MIT `LICENSE`, portfolio-quality `README.md`.

**Out of scope (YAGNI — do NOT build now):**
- Module B (report-generation eval) — placeholder folder with a docstring only.
- Any UI / dashboard / web app.
- DeepEval / RAGAS; RAG.
- Mention-level / boundary metrics (document-level only for the MVP).
- Presidio / PII redaction (note as future).
- Auth; PyPI publishing; CI beyond an optional basic test workflow.
- BioCreative VIII loader — documented fast-follow (its own PR); see §6.
- HTML report (Markdown only for the MVP).
- `replaced_by` auto-remapping of obsolete HPO IDs — post-MVP; see §3.
- Lin-similarity floor for semantic P/R — post-MVP; see §4 and §12.

---

## 2. Architecture — generic core + pluggable task

The seam that makes Module B cheap later: **a Task = (dataset schema + adapter + metric set + report template)**, wired through a shared schema and a task-keyed metric registry.

```
clineval/
├── pyproject.toml                 # uv, latest Python (3.14); runs via Docker
├── Dockerfile                     # python:3.14-slim + uv + deps
├── compose.yaml                   # dev/run service; bind-mounts repo
├── .dockerignore
├── README.md                      # English, portfolio-quality
├── LICENSE                        # MIT
├── .gitignore
├── clineval/
│   ├── __init__.py
│   ├── core/                      # task-agnostic
│   │   ├── schema.py              # PredictionRecord, EvaluationResult
│   │   ├── dataset.py             # DatasetLoader ABC + JSONL loader
│   │   ├── metric.py              # Metric base + registry (dispatch by task)
│   │   ├── evaluator.py           # runs a task's metric set over records
│   │   ├── report.py              # EvaluationResult -> Markdown (Jinja2)
│   │   └── ontology/
│   │       ├── hpo.py             # PyHPO wrapper: load, version, id normalization, alt_id/obsolete
│   │       ├── ic.py              # Information Content access
│   │       └── similarity.py      # Resnik / Lin / JC / Jaccard / BMA
│   ├── tasks/
│   │   ├── hpo_extraction/        # ★ Module A (this build)
│   │   │   ├── metrics.py         # Tier 1/2/3 metrics (registered)
│   │   │   ├── extractor.py       # OpenAICompatible + Cached
│   │   │   ├── adapters.py        # normalize system output -> HPO ID list
│   │   │   └── datasets.py        # GscPlusLoader
│   │   └── report_generation/     # Module B placeholder (docstring only)
│   ├── regulatory/
│   │   └── mapping.py             # metric -> AI Act / IVDR / ISO 15189:2022
│   ├── templates/
│   │   └── report.md.j2
│   └── cli.py                     # Typer: clineval run ...
├── datasets/
│   ├── download_gsc.py            # fetch real GSC+ at runtime (git-ignored output)
│   └── README.md                  # source + license notes
├── examples/
│   ├── data/
│   │   ├── synthetic_mini.jsonl       # ~10 synthetic gold records (committed)
│   │   └── cached_predictions.jsonl   # cached real predictions (committed)
│   └── hpo_extraction_demo.ipynb
├── reports/                       # generated output (git-ignored)
└── tests/
```

**Data contract:** `PredictionRecord = {id, input_text, system_output, gold_reference, metadata}`.
- Module A: `system_output` and `gold_reference` are lists of HPO IDs.
- Module B (future): `system_output` = generated report text; `gold_reference` = reference report + source facts.

The **metric registry dispatches by task name**, so adding Module B = a new task folder + registered metrics, **without touching Module A**. This registry + shared schema is exactly what keeps future tasks additive.

**Data flow:**
`DatasetLoader → records → Extractor fills system_output → Evaluator runs the task's registered metrics (with an EvalContext holding the loaded ontology + config) → EvaluationResult → Report renderer (Jinja2) → Markdown`.

---

## 3. Ontology layer (`core/ontology/`, PyHPO wrapper)

Isolated so metrics never call PyHPO directly — this keeps metrics testable and PyHPO swappable (fallback: pronto/fastobo + custom). Three focused units:

- **`hpo.py`** — load the ontology once; expose the **pinned HPO version**; normalize IDs; resolve `alt_id → primary`; detect obsolete/unknown IDs.
- **`ic.py`** — Information Content per term, `IC(t) = -log(freq)`, using PyHPO's **disease (OMIM) annotation frequency by default** (configurable to gene). The chosen frequency basis is recorded in the report (run metadata + Ontology Alignment), since it affects IC and all IC-weighted/semantic scores.
- **`similarity.py`** — pairwise **Resnik / Lin / Jiang-Conrath / Jaccard(ancestors)** and set-level **Best-Match Average (BMA)**, delegating to PyHPO.

### 3.1 HPO ID format normalization (must exist or nothing matches)

GSC+ writes HPO IDs with underscores (`HP_0000110`); PyHPO uses colons (`HP:0000110`). A shared helper normalizes IDs — `HP_0000110 → HP:0000110`, trimming whitespace and upper-casing the `HP` prefix — and is applied to **both gold and predictions**:
- gold IDs in `GscPlusLoader` (and the JSONL loader),
- predicted IDs in `tasks/hpo_extraction/adapters.py`,

before any ontology lookup or matching. This is a hard prerequisite for Tier 1 exact matching to work at all.

### 3.2 Version alignment (applied at load, to both gold and predictions)

1. **Resolve** secondary IDs `alt_id → primary` (lossless; the same term; logged). PyHPO can look these up.
2. **Merged/obsolete** IDs with no clean alt_id match: **detect, count, and report — do NOT auto-remap** via `replaced_by` in the MVP. Flagged IDs are excluded from scoring, with counts surfaced in the report.
3. **Record** for the report's Ontology Alignment section: HPO version used, IC frequency basis, # alt_ids resolved, # merged/obsolete flagged, and the handling policy.
4. **Pin/record** the exact HPO release PyHPO uses, so results are reproducible.

*Rationale:* `replaced_by` remapping has ambiguous cases (one-to-many, no successor, multiple `consider` candidates) that need judgement; auto-remapping now risks silently altering gold before the core is validated. Full `replaced_by` remapping is a good post-MVP enhancement.

---

## 4. Metrics — three tiers (`tasks/hpo_extraction/metrics.py`)

All metrics are **document-level, macro-averaged** across documents. They are registered as a small set of focused `Metric` units under task `hpo_extraction`; each receives records + an `EvalContext` (loaded ontology + config) and returns a structured result the evaluator merges.

### Tier 1 — standard, exact match
Precision, Recall, and `F1 = 2·P·R / (P + R)` on HPO concept IDs, via set operations, per document, then macro-averaged.

### Tier 2 — semantic / hierarchy-aware (the differentiator)
- **Information Content** per term; **Resnik** (IC of the Most Informative Common Ancestor); **Lin** = `2·IC(MICA) / (IC(t1)+IC(t2))`; **Jiang-Conrath**; **Jaccard** on ancestor sets.
- **Set-based Best-Match Average (BMA)** between the predicted and gold sets (Phenomizer-style document-level semantic score).
- **Semantic P/R/F1 with partial credit**, defined by asymmetric best-match on **Lin** (normalized 0–1):
  - semantic **Recall** = mean over gold terms of `max Lin(gold, any predicted)`
  - semantic **Precision** = mean over predicted terms of `max Lin(pred, any gold)`
  - **IC-weighted** variant weights each term's contribution by its IC (rare/specific terms count more)
  - semantic **F1** = harmonic mean of semantic Precision and Recall.
- Exact P/R/F1 is the special case where match quality is 0/1 on ID equality, so the report's headline **"exact F1 vs semantic F1 gap"** falls straight out. This contrast is itself the persuasive, novel insight (many "errors" are clinically near-misses).

> **Approaches considered for semantic P/R/F1:** (a) **best-match / BMA partial credit** — *chosen*: literature-grounded, continuous, directly comparable to exact; (b) threshold-based near-miss credit (a near-miss counts as a full hit above a similarity cutoff) — rejected as coarser and cutoff-sensitive; (c) ancestor-set Jaccard only — rejected as it ignores IC.

> **Deferred (post-MVP):** a small **Lin floor** for semantic P/R, to avoid crediting distant, coincidental shared ancestry. Not in the MVP; noted in §12.

### Tier 3 — clinical layer
- **Error taxonomy** (per residual term after exact matching):
  - **missed** — a gold term the system failed to output, with no near counterpart (FN).
  - **wrong-granularity** — a predicted term that is a true-path ancestor/descendant of a gold term (parent-child near-miss).
  - **wrong-term** — a predicted term that is related but not parent-child (shares informative ancestry / Lin ≥ τ) — "in the neighborhood but wrong".
  - **spurious** — an unrelated predicted term (~no shared informative ancestor; hallucination) (FP).
  - `τ` (relatedness threshold) is configurable with a documented default.
- **Clinical-significance flags:**
  - missed **high-IC** gold term (rare/specific phenotype missed).
  - high-IC **spurious** FP (could change variant prioritization).
  - IC threshold configurable.

---

## 5. Extractor — the system-under-test (`tasks/hpo_extraction/extractor.py`)

Deliberately simple — it is the **evaluated** object, not the product. An `Extractor` protocol `extract(text) -> list[HPO IDs]`, with two implementations:

- **`OpenAICompatibleExtractor(base_url, model, api_key)`** — calls LM Studio (`http://localhost:1234/v1` by default) via the `openai` client; prompts for HPO terms; `adapters.py` normalizes the raw output to HPO IDs (including the `HP_ → HP:` normalization of §3.1). Configurable, so it also works with Ollama / vLLM / any OpenAI-compatible server.
- **`CachedExtractor(path)`** — replays committed predictions keyed by record id.

**Default behaviour (per approved decision):** the demo defaults to **cached** predictions — a reviewer with no LM Studio still gets a real report with genuine model numbers, and CI can exercise the whole pipeline. A `--live` flag calls LM Studio and can refresh the cache. Poor raw-LLM accuracy is expected and is exactly what the eval measures.

**Provenance:** the cached-predictions file records **which model/version produced it** (a header/metadata line), and that model identifier is surfaced in the report's run metadata.

---

## 6. Datasets (`tasks/hpo_extraction/datasets.py`, `datasets/`)

- **`DatasetLoader` ABC** (in `core/dataset.py`) + a **JSONL loader** for user-supplied `{input_text, gold_reference}` records (bring-your-own gold + predictions).
- **`GscPlusLoader`** — parses GSC+ into `PredictionRecord`s, applying HPO-ID normalization (§3.1) to gold.
- **`datasets/download_gsc.py`** — fetches real GSC+ at runtime into a **git-ignored** folder. **`datasets/README.md`** records the source and **license** (license confirmed during implementation *before* any bundling; prefer the downloader over committing raw data).
- **`examples/data/synthetic_mini.jsonl`** — ~10 clearly-synthetic records (committed), powering pytest and the always-offline smoke demo.
- **`examples/data/cached_predictions.jsonl`** — cached real predictions (committed), with model provenance (§5).

**BioCreative VIII Track 3** — deliberately deferred. The `DatasetLoader` seam is designed so a `BioCreativeLoader` drops in later as its own PR without touching Module A.

---

## 7. Report (`core/report.py`, `templates/report.md.j2`)

Jinja2 → Markdown (HTML deferred). Sections:
1. **Run metadata** — dataset, N docs, model/endpoint (or "cached", with the cached model identifier), **HPO version**, **IC frequency basis**, timestamp (injected so tests stay deterministic).
2. **Overall scores** — Tier 1 exact P/R/F1; Tier 2 semantic P/R/F1, BMA, IC-weighted — with the **exact-vs-semantic F1 gap highlighted**.
3. **Per-document breakdown** table.
4. **Error-taxonomy** counts + examples (missed / spurious / wrong-granularity / wrong-term).
5. **Clinical-significance flags.**
6. **Ontology Alignment** — HPO version, IC frequency basis, # alt_ids resolved, # merged/obsolete flagged, handling policy.
7. **Regulatory Evidence Mapping** — the table in §8.
8. **Disclaimer** — not legal/regulatory advice.

---

## 8. Regulatory mapping (`regulatory/mapping.py`)

A static mapping, rendered as a table (MVP = a simple mapping table). ISO 15189 references use the **2022 edition** numbering.

| ClinEval evidence | EU AI Act | IVDR | ISO 15189:2022 |
|---|---|---|---|
| Exact P/R/F1 | Art 15 (accuracy) | Annex XIII analytical performance | 7.3.2 verification of examination methods |
| Semantic F1 / IC-weighted | Art 15 (appropriate accuracy metrics; robustness) | performance evaluation | 7.3.3 validation of examination methods |
| Error taxonomy + significance flags | Art 15 (robustness) | performance / risk evidence | 7.3.7 ensuring validity of results + 7.5 nonconforming work (clinical significance) |
| Ontology alignment / traceability | Art 12 (logging & traceability) | technical documentation | Clause 8 management system (control of records & documents) |

The rendered table carries the §0 disclaimer.

---

## 9. CLI (`cli.py`, Typer)

```
clineval run \
  --task hpo_extraction \
  --dataset <gsc|synthetic|path.jsonl> \
  --report <out.md> \
  [--live] [--base-url http://localhost:1234/v1] [--model <name>] [--api-key <key>]
```

The same pipeline is callable from the notebook / a plain script. **Docker note:** because the CLI runs inside a container, `--live` must reach the host's LM Studio via `--base-url http://host.docker.internal:1234/v1` (not `localhost`); the offline default path needs no network.

---

## 10. Testing (TDD, pytest)

Red-green-refactor per unit. Tests use tiny hand-crafted inputs and the synthetic fixture, and run **offline and deterministic** (no live LLM; injected timestamp). Coverage:
- schema round-trip;
- dataset / JSONL parse (incl. `HP_ → HP:` normalization);
- ontology wrapper (assert relationships/ranges, not brittle exact floats);
- Tier 1 / 2 / 3 metrics;
- version alignment (alt_id resolve + obsolete flag);
- report rendering (expected sections given a known `EvaluationResult`);
- regulatory table;
- CLI smoke test producing a report file.

PyHPO-backed tests load the real ontology once (shared fixture).

---

## 11. Tooling & conventions

- **Everything runs in Docker / docker compose. Nothing is installed on the host machine** (no host Python, no host uv). The one dev/run image builds the toolchain; all `uv` / `pytest` / `clineval` commands execute via `docker compose run --rm clineval <cmd>`.
- **Latest Python** — target **3.14** (the current release) via the container base image; the floor is set so a one-line base-image change drops to the latest previous minor if a dependency lacks 3.14 wheels at build time.
- Packaged with **uv** + `pyproject.toml`; `uv` resolves the **newest compatible** version of each dependency (no upper pins).
- Runtime deps: `pyhpo`, `openai`, `typer`, `jinja2`. Dev: `pytest`, `ruff`.
- `reports/` and downloaded datasets are git-ignored.
- All code, comments, docstrings, README, and docs in **English**.
- **PUBLIC data only. No PHI.** Runs fully locally (on-prem, containerized). Permissive licenses only.
- **MIT `LICENSE`** at repo root.

---

## 12. Known risks / to verify during implementation

- **Docker Desktop must be running** — the CLI is installed but the daemon was stopped when this plan was written. Start it before the first task builds the image. No host Python/uv is installed (by design — everything is containerized).
- **Python 3.14 dependency support** — if PyHPO or another dependency lacks 3.14 wheels at build time, drop the base image to the latest previous minor (e.g. `python:3.13-slim`) and the `requires-python` floor accordingly; this is a one-line change thanks to Docker. The ontology smoke test (Task 7) surfaces any runtime incompatibility immediately.
- **PyHPO API specifics** (exact method names for IC kind, `similarity_score`, BMA, alt_id lookup) and **whether PyHPO bundles its ontology data or fetches it at runtime** are verified in the first ontology task; the wrapper isolates any surprises. If data is fetched at runtime, mount a cache volume so it persists across container runs.
- **GSC+ license & on-disk format** confirmed before the loader/downloader is finalized.
- **Local-model HPO-ID output quality** is low by nature; the adapter tolerates unresolvable outputs (they score as errors — realistic).
- **Deferred:** Lin-similarity floor for semantic P/R (avoid crediting distant coincidental ancestry); `replaced_by` remapping of obsolete IDs; BioCreative VIII loader; HTML report.
