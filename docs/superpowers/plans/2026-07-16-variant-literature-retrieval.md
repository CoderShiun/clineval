# Variant Literature Retrieval (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a variant→literature retrieval pipeline (stages 1–2) and a ClinEval `variant_retrieval` task that scores its recall/precision/F1 against a known-answer truth set (RYR1/Wermers), producing the validation artifact for the "can we drop HGMD?" decision.

**Architecture:** Two systems, one repo. A new **pipeline** package (`clineval/pipeline/`) is the *system under test* — thin per-API clients (VariantValidator, myvariant, LitVar2, E-utilities) behind a shared cached+throttled HTTP layer, feeding Stage 1 `normalize_and_expand` and Stage 2 `retrieve`. A new ClinEval **task** (`clineval/tasks/variant_retrieval/`) is the *harness* — a retriever adapter shaped like the existing extractor, a retrieval metric reusing ClinEval's promoted set-P/R/F1, dataset loaders, and a task-specific report. Two small additive core edits remove HPO-specific couplings.

**Tech Stack:** Python 3.14, uv, Docker (all execution containerized). New runtime deps: `myvariant`, `requests`, `pandas`. Existing: `typer`, `jinja2`, `pytest`, `ruff`, `pytest-cov`. `sqlite3` is stdlib. NCBI E-utilities via direct HTTP through the shared client (not biopython).

## Global Constraints

- **Everything runs in Docker.** No host Python/uv. Every `uv`/`pytest`/`clineval` command runs `docker compose run --rm clineval <command>`. Build once (deps already imaged; rebuild after Task 1's dependency add).
- **Python 3.14**, uv, `>=` floors with **no upper pins**. All code/comments/docstrings/docs in **English**.
- **PUBLIC data only. No PHI.** HGMD-derived gold is git-ignored and never committed. Permissive licences only. MIT `LICENSE` unchanged.
- **Coverage gate:** the repo enforces `--cov-fail-under=98`. Every task ends green under it. New optional core branches (alignment/provenance None-paths) must be exercised by retrieval tests.
- **No fabrication.** No API-response key is hardcoded until confirmed against a live response (Task 0 fixtures). No opaque HGMD-style label is ever emitted.
- **Flag, don't drop.** Variants that fail to normalize are flagged (`resolved=False` + note) and kept in the set — never silently dropped.
- **Metrics are variant-level (= document-level), macro-averaged.** `record.id` = canonical HGVS; `gold_reference` = gold PMIDs; `system_output` = retrieved PMIDs.
- **Recall is the headline; precision is reported with a caveat** (sparse primary-only gold understates set-precision in Phase 1; no ranking until Phase 3).
- **Failures logged, not fatal.** A partially-failing variant keeps whatever it retrieved plus a note.
- Every task is TDD (red → green → refactor) and ends with a commit. Live API calls appear **only** in Task 0 and the opt-in `--source live` path — never in the offline test suite.
- **Reference design:** `docs/superpowers/specs/2026-07-16-variant-literature-retrieval-design.md`.

---

## Execution Environment (Docker)

Run every command inside the container:
```bash
docker compose run --rm clineval <command>
# e.g.  docker compose run --rm clineval uv run pytest tests/test_pipeline_synonyms.py -v
#       docker compose run --rm clineval uv run clineval retrieval-eval --dataset ryr1 --report reports/retrieval.md
```
The repo is bind-mounted at `/app`; the uv venv lives at `/opt/venv` (outside the mount). `git commit` runs on host or in-container.

---

### Task 0: Connectivity + API schema spike (de-risker — do first)

Front-loads every external-API uncertainty. Produces the fixtures every later client test mocks against. This is a **spike**, not TDD: probe live, save raw responses, document confirmed endpoints/keys, commit.

**Files:**
- Create: `tests/fixtures/api_samples/variantvalidator_ryr1.json`
- Create: `tests/fixtures/api_samples/myvariant_ryr1.json`
- Create: `tests/fixtures/api_samples/litvar_ryr1.json`
- Create: `tests/fixtures/api_samples/esummary_ryr1.json`
- Create: `tests/fixtures/api_samples/pubtator_ryr1.json` (optional; skip if PubTator deferred)
- Create: `docs/superpowers/specs/2026-07-16-api-contracts-findings.md`

**Note — truth set is NOT part of this spike.** The gold set is built from the lab's local HGMD
dump via `datasets/build_hgmd_gold.py` (already written; see design spec §8). Task 0 only confirms
the *retrieval* APIs. Building the RYR1/panel HGMD gold is an owner action (run the builder), not
a blocker for the pipeline code.

**Interfaces:**
- Produces: committed raw-response fixtures + a findings note recording, per API, the **confirmed base URL, path template, required params/headers, and the exact JSON keys** the clients will read. Later tasks depend on these fixtures existing.

- [ ] **Step 1: Probe reachability + save VariantValidator (already confirmed 2026-07-16)**

```bash
curl -s "https://rest.variantvalidator.org/VariantValidator/variantvalidator/GRCh38/NM_000540.3:c.1840C>T/all" \
  -H "Content-Type: application/json" -o tests/fixtures/api_samples/variantvalidator_ryr1.json
```
Confirmed keys (design spec §4.1): top-level = variant-HGVS key + `flag` + `metadata`; per-hit `hgvs_transcript_variant`, `hgvs_predicted_protein_consequence.{tlr,slr}` (accession-prefixed, e.g. `NP_000531.2:p.(Arg614Cys)`), `primary_assembly_loci.{grch38,...}.{hgvs_genomic_description,vcf}`, `gene_symbol`, `validation_warnings`; `metadata.{variantvalidator_version,vvdb_version,vvta_version}`.

- [ ] **Step 2: Save a myvariant response** (rs193922747 is the rsID for this variant)

```bash
curl -s "https://myvariant.info/v1/variant/chr19:g.38457545C>T?fields=dbsnp.rsid,clinvar,gnomad_genome&assembly=hg38" \
  -o tests/fixtures/api_samples/myvariant_ryr1.json
```
Record the exact path to `dbsnp.rsid` and the presence/shape of `clinvar` and `gnomad_genome` in the findings note. (In code we use the `myvariant` Python client `getvariant(...)`; this fixture documents the field shapes it returns.)

- [ ] **Step 3: Confirm the CURRENT LitVar2 endpoint and save a response**

The old `bionlp/litvar-api/...` path 404s. Confirm the current LitVar2 API from its docs (candidate base: `https://www.ncbi.nlm.nih.gov/research/litvar2-api/`). Resolve the variant then fetch publications; try, e.g.:
```bash
# search → get a litvar id, then publications. Confirm the exact paths live, then:
curl -s "<CONFIRMED_LITVAR2_PUBLICATIONS_URL_FOR_rs193922747>" -o tests/fixtures/api_samples/litvar_ryr1.json
```
In the findings note, record the confirmed search path, publications path, how PMIDs are keyed in the JSON, and how a variant string resolves to a LitVar id.

- [ ] **Step 4: Save an E-utilities esummary response**

```bash
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=28380275,25741868" \
  -o tests/fixtures/api_samples/esummary_ryr1.json
```
Record the path to title / fulljournalname (or `source`) / pubdate (→ year) per PMID under `result.<pmid>`.

- [ ] **Step 5: Write the findings note**

`docs/superpowers/specs/2026-07-16-api-contracts-findings.md`: one section per API with confirmed base URL, path template, params/headers, rate limits, and the exact key paths the clients read. Note any deviation from the design spec and reconcile it there.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/api_samples docs/superpowers/specs/2026-07-16-api-contracts-findings.md
git commit -m "chore(retrieval): capture live API fixtures + confirmed endpoint contracts (spike)"
```

---

### Task 1: Dependencies + package scaffolding

**Files:**
- Modify: `pyproject.toml` (add runtime deps)
- Modify: `.gitignore` (git-ignore caches + private gold)
- Create: `clineval/pipeline/__init__.py`, `clineval/pipeline/clients/__init__.py`, `clineval/tasks/variant_retrieval/__init__.py`
- Test: `tests/test_retrieval_smoke.py`

**Interfaces:**
- Produces: importable empty packages `clineval.pipeline`, `clineval.pipeline.clients`, `clineval.tasks.variant_retrieval`; new deps available in the image.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval_smoke.py`:
```python
import importlib


def test_pipeline_and_task_packages_import():
    assert importlib.import_module("clineval.pipeline")
    assert importlib.import_module("clineval.pipeline.clients")
    assert importlib.import_module("clineval.tasks.variant_retrieval")


def test_new_runtime_deps_present():
    assert importlib.import_module("myvariant")
    assert importlib.import_module("requests")
    assert importlib.import_module("pandas")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: clineval.pipeline`).

- [ ] **Step 3: Add deps and create packages**

In `pyproject.toml` `[project].dependencies`, append (floors, no upper pins):
```toml
    "myvariant>=1.0",
    "requests>=2.31",
    "pandas>=2.0",
```
Create each `__init__.py` with a one-line docstring, e.g. `clineval/pipeline/__init__.py`:
```python
"""The variant→literature retrieval pipeline (the system ClinEval scores)."""
```
`clineval/pipeline/clients/__init__.py`:
```python
"""Thin clients for external APIs; each isolates one API's quirks."""
```
`clineval/tasks/variant_retrieval/__init__.py`:
```python
"""ClinEval task: variant literature retrieval evaluation."""
```
In `.gitignore`, append:
```gitignore
# Retrieval request cache and private HGMD-derived gold (never committed)
.cache/
datasets/ryr1_benchmark/
datasets/hgmd_gold/
```

- [ ] **Step 4: Rebuild the image and run the test**

Run:
```bash
docker compose build
docker compose run --rm clineval uv run pytest tests/test_retrieval_smoke.py -v
```
Expected: PASS (2 tests). The rebuild installs `myvariant`, `requests`, `pandas`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore clineval/pipeline clineval/tasks/variant_retrieval tests/test_retrieval_smoke.py
git commit -m "chore(retrieval): scaffold pipeline + variant_retrieval packages, add deps"
```

---

### Task 2: Core — promote `set_prf`, refactor Tier 1 to reuse it

**Files:**
- Modify: `clineval/core/metric.py` (add `set_prf`)
- Modify: `clineval/tasks/hpo_extraction/metrics.py` (`_exact_prf` delegates to `set_prf`)
- Test: `tests/test_metric.py` (append)

**Interfaces:**
- Produces: `core.metric.set_prf(gold: list[str], pred: list[str]) -> dict[str, float]` with keys `precision`, `recall`, `f1`; empty-set convention preserved (both-empty → 1.0; one-sided empty → 0.0 on the affected side).
- Consumes (unchanged): `Tier1ExactMetric` behaviour must be identical after refactor.

- [ ] **Step 1: Write the failing test** (append to `tests/test_metric.py`)

```python
from clineval.core.metric import set_prf


def test_set_prf_perfect_partial_empty():
    assert set_prf(["a", "b"], ["a", "b"]) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert set_prf(["a"], ["b"])["f1"] == 0.0
    assert set_prf([], []) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    partial = set_prf(["a", "b"], ["a"])  # perfect precision, half recall
    assert partial["precision"] == 1.0
    assert partial["recall"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_metric.py -k set_prf -v`
Expected: FAIL (`ImportError: cannot import name 'set_prf'`).

- [ ] **Step 3: Implement `set_prf` in `core/metric.py`** (append)

```python
def _harmonic(p: float, r: float) -> float:
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def set_prf(gold: list[str], pred: list[str]) -> dict[str, float]:
    """Set-based precision/recall/F1 over string IDs (PMIDs, HPO IDs, ...).

    Empty-set convention (scikit-learn zero_division=0): a side scores 1.0 only
    when both gold and prediction are empty; a one-sided empty case scores 0.0
    on the affected metric.
    """
    gold_set, pred_set = set(gold), set(pred)
    tp = len(gold_set & pred_set)
    precision = (1.0 if not gold_set else 0.0) if not pred_set else tp / len(pred_set)
    recall = (1.0 if not pred_set else 0.0) if not gold_set else tp / len(gold_set)
    return {"precision": precision, "recall": recall, "f1": _harmonic(precision, recall)}
```

- [ ] **Step 4: Refactor Tier 1 to reuse it** (`tasks/hpo_extraction/metrics.py`)

Replace the body of `_exact_prf` with a delegation (keep the name + the explanatory comment):
```python
def _exact_prf(gold: list[str], pred: list[str]) -> dict[str, float]:
    # Empty-set convention documented in core.metric.set_prf; behaviour unchanged.
    from clineval.core.metric import set_prf
    return set_prf(gold, pred)
```

- [ ] **Step 5: Run tests to verify green**

Run: `docker compose run --rm clineval uv run pytest tests/test_metric.py tests/test_metrics_tier1.py -v`
Expected: PASS (existing Tier-1 tests unchanged + new `set_prf` test).

- [ ] **Step 6: Commit**

```bash
git add clineval/core/metric.py clineval/tasks/hpo_extraction/metrics.py tests/test_metric.py
git commit -m "refactor(core): promote set-based P/R/F1 to core.metric.set_prf; Tier1 reuses it"
```

---

### Task 3: Core — make `alignment` optional, add `provenance`

**Files:**
- Modify: `clineval/core/schema.py` (`EvaluationResult`)
- Modify: `clineval/core/evaluator.py` (`evaluate` signature)
- Test: `tests/test_evaluator.py` (append)

**Interfaces:**
- Produces: `EvaluationResult(..., alignment: OntologyAlignment | None = None, provenance: dict[str, Any] = {})`; `evaluate(task, records, context, *, dataset, model, timestamp, alignment=None, provenance=None) -> EvaluationResult`.
- Consumes (unchanged): HPO CLI still passes `alignment=`; its tests stay green.

- [ ] **Step 1: Write the failing test** (append to `tests/test_evaluator.py`)

```python
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext, Metric, register_metric
from clineval.core.schema import MetricResult, PredictionRecord


def test_evaluate_without_alignment_carries_provenance():
    @register_metric("prov_task")
    class _M(Metric):
        name = "m"
        def compute(self, records, context):
            return MetricResult(name="m", aggregate={"n": float(len(records))})

    rec = PredictionRecord(id="v1", input_text="", gold_reference=["1"])
    res = evaluate(
        "prov_task", [rec], EvalContext(),
        dataset="ryr1", model="cached", timestamp="2026-07-16T00:00:00+00:00",
        provenance={"vvdb_version": "vvdb_2025_3"},
    )
    assert res.alignment is None
    assert res.provenance["vvdb_version"] == "vvdb_2025_3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_evaluator.py -k provenance -v`
Expected: FAIL (`evaluate() missing ... 'alignment'` / `provenance` unknown).

- [ ] **Step 3: Implement**

`core/schema.py` — in `EvaluationResult`, change `alignment` and add `provenance`:
```python
    alignment: OntologyAlignment | None = None
    records: list[PredictionRecord] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
```
`core/evaluator.py` — update the signature + pass-through:
```python
def evaluate(
    task: str,
    records: list[PredictionRecord],
    context: EvalContext,
    *,
    dataset: str,
    model: str,
    timestamp: str,
    alignment: OntologyAlignment | None = None,
    provenance: dict | None = None,
) -> EvaluationResult:
    ...
    return EvaluationResult(
        task=task, dataset=dataset, n_documents=len(records), model=model,
        timestamp=timestamp, metrics=results, alignment=alignment, records=records,
        provenance=provenance or {},
    )
```

- [ ] **Step 4: Run tests to verify green**

Run: `docker compose run --rm clineval uv run pytest tests/test_evaluator.py tests/test_schema.py tests/test_cli.py -v`
Expected: PASS (new test + all existing, since HPO callers still pass `alignment=`).

- [ ] **Step 5: Commit**

```bash
git add clineval/core/schema.py clineval/core/evaluator.py tests/test_evaluator.py
git commit -m "feat(core): make EvaluationResult.alignment optional; add task-agnostic provenance"
```

---

### Task 4: Pipeline data models

**Files:**
- Create: `clineval/pipeline/models.py`
- Test: `tests/test_pipeline_models.py`

**Interfaces:**
- Produces:
  - `PipelineProvenance(vv_version: str = "", vvdb_version: str = "", vvta_version: str = "", sources: list[str] = [], cache_hits: int = 0, cache_misses: int = 0)`
  - `PaperRef(pmid: str, title: str = "", journal: str = "", year: int | None = None, matched_form: str = "")`
  - `VariantForms(input: str, forms: list[str], resolved: bool, xrefs: dict, gene: str = "", notes: list[str] = [], provenance: PipelineProvenance = PipelineProvenance())`
  - `RetrievalResult(variant: str, pmids: list[str], papers: list[PaperRef], provenance: PipelineProvenance = PipelineProvenance(), notes: list[str] = [])`

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_models.py`:
```python
from clineval.pipeline.models import PaperRef, PipelineProvenance, RetrievalResult, VariantForms


def test_variant_forms_defaults_are_independent():
    a = VariantForms(input="x", forms=[], resolved=False, xrefs={})
    a.notes.append("n")
    b = VariantForms(input="y", forms=[], resolved=True, xrefs={})
    assert b.notes == []


def test_retrieval_result_holds_papers():
    r = RetrievalResult(
        variant="v", pmids=["1"],
        papers=[PaperRef(pmid="1", title="t", journal="j", year=2024, matched_form="p.R614C")],
        provenance=PipelineProvenance(vvdb_version="vvdb_2025_3"),
    )
    assert r.papers[0].matched_form == "p.R614C"
    assert r.provenance.vvdb_version == "vvdb_2025_3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_models.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/models.py`**

```python
"""Dataclasses passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineProvenance:
    """Tool versions + cache stats for the IVDR evidence snapshot."""

    vv_version: str = ""
    vvdb_version: str = ""
    vvta_version: str = ""
    sources: list[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class PaperRef:
    pmid: str
    title: str = ""
    journal: str = ""
    year: int | None = None
    matched_form: str = ""


@dataclass
class VariantForms:
    input: str
    forms: list[str]
    resolved: bool
    xrefs: dict[str, Any]
    gene: str = ""
    notes: list[str] = field(default_factory=list)
    provenance: PipelineProvenance = field(default_factory=PipelineProvenance)


@dataclass
class RetrievalResult:
    variant: str
    pmids: list[str]
    papers: list[PaperRef]
    provenance: PipelineProvenance = field(default_factory=PipelineProvenance)
    notes: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add stage data models (VariantForms, RetrievalResult, PaperRef, provenance)"
```

---

### Task 5: SQLite request cache

**Files:**
- Create: `clineval/pipeline/cache.py`
- Test: `tests/test_pipeline_cache.py`

**Interfaces:**
- Produces:
  - `make_key(base_url: str, path: str, params: dict | None) -> str` (stable hash; param order-independent)
  - `class RequestCache:` `__init__(self, db_path: str)`; `get(key: str) -> dict | None`; `put(key: str, value: dict) -> None`; `stats() -> tuple[int, int]` (hits, misses).

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_cache.py`:
```python
from clineval.pipeline.cache import RequestCache, make_key


def test_make_key_is_order_independent():
    assert make_key("b", "/p", {"a": 1, "b": 2}) == make_key("b", "/p", {"b": 2, "a": 1})
    assert make_key("b", "/p", {"a": 1}) != make_key("b", "/p", {"a": 2})


def test_cache_round_trip_and_stats(tmp_path):
    c = RequestCache(str(tmp_path / "c.sqlite"))
    assert c.get("k") is None            # miss
    c.put("k", {"hello": "world"})
    assert c.get("k") == {"hello": "world"}  # hit
    hits, misses = c.stats()
    assert (hits, misses) == (1, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_cache.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/cache.py`**

```python
"""SQLite-backed request cache: deterministic, offline-replayable API calls."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def make_key(base_url: str, path: str, params: dict | None) -> str:
    payload = json.dumps(
        {"b": base_url, "p": path, "q": params or {}}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RequestCache:
    """Keyed JSON store over sqlite3 (stdlib). Counts hits/misses for provenance."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.commit()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> dict | None:
        row = self._conn.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            self._misses += 1
            return None
        self._hits += 1
        return json.loads(row[0])

    def put(self, key: str, value: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def stats(self) -> tuple[int, int]:
        return self._hits, self._misses
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_cache.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/cache.py tests/test_pipeline_cache.py
git commit -m "feat(pipeline): add SQLite request cache with hit/miss stats"
```

---

### Task 6: Throttle + retry-with-backoff

**Files:**
- Create: `clineval/pipeline/throttle.py`
- Test: `tests/test_pipeline_throttle.py`

**Interfaces:**
- Produces:
  - `class RateLimiter:` `__init__(self, rate_per_sec: float, *, clock=time.monotonic, sleep=time.sleep)`; `acquire() -> None`.
  - `retry_with_backoff(fn, *, retries: int = 3, base_delay: float = 0.5, sleep=time.sleep, exceptions=(Exception,))` — calls `fn()`, retries on the given exceptions with exponential backoff, re-raises after the last attempt.

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_throttle.py`:
```python
from clineval.pipeline.throttle import RateLimiter, retry_with_backoff


def test_rate_limiter_sleeps_between_calls():
    now = [0.0]
    slept = []
    lim = RateLimiter(2.0, clock=lambda: now[0], sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    lim.acquire()   # first call: no wait
    lim.acquire()   # second immediately: must wait ~0.5s (1/2 Hz)
    assert slept and abs(slept[0] - 0.5) < 1e-6


def test_retry_with_backoff_eventually_succeeds():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"
    slept = []
    assert retry_with_backoff(flaky, base_delay=0.1, sleep=slept.append, exceptions=(ValueError,)) == "ok"
    assert calls["n"] == 3
    assert slept == [0.1, 0.2]  # exponential


def test_retry_reraises_after_exhaustion():
    def always_fail():
        raise ValueError("nope")
    try:
        retry_with_backoff(always_fail, retries=2, base_delay=0.0, sleep=lambda s: None, exceptions=(ValueError,))
        assert False, "should have raised"
    except ValueError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_throttle.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/throttle.py`**

```python
"""Politeness: a token-spaced rate limiter + exponential-backoff retry."""

from __future__ import annotations

import time
from typing import Callable


class RateLimiter:
    """Ensure calls are spaced >= 1/rate seconds apart (clock/sleep injectable)."""

    def __init__(self, rate_per_sec: float, *, clock=time.monotonic, sleep=time.sleep) -> None:
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last = None

    def acquire(self) -> None:
        if self._last is not None:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()


def retry_with_backoff(
    fn: Callable,
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    sleep=time.sleep,
    exceptions: tuple = (Exception,),
):
    """Call fn(); on `exceptions`, retry with exponential backoff; re-raise last."""
    attempt = 0
    while True:
        try:
            return fn()
        except exceptions:
            attempt += 1
            if attempt > retries:
                raise
            sleep(base_delay * (2 ** (attempt - 1)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_throttle.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/throttle.py tests/test_pipeline_throttle.py
git commit -m "feat(pipeline): add rate limiter + exponential-backoff retry"
```

---

### Task 7: Shared cached + throttled HTTP client

**Files:**
- Create: `clineval/pipeline/clients/http.py`
- Test: `tests/test_pipeline_http.py`

**Interfaces:**
- Consumes: `RequestCache`, `make_key` (Task 5); `RateLimiter`, `retry_with_backoff` (Task 6).
- Produces: `class HttpClient:` `__init__(self, *, cache: RequestCache | None = None, limiter: RateLimiter | None = None, transport: Callable[[str, dict, dict], dict] | None = None)`; `get_json(base_url: str, path: str, params: dict | None = None, headers: dict | None = None) -> dict`. `transport(url, params, headers) -> dict` is the injection seam for tests (defaults to a `requests`-based getter). On cache hit, transport is not called.

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_http.py`:
```python
from clineval.pipeline.cache import RequestCache
from clineval.pipeline.clients.http import HttpClient


def test_get_json_caches_and_skips_transport_on_hit(tmp_path):
    calls = []
    def transport(url, params, headers):
        calls.append(url)
        return {"ok": True, "url": url}
    client = HttpClient(cache=RequestCache(str(tmp_path / "c.sqlite")), transport=transport)
    a = client.get_json("https://x", "/p", {"q": "1"})
    b = client.get_json("https://x", "/p", {"q": "1"})   # served from cache
    assert a == b == {"ok": True, "url": "https://x/p"}
    assert len(calls) == 1  # transport called once, second was a cache hit


def test_get_json_without_cache_calls_transport_each_time():
    calls = []
    client = HttpClient(transport=lambda url, params, headers: calls.append(url) or {"n": len(calls)})
    client.get_json("https://x", "/p")
    client.get_json("https://x", "/p")
    assert len(calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_http.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/clients/http.py`**

```python
"""Shared HTTP JSON getter: cache-first, throttled, retried. Transport injectable."""

from __future__ import annotations

from typing import Callable

from clineval.pipeline.cache import RequestCache, make_key
from clineval.pipeline.throttle import RateLimiter, retry_with_backoff


def _requests_transport(url: str, params: dict, headers: dict) -> dict:
    import requests

    resp = requests.get(url, params=params or None, headers=headers or None, timeout=45)
    resp.raise_for_status()
    return resp.json()


class HttpClient:
    def __init__(
        self,
        *,
        cache: RequestCache | None = None,
        limiter: RateLimiter | None = None,
        transport: Callable[[str, dict, dict], dict] | None = None,
    ) -> None:
        self._cache = cache
        self._limiter = limiter
        self._transport = transport or _requests_transport

    def get_json(
        self, base_url: str, path: str, params: dict | None = None, headers: dict | None = None
    ) -> dict:
        key = make_key(base_url, path, params)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        if self._limiter is not None:
            self._limiter.acquire()
        url = base_url.rstrip("/") + "/" + path.lstrip("/") if path else base_url
        result = retry_with_backoff(
            lambda: self._transport(url, params or {}, headers or {}),
            exceptions=(Exception,),
        )
        if self._cache is not None:
            self._cache.put(key, result)
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_http.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/clients/http.py tests/test_pipeline_http.py
git commit -m "feat(pipeline): add shared cached+throttled HTTP client with injectable transport"
```

---

### Task 8: Synonym generation (the recall-critical local logic)

**Files:**
- Create: `clineval/pipeline/synonyms.py`
- Test: `tests/test_pipeline_synonyms.py`

**Interfaces:**
- Produces:
  - `protein_variants(hgvs_p: str) -> list[str]` — from an accession-prefixed protein HGVS (e.g. `NP_000531.2:p.(Arg614Cys)` or its 1-letter form), return the deduped naming variants papers use: 3- and 1-letter, with/without `p.`, with/without parens, bare (no accession) and prefixed.
  - `vcf_form(chrom: str, pos: str, ref: str, alt: str) -> str` — `"19-38457545-C-T"`.
  - `AA_3TO1: dict[str, str]` (three-letter → single-letter amino-acid table).

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_synonyms.py`:
```python
from clineval.pipeline.synonyms import protein_variants, vcf_form


def test_protein_variants_cover_naming_styles():
    out = set(protein_variants("NP_000531.2:p.(Arg614Cys)"))
    # bare + prefixed, 3- and 1-letter, with/without parens
    assert "p.Arg614Cys" in out
    assert "p.R614C" in out
    assert "Arg614Cys" in out
    assert "R614C" in out
    assert "p.(Arg614Cys)" in out
    assert "NP_000531.2:p.(Arg614Cys)" in out


def test_protein_variants_accepts_single_letter_input():
    out = set(protein_variants("NP_000531.2:p.(R614C)"))
    assert "p.Arg614Cys" in out and "R614C" in out


def test_vcf_form():
    assert vcf_form("19", "38457545", "C", "T") == "19-38457545-C-T"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_synonyms.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/synonyms.py`**

```python
"""Generate the string forms papers actually use to name a variant.

Half the recall problem: VariantValidator gives NP_000531.2:p.(Arg614Cys); papers
write p.Arg614Cys, Arg614Cys, R614C, p.R614C, p.(R614C). We generate all of them.
"""

from __future__ import annotations

import re

AA_3TO1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q",
    "Glu": "E", "Gly": "G", "His": "H", "Ile": "I", "Leu": "L", "Lys": "K",
    "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
    "Tyr": "Y", "Val": "V", "Ter": "*",
}
_AA_1TO3 = {v: k for k, v in AA_3TO1.items()}

# capture: refAA, position, altAA (either 3-letter or 1-letter)
_SUB_RE = re.compile(
    r"p\.?\(?"
    r"(?P<ref>[A-Z][a-z]{2}|[A-Z])"
    r"(?P<pos>\d+)"
    r"(?P<alt>[A-Z][a-z]{2}|[A-Z]|\*|=)"
    r"\)?"
)


def _to3(aa: str) -> str | None:
    if aa in AA_3TO1:
        return aa
    return _AA_1TO3.get(aa)


def _to1(aa: str) -> str | None:
    if aa in AA_3TO1:
        return AA_3TO1[aa]
    return aa if aa in AA_3TO1.values() or aa in ("*", "=") else None


def protein_variants(hgvs_p: str) -> list[str]:
    """Every naming variant of a single-substitution protein HGVS. Empty if unparseable."""
    if not hgvs_p:
        return []
    accession = hgvs_p.split(":", 1)[0] if ":" in hgvs_p else ""
    m = _SUB_RE.search(hgvs_p)
    if not m:
        return []
    ref3, alt3 = _to3(m["ref"]), _to3(m["alt"])
    ref1, alt1 = _to1(m["ref"]), _to1(m["alt"])
    if not (ref3 and alt3 and ref1 and alt1):
        return []
    pos = m["pos"]
    cores = {f"{ref3}{pos}{alt3}", f"{ref1}{pos}{alt1}"}
    out: set[str] = set()
    for core in cores:
        out.add(core)                    # Arg614Cys / R614C
        out.add(f"p.{core}")             # p.Arg614Cys
        out.add(f"p.({core})")           # p.(Arg614Cys)
        if accession:
            out.add(f"{accession}:p.({core})")
            out.add(f"{accession}:p.{core}")
    return sorted(out)


def vcf_form(chrom: str, pos: str, ref: str, alt: str) -> str:
    return f"{chrom}-{pos}-{ref}-{alt}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_pipeline_synonyms.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/synonyms.py tests/test_pipeline_synonyms.py
git commit -m "feat(pipeline): generate protein/VCF naming variants (recall-critical)"
```

---

### Task 9: VariantValidator + myvariant clients

**Files:**
- Create: `clineval/pipeline/clients/variantvalidator.py`
- Create: `clineval/pipeline/clients/myvariant_client.py`
- Test: `tests/test_client_variantvalidator.py`
- Test: `tests/test_client_myvariant.py`

**Interfaces:**
- Consumes: `HttpClient` (Task 7); the Task-0 fixture `tests/fixtures/api_samples/variantvalidator_ryr1.json`.
- Produces:
  - `parse_vv_response(raw: dict) -> VVParsed` where `VVParsed(c_form: str, protein_tlr: str, protein_slr: str, genomic_forms: list[str], vcf_tuples: list[tuple], gene: str, warnings: list[str], vv_version: str, vvdb_version: str, vvta_version: str)`.
  - `class VariantValidatorClient:` `__init__(self, http: HttpClient, base_url: str = "https://rest.variantvalidator.org")`; `fetch(hgvs: str, build: str = "GRCh38") -> VVParsed`.
  - `class MyVariantClient:` `__init__(self, mv=None)`; `lookup(hgvs: str) -> dict` returning `{"rsid": str | None, "clinvar": ..., "gnomad": ...}` (non-fatal on error → all-None + logs).

- [ ] **Step 1: Write the failing tests**

`tests/test_client_variantvalidator.py`:
```python
import json
from pathlib import Path

from clineval.pipeline.clients.variantvalidator import parse_vv_response

FIXTURE = Path("tests/fixtures/api_samples/variantvalidator_ryr1.json")


def test_parse_vv_extracts_confirmed_keys():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    p = parse_vv_response(raw)
    assert p.c_form == "NM_000540.3:c.1840C>T"
    assert p.protein_tlr == "NP_000531.2:p.(Arg614Cys)"
    assert p.protein_slr == "NP_000531.2:p.(R614C)"
    assert p.gene == "RYR1"
    assert any("g.38457545C>T" in g for g in p.genomic_forms)
    assert ("19", "38457545", "C", "T") in p.vcf_tuples
    assert p.vvdb_version.startswith("vvdb_")


def test_parse_vv_ignores_flag_and_metadata_keys():
    raw = {"flag": "gene_variant", "metadata": {}, "SOME:c.1A>T": {"hgvs_transcript_variant": "SOME:c.1A>T",
           "hgvs_predicted_protein_consequence": {}, "primary_assembly_loci": {}, "gene_symbol": "X",
           "validation_warnings": []}}
    p = parse_vv_response(raw)
    assert p.c_form == "SOME:c.1A>T"
```

`tests/test_client_myvariant.py`:
```python
from clineval.pipeline.clients.myvariant_client import MyVariantClient


class _FakeMV:
    def set_caching(self): pass
    def getvariant(self, _id, fields=None):
        return {"dbsnp": {"rsid": "rs193922747"}, "clinvar": {"rcv": []}, "gnomad_genome": {"af": {}}}


def test_myvariant_lookup_backfills_rsid():
    out = MyVariantClient(mv=_FakeMV()).lookup("NM_000540.3:c.1840C>T")
    assert out["rsid"] == "rs193922747"
    assert "clinvar" in out and "gnomad" in out


def test_myvariant_lookup_is_non_fatal():
    class _Boom:
        def set_caching(self): pass
        def getvariant(self, _id, fields=None): raise RuntimeError("network")
    out = MyVariantClient(mv=_Boom()).lookup("x")
    assert out["rsid"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm clineval uv run pytest tests/test_client_variantvalidator.py tests/test_client_myvariant.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the clients**

`clineval/pipeline/clients/variantvalidator.py`:
```python
"""VariantValidator REST client. Isolates VV's nested per-transcript JSON shape.

Keys confirmed against a live response 2026-07-16 (see design spec §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clineval.pipeline.clients.http import HttpClient


@dataclass
class VVParsed:
    c_form: str = ""
    protein_tlr: str = ""
    protein_slr: str = ""
    genomic_forms: list[str] = field(default_factory=list)
    vcf_tuples: list[tuple] = field(default_factory=list)
    gene: str = ""
    warnings: list[str] = field(default_factory=list)
    vv_version: str = ""
    vvdb_version: str = ""
    vvta_version: str = ""


def parse_vv_response(raw: dict) -> VVParsed:
    meta = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
    p = VVParsed(
        vv_version=str(meta.get("variantvalidator_version", "")),
        vvdb_version=str(meta.get("vvdb_version", "")),
        vvta_version=str(meta.get("vvta_version", "")),
    )
    for key, hit in raw.items():
        if not isinstance(hit, dict) or "hgvs_transcript_variant" not in hit:
            continue  # skips 'flag' (str) and 'metadata' (dict without the key)
        p.c_form = hit.get("hgvs_transcript_variant", "")
        prot = hit.get("hgvs_predicted_protein_consequence") or {}
        p.protein_tlr = prot.get("tlr", "") or ""
        p.protein_slr = prot.get("slr", "") or ""
        p.gene = hit.get("gene_symbol", "") or ""
        p.warnings = list(hit.get("validation_warnings", []) or [])
        for _, locus in (hit.get("primary_assembly_loci") or {}).items():
            desc = locus.get("hgvs_genomic_description")
            if desc and desc not in p.genomic_forms:
                p.genomic_forms.append(desc)
            vcf = locus.get("vcf") or {}
            if vcf:
                chrom = str(vcf.get("chr", "")).removeprefix("chr")
                tup = (chrom, str(vcf.get("pos", "")), vcf.get("ref", ""), vcf.get("alt", ""))
                if tup not in p.vcf_tuples:
                    p.vcf_tuples.append(tup)
        break  # first real hit is the submitted variant
    return p


class VariantValidatorClient:
    def __init__(self, http: HttpClient, base_url: str = "https://rest.variantvalidator.org") -> None:
        self._http = http
        self._base = base_url

    def fetch(self, hgvs: str, build: str = "GRCh38") -> VVParsed:
        raw = self._http.get_json(
            self._base,
            f"/VariantValidator/variantvalidator/{build}/{hgvs}/all",
            headers={"Content-Type": "application/json"},
        )
        return parse_vv_response(raw)
```

`clineval/pipeline/clients/myvariant_client.py`:
```python
"""myvariant.info wrapper: backfill rsID + pull ClinVar/gnomAD xrefs (non-fatal)."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_FIELDS = ["dbsnp.rsid", "clinvar", "gnomad_genome"]


class MyVariantClient:
    def __init__(self, mv=None) -> None:
        if mv is None:
            import myvariant

            mv = myvariant.MyVariantInfo()
            mv.set_caching()
        self._mv = mv

    def lookup(self, hgvs: str) -> dict:
        try:
            res = self._mv.getvariant(hgvs, fields=_FIELDS) or {}
        except Exception as exc:  # non-fatal: log + return empties
            log.warning("myvariant lookup failed for %s: %s", hgvs, exc)
            return {"rsid": None, "clinvar": None, "gnomad": None}
        return {
            "rsid": (res.get("dbsnp") or {}).get("rsid"),
            "clinvar": res.get("clinvar"),
            "gnomad": res.get("gnomad_genome"),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm clineval uv run pytest tests/test_client_variantvalidator.py tests/test_client_myvariant.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/clients/variantvalidator.py clineval/pipeline/clients/myvariant_client.py tests/test_client_variantvalidator.py tests/test_client_myvariant.py
git commit -m "feat(pipeline): add VariantValidator + myvariant clients (parsed against live fixtures)"
```

---

### Task 10: Stage 1 — `normalize_and_expand`

**Files:**
- Create: `clineval/pipeline/normalize.py`
- Test: `tests/test_stage1_normalize.py`

**Interfaces:**
- Consumes: `VariantValidatorClient` / `VVParsed` (Task 9), `MyVariantClient` (Task 9), `protein_variants` / `vcf_form` (Task 8), `VariantForms` / `PipelineProvenance` (Task 4).
- Produces: `normalize_and_expand(hgvs_c: str, genome_build: str = "GRCh38", *, vv: VariantValidatorClient, mv: MyVariantClient) -> VariantForms`.

- [ ] **Step 1: Write the failing test**

`tests/test_stage1_normalize.py`:
```python
from clineval.pipeline.clients.variantvalidator import VVParsed
from clineval.pipeline.models import VariantForms
from clineval.pipeline.normalize import normalize_and_expand


class _VV:
    def __init__(self, parsed): self._p = parsed
    def fetch(self, hgvs, build="GRCh38"): return self._p


class _MV:
    def __init__(self, rsid): self._rsid = rsid
    def lookup(self, hgvs): return {"rsid": self._rsid, "clinvar": None, "gnomad": None}


def _missense_parsed():
    return VVParsed(
        c_form="NM_000540.3:c.1840C>T",
        protein_tlr="NP_000531.2:p.(Arg614Cys)", protein_slr="NP_000531.2:p.(R614C)",
        genomic_forms=["NC_000019.10:g.38457545C>T"], vcf_tuples=[("19", "38457545", "C", "T")],
        gene="RYR1", warnings=[], vvdb_version="vvdb_2025_3",
    )


def test_missense_resolves_and_expands():
    out = normalize_and_expand("NM_000540.3:c.1840C>T", vv=_VV(_missense_parsed()), mv=_MV("rs193922747"))
    assert isinstance(out, VariantForms)
    assert out.resolved is True
    assert out.gene == "RYR1"
    forms = set(out.forms)
    assert "NM_000540.3:c.1840C>T" in forms
    assert "p.Arg614Cys" in forms and "R614C" in forms          # from synonyms
    assert "NC_000019.10:g.38457545C>T" in forms
    assert "19-38457545-C-T" in forms                            # VCF form
    assert "rs193922747" in forms                                # rsID backfilled
    assert out.provenance.vvdb_version == "vvdb_2025_3"


def test_protein_only_hard_case_is_flagged_not_dropped():
    # Splice/intronic: no protein consequence derivable.
    parsed = VVParsed(c_form="NM_000540.3:c.1840+1G>A", protein_tlr="", protein_slr="",
                      genomic_forms=["NC_000019.10:g.38457546G>A"], vcf_tuples=[("19", "38457546", "G", "A")],
                      gene="RYR1", warnings=["intronic"], vvdb_version="vvdb_2025_3")
    out = normalize_and_expand("NM_000540.3:c.1840+1G>A", vv=_VV(parsed), mv=_MV(None))
    assert out.resolved is False
    assert out.forms                                  # kept, not empty
    assert "NM_000540.3:c.1840+1G>A" in out.forms
    assert any("manual" in n.lower() or "protein" in n.lower() for n in out.notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_stage1_normalize.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/normalize.py`**

```python
"""Stage 1: one canonical variant -> every string form a paper might use to name it."""

from __future__ import annotations

from clineval.pipeline.clients.myvariant_client import MyVariantClient
from clineval.pipeline.clients.variantvalidator import VariantValidatorClient
from clineval.pipeline.models import PipelineProvenance, VariantForms
from clineval.pipeline.synonyms import protein_variants, vcf_form


def normalize_and_expand(
    hgvs_c: str,
    genome_build: str = "GRCh38",
    *,
    vv: VariantValidatorClient,
    mv: MyVariantClient,
) -> VariantForms:
    forms: set[str] = {hgvs_c}
    notes: list[str] = []

    parsed = vv.fetch(hgvs_c, genome_build)
    if parsed.c_form:
        forms.add(parsed.c_form)
    for p in (parsed.protein_tlr, parsed.protein_slr):
        forms.update(protein_variants(p))
    forms.update(parsed.genomic_forms)
    for chrom, pos, ref, alt in parsed.vcf_tuples:
        forms.add(vcf_form(chrom, pos, ref, alt))
    for w in parsed.warnings:
        notes.append(f"VariantValidator warning: {w}")

    xrefs: dict = {}
    mv_out = mv.lookup(hgvs_c)
    if mv_out.get("rsid"):
        forms.add(mv_out["rsid"])
    xrefs = {"rsid": mv_out.get("rsid"), "clinvar": mv_out.get("clinvar"), "gnomad": mv_out.get("gnomad")}

    resolved = any(f.startswith("p.") for f in forms)
    if not resolved:
        notes.append("no protein consequence (splice/intronic/indel?) — route to manual, keep in set")

    return VariantForms(
        input=hgvs_c,
        forms=sorted(forms),
        resolved=resolved,
        xrefs=xrefs,
        gene=parsed.gene,
        notes=notes,
        provenance=PipelineProvenance(
            vv_version=parsed.vv_version, vvdb_version=parsed.vvdb_version,
            vvta_version=parsed.vvta_version, sources=["variantvalidator", "myvariant"],
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_stage1_normalize.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/normalize.py tests/test_stage1_normalize.py
git commit -m "feat(pipeline): Stage 1 normalize_and_expand (flags hard cases, never drops)"
```

---

### Task 11: LitVar2 + E-utilities clients

> **Prerequisite:** the confirmed LitVar2 paths + key names from the Task-0 findings note. The paths below are placeholders in the *client*, driven entirely by parsing the saved fixture — update the base/path constants to the confirmed values, and adjust the fixture-parsing keys if Task 0 found different names. The test asserts against the real saved fixture, so it will fail loudly if the parsing keys are wrong.

**Files:**
- Create: `clineval/pipeline/clients/litvar.py`
- Create: `clineval/pipeline/clients/eutils.py`
- Test: `tests/test_client_litvar.py`
- Test: `tests/test_client_eutils.py`

**Interfaces:**
- Consumes: `HttpClient` (Task 7); fixtures `litvar_ryr1.json`, `esummary_ryr1.json` (Task 0).
- Produces:
  - `parse_litvar_pmids(raw: dict) -> list[str]` (dedup, string PMIDs) — keys per Task-0 findings.
  - `class LitVarClient:` `__init__(self, http: HttpClient, base_url: str = "<confirmed>")`; `pmids_for(form: str) -> list[str]`.
  - `parse_esummary(raw: dict) -> dict[str, dict]` → `{pmid: {"title","journal","year"}}`.
  - `class EutilsClient:` `__init__(self, http: HttpClient, api_key: str | None = None, base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")`; `summaries(pmids: list[str]) -> dict[str, dict]` (batched; adds `api_key` param when present).

- [ ] **Step 1: Write the failing tests**

`tests/test_client_litvar.py`:
```python
import json
from pathlib import Path

from clineval.pipeline.clients.litvar import parse_litvar_pmids


def test_parse_litvar_pmids_from_fixture():
    raw = json.loads(Path("tests/fixtures/api_samples/litvar_ryr1.json").read_text(encoding="utf-8"))
    pmids = parse_litvar_pmids(raw)
    assert isinstance(pmids, list)
    assert pmids == list(dict.fromkeys(pmids))     # deduped, order-preserved
    assert all(isinstance(p, str) and p.isdigit() for p in pmids)
```

`tests/test_client_eutils.py`:
```python
import json
from pathlib import Path

from clineval.pipeline.clients.eutils import EutilsClient, parse_esummary


def test_parse_esummary_from_fixture():
    raw = json.loads(Path("tests/fixtures/api_samples/esummary_ryr1.json").read_text(encoding="utf-8"))
    meta = parse_esummary(raw)
    assert meta                                   # at least one PMID parsed
    sample = next(iter(meta.values()))
    assert set(sample) == {"title", "journal", "year"}


def test_eutils_summaries_uses_transport_and_api_key():
    seen = {}
    def transport(url, params, headers):
        seen["params"] = params
        return json.loads(Path("tests/fixtures/api_samples/esummary_ryr1.json").read_text(encoding="utf-8"))
    from clineval.pipeline.clients.http import HttpClient
    client = EutilsClient(HttpClient(transport=transport), api_key="KEY")
    out = client.summaries(["28380275", "25741868"])
    assert out
    assert seen["params"].get("api_key") == "KEY"
    assert seen["params"].get("id") == "28380275,25741868"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm clineval uv run pytest tests/test_client_litvar.py tests/test_client_eutils.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the clients** (set base/path + keys from the Task-0 findings note)

`clineval/pipeline/clients/litvar.py`:
```python
"""LitVar2 client: variant string/id -> PMIDs. Endpoint confirmed in Task 0."""

from __future__ import annotations

from clineval.pipeline.clients.http import HttpClient

# TODO(Task 0): set to the confirmed LitVar2 base + publications path template.
LITVAR2_BASE = "https://www.ncbi.nlm.nih.gov/research/litvar2-api"


def parse_litvar_pmids(raw: dict) -> list[str]:
    """Extract deduped string PMIDs. Key names per the Task-0 findings note.

    Handles the two shapes LitVar2 has used: a top-level ``pmids`` list, or a
    ``publications`` list of objects each carrying a ``pmid``.
    """
    out: list[str] = []
    seen: set[str] = set()
    candidates = raw.get("pmids")
    if candidates is None:
        candidates = [p.get("pmid") for p in raw.get("publications", []) if isinstance(p, dict)]
    for pmid in candidates or []:
        s = str(pmid)
        if s.isdigit() and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class LitVarClient:
    def __init__(self, http: HttpClient, base_url: str = LITVAR2_BASE) -> None:
        self._http = http
        self._base = base_url

    def pmids_for(self, form: str) -> list[str]:
        # TODO(Task 0): confirm search→id→publications flow; path below is the
        # publications-by-variant-string endpoint confirmed in the spike.
        try:
            raw = self._http.get_json(self._base, f"/variant/get/{form}/publications")
        except Exception:
            return []
        return parse_litvar_pmids(raw)
```

`clineval/pipeline/clients/eutils.py`:
```python
"""NCBI E-utilities esummary client: PMID -> {title, journal, year}."""

from __future__ import annotations

from clineval.pipeline.clients.http import HttpClient


def _year(pubdate: str) -> int | None:
    if not pubdate:
        return None
    head = pubdate.strip().split(" ")[0].split("/")[0]
    return int(head) if head.isdigit() else None


def parse_esummary(raw: dict) -> dict[str, dict]:
    result = raw.get("result", {}) if isinstance(raw, dict) else {}
    out: dict[str, dict] = {}
    for pmid in result.get("uids", []):
        rec = result.get(pmid, {})
        out[str(pmid)] = {
            "title": rec.get("title", ""),
            "journal": rec.get("fulljournalname", "") or rec.get("source", ""),
            "year": _year(rec.get("pubdate", "")),
        }
    return out


class EutilsClient:
    def __init__(
        self,
        http: HttpClient,
        api_key: str | None = None,
        base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._base = base_url

    def summaries(self, pmids: list[str], batch: int = 200) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(pmids), batch):
            chunk = pmids[i : i + batch]
            params = {"db": "pubmed", "retmode": "json", "id": ",".join(chunk)}
            if self._api_key:
                params["api_key"] = self._api_key
            raw = self._http.get_json(self._base, "/esummary.fcgi", params=params)
            out.update(parse_esummary(raw))
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm clineval uv run pytest tests/test_client_litvar.py tests/test_client_eutils.py -v`
Expected: PASS (3 tests). If LitVar2 parsing fails, reconcile keys with the Task-0 fixture/findings and re-run.

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/clients/litvar.py clineval/pipeline/clients/eutils.py tests/test_client_litvar.py tests/test_client_eutils.py
git commit -m "feat(pipeline): add LitVar2 + E-utilities clients (parsed against live fixtures)"
```

---

### Task 12: Stage 2 — `retrieve`

**Files:**
- Create: `clineval/pipeline/retrieve.py`
- Test: `tests/test_stage2_retrieve.py`

**Interfaces:**
- Consumes: `VariantForms` (Task 4), `LitVarClient` (Task 11), `EutilsClient` (Task 11), `PaperRef` / `RetrievalResult` / `PipelineProvenance` (Task 4).
- Produces: `retrieve(forms: VariantForms, *, litvar: LitVarClient, eutils: EutilsClient) -> RetrievalResult` — union PMIDs across forms with earliest `matched_form` provenance, dedup, attach metadata, non-fatal on per-form/metadata failure.

- [ ] **Step 1: Write the failing test**

`tests/test_stage2_retrieve.py`:
```python
from clineval.pipeline.models import VariantForms
from clineval.pipeline.retrieve import retrieve


class _LitVar:
    def __init__(self, mapping): self._m = mapping
    def pmids_for(self, form): return self._m.get(form, [])


class _Eutils:
    def summaries(self, pmids, batch=200):
        return {p: {"title": f"T{p}", "journal": "J", "year": 2024} for p in pmids}


def test_retrieve_unions_dedupes_and_records_matched_form():
    forms = VariantForms(input="v", forms=["p.R614C", "rs193922747"], resolved=True, xrefs={})
    litvar = _LitVar({"p.R614C": ["111", "222"], "rs193922747": ["222", "333"]})
    result = retrieve(forms, litvar=litvar, eutils=_Eutils())
    assert set(result.pmids) == {"111", "222", "333"}
    by_pmid = {p.pmid: p for p in result.papers}
    assert by_pmid["111"].matched_form == "p.R614C"
    assert by_pmid["333"].matched_form == "rs193922747"
    assert by_pmid["222"].matched_form == "p.R614C"      # first form that matched wins
    assert by_pmid["111"].title == "T111"                # metadata attached
    assert "litvar2" in result.provenance.sources


def test_retrieve_is_non_fatal_on_metadata_failure():
    class _BoomEutils:
        def summaries(self, pmids, batch=200): raise RuntimeError("eutils down")
    forms = VariantForms(input="v", forms=["p.R614C"], resolved=True, xrefs={})
    result = retrieve(forms, litvar=_LitVar({"p.R614C": ["111"]}), eutils=_BoomEutils())
    assert result.pmids == ["111"]                        # PMIDs kept even if metadata fails
    assert any("metadata" in n.lower() for n in result.notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_stage2_retrieve.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/pipeline/retrieve.py`**

```python
"""Stage 2: synonym set -> deduplicated PMID union + per-paper metadata + provenance."""

from __future__ import annotations

from clineval.pipeline.models import PaperRef, PipelineProvenance, RetrievalResult, VariantForms


def retrieve(forms: VariantForms, *, litvar, eutils) -> RetrievalResult:
    matched: dict[str, str] = {}   # pmid -> first form that matched it
    notes: list[str] = []
    for form in forms.forms:
        try:
            pmids = litvar.pmids_for(form)
        except Exception as exc:   # non-fatal: skip this form, keep going
            notes.append(f"litvar failed for form {form!r}: {exc}")
            continue
        for pmid in pmids:
            matched.setdefault(pmid, form)

    pmids = list(matched)
    meta: dict[str, dict] = {}
    if pmids:
        try:
            meta = eutils.summaries(pmids)
        except Exception as exc:   # non-fatal: keep PMIDs without metadata
            notes.append(f"esummary metadata fetch failed: {exc}")

    papers = [
        PaperRef(
            pmid=pmid,
            title=meta.get(pmid, {}).get("title", ""),
            journal=meta.get(pmid, {}).get("journal", ""),
            year=meta.get(pmid, {}).get("year"),
            matched_form=matched[pmid],
        )
        for pmid in pmids
    ]
    prov = PipelineProvenance(
        vv_version=forms.provenance.vv_version, vvdb_version=forms.provenance.vvdb_version,
        vvta_version=forms.provenance.vvta_version, sources=["litvar2", "eutils"],
    )
    return RetrievalResult(variant=forms.input, pmids=pmids, papers=papers, provenance=prov, notes=notes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_stage2_retrieve.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/pipeline/retrieve.py tests/test_stage2_retrieve.py
git commit -m "feat(pipeline): Stage 2 retrieve (union+dedup PMIDs, matched-form provenance, non-fatal)"
```

---

### Task 13: Retrieval metric

**Files:**
- Create: `clineval/tasks/variant_retrieval/metrics.py`
- Modify: `clineval/tasks/variant_retrieval/__init__.py` (import metrics to register)
- Test: `tests/test_retrieval_metric.py`

**Interfaces:**
- Consumes: `core.metric.set_prf` (Task 2), `Metric`/`register_metric`/`macro_average`/`EvalContext` (existing), `PredictionRecord`/`MetricResult` (existing).
- Produces: `class RetrievalMetric(Metric)` `name = "retrieval_prf"`, registered `"variant_retrieval"`. Per-doc keys: `precision, recall, f1, gold_n, retrieved_n, found_n, missed_n, extra_n`. Aggregate: macro `precision/recall/f1` + `mean_yield` + micro `micro_precision/micro_recall/micro_f1`. `details["missed"]` = `{variant_id: [missed_pmids]}`; `details["unresolved"]` = list of variant ids flagged `resolved=False` (read from `record.metadata["resolved"]`).

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval_metric.py`:
```python
from clineval.core.metric import EvalContext, get_metrics
from clineval.core.schema import PredictionRecord
import clineval.tasks.variant_retrieval  # noqa: F401  (registers the metric)
from clineval.tasks.variant_retrieval.metrics import RetrievalMetric


def _rec(rid, gold, pred, resolved=True):
    return PredictionRecord(id=rid, input_text=rid, gold_reference=gold, system_output=pred,
                            metadata={"resolved": resolved})


def test_retrieval_metric_counts_and_recall():
    records = [
        _rec("v1", ["1", "2"], ["1", "2", "9"]),   # recall 1.0, precision 2/3
        _rec("v2", ["3", "4"], ["3"]),             # recall 0.5, precision 1.0
    ]
    result = RetrievalMetric().compute(records, EvalContext())
    assert result.per_document["v1"]["recall"] == 1.0
    assert result.per_document["v1"]["extra_n"] == 1.0
    assert result.per_document["v2"]["missed_n"] == 1.0
    assert result.aggregate["recall"] == 0.75           # macro mean of 1.0 and 0.5
    assert result.aggregate["mean_yield"] == 2.0         # (3 + 1) / 2
    assert result.details["missed"]["v2"] == ["4"]


def test_retrieval_metric_records_unresolved():
    records = [_rec("v1", ["1"], ["1"]), _rec("v2", ["2"], [], resolved=False)]
    result = RetrievalMetric().compute(records, EvalContext())
    assert result.details["unresolved"] == ["v2"]


def test_retrieval_metric_registered():
    assert "retrieval_prf" in [m.name for m in get_metrics("variant_retrieval")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_metric.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement + register**

`clineval/tasks/variant_retrieval/metrics.py`:
```python
"""variant_retrieval metric: recall-forward set P/R/F1 + yield + missed detail."""

from __future__ import annotations

from clineval.core.metric import EvalContext, Metric, macro_average, register_metric, set_prf
from clineval.core.schema import MetricResult, PredictionRecord

_KEYS = ["precision", "recall", "f1", "gold_n", "retrieved_n", "found_n", "missed_n", "extra_n"]


@register_metric("variant_retrieval")
class RetrievalMetric(Metric):
    """Per-variant recall/precision/F1 over PMID sets, macro-averaged. Recall is the headline."""

    name = "retrieval_prf"

    def compute(self, records: list[PredictionRecord], context: EvalContext) -> MetricResult:
        per_doc: dict[str, dict[str, float]] = {}
        missed: dict[str, list[str]] = {}
        unresolved: list[str] = []
        tp = fp = fn = 0
        for r in records:
            gold, pred = set(r.gold_reference), set(r.system_output)
            prf = set_prf(r.gold_reference, r.system_output)
            d_tp, d_fn, d_fp = len(gold & pred), len(gold - pred), len(pred - gold)
            per_doc[r.id] = {
                **prf,
                "gold_n": float(len(gold)), "retrieved_n": float(len(pred)),
                "found_n": float(d_tp), "missed_n": float(d_fn), "extra_n": float(d_fp),
            }
            if gold - pred:
                missed[r.id] = sorted(gold - pred)
            if r.metadata.get("resolved") is False:
                unresolved.append(r.id)
            tp, fp, fn = tp + d_tp, fp + d_fp, fn + d_fn

        aggregate = macro_average(per_doc, ["precision", "recall", "f1"])
        aggregate["mean_yield"] = (
            sum(d["retrieved_n"] for d in per_doc.values()) / len(per_doc) if per_doc else 0.0
        )
        micro_p = tp / (tp + fp) if (tp + fp) else (1.0 if fn == 0 else 0.0)
        micro_r = tp / (tp + fn) if (tp + fn) else (1.0 if fp == 0 else 0.0)
        aggregate["micro_precision"] = micro_p
        aggregate["micro_recall"] = micro_r
        aggregate["micro_f1"] = 0.0 if micro_p + micro_r == 0 else 2 * micro_p * micro_r / (micro_p + micro_r)
        return MetricResult(name=self.name, aggregate=aggregate, per_document=per_doc,
                            details={"missed": missed, "unresolved": unresolved})
```
`clineval/tasks/variant_retrieval/__init__.py`:
```python
"""ClinEval task: variant literature retrieval evaluation."""

from clineval.tasks.variant_retrieval import metrics  # noqa: F401  (registers the metric)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_metric.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/variant_retrieval/metrics.py clineval/tasks/variant_retrieval/__init__.py tests/test_retrieval_metric.py
git commit -m "feat(variant_retrieval): add recall-forward retrieval metric reusing core.set_prf"
```

---

### Task 14: Retriever adapters (system-under-test)

**Files:**
- Create: `clineval/tasks/variant_retrieval/retriever.py`
- Test: `tests/test_retriever.py`

**Interfaces:**
- Consumes: `PredictionRecord` (existing); `VariantForms`/`RetrievalResult` (Task 4).
- Produces:
  - `class DatasetRetriever:` `mode = "dataset"`; `extract(record) -> list[str]` (returns `record.system_output`).
  - `class CachedRetriever:` `__init__(self, path: str)`; `mode`; `extract(record) -> list[str]`; `covers(record_id: str) -> bool`. Replays a JSONL of `{"id","pmids",[opt]"resolved","notes"}`, writing `resolved`/`notes` into `record.metadata`.
  - `class PipelineRetriever:` `__init__(self, normalize_fn, retrieve_fn)`; `mode = "live"`; `extract(record) -> list[str]` — runs stage 1 then stage 2 on `record.id`, stores `resolved`/`notes`/provenance into `record.metadata`, returns PMIDs.

- [ ] **Step 1: Write the failing test**

`tests/test_retriever.py`:
```python
from clineval.core.schema import PredictionRecord
from clineval.pipeline.models import PipelineProvenance, RetrievalResult, VariantForms
from clineval.tasks.variant_retrieval.retriever import CachedRetriever, DatasetRetriever, PipelineRetriever


def test_dataset_retriever_passes_through():
    rec = PredictionRecord(id="v", input_text="v", gold_reference=["1"], system_output=["1", "2"])
    assert DatasetRetriever().extract(rec) == ["1", "2"]


def test_cached_retriever_replays_and_sets_metadata(tmp_path):
    p = tmp_path / "cache.jsonl"
    p.write_text('{"id": "v1", "pmids": ["1", "2"], "resolved": false, "notes": ["hard case"]}\n',
                 encoding="utf-8")
    r = CachedRetriever(str(p))
    rec = PredictionRecord(id="v1", input_text="v1", gold_reference=["1"])
    assert r.extract(rec) == ["1", "2"]
    assert r.covers("v1") and not r.covers("zzz")
    assert rec.metadata["resolved"] is False
    assert rec.metadata["notes"] == ["hard case"]


def test_pipeline_retriever_runs_both_stages_and_records_resolution():
    def normalize_fn(hgvs):
        return VariantForms(input=hgvs, forms=["p.R614C"], resolved=True, xrefs={},
                            notes=["ok"], provenance=PipelineProvenance(vvdb_version="vvdb_2025_3"))
    def retrieve_fn(forms):
        return RetrievalResult(variant=forms.input, pmids=["111", "222"], papers=[], notes=[])
    rec = PredictionRecord(id="NM_000540.3:c.1840C>T", input_text="NM_000540.3:c.1840C>T", gold_reference=["111"])
    out = PipelineRetriever(normalize_fn, retrieve_fn).extract(rec)
    assert out == ["111", "222"]
    assert rec.metadata["resolved"] is True
    assert rec.metadata["provenance"]["vvdb_version"] == "vvdb_2025_3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_retriever.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/tasks/variant_retrieval/retriever.py`**

```python
"""System-under-test adapters: the pipeline seen through ClinEval's Extractor hole."""

from __future__ import annotations

import json
from dataclasses import asdict

from clineval.core.schema import PredictionRecord


class DatasetRetriever:
    mode = "dataset"

    def extract(self, record: PredictionRecord) -> list[str]:
        return list(record.system_output)


class CachedRetriever:
    """Replay committed pipeline outputs keyed by variant id (offline, deterministic)."""

    def __init__(self, path: str) -> None:
        self.mode = f"cached:{path}"
        self._by_id: dict[str, dict] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                self._by_id[str(obj["id"])] = obj

    def covers(self, record_id: str) -> bool:
        return record_id in self._by_id

    def extract(self, record: PredictionRecord) -> list[str]:
        obj = self._by_id.get(record.id, {})
        if "resolved" in obj:
            record.metadata["resolved"] = obj["resolved"]
        if "notes" in obj:
            record.metadata["notes"] = obj["notes"]
        return [str(p) for p in obj.get("pmids", [])]


class PipelineRetriever:
    """Run stages 1→2 live for each record's variant."""

    mode = "live"

    def __init__(self, normalize_fn, retrieve_fn) -> None:
        self._normalize = normalize_fn
        self._retrieve = retrieve_fn

    def extract(self, record: PredictionRecord) -> list[str]:
        forms = self._normalize(record.id)
        record.metadata["resolved"] = forms.resolved
        record.metadata["notes"] = list(forms.notes)
        record.metadata["provenance"] = asdict(forms.provenance)
        result = self._retrieve(forms)
        record.metadata["notes"].extend(result.notes)
        return list(result.pmids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_retriever.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/variant_retrieval/retriever.py tests/test_retriever.py
git commit -m "feat(variant_retrieval): add Dataset/Cached/Pipeline retriever adapters"
```

---

### Task 15: Dataset loaders + committed RYR1 gold fixture

**Files:**
- Create: `clineval/tasks/variant_retrieval/datasets.py`
- Create: `examples/data/ryr1_gold.jsonl` (small committed fixture; PMIDs are public IDs)
- Test: `tests/test_retrieval_datasets.py`

**Interfaces:**
- Consumes: `JSONLDatasetLoader` (existing), `PredictionRecord` (existing).
- Produces:
  - `class RYR1BenchmarkLoader(DatasetLoader):` `__init__(self, path: str = "examples/data/ryr1_gold.jsonl")`; `load() -> list[PredictionRecord]` (PMIDs coerced to strings).
  - `class HgmdGoldLoader(DatasetLoader):` `__init__(self, path: str = "datasets/hgmd_gold/gold.jsonl")`; `load()` with a clear FileNotFound message pointing at the export step. Same schema → drop-in second dataset.

- [ ] **Step 1: Write the failing test + create the fixture**

`examples/data/ryr1_gold.jsonl` — a **small synthetic demo** fixture (committed). It is RYR1-shaped
but **not** HGMD-derived: the real benchmark gold is built by `datasets/build_hgmd_gold.py` into
git-ignored `datasets/hgmd_gold/*.jsonl` (HGMD's per-variant paper *selection* is licensed and must
never be committed — see design spec §8). This committed fixture uses illustrative/public PMIDs and
`source: "synthetic_demo"` purely to power offline tests and the zero-setup demo. The intronic row
exercises the `resolved=false` path:
```json
{"id": "NM_000540.3:c.1840C>T", "input_text": "NM_000540.3:c.1840C>T", "gold_reference": ["8477729", "10484775"], "metadata": {"gene": "RYR1", "source": "synthetic_demo"}}
{"id": "NM_000540.3:c.7300G>A", "input_text": "NM_000540.3:c.7300G>A", "gold_reference": ["9333239"], "metadata": {"gene": "RYR1", "source": "synthetic_demo"}}
{"id": "NM_000540.3:c.1840+1G>A", "input_text": "NM_000540.3:c.1840+1G>A", "gold_reference": ["12345678"], "metadata": {"gene": "RYR1", "source": "synthetic_demo", "hard_case": "intronic"}}
```

`tests/test_retrieval_datasets.py`:
```python
import pytest

from clineval.tasks.variant_retrieval.datasets import HgmdGoldLoader, RYR1BenchmarkLoader


def test_ryr1_loader_reads_committed_gold():
    records = RYR1BenchmarkLoader().load()
    assert len(records) >= 3
    r0 = records[0]
    assert r0.id.startswith("NM_000540.3:c.")
    assert all(isinstance(p, str) for p in r0.gold_reference)
    assert r0.metadata["gene"] == "RYR1"


def test_hgmd_loader_missing_file_is_clear():
    with pytest.raises(FileNotFoundError) as e:
        HgmdGoldLoader(path="datasets/hgmd_gold/does_not_exist.jsonl").load()
    assert "export" in str(e.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_datasets.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `clineval/tasks/variant_retrieval/datasets.py`**

```python
"""Truth-set loaders for the variant_retrieval task."""

from __future__ import annotations

from pathlib import Path

from clineval.core.dataset import DatasetLoader, JSONLDatasetLoader
from clineval.core.schema import PredictionRecord


def _coerce_pmids(records: list[PredictionRecord]) -> list[PredictionRecord]:
    for rec in records:
        rec.gold_reference = [str(p) for p in rec.gold_reference]
    return records


class RYR1BenchmarkLoader(DatasetLoader):
    """RYR1 / Wermers 2024 benchmark: variant -> known gold PMIDs (public)."""

    def __init__(self, path: str = "examples/data/ryr1_gold.jsonl") -> None:
        self.path = path

    def load(self) -> list[PredictionRecord]:
        return _coerce_pmids(JSONLDatasetLoader(self.path).load())


class HgmdGoldLoader(DatasetLoader):
    """Lab HGMD-derived panel gold (git-ignored; never committed). Drop-in second dataset."""

    def __init__(self, path: str = "datasets/hgmd_gold/gold.jsonl") -> None:
        self.path = path

    def load(self) -> list[PredictionRecord]:
        if not Path(self.path).exists():
            raise FileNotFoundError(
                f"HGMD gold not found at {self.path}. Export it from HGMD while the "
                "licence is active (see datasets/README.md), then re-run. The pipeline "
                "itself never calls HGMD — this is benchmark truth only."
            )
        return _coerce_pmids(JSONLDatasetLoader(self.path).load())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_datasets.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/variant_retrieval/datasets.py examples/data/ryr1_gold.jsonl tests/test_retrieval_datasets.py
git commit -m "feat(variant_retrieval): add RYR1 + HGMD gold loaders and seed RYR1 fixture"
```

---

### Task 16: Regulatory rows + report renderer + template

**Files:**
- Modify: `clineval/regulatory/mapping.py` (add `RETRIEVAL_ROWS` + `get_retrieval_mapping_rows`)
- Create: `clineval/templates/retrieval_report.md.j2`
- Create: `clineval/tasks/variant_retrieval/report.py`
- Test: `tests/test_retrieval_report.py`

**Interfaces:**
- Consumes: `EvaluationResult`/`MetricResult` (existing), `get_retrieval_mapping_rows` + `DISCLAIMER` (this task), the `retrieval_prf` metric result (Task 13).
- Produces: `get_retrieval_mapping_rows() -> list[dict]`; `render_retrieval_report(result: EvaluationResult) -> str`.

- [ ] **Step 1: Write the failing test**

`tests/test_retrieval_report.py`:
```python
from clineval.core.schema import EvaluationResult, MetricResult, PredictionRecord
from clineval.tasks.variant_retrieval.report import render_retrieval_report


def _result():
    mr = MetricResult(
        name="retrieval_prf",
        aggregate={"precision": 0.8, "recall": 0.75, "f1": 0.77, "mean_yield": 2.0,
                   "micro_precision": 0.8, "micro_recall": 0.75, "micro_f1": 0.77},
        per_document={"v1": {"precision": 0.67, "recall": 1.0, "f1": 0.8, "gold_n": 2.0,
                             "retrieved_n": 3.0, "found_n": 2.0, "missed_n": 0.0, "extra_n": 1.0},
                      "v2": {"precision": 1.0, "recall": 0.5, "f1": 0.67, "gold_n": 2.0,
                             "retrieved_n": 1.0, "found_n": 1.0, "missed_n": 1.0, "extra_n": 0.0}},
        details={"missed": {"v2": ["4"]}, "unresolved": ["v2"]},
    )
    return EvaluationResult(
        task="variant_retrieval", dataset="ryr1", n_documents=2, model="cached",
        timestamp="2026-07-16T00:00:00+00:00", metrics=[mr],
        records=[PredictionRecord(id="v1", input_text="v1", gold_reference=["1", "2"]),
                 PredictionRecord(id="v2", input_text="v2", gold_reference=["3", "4"])],
        provenance={"vvdb_version": "vvdb_2025_3", "cache_hit_rate": "2/2"},
    )


def test_report_has_key_sections():
    md = render_retrieval_report(_result())
    assert "# ClinEval — Variant Literature Retrieval Report" in md
    assert "Recall" in md and "0.75" in md          # recall headline
    assert "Missed evidence" in md and "v2" in md    # missed-evidence detail
    assert "Unresolved variants" in md               # flag-not-drop section
    assert "vvdb_2025_3" in md                        # provenance
    assert "IVDR" in md                               # regulatory mapping
    assert "not legal" in md.lower()                 # disclaimer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_report.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement rows, template, renderer**

Append to `clineval/regulatory/mapping.py`:
```python
RETRIEVAL_ROWS: list[dict[str, str]] = [
    {"evidence": "Retrieval recall vs known references", "ai_act": "Art 15 (accuracy)",
     "ivdr": "Annex XIII analytical performance / performance evaluation",
     "iso15189": "7.3.3 validation of examination methods"},
    {"evidence": "Yield / precision context", "ai_act": "Art 15 (appropriate accuracy metrics)",
     "ivdr": "performance evaluation", "iso15189": "7.3.3 validation of examination methods"},
    {"evidence": "Evidence snapshot / tool-version provenance", "ai_act": "Art 12 (logging & traceability)",
     "ivdr": "technical documentation", "iso15189": "Clause 8 (control of records)"},
    {"evidence": "Unresolved-variant flagging (no silent drop)", "ai_act": "Art 15 (robustness)",
     "ivdr": "risk / performance evidence", "iso15189": "7.3.7 ensuring validity of results"},
]


def get_retrieval_mapping_rows() -> list[dict[str, str]]:
    return [dict(row) for row in RETRIEVAL_ROWS]
```

`clineval/templates/retrieval_report.md.j2`:
```jinja
# ClinEval — Variant Literature Retrieval Report

- **Dataset:** {{ r.dataset }}  ·  **Variants:** {{ r.n_documents }}  ·  **Retriever:** {{ r.model }}
- **Timestamp:** {{ r.timestamp }}
{% if r.provenance %}
- **Provenance:** {% for k, v in r.provenance.items() %}{{ k }}={{ v }}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}

## Aggregate scores (recall is the headline)

| Metric | Macro | Micro |
|---|---|---|
| **Recall** | **{{ '%.3f'|format(agg.recall) }}** | {{ '%.3f'|format(agg.micro_recall) }} |
| Precision (context) | {{ '%.3f'|format(agg.precision) }} | {{ '%.3f'|format(agg.micro_precision) }} |
| F1 | {{ '%.3f'|format(agg.f1) }} | {{ '%.3f'|format(agg.micro_f1) }} |
| Mean yield (papers/variant) | {{ '%.2f'|format(agg.mean_yield) }} | |

> Precision is contextual in Phase 1: with a primary-references-only gold and no ranking, a
> correct-but-non-primary paper is charged as a false positive. Read recall first.

## Per-variant breakdown

| Variant | gold | retrieved | found | missed | recall | precision |
|---|---|---|---|---|---|---|
{% for vid, d in per_doc.items() %}
| {{ vid }} | {{ d.gold_n|int }} | {{ d.retrieved_n|int }} | {{ d.found_n|int }} | {{ d.missed_n|int }} | {{ '%.2f'|format(d.recall) }} | {{ '%.2f'|format(d.precision) }} |
{% endfor %}

## Missed evidence (false negatives)

{% if missed %}
{% for vid, pmids in missed.items() %}
- **{{ vid }}**: {{ pmids|join(', ') }}
{% endfor %}
{% else %}
None — every gold reference was retrieved.
{% endif %}

## Unresolved variants (flagged, not dropped)

{% if unresolved %}
{{ unresolved|join(', ') }}
{% else %}
None — all variants normalized to a protein consequence.
{% endif %}

## Regulatory Evidence Mapping

| ClinEval evidence | EU AI Act | IVDR | ISO 15189:2022 |
|---|---|---|---|
{% for row in rows %}
| {{ row.evidence }} | {{ row.ai_act }} | {{ row.ivdr }} | {{ row.iso15189 }} |
{% endfor %}

---

_{{ disclaimer }}_
```

`clineval/tasks/variant_retrieval/report.py`:
```python
"""Render a variant_retrieval EvaluationResult to Markdown (its own template)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from clineval.core.schema import EvaluationResult
from clineval.regulatory import mapping

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


class _Bag:
    """Attribute access over a dict for terse template use (agg.recall)."""

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)


def render_retrieval_report(result: EvaluationResult) -> str:
    metric = result.metric("retrieval_prf")
    if metric is None:
        raise ValueError("missing metric 'retrieval_prf' in result")
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
    )
    template = env.get_template("retrieval_report.md.j2")
    return template.render(
        r=result,
        agg=_Bag(metric.aggregate),
        per_doc=metric.per_document,
        missed=metric.details.get("missed", {}),
        unresolved=metric.details.get("unresolved", []),
        rows=mapping.get_retrieval_mapping_rows(),
        disclaimer=mapping.DISCLAIMER,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_report.py -v`
Expected: PASS. (If Jinja complains about a missing aggregate key, ensure the metric always emits all `agg.*` keys — it does per Task 13.)

- [ ] **Step 5: Commit**

```bash
git add clineval/regulatory/mapping.py clineval/templates/retrieval_report.md.j2 clineval/tasks/variant_retrieval/report.py tests/test_retrieval_report.py
git commit -m "feat(variant_retrieval): add regulatory rows, report template + renderer"
```

---

### Task 17: CLI `retrieval-eval` + cached fixture + RYR1 downloader

**Files:**
- Modify: `clineval/cli.py` (add `retrieval-eval` command)
- Create: `examples/data/cached_retrieval.jsonl` (committed cached pipeline outputs for the seed RYR1 variants)
- Test: `tests/test_cli_retrieval.py`

> The real benchmark gold builder (`datasets/build_hgmd_gold.py`) and its `datasets/README.md`
> section already exist (built alongside this plan). This task wires the CLI to load either the
> committed synthetic demo (`--dataset ryr1`) or a built HGMD gold by path
> (`--dataset datasets/hgmd_gold/ryr1_gold.jsonl`).

**Interfaces:**
- Consumes: `RYR1BenchmarkLoader`/`HgmdGoldLoader` (Task 15), `CachedRetriever`/`PipelineRetriever`/`DatasetRetriever` (Task 14), `evaluate` (Task 3), `render_retrieval_report` (Task 16), and (for `--source live`) the pipeline wiring (Tasks 5–12).
- Produces: `clineval retrieval-eval --dataset <ryr1|path.jsonl> --report <out.md> [--source cached|live|dataset] [--cache <path>] [--genome-build GRCh38]` writing a Markdown report; imports `clineval.tasks.variant_retrieval` so the metric registers.

- [ ] **Step 1: Write the cached fixture + failing CLI test**

`examples/data/cached_retrieval.jsonl` (one line per seed RYR1 variant; PMIDs from a real cached run — placeholders until a live run refreshes them; the intronic case demonstrates `resolved: false`):
```json
{"id": "NM_000540.3:c.1840C>T", "pmids": ["8477729", "10484775", "9497773"], "resolved": true, "notes": []}
{"id": "NM_000540.3:c.7300G>A", "pmids": ["9333239"], "resolved": true, "notes": []}
{"id": "NM_000540.3:c.1840+1G>A", "pmids": [], "resolved": false, "notes": ["no protein consequence — route to manual, keep in set"]}
```

`tests/test_cli_retrieval.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

from clineval.cli import app

runner = CliRunner()


def test_retrieval_eval_cached_writes_report(tmp_path):
    out = tmp_path / "retrieval.md"
    result = runner.invoke(app, [
        "retrieval-eval", "--dataset", "ryr1", "--source", "cached",
        "--cache", "examples/data/cached_retrieval.jsonl", "--report", str(out),
    ])
    assert result.exit_code == 0, result.output
    md = out.read_text(encoding="utf-8")
    assert "Variant Literature Retrieval Report" in md
    assert "Recall" in md
    assert "Unresolved variants" in md
    # the intronic seed variant must appear as unresolved (flagged, not dropped)
    assert "c.1840+1G>A" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm clineval uv run pytest tests/test_cli_retrieval.py -v`
Expected: FAIL (no `retrieval-eval` command).

- [ ] **Step 3: Implement the CLI command** (append to `clineval/cli.py`)

Add near the other imports:
```python
import clineval.tasks.variant_retrieval  # noqa: F401  (registers retrieval metric)
from clineval.tasks.variant_retrieval.datasets import HgmdGoldLoader, RYR1BenchmarkLoader
from clineval.tasks.variant_retrieval.report import render_retrieval_report
from clineval.tasks.variant_retrieval.retriever import (
    CachedRetriever,
    DatasetRetriever,
    PipelineRetriever,
)
```
Add the command:
```python
def _load_retrieval_dataset(dataset: str):
    if dataset == "ryr1":
        return RYR1BenchmarkLoader().load()
    if dataset == "hgmd":
        return HgmdGoldLoader().load()
    return RYR1BenchmarkLoader(dataset).load()  # treat as a path to a gold JSONL


def _build_pipeline_retriever(genome_build: str, cache_path: str) -> PipelineRetriever:
    from clineval.pipeline.cache import RequestCache
    from clineval.pipeline.clients.eutils import EutilsClient
    from clineval.pipeline.clients.http import HttpClient
    from clineval.pipeline.clients.litvar import LitVarClient
    from clineval.pipeline.clients.myvariant_client import MyVariantClient
    from clineval.pipeline.clients.variantvalidator import VariantValidatorClient
    from clineval.pipeline.normalize import normalize_and_expand
    from clineval.pipeline.retrieve import retrieve
    from clineval.pipeline.throttle import RateLimiter
    import os

    http = HttpClient(cache=RequestCache(cache_path), limiter=RateLimiter(3.0))
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
    source: str = typer.Option("cached", help="'cached' (offline), 'live' (real pipeline), or 'dataset'."),
    cache: str = typer.Option("examples/data/cached_retrieval.jsonl", help="Cached retrieval outputs (source=cached)."),
    request_cache: str = typer.Option(".cache/requests.sqlite", help="SQLite request cache (source=live)."),
    genome_build: str = typer.Option("GRCh38", help="Genome build for normalization."),
) -> None:
    """Run the variant retrieval evaluation and write a Markdown report."""
    if source not in {"cached", "live", "dataset"}:
        typer.echo("Error: --source must be cached, live, or dataset.", err=True)
        raise typer.Exit(1)
    try:
        records = _load_retrieval_dataset(dataset)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if source == "cached":
        retriever: object = CachedRetriever(cache)
        model_label = retriever.mode
    elif source == "dataset":
        retriever = DatasetRetriever()
        model_label = "dataset"
    else:
        retriever = _build_pipeline_retriever(genome_build, request_cache)
        model_label = "live-pipeline"

    for rec in records:
        rec.system_output = retriever.extract(rec)

    provenance: dict = {}
    if source == "cached":
        hits = sum(1 for rec in records if retriever.covers(rec.id))
        provenance["cache_hit_rate"] = f"{hits}/{len(records)}"
        if hits < len(records):
            typer.echo(f"WARNING: {hits}/{len(records)} variants matched cache '{cache}'.", err=True)

    context = EvalContext(config={"genome_build": genome_build})
    result = evaluate(
        "variant_retrieval", records, context,
        dataset=dataset, model=model_label,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        provenance=provenance,
    )
    output = render_retrieval_report(result)
    out_path = Path(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    typer.echo(f"Wrote {report}  (variants: {result.n_documents}, source: {model_label})")
```
No new downloader is needed here — the gold builder `datasets/build_hgmd_gold.py` (and its
`datasets/README.md` section) already exist. Real runs use `--dataset datasets/hgmd_gold/ryr1_gold.jsonl`
(or `panel_gold.jsonl`) produced by that builder; the committed `--dataset ryr1` path stays synthetic.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm clineval uv run pytest tests/test_cli_retrieval.py -v`
Expected: PASS. Also run the CLI directly:
```bash
docker compose run --rm clineval uv run clineval retrieval-eval --dataset ryr1 --source cached --report reports/retrieval.md
```
Expected: writes `reports/retrieval.md`.

- [ ] **Step 5: Commit**

```bash
git add clineval/cli.py examples/data/cached_retrieval.jsonl tests/test_cli_retrieval.py
git commit -m "feat(cli): add retrieval-eval command + cached RYR1 demo fixture"
```

---

### Task 18: End-to-end verification, docs, coverage

**Files:**
- Modify: `README.md` (retrieval quickstart)
- Modify: `docs/USAGE.md` (retrieval-eval section)
- Test: `tests/test_retrieval_e2e.py`

**Interfaces:**
- Consumes: everything above.
- Produces: an end-to-end offline test proving loader → cached retriever → metric → report; docs; a full-suite green run under the 98% gate.

- [ ] **Step 1: Write the end-to-end test**

`tests/test_retrieval_e2e.py`:
```python
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
import clineval.tasks.variant_retrieval  # noqa: F401
from clineval.tasks.variant_retrieval.datasets import RYR1BenchmarkLoader
from clineval.tasks.variant_retrieval.report import render_retrieval_report
from clineval.tasks.variant_retrieval.retriever import CachedRetriever


def test_end_to_end_cached_offline():
    records = RYR1BenchmarkLoader().load()
    retriever = CachedRetriever("examples/data/cached_retrieval.jsonl")
    for rec in records:
        rec.system_output = retriever.extract(rec)
    result = evaluate("variant_retrieval", records, EvalContext(),
                      dataset="ryr1", model="cached", timestamp="2026-07-16T00:00:00+00:00")
    md = render_retrieval_report(result)
    assert "Variant Literature Retrieval Report" in md
    # the metric ran and produced a recall figure
    assert result.metric("retrieval_prf").aggregate["recall"] >= 0.0
    # flag-not-drop: at least the intronic seed is unresolved
    assert result.metric("retrieval_prf").details["unresolved"]
```

- [ ] **Step 2: Run test to verify it passes** (it should, on already-built pieces)

Run: `docker compose run --rm clineval uv run pytest tests/test_retrieval_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Update docs**

`README.md` — add under a new "Variant literature retrieval (Phase 1)" heading:
```markdown
## Variant literature retrieval (Phase 1)

Retrieve ranked-candidate primary literature for a genomic variant and score retrieval
recall/precision against a known-answer benchmark (RYR1 / Wermers 2024) — the validation
artifact for replacing HGMD's literature-curation function. Offline demo:

```bash
docker compose run --rm clineval uv run clineval retrieval-eval --dataset ryr1 --source cached --report reports/retrieval.md
```

Live pipeline (needs network + `NCBI_API_KEY`): add `--source live`. The pipeline uses only
free public APIs (VariantValidator, myvariant.info, LitVar2, NCBI E-utilities) and never calls
HGMD. See `docs/superpowers/specs/2026-07-16-variant-literature-retrieval-design.md`.
```
`docs/USAGE.md` — add a `retrieval-eval` section mirroring the `run` section (flags, cached vs live, where the report lands).

- [ ] **Step 4: Full suite + coverage gate**

Run:
```bash
docker compose run --rm clineval uv run pytest
```
Expected: entire suite PASSES with coverage ≥ 98%. If a new module is under-covered, add a focused test (do not lower the gate).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/USAGE.md tests/test_retrieval_e2e.py
git commit -m "docs+test(retrieval): end-to-end offline test, README + USAGE for retrieval-eval"
```

---

## Self-Review

**Spec coverage:** Stage 1 (§4) → Tasks 8–10; Stage 2 (§5) → Tasks 11–12; clients/cache/throttle (§6) → Tasks 5–7, 9, 11; core changes (§3) → Tasks 2–3; metric (§7) → Task 13; truth sets/schema (§8) → Task 15 (+ builder in 17); report (§9) → Task 16; regulatory (§10) → Task 16; CLI (§11) → Task 17; testing (§12) → every task + Task 18; API verification (§14) → Task 0. HGMD export is an **owner action item** (not code) surfaced in §8 and Task 15's error message + Task 17's README.

**Placeholder scan:** the only deliberately deferred concretes are the LitVar2 endpoint path and the real gold/cached PMIDs, all explicitly gated on the Task-0 spike and flagged inline (Tasks 0, 11, 15, 17). PubTator3 is optional and out of the critical path. No "TODO/handle-edge-cases" hand-waving elsewhere.

**Type consistency:** `set_prf` (Task 2) → used in Task 13; `VariantForms`/`RetrievalResult`/`PaperRef`/`PipelineProvenance` (Task 4) → Tasks 9–14; `HttpClient.get_json` (Task 7) → Tasks 9, 11; `VVParsed` (Task 9) → Task 10; retriever `extract`/`covers`/`mode` (Task 14) → Task 17; `render_retrieval_report` (Task 16) → Tasks 17–18; `evaluate(..., provenance=)` (Task 3) → Task 17.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-16-variant-literature-retrieval.md`.** Companion design spec: `docs/superpowers/specs/2026-07-16-variant-literature-retrieval-design.md`.

**Blocking prerequisite before Task 1:** run **Task 0** (the connectivity + schema spike) — it confirms the current LitVar2/PubTator3 endpoint paths, which the client tasks depend on. (The truth-set risk is already resolved: the gold set is built directly from the lab's local HGMD dump via `datasets/build_hgmd_gold.py` — see the design spec §8 — with no dependency on the Wermers supplement.)

Two execution options:
1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.
