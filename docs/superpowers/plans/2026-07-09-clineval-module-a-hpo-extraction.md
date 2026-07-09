# ClinEval Module A (HPO Extraction Evaluation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ClinEval's generic evaluation core plus Module A (HPO extraction evaluation), so that one command runs an end-to-end evaluation on ~10 documents and writes a Markdown report including a regulatory-evidence mapping.

**Architecture:** A task-agnostic `core/` (schema, dataset loading, metric base + task-keyed registry, evaluator, report) with a PyHPO-backed `core/ontology/` layer. Module A lives under `tasks/hpo_extraction/` (metrics for Tiers 1–3, a pluggable extractor, HPO-ID adapters, dataset loader). A task = (dataset schema + adapter + metric set + report template); the metric registry dispatches by task name so future tasks (Module B) are additive without touching Module A.

**Tech Stack:** Latest Python (target **3.14**), uv, PyHPO (ontology / IC / semantic similarity), openai (OpenAI-compatible LLM client), Typer (CLI), Jinja2 (report), pytest (tests). **All execution is containerized (Docker / docker compose) — nothing is installed on the host.**

## Global Constraints

- **Everything runs in Docker.** No host Python / uv / pip installs. Every `uv` / `pytest` / `python` / `clineval` command in this plan runs **inside the container** — see "Execution Environment" below.
- **Latest Python** — target **3.14** via the container base image. `requires-python = ">=3.14"`; if a dependency lacks 3.14 wheels at build time, drop the base image + floor to `3.13` (a one-line change, noted in Task 1).
- Packaged with **uv** + `pyproject.toml`. Dependency constraints use `>=` floors with **no upper pins**, so `uv` resolves the **newest compatible** version of each: `pyhpo`, `openai`, `typer`, `jinja2` (runtime); `pytest`, `ruff` (dev). **No DeepEval, RAGAS, RAG, scikit-learn.**
- All code, comments, docstrings, README, docs in **English**.
- **PUBLIC data only. No PHI.** Runs fully locally (on-prem, containerized). Permissive licenses only. **MIT `LICENSE`** at repo root.
- Metrics are **document-level, macro-averaged**. No mention-level/boundary metrics.
- HPO IDs are normalized to colon form: `HP_0000110` / `hp:0000110` → **`HP:0000110`**, applied to **both** gold and predictions before any lookup.
- Version alignment policy: resolve `alt_id → primary`; **flag** merged/obsolete (count + list), exclude from scoring, **no `replaced_by` auto-remap** in the MVP.
- Semantic P/R/F1 = asymmetric best-match on **Lin** (0–1), plus IC-weighted variants. No Lin floor in the MVP.
- Demo extractor defaults to **cached predictions**; `--live` calls an OpenAI-compatible endpoint. From inside Docker the host's LM Studio is reached at `http://host.docker.internal:1234/v1` (not `localhost`). Cached file records the producing **model/version**.
- Report is **Markdown only**. Regulatory table labels ISO clauses as **ISO 15189:2022**.
- Module B: **placeholder folder + docstring only** — do not implement.
- Every task is TDD (red → green → refactor) and ends with a commit. PyHPO is touched **only** inside `core/ontology/`.

---

## Execution Environment (Docker) — read before Task 1

**Prerequisite:** Docker Desktop must be **running** (the daemon was stopped when this plan was written; `docker`/`docker compose` CLIs are installed). Nothing else is installed on the host.

**Convention used by every task:** each step shows commands like `uv run pytest ...`. Run each **inside the container**:

```bash
docker compose run --rm clineval <command>
# e.g.  docker compose run --rm clineval uv run pytest tests/test_schema.py -v
#       docker compose run --rm clineval uv run clineval run --dataset synthetic --report reports/report.md
```

The repo is bind-mounted into `/app`, so edits on the host are seen immediately and files the container writes (reports, git commits) land on the host. The uv virtualenv lives at `/opt/venv` (outside the mount) so it is not shadowed. `git commit` steps run on the **host** (or in-container — either works, same repo). Build the image once in Task 1; subsequent `docker compose run` calls are fast (deps cached in the image layer).

---

### Task 1: Project scaffolding, tooling, and license

**Files:**
- Create: `pyproject.toml`
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `.gitignore` (replace existing)
- Create: `clineval/__init__.py`, `clineval/core/__init__.py`, `clineval/core/ontology/__init__.py`, `clineval/tasks/__init__.py`, `clineval/tasks/hpo_extraction/__init__.py`, `clineval/tasks/report_generation/__init__.py`, `clineval/regulatory/__init__.py`, `clineval/templates/` (dir), `datasets/__init__.py`, `examples/data/` (dir), `tests/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: an importable `clineval` package (version `0.1.0`) and a working containerized `pytest`/`uv` toolchain that every later task relies on.

- [ ] **Step 1: Prerequisite — Docker Desktop running (no host installs)**

Do **not** install Python or uv on the host. Confirm Docker is up:
```bash
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
```
Expected: all three print (a server version means the daemon is running). If the last one errors, **start Docker Desktop** and retry. The image (built in Step 9) provides Python 3.14 + uv + all deps.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "clineval"
version = "0.1.0"
description = "Open-source, self-hostable evaluation toolkit for clinical LLM outputs. Module A: HPO extraction evaluation."
readme = "README.md"
requires-python = ">=3.14"
license = { text = "MIT" }
authors = [{ name = "ClinEval contributors" }]
keywords = ["clinical", "evaluation", "HPO", "phenotype", "LLM", "regulatory"]
# Floors only (no upper pins): uv resolves the newest compatible version of each.
dependencies = [
    "pyhpo>=3.1.4",
    "openai>=1.40",
    "typer>=0.12",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[project.scripts]
clineval = "clineval.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["clineval"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py314"
```

> **3.14 fallback:** if `uv sync` fails because a dependency has no 3.14 wheel yet, change `requires-python` to `">=3.13"`, set `target-version = "py313"`, and change the Dockerfile base image tag to `3.13-slim` — nothing else changes.

- [ ] **Step 3: Write `LICENSE` (MIT)**

```text
MIT License

Copyright (c) 2026 ClinEval contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Write `.gitignore` (replace the existing one; keep ignoring the private notes)**

```gitignore
# Private notes (existing)
docs/Self

# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/
.pytest_cache/
.ruff_cache/

# Generated reports and downloaded datasets
reports/
datasets/gsc_plus/
```

- [ ] **Step 5: Write `README.md` (portfolio stub — expanded in Task 18)**

```markdown
# ClinEval

**Open-source, self-hostable evaluation toolkit for clinical LLM outputs.** ClinEval is an *evaluator* — an inspection rig for clinical AI — not a system that builds extraction or generation models. It produces clinically meaningful quality metrics **and** evidence mapped to medical-device regulation (EU AI Act, IVDR, ISO 15189:2022).

**Module A (this MVP): HPO extraction evaluation.** Given clinical text, a system's extracted HPO term IDs, and a gold standard, ClinEval scores precision/recall/F1 (exact), semantic/hierarchy-aware similarity (via PyHPO), and a clinical error taxonomy — then renders a Markdown report including a regulatory-evidence mapping.

> **Disclaimer:** General technical/educational reference, not legal or regulatory-compliance advice. Confirm dataset licenses before use and consult qualified regulatory/quality professionals against current official texts.

## Quickstart (Docker — no host installs)

```bash
docker compose build
docker compose run --rm clineval uv run clineval run --dataset synthetic --report reports/report.md
```

For a live run against a local LM Studio on the host, add `--live --base-url http://host.docker.internal:1234/v1`.
See `examples/hpo_extraction_demo.ipynb` for a notebook walkthrough.

## License

MIT — see `LICENSE`.
```

- [ ] **Step 6: Create the package `__init__.py` files**

`clineval/__init__.py`:
```python
"""ClinEval: evaluation toolkit for clinical LLM outputs."""

__version__ = "0.1.0"
```
Create empty (single-line docstring) `__init__.py` for: `clineval/core/`, `clineval/core/ontology/`, `clineval/tasks/`, `clineval/regulatory/`, `datasets/`, `tests/`. For example `clineval/core/__init__.py`:
```python
"""Task-agnostic evaluation core."""
```
`clineval/tasks/report_generation/__init__.py` (Module B placeholder — do NOT implement):
```python
"""Module B placeholder: report-generation evaluation.

Intentionally empty for the MVP. A future task adds report-generation metrics
(faithfulness / hallucination) here, registered under task name
"report_generation", reusing the same core schema, evaluator, and report
machinery — without touching Module A.
"""
```
`clineval/tasks/hpo_extraction/__init__.py` (imports its metrics so the registry is populated on import — the concrete metrics arrive in Tasks 6, 8, 9; this import line is added in Task 6):
```python
"""Module A: HPO extraction evaluation."""
```
Also create the empty directory `clineval/templates/` with a `.gitkeep`, and `examples/data/` with a `.gitkeep`.

- [ ] **Step 7: Write the smoke test**

`tests/test_smoke.py`:
```python
import clineval


def test_package_version():
    assert clineval.__version__ == "0.1.0"
```

- [ ] **Step 8: Write `Dockerfile`, `compose.yaml`, `.dockerignore`**

`Dockerfile`:
```dockerfile
# Latest Python (see the 3.14 fallback note in Step 2 if a dep lacks 3.14 wheels).
FROM python:3.14-slim

# uv installs into a venv OUTSIDE /app so the runtime bind-mount does not shadow it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN pip install --no-cache-dir uv

WORKDIR /app

# Layer-cache dependencies: copy only manifests first, sync deps without the project.
COPY pyproject.toml ./
RUN uv sync --extra dev --no-install-project

# Copy the rest and install the project itself (editable).
COPY . .
RUN uv sync --extra dev

CMD ["uv", "run", "pytest", "-q"]
```

`compose.yaml`:
```yaml
services:
  clineval:
    build: .
    working_dir: /app
    environment:
      - UV_PROJECT_ENVIRONMENT=/opt/venv
    volumes:
      - .:/app                      # host repo is the source of truth
      - pyhpo-cache:/root/.cache    # persist any PyHPO/uv runtime cache
    extra_hosts:
      - "host.docker.internal:host-gateway"   # reach host LM Studio for --live

volumes:
  pyhpo-cache:
```

`.dockerignore`:
```gitignore
.git
.venv
__pycache__
*.pyc
.pytest_cache
.ruff_cache
reports
datasets/gsc_plus
docs/Self
```

- [ ] **Step 9: Build the image and run the smoke test (in the container)**

Run:
```bash
docker compose build
docker compose run --rm clineval uv run pytest tests/test_smoke.py -v
```
Expected: the image builds (installs Python 3.14 + uv + deps); the smoke test PASSES. From here on, every `uv ...` / `pytest ...` / `clineval ...` command runs via `docker compose run --rm clineval <command>`.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "chore: scaffold clineval package, Docker toolchain, MIT license"
```

---

### Task 2: Core data schema

**Files:**
- Create: `clineval/core/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces:
  - `PredictionRecord(id: str, input_text: str, gold_reference: list[str], system_output: list[str] = [], metadata: dict = {})`
  - `MetricResult(name: str, aggregate: dict[str, float], per_document: dict[str, dict[str, float]] = {}, details: dict = {})`
  - `OntologyAlignment(hpo_version: str, ic_basis: str, alt_ids_resolved: int, obsolete_flagged: int, obsolete_ids: list[str], policy: str)`
  - `EvaluationResult(task, dataset, n_documents, model, timestamp, metrics: list[MetricResult], alignment: OntologyAlignment, records: list[PredictionRecord] = [])`

- [ ] **Step 1: Write the failing test**

`tests/test_schema.py`:
```python
from clineval.core.schema import (
    EvaluationResult,
    MetricResult,
    OntologyAlignment,
    PredictionRecord,
)


def test_prediction_record_defaults():
    rec = PredictionRecord(id="r1", input_text="text", gold_reference=["HP:0001250"])
    assert rec.system_output == []
    assert rec.metadata == {}
    # defaults must be independent instances, not shared
    rec.system_output.append("HP:0000252")
    assert PredictionRecord(id="r2", input_text="", gold_reference=[]).system_output == []


def test_evaluation_result_holds_components():
    mr = MetricResult(name="tier1_exact", aggregate={"f1": 0.5})
    align = OntologyAlignment(
        hpo_version="2025-01-01", ic_basis="omim", alt_ids_resolved=1,
        obsolete_flagged=0, obsolete_ids=[], policy="p",
    )
    res = EvaluationResult(
        task="hpo_extraction", dataset="synthetic", n_documents=1, model="cached:x",
        timestamp="2026-07-09T00:00:00+00:00", metrics=[mr], alignment=align,
    )
    assert res.metrics[0].aggregate["f1"] == 0.5
    assert res.alignment.ic_basis == "omim"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clineval.core.schema'`.

- [ ] **Step 3: Write minimal implementation**

`clineval/core/schema.py`:
```python
"""Shared, task-agnostic data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PredictionRecord:
    """One evaluation unit. For Module A, gold_reference/system_output are HPO IDs."""

    id: str
    input_text: str
    gold_reference: list[str]
    system_output: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricResult:
    """Output of a single Metric across the dataset."""

    name: str
    aggregate: dict[str, float]
    per_document: dict[str, dict[str, float]] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OntologyAlignment:
    """Record of HPO version-alignment applied before scoring."""

    hpo_version: str
    ic_basis: str
    alt_ids_resolved: int
    obsolete_flagged: int
    obsolete_ids: list[str]
    policy: str


@dataclass
class EvaluationResult:
    """Everything the report renderer needs."""

    task: str
    dataset: str
    n_documents: int
    model: str
    timestamp: str
    metrics: list[MetricResult]
    alignment: OntologyAlignment
    records: list[PredictionRecord] = field(default_factory=list)

    def metric(self, name: str) -> MetricResult | None:
        for m in self.metrics:
            if m.name == name:
                return m
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/core/schema.py tests/test_schema.py
git commit -m "feat: add core evaluation schema"
```

---

### Task 3: Generic dataset loading (ABC + JSONL)

**Files:**
- Create: `clineval/core/dataset.py`
- Test: `tests/test_dataset.py`

**Interfaces:**
- Consumes: `PredictionRecord` (Task 2).
- Produces:
  - `class DatasetLoader(ABC)` with `load(self) -> list[PredictionRecord]`.
  - `class JSONLDatasetLoader(DatasetLoader)`; `__init__(self, path: str)`.

- [ ] **Step 1: Write the failing test**

`tests/test_dataset.py`:
```python
from clineval.core.dataset import JSONLDatasetLoader


def test_jsonl_loader_reads_records(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text(
        '{"id": "r1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n'
        "\n"  # blank lines ignored
        '{"id": "r2", "input_text": "x", "gold_reference": [], '
        '"system_output": ["HP:0000252"], "metadata": {"src": "t"}}\n',
        encoding="utf-8",
    )
    records = JSONLDatasetLoader(str(p)).load()
    assert [r.id for r in records] == ["r1", "r2"]
    assert records[0].gold_reference == ["HP:0001250"]
    assert records[0].system_output == []
    assert records[1].system_output == ["HP:0000252"]
    assert records[1].metadata == {"src": "t"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dataset.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/core/dataset.py`:
```python
"""Task-agnostic dataset loading."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from clineval.core.schema import PredictionRecord


class DatasetLoader(ABC):
    """A dataset loader yields PredictionRecords for evaluation."""

    @abstractmethod
    def load(self) -> list[PredictionRecord]:
        raise NotImplementedError


class JSONLDatasetLoader(DatasetLoader):
    """Load user-supplied records from a JSON Lines file.

    Each line: {"id", "input_text", "gold_reference", [optional] "system_output",
    [optional] "metadata"}.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> list[PredictionRecord]:
        records: list[PredictionRecord] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                records.append(
                    PredictionRecord(
                        id=str(obj["id"]),
                        input_text=obj.get("input_text", ""),
                        gold_reference=list(obj.get("gold_reference", [])),
                        system_output=list(obj.get("system_output", [])),
                        metadata=dict(obj.get("metadata", {})),
                    )
                )
        return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dataset.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clineval/core/dataset.py tests/test_dataset.py
git commit -m "feat: add DatasetLoader ABC and JSONL loader"
```

---

### Task 4: HPO-ID adapters (normalization + LLM-output parsing)

**Files:**
- Create: `clineval/tasks/hpo_extraction/adapters.py`
- Test: `tests/test_adapters.py`

**Interfaces:**
- Consumes: `PredictionRecord` (Task 2).
- Produces (pure, no PyHPO):
  - `normalize_hpo_id(raw: str | None) -> str | None`
  - `normalize_hpo_ids(raw_ids: Iterable[str]) -> list[str]` (normalize, drop invalid, dedupe, keep order)
  - `parse_llm_output(text: str) -> list[str]` (extract HPO IDs from free text/JSON)
  - `normalize_record(rec: PredictionRecord) -> PredictionRecord` (normalizes gold + system_output in place, returns it)
  - (`align_records` is added in Task 10.)

- [ ] **Step 1: Write the failing test**

`tests/test_adapters.py`:
```python
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction import adapters


def test_normalize_underscore_and_case():
    assert adapters.normalize_hpo_id("HP_0000110") == "HP:0000110"
    assert adapters.normalize_hpo_id("hp:0000110") == "HP:0000110"
    assert adapters.normalize_hpo_id("  HP:0000110  ") == "HP:0000110"


def test_normalize_rejects_invalid():
    assert adapters.normalize_hpo_id("not-an-id") is None
    assert adapters.normalize_hpo_id("HP:123") is None  # too short
    assert adapters.normalize_hpo_id(None) is None


def test_normalize_ids_dedupes_and_drops_invalid():
    assert adapters.normalize_hpo_ids(["HP_0000110", "HP:0000110", "junk"]) == ["HP:0000110"]


def test_parse_llm_output_extracts_ids():
    text = 'Terms: HP_0001250 (seizure), "HP:0000252". Also nonsense HP:99.'
    assert adapters.parse_llm_output(text) == ["HP:0001250", "HP:0000252"]


def test_normalize_record_in_place():
    rec = PredictionRecord(
        id="r", input_text="", gold_reference=["HP_0001250"], system_output=["hp:0000252"]
    )
    out = adapters.normalize_record(rec)
    assert out is rec
    assert rec.gold_reference == ["HP:0001250"]
    assert rec.system_output == ["HP:0000252"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/tasks/hpo_extraction/adapters.py`:
```python
"""Normalize system/gold HPO IDs into the canonical ``HP:0000000`` form.

Pure string handling — no PyHPO. GSC+ uses underscores (``HP_0000110``) while
PyHPO uses colons (``HP:0000110``); without normalization nothing matches.
"""

from __future__ import annotations

import re
from typing import Iterable

from clineval.core.schema import PredictionRecord

_HPO_RE = re.compile(r"HP[:_](\d{7})", re.IGNORECASE)


def normalize_hpo_id(raw: str | None) -> str | None:
    """Return canonical ``HP:0000000`` for a single ID, or None if not an HPO ID."""
    if raw is None:
        return None
    match = _HPO_RE.search(str(raw).strip())
    if not match:
        return None
    return f"HP:{match.group(1)}"


def normalize_hpo_ids(raw_ids: Iterable[str]) -> list[str]:
    """Normalize a collection: drop invalid, dedupe, preserve first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_ids:
        nid = normalize_hpo_id(raw)
        if nid is not None and nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def parse_llm_output(text: str) -> list[str]:
    """Extract HPO IDs from free-form or JSON LLM output."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for digits in _HPO_RE.findall(text):
        nid = f"HP:{digits}"
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def normalize_record(rec: PredictionRecord) -> PredictionRecord:
    """Normalize gold_reference and system_output in place; return the record."""
    rec.gold_reference = normalize_hpo_ids(rec.gold_reference)
    rec.system_output = normalize_hpo_ids(rec.system_output)
    return rec
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adapters.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/adapters.py tests/test_adapters.py
git commit -m "feat: add HPO-ID normalization and LLM-output parsing adapters"
```

---

### Task 5: Metric base, EvalContext, registry

**Files:**
- Create: `clineval/core/metric.py`
- Test: `tests/test_metric.py`

**Interfaces:**
- Consumes: `PredictionRecord`, `MetricResult` (Task 2).
- Produces:
  - `class EvalContext:` `__init__(self, ontology=None, config: dict | None = None)`; attributes `.ontology`, `.config`.
  - `class Metric(ABC):` class attr `name: str`; `compute(self, records: list[PredictionRecord], context: EvalContext) -> MetricResult`.
  - `register_metric(task: str)` decorator; `get_metrics(task: str) -> list[Metric]`.
  - `macro_average(per_doc: dict[str, dict[str, float]], keys: list[str]) -> dict[str, float]`.

- [ ] **Step 1: Write the failing test**

`tests/test_metric.py`:
```python
from clineval.core.metric import (
    EvalContext,
    Metric,
    get_metrics,
    macro_average,
    register_metric,
)
from clineval.core.schema import MetricResult


def test_macro_average():
    per_doc = {"a": {"f1": 1.0}, "b": {"f1": 0.0}}
    assert macro_average(per_doc, ["f1"]) == {"f1": 0.5}
    assert macro_average({}, ["f1"]) == {"f1": 0.0}


def test_register_and_get_metrics():
    @register_metric("unit_test_task")
    class Dummy(Metric):
        name = "dummy"

        def compute(self, records, context):
            return MetricResult(name=self.name, aggregate={"n": float(len(records))})

    metrics = get_metrics("unit_test_task")
    assert [m.name for m in metrics] == ["dummy"]
    result = metrics[0].compute([1, 2, 3], EvalContext())
    assert result.aggregate["n"] == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metric.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/core/metric.py`:
```python
"""Metric base class, evaluation context, and a task-keyed registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from clineval.core.schema import MetricResult, PredictionRecord


class EvalContext:
    """Shared state passed to every metric (loaded ontology + config)."""

    def __init__(self, ontology: object | None = None, config: dict | None = None) -> None:
        self.ontology = ontology
        self.config = config or {}


class Metric(ABC):
    """A metric computes a MetricResult over a list of records."""

    name: str = "metric"

    @abstractmethod
    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        raise NotImplementedError


_REGISTRY: dict[str, list[type[Metric]]] = {}


def register_metric(task: str) -> Callable[[type[Metric]], type[Metric]]:
    """Class decorator: register a Metric subclass under a task name."""

    def decorator(cls: type[Metric]) -> type[Metric]:
        bucket = _REGISTRY.setdefault(task, [])
        if cls not in bucket:
            bucket.append(cls)
        return cls

    return decorator


def get_metrics(task: str) -> list[Metric]:
    """Instantiate the metrics registered for a task."""
    return [cls() for cls in _REGISTRY.get(task, [])]


def macro_average(
    per_doc: dict[str, dict[str, float]], keys: list[str]
) -> dict[str, float]:
    """Mean of each key across documents (0.0 for each key if no documents)."""
    n = len(per_doc)
    if n == 0:
        return {k: 0.0 for k in keys}
    return {k: sum(d.get(k, 0.0) for d in per_doc.values()) / n for k in keys}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metric.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/core/metric.py tests/test_metric.py
git commit -m "feat: add metric base class, eval context, and task registry"
```

---

### Task 6: Tier 1 exact P/R/F1 metric

**Files:**
- Create: `clineval/tasks/hpo_extraction/metrics.py`
- Modify: `clineval/tasks/hpo_extraction/__init__.py` (import metrics so registration runs)
- Test: `tests/test_metrics_tier1.py`

**Interfaces:**
- Consumes: `Metric`, `register_metric`, `EvalContext`, `macro_average` (Task 5); `MetricResult`, `PredictionRecord` (Task 2).
- Produces: `class Tier1ExactMetric(Metric)` with `name = "tier1_exact"`, registered under `"hpo_extraction"`; aggregate/per-doc keys `precision`, `recall`, `f1`. Also a module-level helper `harmonic(p: float, r: float) -> float` reused by later tiers.

- [ ] **Step 1: Write the failing test**

`tests/test_metrics_tier1.py`:
```python
from clineval.core.metric import EvalContext, get_metrics
from clineval.core.schema import PredictionRecord
import clineval.tasks.hpo_extraction  # noqa: F401  (triggers metric registration)
from clineval.tasks.hpo_extraction.metrics import Tier1ExactMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


def test_tier1_perfect_and_partial():
    records = [
        _rec("r1", ["HP:0001250", "HP:0000252"], ["HP:0001250", "HP:0000252"]),  # perfect
        _rec("r2", ["HP:0001250"], ["HP:0000252"]),  # all wrong
    ]
    result = Tier1ExactMetric().compute(records, EvalContext())
    assert result.per_document["r1"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert result.per_document["r2"]["f1"] == 0.0
    assert result.aggregate["f1"] == 0.5  # macro mean of 1.0 and 0.0


def test_tier1_empty_sets_are_perfect():
    result = Tier1ExactMetric().compute([_rec("r", [], [])], EvalContext())
    assert result.per_document["r"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_tier1_is_registered_for_task():
    names = [m.name for m in get_metrics("hpo_extraction")]
    assert "tier1_exact" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_tier1.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/tasks/hpo_extraction/metrics.py`:
```python
"""Module A metrics: Tier 1 (exact), Tier 2 (semantic), Tier 3 (clinical).

Tiers 2 and 3 (added in later tasks) read the loaded ontology from
``context.ontology``; Tier 1 needs no ontology.
"""

from __future__ import annotations

from clineval.core.metric import EvalContext, Metric, macro_average, register_metric
from clineval.core.schema import MetricResult, PredictionRecord


def harmonic(precision: float, recall: float) -> float:
    """Harmonic mean; 0.0 when both are 0."""
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _exact_prf(gold: list[str], pred: list[str]) -> dict[str, float]:
    gold_set, pred_set = set(gold), set(pred)
    tp = len(gold_set & pred_set)
    if not pred_set:
        precision = 1.0 if not gold_set else 0.0
    else:
        precision = tp / len(pred_set)
    if not gold_set:
        recall = 1.0 if not pred_set else 0.0
    else:
        recall = tp / len(gold_set)
    return {"precision": precision, "recall": recall, "f1": harmonic(precision, recall)}


@register_metric("hpo_extraction")
class Tier1ExactMetric(Metric):
    """Exact-match precision/recall/F1 on HPO concept IDs (document-level macro)."""

    name = "tier1_exact"

    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        per_doc = {r.id: _exact_prf(r.gold_reference, r.system_output) for r in records}
        aggregate = macro_average(per_doc, ["precision", "recall", "f1"])
        return MetricResult(name=self.name, aggregate=aggregate, per_document=per_doc)
```

Modify `clineval/tasks/hpo_extraction/__init__.py` to trigger registration on import:
```python
"""Module A: HPO extraction evaluation."""

from clineval.tasks.hpo_extraction import metrics  # noqa: F401  (registers metrics)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics_tier1.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/metrics.py clineval/tasks/hpo_extraction/__init__.py tests/test_metrics_tier1.py
git commit -m "feat: add Tier 1 exact P/R/F1 metric"
```

---

### Task 7: Ontology layer (PyHPO wrapper) + smoke test

> This is the **only** code that touches PyHPO. If the installed PyHPO API differs from the calls below, fix it **here** and nowhere else. The smoke test surfaces API drift immediately.

**Files:**
- Create: `clineval/core/ontology/ic.py`
- Create: `clineval/core/ontology/similarity.py`
- Create: `clineval/core/ontology/hpo.py`
- Create: `tests/conftest.py` (session-scoped ontology fixture)
- Test: `tests/test_ontology.py`

**Interfaces:**
- Produces:
  - `ic.term_ic(term, basis: str) -> float`
  - `similarity.pairwise(term1, term2, method: str, basis: str) -> float`
  - `similarity.bma(ontology, ids1: list[str], ids2: list[str], method: str = "lin") -> float`
  - `similarity.is_ancestor_or_descendant(term1, term2) -> bool`
  - `hpo.TermResolution(original: str, resolved: str | None, status: str)` where `status ∈ {"primary","alt_id","obsolete"}`
  - `hpo.Ontology`: `__init__(self, ic_basis: str = "omim")`; `.version -> str`; `.ic_basis`; `resolve(id) -> TermResolution`; `term(id)`; `ic(id) -> float`; `similarity(id1, id2, method="lin") -> float`; `bma(ids1, ids2, method="lin") -> float`; `related(id1, id2) -> bool`.

- [ ] **Step 1: Write the smoke/behaviour test**

`tests/conftest.py`:
```python
import pytest

from clineval.core.ontology.hpo import Ontology


@pytest.fixture(scope="session")
def ontology():
    """Load PyHPO once per test session (heavy: loads the HPO graph + annotations)."""
    return Ontology(ic_basis="omim")
```

`tests/test_ontology.py`:
```python
# Known relationships used across tests:
#   HP:0001629 Ventricular septal defect (parent)
#   HP:0011682 Perimembranous VSD  (child of 0001629)
#   HP:0011623 Muscular VSD        (child of 0001629; sibling of 0011682)
#   HP:0001250 Seizure             (unrelated to the VSD subtree)
#   HP:0000118 Phenotypic abnormality (very broad -> low IC)


def test_version_is_nonempty(ontology):
    assert isinstance(ontology.version, str) and ontology.version


def test_resolve_primary(ontology):
    res = ontology.resolve("HP:0001629")
    assert res.status == "primary"
    assert res.resolved == "HP:0001629"


def test_resolve_obsolete_or_unknown(ontology):
    res = ontology.resolve("HP:0000000")  # not a real term
    assert res.status == "obsolete"
    assert res.resolved is None


def test_ic_specific_higher_than_broad(ontology):
    assert ontology.ic("HP:0011682") > ontology.ic("HP:0000118")


def test_lin_self_is_one(ontology):
    assert ontology.similarity("HP:0001250", "HP:0001250", method="lin") == 1.0


def test_siblings_more_similar_than_unrelated(ontology):
    sib = ontology.similarity("HP:0011682", "HP:0011623", method="lin")
    unrel = ontology.similarity("HP:0011682", "HP:0001250", method="lin")
    assert sib > unrel


def test_ancestor_relationship(ontology):
    assert ontology.related("HP:0011682", "HP:0001629") is True   # child/parent
    assert ontology.related("HP:0011682", "HP:0011623") is False  # siblings


def test_bma_perfect_and_partial(ontology):
    assert ontology.bma(["HP:0001250"], ["HP:0001250"]) == 1.0
    partial = ontology.bma(["HP:0011682"], ["HP:0011623"])
    assert 0.0 < partial < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ontology.py -v`
Expected: FAIL with `ModuleNotFoundError: clineval.core.ontology.hpo`.

- [ ] **Step 3: Write minimal implementation**

`clineval/core/ontology/ic.py`:
```python
"""Information Content access (delegates to PyHPO term annotations)."""

from __future__ import annotations


def term_ic(term: object, basis: str) -> float:
    """IC for a PyHPO term under the given annotation basis ('omim' or 'gene')."""
    ic = getattr(term, "information_content", None)
    if ic is None:
        return 0.0
    value = getattr(ic, basis, None)
    if value is None and isinstance(ic, dict):
        value = ic.get(basis)
    return float(value) if value is not None else 0.0
```

`clineval/core/ontology/similarity.py`:
```python
"""Pairwise and set-based semantic similarity (delegates pairwise to PyHPO)."""

from __future__ import annotations


def pairwise(term1: object, term2: object, method: str = "lin", basis: str = "omim") -> float:
    """Pairwise similarity between two PyHPO terms via the given method."""
    try:
        return float(term1.similarity_score(term2, kind=basis, method=method))
    except TypeError:
        # Fallback for a keyword-only signature variant.
        return float(term1.similarity_score(other=term2, kind=basis, method=method))
    except Exception:
        return 0.0


def bma(ontology: object, ids1: list[str], ids2: list[str], method: str = "lin") -> float:
    """Best-Match Average between two ID sets, using ontology.similarity."""
    if not ids1 or not ids2:
        return 0.0

    def best(a: str, group: list[str]) -> float:
        return max((ontology.similarity(a, b, method=method) for b in group), default=0.0)

    precision = sum(best(a, ids2) for a in ids1) / len(ids1)
    recall = sum(best(b, ids1) for b in ids2) / len(ids2)
    return (precision + recall) / 2


def _ancestors(term: object) -> set[str]:
    seen: set[str] = set()
    stack = list(getattr(term, "parents", []) or [])
    while stack:
        node = stack.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        stack.extend(getattr(node, "parents", []) or [])
    return seen


def is_ancestor_or_descendant(term1: object, term2: object) -> bool:
    """True if one term is a (transitive) parent of the other."""
    if term1.id == term2.id:
        return False
    return term2.id in _ancestors(term1) or term1.id in _ancestors(term2)
```

`clineval/core/ontology/hpo.py`:
```python
"""PyHPO wrapper: loading, version, ID resolution, IC and similarity access.

This is the only module that imports PyHPO. Metrics depend on this wrapper, not
on PyHPO directly, so any PyHPO API change is isolated here.
"""

from __future__ import annotations

from dataclasses import dataclass

from clineval.core.ontology.ic import term_ic
from clineval.core.ontology.similarity import (
    bma as _bma,
    is_ancestor_or_descendant,
    pairwise,
)


@dataclass
class TermResolution:
    """Result of aligning one HPO ID against the active ontology."""

    original: str
    resolved: str | None
    status: str  # "primary" | "alt_id" | "obsolete"


class Ontology:
    """Loaded HPO ontology + semantic-similarity helpers."""

    def __init__(self, ic_basis: str = "omim") -> None:
        from pyhpo import Ontology as _PyOntology

        _PyOntology()  # initialize the PyHPO singleton (loads graph + annotations)
        self._onto = _PyOntology
        self.ic_basis = ic_basis
        self._alt_index = self._build_alt_index()

    @property
    def version(self) -> str:
        raw = getattr(self._onto, "version", None)
        if callable(raw):
            try:
                return str(raw())
            except Exception:
                return "unknown"
        return str(raw) if raw else "unknown"

    def _build_alt_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        try:
            for term in self._onto:
                for alt in getattr(term, "alternative_ids", []) or []:
                    index[str(alt)] = term.id
        except Exception:
            pass
        return index

    def _lookup(self, hpo_id: str):
        try:
            return self._onto.get_hpo_object(hpo_id)
        except Exception:
            return None

    def resolve(self, hpo_id: str) -> TermResolution:
        term = self._lookup(hpo_id)
        if term is not None and term.id == hpo_id:
            return TermResolution(hpo_id, hpo_id, "primary")
        if hpo_id in self._alt_index:
            return TermResolution(hpo_id, self._alt_index[hpo_id], "alt_id")
        if term is not None and term.id != hpo_id:
            return TermResolution(hpo_id, term.id, "alt_id")
        return TermResolution(hpo_id, None, "obsolete")

    def term(self, hpo_id: str):
        return self._lookup(hpo_id)

    def ic(self, hpo_id: str) -> float:
        term = self._lookup(hpo_id)
        return term_ic(term, self.ic_basis) if term is not None else 0.0

    def similarity(self, id1: str, id2: str, method: str = "lin") -> float:
        if id1 == id2:
            return 1.0 if method in ("lin", "jc") else self.ic(id1)
        t1, t2 = self._lookup(id1), self._lookup(id2)
        if t1 is None or t2 is None:
            return 0.0
        return pairwise(t1, t2, method=method, basis=self.ic_basis)

    def bma(self, ids1: list[str], ids2: list[str], method: str = "lin") -> float:
        return _bma(self, ids1, ids2, method=method)

    def related(self, id1: str, id2: str) -> bool:
        t1, t2 = self._lookup(id1), self._lookup(id2)
        if t1 is None or t2 is None:
            return False
        return is_ancestor_or_descendant(t1, t2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ontology.py -v`
Expected: PASS (8 tests). If any fails due to a PyHPO API mismatch (e.g. `similarity_score` signature, `get_hpo_object`, `information_content` attribute), adjust **only** `hpo.py`/`ic.py`/`similarity.py` and re-run. Confirm the loaded HPO version prints via a scratch `python -c "from clineval.core.ontology.hpo import Ontology; print(Ontology().version)"`.

- [ ] **Step 5: Commit**

```bash
git add clineval/core/ontology/ic.py clineval/core/ontology/similarity.py clineval/core/ontology/hpo.py tests/conftest.py tests/test_ontology.py
git commit -m "feat: add PyHPO ontology wrapper (IC, similarity, resolution)"
```

---

### Task 8: Tier 2 semantic metric

**Files:**
- Modify: `clineval/tasks/hpo_extraction/metrics.py` (append Tier 2)
- Test: `tests/test_metrics_tier2.py`

**Interfaces:**
- Consumes: `context.ontology` (Task 7); `harmonic` (Task 6); `macro_average` (Task 5).
- Produces: `class Tier2SemanticMetric(Metric)` with `name = "tier2_semantic"`; aggregate/per-doc keys: `sem_precision`, `sem_recall`, `sem_f1`, `sem_precision_icw`, `sem_recall_icw`, `sem_f1_icw`, `bma`. Config keys read: `context.config["similarity_method"]` (default `"lin"`).

- [ ] **Step 1: Write the failing test**

`tests/test_metrics_tier2.py`:
```python
from clineval.core.metric import EvalContext
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.metrics import Tier2SemanticMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


def test_semantic_gives_partial_credit_for_near_miss(ontology):
    # Predicted the parent VSD instead of the exact perimembranous VSD.
    rec = _rec("r1", ["HP:0011682"], ["HP:0001629"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    f1 = result.per_document["r1"]["sem_f1"]
    assert 0.0 < f1 < 1.0  # partial credit, not zero and not full


def test_semantic_exact_match_is_one(ontology):
    rec = _rec("r1", ["HP:0001250"], ["HP:0001250"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.per_document["r1"]["sem_f1"] == 1.0
    assert result.per_document["r1"]["bma"] == 1.0


def test_semantic_aggregate_keys_present(ontology):
    rec = _rec("r1", ["HP:0001250"], ["HP:0000252"])
    result = Tier2SemanticMetric().compute([rec], EvalContext(ontology=ontology))
    for key in ["sem_precision", "sem_recall", "sem_f1",
                "sem_precision_icw", "sem_recall_icw", "sem_f1_icw", "bma"]:
        assert key in result.aggregate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_tier2.py -v`
Expected: FAIL with `ImportError: cannot import name 'Tier2SemanticMetric'`.

- [ ] **Step 3: Write minimal implementation (append to `metrics.py`)**

```python
_SEM_KEYS = [
    "sem_precision", "sem_recall", "sem_f1",
    "sem_precision_icw", "sem_recall_icw", "sem_f1_icw", "bma",
]


def _best(ontology, term_id: str, group: list[str], method: str) -> float:
    return max((ontology.similarity(term_id, g, method=method) for g in group), default=0.0)


def _semantic_doc(ontology, gold: list[str], pred: list[str], method: str) -> dict[str, float]:
    if not gold and not pred:
        return {k: 1.0 for k in _SEM_KEYS}

    if pred:
        sem_p = sum(_best(ontology, p, gold, method) for p in pred) / len(pred)
    else:
        sem_p = 1.0 if not gold else 0.0
    if gold:
        sem_r = sum(_best(ontology, g, pred, method) for g in gold) / len(gold)
    else:
        sem_r = 1.0 if not pred else 0.0

    def ic_weighted(items: list[str], other: list[str]) -> float:
        num = den = 0.0
        for x in items:
            weight = ontology.ic(x)
            num += weight * _best(ontology, x, other, method)
            den += weight
        return num / den if den else 0.0

    if pred:
        sem_p_icw = ic_weighted(pred, gold)
    else:
        sem_p_icw = 1.0 if not gold else 0.0
    if gold:
        sem_r_icw = ic_weighted(gold, pred)
    else:
        sem_r_icw = 1.0 if not pred else 0.0

    return {
        "sem_precision": sem_p,
        "sem_recall": sem_r,
        "sem_f1": harmonic(sem_p, sem_r),
        "sem_precision_icw": sem_p_icw,
        "sem_recall_icw": sem_r_icw,
        "sem_f1_icw": harmonic(sem_p_icw, sem_r_icw),
        "bma": (sem_p + sem_r) / 2,
    }


@register_metric("hpo_extraction")
class Tier2SemanticMetric(Metric):
    """Semantic / hierarchy-aware P/R/F1 (best-match on Lin) + IC-weighted + BMA."""

    name = "tier2_semantic"

    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        method = context.config.get("similarity_method", "lin")
        per_doc = {
            r.id: _semantic_doc(context.ontology, r.gold_reference, r.system_output, method)
            for r in records
        }
        aggregate = macro_average(per_doc, _SEM_KEYS)
        return MetricResult(name=self.name, aggregate=aggregate, per_document=per_doc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics_tier2.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/metrics.py tests/test_metrics_tier2.py
git commit -m "feat: add Tier 2 semantic (best-match Lin + IC-weighted + BMA) metric"
```

---

### Task 9: Tier 3 clinical metric (error taxonomy + significance flags)

**Files:**
- Modify: `clineval/tasks/hpo_extraction/metrics.py` (append Tier 3)
- Test: `tests/test_metrics_tier3.py`

**Interfaces:**
- Consumes: `context.ontology` (Task 7).
- Produces: `class Tier3ClinicalMetric(Metric)` with `name = "tier3_clinical"`; aggregate keys `missed`, `spurious`, `wrong_granularity`, `wrong_term` (summed counts); `details["flags"]` = list of `{record, type, hpo_id, ic}` where `type ∈ {"missed_high_ic","high_ic_spurious_fp"}`. Config keys read: `relatedness_tau` (default `0.3`), `ic_high_threshold` (default `3.0`), `similarity_method` (default `"lin"`).

- [ ] **Step 1: Write the failing test**

`tests/test_metrics_tier3.py`:
```python
from clineval.core.metric import EvalContext
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.metrics import Tier3ClinicalMetric


def _rec(rid, gold, pred):
    return PredictionRecord(id=rid, input_text="", gold_reference=gold, system_output=pred)


def test_wrong_granularity_when_parent_predicted(ontology):
    # gold = perimembranous VSD; predicted its parent VSD -> wrong granularity.
    rec = _rec("r1", ["HP:0011682"], ["HP:0001629"])
    result = Tier3ClinicalMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.aggregate["wrong_granularity"] == 1.0
    assert result.aggregate["missed"] == 1.0  # gold not exactly present


def test_spurious_unrelated_fp(ontology):
    # gold = VSD; predicted an unrelated seizure -> spurious; gold missed.
    rec = _rec("r1", ["HP:0001629"], ["HP:0001250"])
    result = Tier3ClinicalMetric().compute([rec], EvalContext(ontology=ontology))
    assert result.aggregate["spurious"] == 1.0
    assert result.aggregate["missed"] == 1.0


def test_wrong_term_for_sibling(ontology):
    # gold = muscular VSD; predicted sibling perimembranous VSD (related, not parent/child).
    # Siblings share the specific VSD parent, so their Lin is comfortably > 0.1;
    # a low tau keeps this robust to exact IC values while still excluding unrelated terms.
    rec = _rec("r1", ["HP:0011623"], ["HP:0011682"])
    result = Tier3ClinicalMetric().compute(
        [rec], EvalContext(ontology=ontology, config={"relatedness_tau": 0.1})
    )
    assert result.aggregate["wrong_term"] == 1.0


def test_missed_high_ic_flag(ontology):
    # A rare, specific gold term missed entirely should be flagged.
    rec = _rec("r1", ["HP:0011682"], [])
    result = Tier3ClinicalMetric().compute(
        [rec], EvalContext(ontology=ontology, config={"ic_high_threshold": 0.0})
    )
    types = {f["type"] for f in result.details["flags"]}
    assert "missed_high_ic" in types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_tier3.py -v`
Expected: FAIL with `ImportError: cannot import name 'Tier3ClinicalMetric'`.

- [ ] **Step 3: Write minimal implementation (append to `metrics.py`)**

```python
_TAXONOMY_KEYS = ["missed", "spurious", "wrong_granularity", "wrong_term"]


@register_metric("hpo_extraction")
class Tier3ClinicalMetric(Metric):
    """Clinical error taxonomy + clinical-significance flags."""

    name = "tier3_clinical"

    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        onto = context.ontology
        tau = context.config.get("relatedness_tau", 0.3)
        ic_high = context.config.get("ic_high_threshold", 3.0)
        method = context.config.get("similarity_method", "lin")

        totals = {k: 0 for k in _TAXONOMY_KEYS}
        flags: list[dict] = []
        per_doc: dict[str, dict[str, float]] = {}

        for r in records:
            gold_set, pred_set = set(r.gold_reference), set(r.system_output)
            residual_pred = [p for p in r.system_output if p not in gold_set]
            residual_gold = [g for g in r.gold_reference if g not in pred_set]
            doc = {k: 0 for k in _TAXONOMY_KEYS}

            for p in residual_pred:
                if any(onto.related(p, g) for g in gold_set):
                    category = "wrong_granularity"
                elif max((onto.similarity(p, g, method=method) for g in gold_set),
                         default=0.0) >= tau:
                    category = "wrong_term"
                else:
                    category = "spurious"
                    ic_p = onto.ic(p)
                    if ic_p >= ic_high:
                        flags.append({"record": r.id, "type": "high_ic_spurious_fp",
                                      "hpo_id": p, "ic": round(ic_p, 3)})
                doc[category] += 1
                totals[category] += 1

            for g in residual_gold:
                doc["missed"] += 1
                totals["missed"] += 1
                ic_g = onto.ic(g)
                if ic_g >= ic_high:
                    flags.append({"record": r.id, "type": "missed_high_ic",
                                  "hpo_id": g, "ic": round(ic_g, 3)})

            per_doc[r.id] = {k: float(v) for k, v in doc.items()}

        aggregate = {k: float(v) for k, v in totals.items()}
        return MetricResult(name=self.name, aggregate=aggregate,
                            per_document=per_doc, details={"flags": flags})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics_tier3.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/metrics.py tests/test_metrics_tier3.py
git commit -m "feat: add Tier 3 clinical error taxonomy and significance flags"
```

---

### Task 10: Version alignment (`align_records`)

**Files:**
- Modify: `clineval/tasks/hpo_extraction/adapters.py` (append `align_records`)
- Test: `tests/test_version_alignment.py`

**Interfaces:**
- Consumes: `Ontology.resolve` (Task 7); `OntologyAlignment`, `PredictionRecord` (Task 2).
- Produces: `align_records(records: list[PredictionRecord], ontology) -> tuple[list[PredictionRecord], OntologyAlignment]`. Mutates each record's `gold_reference`/`system_output` to resolved primary IDs (obsolete dropped), and returns an `OntologyAlignment` summary.

- [ ] **Step 1: Write the failing test (uses a fake ontology — no PyHPO)**

`tests/test_version_alignment.py`:
```python
from clineval.core.ontology.hpo import TermResolution
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.adapters import align_records


class FakeOntology:
    version = "test-1.0"
    ic_basis = "omim"

    def resolve(self, hpo_id):
        table = {
            "HP:0000001": TermResolution("HP:0000001", "HP:0000001", "primary"),
            "HP:0000002": TermResolution("HP:0000002", "HP:0000100", "alt_id"),
            "HP:0000999": TermResolution("HP:0000999", None, "obsolete"),
        }
        return table[hpo_id]


def test_align_resolves_alt_and_flags_obsolete():
    records = [
        PredictionRecord(
            id="r1", input_text="",
            gold_reference=["HP:0000001", "HP:0000002"],  # primary + alt
            system_output=["HP:0000999"],                 # obsolete
        )
    ]
    aligned, alignment = align_records(records, FakeOntology())
    assert aligned[0].gold_reference == ["HP:0000001", "HP:0000100"]  # alt resolved
    assert aligned[0].system_output == []                             # obsolete dropped
    assert alignment.alt_ids_resolved == 1
    assert alignment.obsolete_flagged == 1
    assert alignment.obsolete_ids == ["HP:0000999"]
    assert alignment.hpo_version == "test-1.0"
    assert alignment.ic_basis == "omim"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_version_alignment.py -v`
Expected: FAIL with `ImportError: cannot import name 'align_records'`.

- [ ] **Step 3: Write minimal implementation (append to `adapters.py`)**

Add the import at the top of `adapters.py` (next to the existing `PredictionRecord` import):
```python
from clineval.core.schema import OntologyAlignment, PredictionRecord
```
Append:
```python
def _align_list(ontology, ids: list[str], counters: dict) -> list[str]:
    resolved: list[str] = []
    for hpo_id in ids:
        res = ontology.resolve(hpo_id)
        if res.status == "primary":
            resolved.append(res.resolved)
        elif res.status == "alt_id":
            counters["alt"] += 1
            resolved.append(res.resolved)
        else:  # obsolete / unknown
            counters["obsolete"] += 1
            counters["obsolete_ids"].append(hpo_id)
    seen: set[str] = set()
    deduped: list[str] = []
    for x in resolved:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped


def align_records(records: list[PredictionRecord], ontology) -> tuple[list[PredictionRecord], OntologyAlignment]:
    """Resolve alt_ids to primary and flag/drop obsolete IDs; summarize alignment."""
    counters = {"alt": 0, "obsolete": 0, "obsolete_ids": []}
    for rec in records:
        rec.gold_reference = _align_list(ontology, rec.gold_reference, counters)
        rec.system_output = _align_list(ontology, rec.system_output, counters)
    alignment = OntologyAlignment(
        hpo_version=ontology.version,
        ic_basis=ontology.ic_basis,
        alt_ids_resolved=counters["alt"],
        obsolete_flagged=counters["obsolete"],
        obsolete_ids=sorted(set(counters["obsolete_ids"])),
        policy=(
            "alt_id resolved to primary; merged/obsolete IDs flagged and excluded "
            "from scoring (no replaced_by remap in the MVP)."
        ),
    )
    return records, alignment
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_version_alignment.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/adapters.py tests/test_version_alignment.py
git commit -m "feat: add HPO version alignment (alt_id resolve + obsolete flag)"
```

---

### Task 11: Evaluator

**Files:**
- Create: `clineval/core/evaluator.py`
- Test: `tests/test_evaluator.py`

**Interfaces:**
- Consumes: `get_metrics`, `EvalContext` (Task 5); `EvaluationResult`, `OntologyAlignment` (Task 2).
- Produces: `evaluate(task: str, records, context: EvalContext, *, dataset: str, model: str, timestamp: str, alignment: OntologyAlignment) -> EvaluationResult`.

- [ ] **Step 1: Write the failing test**

`tests/test_evaluator.py`:
```python
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
from clineval.core.schema import OntologyAlignment, PredictionRecord
import clineval.tasks.hpo_extraction  # noqa: F401  (registers metrics)


def test_evaluate_runs_registered_metrics(ontology):
    records = [
        PredictionRecord(id="r1", input_text="", gold_reference=["HP:0001250"],
                         system_output=["HP:0001250"])
    ]
    alignment = OntologyAlignment("v", "omim", 0, 0, [], "policy")
    result = evaluate(
        "hpo_extraction", records, EvalContext(ontology=ontology),
        dataset="synthetic", model="cached:x", timestamp="2026-07-09T00:00:00+00:00",
        alignment=alignment,
    )
    assert result.n_documents == 1
    names = {m.name for m in result.metrics}
    assert {"tier1_exact", "tier2_semantic", "tier3_clinical"} <= names
    assert result.metric("tier1_exact").aggregate["f1"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/core/evaluator.py`:
```python
"""Run a task's registered metrics over records and package the result."""

from __future__ import annotations

from clineval.core.metric import EvalContext, get_metrics
from clineval.core.schema import EvaluationResult, OntologyAlignment, PredictionRecord


def evaluate(
    task: str,
    records: list[PredictionRecord],
    context: EvalContext,
    *,
    dataset: str,
    model: str,
    timestamp: str,
    alignment: OntologyAlignment,
) -> EvaluationResult:
    """Evaluate ``records`` with every metric registered under ``task``."""
    metrics = get_metrics(task)
    results = [m.compute(records, context) for m in metrics]
    return EvaluationResult(
        task=task,
        dataset=dataset,
        n_documents=len(records),
        model=model,
        timestamp=timestamp,
        metrics=results,
        alignment=alignment,
        records=records,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clineval/core/evaluator.py tests/test_evaluator.py
git commit -m "feat: add evaluator that runs registered metrics into a result"
```

---

### Task 12: Extractor (cached replay + OpenAI-compatible live)

**Files:**
- Create: `clineval/tasks/hpo_extraction/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- Consumes: `adapters.normalize_hpo_ids`, `adapters.parse_llm_output` (Task 4); `PredictionRecord` (Task 2).
- Produces:
  - `class CachedExtractor`: `__init__(self, path: str)`; attr `.model: str`; `extract(self, record) -> list[str]` (by `record.id`).
  - `class OpenAICompatibleExtractor`: `__init__(self, base_url="http://localhost:1234/v1", model="local-model", api_key="not-needed")`; attr `.model`; `extract(self, record) -> list[str]` (by `record.input_text`).
- Cache file format: first line `{"_meta": true, "model": "<name>"}`, then per-record lines `{"id": "...", "system_output": ["HP:..."]}`.

- [ ] **Step 1: Write the failing test**

`tests/test_extractor.py`:
```python
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.extractor import CachedExtractor, OpenAICompatibleExtractor


def test_cached_extractor_replays_and_reads_model(tmp_path):
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        '{"_meta": true, "model": "qwen2.5-7b (LM Studio)"}\n'
        '{"id": "r1", "system_output": ["HP_0001250", "HP:0001250"]}\n',
        encoding="utf-8",
    )
    ext = CachedExtractor(str(cache))
    assert ext.model == "qwen2.5-7b (LM Studio)"
    rec = PredictionRecord(id="r1", input_text="", gold_reference=[])
    assert ext.extract(rec) == ["HP:0001250"]  # normalized + deduped
    assert ext.extract(PredictionRecord(id="missing", input_text="", gold_reference=[])) == []


def test_openai_extractor_parses_response(monkeypatch):
    class FakeMessage:
        content = "Findings: HP_0001250 and HP:0000252."

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs):
            class R:
                choices = [FakeChoice()]
            return R()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    ext = OpenAICompatibleExtractor.__new__(OpenAICompatibleExtractor)
    ext.client = FakeClient()
    ext.model = "local-model"
    rec = PredictionRecord(id="r1", input_text="patient text", gold_reference=[])
    assert ext.extract(rec) == ["HP:0001250", "HP:0000252"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/tasks/hpo_extraction/extractor.py`:
```python
"""System-under-test extractors. Deliberately simple — this is the evaluated
component, not the product.

Default demo path replays cached predictions (zero setup, real numbers). The
``--live`` path calls an OpenAI-compatible endpoint (LM Studio by default).
"""

from __future__ import annotations

import json

from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction import adapters

_EXTRACTION_PROMPT = (
    "You extract Human Phenotype Ontology (HPO) terms from clinical text. "
    "Return every phenotype you find as its HPO ID in the form HP:0000000, "
    "comma-separated. Output only the IDs."
)


class CachedExtractor:
    """Replay committed predictions keyed by record id."""

    def __init__(self, path: str) -> None:
        self.model = "unknown"
        self._by_id: dict[str, list[str]] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("_meta"):
                    self.model = obj.get("model", "unknown")
                    continue
                self._by_id[str(obj["id"])] = adapters.normalize_hpo_ids(
                    obj.get("system_output", [])
                )

    def extract(self, record: PredictionRecord) -> list[str]:
        return list(self._by_id.get(record.id, []))


class OpenAICompatibleExtractor:
    """Call a local OpenAI-compatible endpoint (LM Studio / Ollama / vLLM)."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "local-model",
        api_key: str = "not-needed",
    ) -> None:
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def extract(self, record: PredictionRecord) -> list[str]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {"role": "user", "content": record.input_text},
            ],
        )
        text = response.choices[0].message.content or ""
        return adapters.parse_llm_output(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/extractor.py tests/test_extractor.py
git commit -m "feat: add cached and OpenAI-compatible HPO extractors"
```

---

### Task 13: GSC+ dataset loader

**Files:**
- Create: `clineval/tasks/hpo_extraction/datasets.py`
- Test: `tests/test_datasets_gsc.py`

**Interfaces:**
- Consumes: `DatasetLoader`, `JSONLDatasetLoader` (Task 3).
- Produces: `class GscPlusLoader(DatasetLoader)`; `__init__(self, root: str = "datasets/gsc_plus")`; reads the normalized `gsc_plus.jsonl` produced by the downloader (Task 17); raises a friendly `FileNotFoundError` if absent.

- [ ] **Step 1: Write the failing test**

`tests/test_datasets_gsc.py`:
```python
import pytest

from clineval.tasks.hpo_extraction.datasets import GscPlusLoader


def test_gsc_loader_reads_converted_jsonl(tmp_path):
    root = tmp_path / "gsc_plus"
    root.mkdir()
    (root / "gsc_plus.jsonl").write_text(
        '{"id": "PMID1", "input_text": "seizures", "gold_reference": ["HP:0001250"]}\n',
        encoding="utf-8",
    )
    records = GscPlusLoader(str(root)).load()
    assert records[0].id == "PMID1"
    assert records[0].gold_reference == ["HP:0001250"]


def test_gsc_loader_missing_gives_friendly_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_gsc"):
        GscPlusLoader(str(tmp_path / "absent")).load()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_datasets_gsc.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/tasks/hpo_extraction/datasets.py`:
```python
"""Dataset loaders for Module A.

GSC+ is fetched and converted to our JSONL schema by ``datasets/download_gsc.py``
(kept out of git). This loader reads that converted file. BioCreative VIII Track 3
is a documented fast-follow: add a ``BioCreativeLoader`` here as its own PR.
"""

from __future__ import annotations

from pathlib import Path

from clineval.core.dataset import DatasetLoader, JSONLDatasetLoader
from clineval.core.schema import PredictionRecord


class GscPlusLoader(DatasetLoader):
    """Load GSC+ (BiolarkGSC+) from the converted JSONL produced by the downloader."""

    def __init__(self, root: str = "datasets/gsc_plus") -> None:
        self.path = Path(root) / "gsc_plus.jsonl"

    def load(self) -> list[PredictionRecord]:
        if not self.path.exists():
            raise FileNotFoundError(
                f"GSC+ not found at {self.path}. Fetch it first: "
                "`python datasets/download_gsc.py` (confirm the source license first)."
            )
        return JSONLDatasetLoader(str(self.path)).load()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_datasets_gsc.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/tasks/hpo_extraction/datasets.py tests/test_datasets_gsc.py
git commit -m "feat: add GSC+ dataset loader"
```

---

### Task 14: Regulatory evidence mapping

**Files:**
- Create: `clineval/regulatory/mapping.py`
- Test: `tests/test_regulatory.py`

**Interfaces:**
- Produces: `get_mapping_rows() -> list[dict]` (each: `evidence`, `ai_act`, `ivdr`, `iso15189`); `DISCLAIMER: str`.

- [ ] **Step 1: Write the failing test**

`tests/test_regulatory.py`:
```python
from clineval.regulatory import mapping


def test_mapping_rows_shape_and_iso_2022():
    rows = mapping.get_mapping_rows()
    assert len(rows) == 4
    for row in rows:
        assert set(row) == {"evidence", "ai_act", "ivdr", "iso15189"}
    # ISO clauses use 2022 numbering (7.3.x / Clause 8), not 2012 (5.5.x).
    iso_blob = " ".join(r["iso15189"] for r in rows)
    assert "7.3.2" in iso_blob and "7.3.3" in iso_blob
    assert "5.5" not in iso_blob


def test_disclaimer_present():
    assert "not legal" in mapping.DISCLAIMER.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_regulatory.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`clineval/regulatory/mapping.py`:
```python
"""Static mapping from ClinEval evidence to regulatory clauses (MVP: a table).

Not legal advice. ISO 15189 references use the 2022 edition numbering.
"""

from __future__ import annotations

DISCLAIMER = (
    "This mapping is a general technical/educational reference, not legal or "
    "regulatory-compliance advice. Clauses and timelines change; consult qualified "
    "regulatory/quality professionals against the current official texts."
)

REGULATORY_ROWS: list[dict[str, str]] = [
    {
        "evidence": "Exact P/R/F1",
        "ai_act": "Art 15 (accuracy)",
        "ivdr": "Annex XIII analytical performance",
        "iso15189": "7.3.2 verification of examination methods",
    },
    {
        "evidence": "Semantic F1 / IC-weighted",
        "ai_act": "Art 15 (appropriate accuracy metrics; robustness)",
        "ivdr": "performance evaluation",
        "iso15189": "7.3.3 validation of examination methods",
    },
    {
        "evidence": "Error taxonomy + significance flags",
        "ai_act": "Art 15 (robustness)",
        "ivdr": "performance / risk evidence",
        "iso15189": "7.3.7 ensuring validity of results + 7.5 nonconforming work",
    },
    {
        "evidence": "Ontology alignment / traceability",
        "ai_act": "Art 12 (logging & traceability)",
        "ivdr": "technical documentation",
        "iso15189": "Clause 8 management system (records & documents)",
    },
]


def get_mapping_rows() -> list[dict[str, str]]:
    """Return a copy of the regulatory mapping rows."""
    return [dict(row) for row in REGULATORY_ROWS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_regulatory.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clineval/regulatory/mapping.py tests/test_regulatory.py
git commit -m "feat: add regulatory evidence mapping (AI Act / IVDR / ISO 15189:2022)"
```

---

### Task 15: Markdown report renderer

**Files:**
- Create: `clineval/templates/report.md.j2`
- Create: `clineval/core/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `EvaluationResult`, `MetricResult` (Task 2); `mapping.get_mapping_rows`, `mapping.DISCLAIMER` (Task 14).
- Produces: `render_report(result: EvaluationResult) -> str`.

- [ ] **Step 1: Write the failing test**

`tests/test_report.py`:
```python
from clineval.core.report import render_report
from clineval.core.schema import (
    EvaluationResult,
    MetricResult,
    OntologyAlignment,
    PredictionRecord,
)


def _result():
    tier1 = MetricResult(
        name="tier1_exact",
        aggregate={"precision": 0.5, "recall": 0.5, "f1": 0.5},
        per_document={"r1": {"precision": 0.5, "recall": 0.5, "f1": 0.5}},
    )
    tier2 = MetricResult(
        name="tier2_semantic",
        aggregate={"sem_precision": 0.8, "sem_recall": 0.8, "sem_f1": 0.8,
                   "sem_precision_icw": 0.8, "sem_recall_icw": 0.8, "sem_f1_icw": 0.8,
                   "bma": 0.8},
        per_document={"r1": {"sem_f1": 0.8, "bma": 0.8}},
    )
    tier3 = MetricResult(
        name="tier3_clinical",
        aggregate={"missed": 1.0, "spurious": 1.0, "wrong_granularity": 1.0, "wrong_term": 0.0},
        details={"flags": [{"record": "r1", "type": "missed_high_ic",
                            "hpo_id": "HP:0011682", "ic": 5.1}]},
    )
    align = OntologyAlignment("2025-01-01", "omim", 2, 1, ["HP:0000999"], "policy text")
    return EvaluationResult(
        task="hpo_extraction", dataset="synthetic", n_documents=1, model="cached:qwen",
        timestamp="2026-07-09T00:00:00+00:00", metrics=[tier1, tier2, tier3],
        alignment=align,
        records=[PredictionRecord(id="r1", input_text="", gold_reference=["HP:0011682"],
                                  system_output=["HP:0001629"])],
    )


def test_report_contains_key_sections():
    md = render_report(_result())
    assert "# ClinEval Report" in md
    assert "Regulatory Evidence Mapping" in md
    assert "Ontology Alignment" in md
    assert "ISO 15189:2022" in md
    assert "cached:qwen" in md          # model provenance
    assert "omim" in md                 # IC basis recorded
    # exact-vs-semantic gap highlighted (0.80 - 0.50 = 0.30)
    assert "0.300" in md or "0.30" in md
    assert "missed_high_ic" in md
    assert "not legal" in md.lower()    # disclaimer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template and renderer**

`clineval/templates/report.md.j2`:
```jinja
# ClinEval Report — {{ r.task }}

- **Dataset:** {{ r.dataset }}
- **Documents:** {{ r.n_documents }}
- **Model:** {{ r.model }}
- **HPO version:** {{ r.alignment.hpo_version }}
- **IC basis:** {{ r.alignment.ic_basis }}
- **Generated:** {{ r.timestamp }}

## Overall scores

| Metric | Precision | Recall | F1 |
|---|---|---|---|
| Tier 1 — exact | {{ '%.3f'|format(tier1.aggregate.precision) }} | {{ '%.3f'|format(tier1.aggregate.recall) }} | {{ '%.3f'|format(tier1.aggregate.f1) }} |
| Tier 2 — semantic | {{ '%.3f'|format(tier2.aggregate.sem_precision) }} | {{ '%.3f'|format(tier2.aggregate.sem_recall) }} | {{ '%.3f'|format(tier2.aggregate.sem_f1) }} |
| Tier 2 — semantic (IC-weighted) | {{ '%.3f'|format(tier2.aggregate.sem_precision_icw) }} | {{ '%.3f'|format(tier2.aggregate.sem_recall_icw) }} | {{ '%.3f'|format(tier2.aggregate.sem_f1_icw) }} |

**Set-based BMA:** {{ '%.3f'|format(tier2.aggregate.bma) }}

**Exact vs semantic F1 gap:** exact {{ '%.3f'|format(exact_f1) }} → semantic {{ '%.3f'|format(sem_f1) }} (**+{{ '%.3f'|format(gap) }}**). A positive gap means many "errors" are clinically near-misses (parent/child/sibling terms), not unrelated hallucinations.

## Per-document breakdown

| Doc | Exact P | Exact R | Exact F1 | Semantic F1 | BMA |
|---|---|---|---|---|---|
{% for rec in r.records -%}
| {{ rec.id }} | {{ '%.3f'|format(tier1.per_document[rec.id].precision) }} | {{ '%.3f'|format(tier1.per_document[rec.id].recall) }} | {{ '%.3f'|format(tier1.per_document[rec.id].f1) }} | {{ '%.3f'|format(tier2.per_document[rec.id].sem_f1) }} | {{ '%.3f'|format(tier2.per_document[rec.id].bma) }} |
{% endfor %}

## Error taxonomy

| Category | Count |
|---|---|
| Missed (FN) | {{ tier3.aggregate.missed|int }} |
| Wrong granularity (parent/child) | {{ tier3.aggregate.wrong_granularity|int }} |
| Wrong term (related, not parent/child) | {{ tier3.aggregate.wrong_term|int }} |
| Spurious (unrelated FP) | {{ tier3.aggregate.spurious|int }} |

## Clinical-significance flags

{% if tier3.details.flags -%}
| Record | Type | HPO ID | IC |
|---|---|---|---|
{% for f in tier3.details.flags -%}
| {{ f.record }} | {{ f.type }} | {{ f.hpo_id }} | {{ '%.3f'|format(f.ic) }} |
{% endfor -%}
{% else -%}
None.
{% endif %}

## Ontology Alignment

- **HPO version:** {{ r.alignment.hpo_version }}
- **IC basis:** {{ r.alignment.ic_basis }}
- **alt_ids resolved:** {{ r.alignment.alt_ids_resolved }}
- **Merged/obsolete flagged:** {{ r.alignment.obsolete_flagged }}{% if r.alignment.obsolete_ids %} ({{ r.alignment.obsolete_ids|join(', ') }}){% endif %}
- **Policy:** {{ r.alignment.policy }}

## Regulatory Evidence Mapping

| ClinEval evidence | EU AI Act | IVDR | ISO 15189:2022 |
|---|---|---|---|
{% for row in rows -%}
| {{ row.evidence }} | {{ row.ai_act }} | {{ row.ivdr }} | {{ row.iso15189 }} |
{% endfor %}

---

*{{ disclaimer }}*
```

`clineval/core/report.py`:
```python
"""Render an EvaluationResult to a Markdown report via Jinja2."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from clineval.core.schema import EvaluationResult, MetricResult
from clineval.regulatory import mapping

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _metric(result: EvaluationResult, name: str) -> MetricResult:
    found = result.metric(name)
    if found is None:
        raise ValueError(f"missing metric '{name}' in result")
    return found


def render_report(result: EvaluationResult) -> str:
    """Return the Markdown report for an evaluation result."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.md.j2")
    tier1 = _metric(result, "tier1_exact")
    tier2 = _metric(result, "tier2_semantic")
    tier3 = _metric(result, "tier3_clinical")
    exact_f1 = tier1.aggregate.get("f1", 0.0)
    sem_f1 = tier2.aggregate.get("sem_f1", 0.0)
    return template.render(
        r=result,
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        exact_f1=exact_f1,
        sem_f1=sem_f1,
        gap=sem_f1 - exact_f1,
        rows=mapping.get_mapping_rows(),
        disclaimer=mapping.DISCLAIMER,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_report.py -v`
Expected: PASS. (Ensure the template is included in the wheel — it lives under the `clineval` package so hatchling packages it.)

- [ ] **Step 5: Commit**

```bash
git add clineval/templates/report.md.j2 clineval/core/report.py tests/test_report.py
git commit -m "feat: add Markdown report renderer with regulatory + alignment sections"
```

---

### Task 16: CLI (`clineval run`)

**Files:**
- Create: `clineval/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: all prior components. Wires: load → normalize → extract → normalize → align → evaluate → render → write.
- Produces: Typer app `app` with command `run`. Dataset keywords: `synthetic` (→ `examples/data/synthetic_mini.jsonl`), `gsc` (→ `GscPlusLoader`), else treated as a JSONL path. Extractor: cached by default (`--cache`), `--live` → `OpenAICompatibleExtractor`.

- [ ] **Step 1: Write the failing test (end-to-end, offline, using tiny inline fixtures)**

`tests/test_cli.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: clineval.cli`.

- [ ] **Step 3: Write minimal implementation**

`clineval/cli.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS. (This loads PyHPO, so it is slower.)

- [ ] **Step 5: Commit**

```bash
git add clineval/cli.py tests/test_cli.py
git commit -m "feat: add clineval run CLI (end-to-end pipeline)"
```

---

### Task 17: Committed fixtures + GSC+ downloader

**Files:**
- Create: `examples/data/synthetic_mini.jsonl`
- Create: `examples/data/cached_predictions.jsonl`
- Create: `datasets/download_gsc.py`
- Create: `datasets/README.md`
- Create: `tests/fixtures/gsc_sample/annotations.tsv` and `tests/fixtures/gsc_sample/PMID_1.txt` (format sample for the converter test)
- Test: `tests/test_download_gsc.py`

**Interfaces:**
- Consumes: `adapters.normalize_hpo_id` (Task 4).
- Produces: `download_gsc.convert(raw_dir: str, out_path: str) -> int` (returns record count) and a `download(dest: str) -> None` entry point. The converter is the isolated, testable part; `download()` fetches the archive from a **verified** URL.

- [ ] **Step 1: Write the synthetic gold fixture**

`examples/data/synthetic_mini.jsonl` (10 clearly-synthetic records; real HPO IDs):
```json
{"id": "syn01", "input_text": "The patient presents with a perimembranous ventricular septal defect and mild short stature.", "gold_reference": ["HP:0011682", "HP:0004322"]}
{"id": "syn02", "input_text": "Examination revealed recurrent seizures and microcephaly.", "gold_reference": ["HP:0001250", "HP:0000252"]}
{"id": "syn03", "input_text": "Bilateral hearing impairment noted; intellectual disability present.", "gold_reference": ["HP:0000365", "HP:0001249"]}
{"id": "syn04", "input_text": "Findings include an atrial septal defect and strabismus.", "gold_reference": ["HP:0001631", "HP:0000486"]}
{"id": "syn05", "input_text": "The child has an abnormal facial shape and renal hypoplasia.", "gold_reference": ["HP:0001999", "HP:0000110"]}
{"id": "syn06", "input_text": "A muscular ventricular septal defect was identified on echocardiography.", "gold_reference": ["HP:0011623"]}
{"id": "syn07", "input_text": "Notable for global developmental delay and hypotonia.", "gold_reference": ["HP:0001263", "HP:0001252"]}
{"id": "syn08", "input_text": "Patient with cleft palate and low-set ears.", "gold_reference": ["HP:0000175", "HP:0000369"]}
{"id": "syn09", "input_text": "Presented with tall stature and arachnodactyly.", "gold_reference": ["HP:0000098", "HP:0001166"]}
{"id": "syn10", "input_text": "No abnormal phenotype was detected on examination.", "gold_reference": []}
```

- [ ] **Step 2: Write the cached predictions fixture (deliberately imperfect, to exercise every taxonomy branch)**

`examples/data/cached_predictions.jsonl`:
```json
{"_meta": true, "model": "qwen2.5-7b-instruct (LM Studio, 2026-07)"}
{"id": "syn01", "system_output": ["HP:0001629", "HP:0004322"]}
{"id": "syn02", "system_output": ["HP:0001250", "HP:0000252"]}
{"id": "syn03", "system_output": ["HP:0000365", "HP:0001256"]}
{"id": "syn04", "system_output": ["HP:0001631", "HP:0001250"]}
{"id": "syn05", "system_output": ["HP:0001999"]}
{"id": "syn06", "system_output": ["HP:0011682"]}
{"id": "syn07", "system_output": ["HP:0001263", "HP:0001252"]}
{"id": "syn08", "system_output": ["HP:0000175", "HP_0000369"]}
{"id": "syn09", "system_output": ["HP:0000098", "HP:0001166"]}
{"id": "syn10", "system_output": ["HP:0001250"]}
```

- [ ] **Step 3: Write the GSC+ format sample + failing converter test**

`tests/fixtures/gsc_sample/PMID_1.txt`:
```text
The patient had seizures and microcephaly.
```
`tests/fixtures/gsc_sample/annotations.tsv` (assumed GSC+-style columns: `pmid<TAB>start<TAB>end<TAB>hpo_id<TAB>mention`; **verify against the real corpus in Step 6 and adjust the parser + this sample together if it differs**):
```text
PMID_1	16	24	HP_0001250	seizures
PMID_1	29	41	HP_0000252	microcephaly
```
`tests/test_download_gsc.py`:
```python
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "download_gsc", str(Path("datasets/download_gsc.py"))
)
download_gsc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(download_gsc)


def test_convert_builds_normalized_jsonl(tmp_path):
    out = tmp_path / "gsc_plus.jsonl"
    count = download_gsc.convert("tests/fixtures/gsc_sample", str(out))
    assert count == 1
    line = out.read_text(encoding="utf-8").strip()
    assert '"id": "PMID_1"' in line
    assert "HP:0001250" in line and "HP:0000252" in line  # normalized to colon form
    assert "HP_" not in line
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_download_gsc.py -v`
Expected: FAIL (module/file not found or `convert` undefined).

- [ ] **Step 5: Write `datasets/download_gsc.py` and `datasets/README.md`**

`datasets/download_gsc.py`:
```python
"""Fetch GSC+ (BiolarkGSC+) and convert it to ClinEval's JSONL schema.

Output (git-ignored): datasets/gsc_plus/gsc_plus.jsonl with one record per line:
{"id", "input_text", "gold_reference": ["HP:0000000", ...]}.

The download URL and license MUST be confirmed before use (see datasets/README.md).
The converter is intentionally small and isolated so that, if the real GSC+ layout
differs from the assumed one, only ``convert`` and the test fixture need adjusting.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Verify this against the official GSC+ distribution before running download().
GSC_PLUS_URL = "https://github.com/lasigeBioTM/IHP/raw/master/GSC%2B.zip"
DEFAULT_DEST = "datasets/gsc_plus"


def convert(raw_dir: str, out_path: str) -> int:
    """Convert an extracted GSC+ directory to normalized JSONL. Returns record count.

    Assumes: for each document ``<ID>.txt`` (the abstract) there are annotation
    rows in ``annotations.tsv`` with tab-separated columns
    ``id, start, end, hpo_id, mention``. Adjust here if the real layout differs.
    """
    from clineval.tasks.hpo_extraction.adapters import normalize_hpo_id

    raw = Path(raw_dir)
    gold: dict[str, list[str]] = defaultdict(list)
    ann_file = raw / "annotations.tsv"
    if ann_file.exists():
        for row in ann_file.read_text(encoding="utf-8").splitlines():
            row = row.strip()
            if not row:
                continue
            parts = row.split("\t")
            if len(parts) < 4:
                continue
            doc_id, hpo_raw = parts[0], parts[3]
            nid = normalize_hpo_id(hpo_raw)
            if nid and nid not in gold[doc_id]:
                gold[doc_id].append(nid)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8") as fh:
        for txt in sorted(raw.glob("*.txt")):
            doc_id = txt.stem
            record = {
                "id": doc_id,
                "input_text": txt.read_text(encoding="utf-8").strip(),
                "gold_reference": gold.get(doc_id, []),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def download(dest: str = DEFAULT_DEST) -> None:
    """Download + extract GSC+ into ``dest`` and convert to gsc_plus.jsonl.

    Network fetch is intentionally explicit so licensing can be reviewed first.
    """
    import io
    import urllib.request
    import zipfile

    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading GSC+ from {GSC_PLUS_URL} ...")
    with urllib.request.urlopen(GSC_PLUS_URL) as resp:  # noqa: S310 (reviewed URL)
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest_dir / "raw")
    n = convert(str(dest_dir / "raw"), str(dest_dir / "gsc_plus.jsonl"))
    print(f"Wrote {n} records to {dest_dir / 'gsc_plus.jsonl'}")


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DEST)
```

`datasets/README.md`:
```markdown
# Datasets

ClinEval does **not** commit third-party corpora. Fetch GSC+ with the downloader.

## GSC+ / BiolarkGSC+

228 PubMed abstracts annotated with HPO concepts (Lobo et al., 2017).

```bash
docker compose run --rm clineval python datasets/download_gsc.py   # writes datasets/gsc_plus/gsc_plus.jsonl (git-ignored)
docker compose run --rm clineval uv run clineval run --dataset gsc --report reports/gsc.md
```

**Before running:** confirm the current download source and its **license** permit
your use, and update `GSC_PLUS_URL` / `convert()` in `download_gsc.py` to match the
official distribution's actual layout. The converter's assumed format is documented
in its docstring and mirrored by `tests/fixtures/gsc_sample/`.

## BioCreative VIII Track 3

Documented fast-follow (not in this MVP). Add a `BioCreativeLoader` in
`clineval/tasks/hpo_extraction/datasets.py` as its own PR.
```

- [ ] **Step 6: Run the converter test and verify the offline demo end-to-end**

Run (in the container):
```bash
docker compose run --rm clineval uv run pytest tests/test_download_gsc.py -v
docker compose run --rm clineval uv run clineval run --dataset synthetic --report reports/report.md
```
Expected: converter test PASSES; the CLI writes `reports/report.md`. Open it and confirm: **exact F1 < semantic F1** (positive gap); **all four taxonomy categories are exercised across the corpus** (a near-miss parent → wrong-granularity, a sibling → wrong-term, an unrelated FP → spurious, an unmatched gold → missed); at least one clinical-significance flag; and the Ontology Alignment + Regulatory Evidence Mapping sections render. (Exact per-document category assignments depend on the live PyHPO IC values and the default `relatedness_tau=0.3`, so verify the *category totals are non-zero* rather than pinning each document.) **Also confirm the real GSC+ source URL + license before relying on `download()`** (the license-confirmation gate from the spec).

- [ ] **Step 7: Commit**

```bash
git add examples/data/synthetic_mini.jsonl examples/data/cached_predictions.jsonl datasets/download_gsc.py datasets/README.md tests/fixtures/gsc_sample tests/test_download_gsc.py
git commit -m "feat: add synthetic fixture, cached predictions, and GSC+ downloader"
```

---

### Task 18: Notebook demo, README polish, full green run

**Files:**
- Create: `examples/hpo_extraction_demo.ipynb`
- Modify: `README.md` (expand)
- Test: full suite

**Interfaces:**
- Consumes: the whole pipeline. No new public API.

- [ ] **Step 1: Write the notebook demo**

Create `examples/hpo_extraction_demo.ipynb` with these cells (a minimal, runnable notebook mirroring the CLI):
- Markdown intro cell explaining ClinEval + Module A.
- Code cell:
```python
from clineval.core.dataset import JSONLDatasetLoader
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
from clineval.core.ontology.hpo import Ontology
from clineval.core.report import render_report
from clineval.tasks.hpo_extraction import adapters
from clineval.tasks.hpo_extraction.extractor import CachedExtractor
import clineval.tasks.hpo_extraction  # registers metrics

records = JSONLDatasetLoader("data/synthetic_mini.jsonl").load()
for r in records:
    adapters.normalize_record(r)

extractor = CachedExtractor("data/cached_predictions.jsonl")
for r in records:
    r.system_output = extractor.extract(r)
    adapters.normalize_record(r)

ontology = Ontology()
records, alignment = adapters.align_records(records, ontology)
result = evaluate(
    "hpo_extraction", records, EvalContext(ontology=ontology),
    dataset="synthetic", model=f"cached:{extractor.model}",
    timestamp="2026-07-09T00:00:00+00:00", alignment=alignment,
)
print("exact F1:", result.metric("tier1_exact").aggregate["f1"])
print("semantic F1:", result.metric("tier2_semantic").aggregate["sem_f1"])
```
- Markdown cell + code cell rendering the report:
```python
from IPython.display import Markdown
Markdown(render_report(result))
```

- [ ] **Step 2: Expand `README.md`**

Replace the stub with a portfolio-grade README covering: what ClinEval is (evaluator, not model-builder), the three metric tiers, the exact-vs-semantic gap as the headline insight, the regulatory-evidence mapping, **Docker install/run** (`docker compose build`; `docker compose run --rm clineval uv run clineval run ...`; `--live --base-url http://host.docker.internal:1234/v1` for host LM Studio), the architecture (generic core + pluggable task; Module B seam), datasets (GSC+ downloader; synthetic fixture), on-prem/public-data/no-PHI stance, and the disclaimer. Keep it concise and skimmable.

- [ ] **Step 3: Run the full suite (green gate, in the container)**

Run:
```bash
docker compose run --rm clineval uv run pytest -v
docker compose run --rm clineval uv run ruff check .
```
Expected: **all tests pass**; ruff clean (fix any lint). Confirm `reports/report.md` from Task 17 still generates.

- [ ] **Step 4: Verify the notebook executes**

Run:
```bash
docker compose run --rm clineval uv run --with jupyter jupyter nbconvert --to notebook --execute examples/hpo_extraction_demo.ipynb --output executed_demo.ipynb
```
Expected: executes without error (then delete `examples/executed_demo.ipynb`). If jupyter isn't desired, manually spot-check the cells against the CLI output instead.

- [ ] **Step 5: Commit**

```bash
git add examples/hpo_extraction_demo.ipynb README.md
git commit -m "docs: add notebook demo and portfolio README"
```

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- §1 scope/DoD → Tasks 1–18; end-to-end DoD verified in Task 17 Step 6.
- §2 architecture / registry / data flow → Tasks 2 (schema), 5 (registry), 11 (evaluator), 16 (CLI wiring); Module B placeholder in Task 1.
- §3 ontology layer (load/version/IC/similarity) → Task 7; §3.1 ID normalization → Task 4 (+ applied in 16/17); §3.2 version alignment → Task 10.
- §4 metrics Tier 1/2/3 → Tasks 6/8/9 (semantic best-match Lin + IC-weighted + BMA; taxonomy + flags).
- §5 extractor (cached default + live; provenance) → Task 12 (+ cache file in Task 17, model label in Task 16).
- §6 datasets (JSONL, GscPlusLoader, downloader, fixtures; BC8 deferred) → Tasks 3, 13, 17.
- §7 report sections → Task 15 (template covers all 8 sections incl. IC basis + provenance + gap).
- §8 regulatory mapping (ISO 15189:2022) → Task 14 (test asserts 7.3.x, no 5.5).
- §9 CLI → Task 16. §10 testing → every task is TDD; full green gate in Task 18. §11 tooling/MIT/**Docker + latest Python (3.14)** → Task 1 (Dockerfile/compose/.dockerignore, `requires-python>=3.14` with a 3.13 fallback note). §12 risks → surfaced in Tasks 1 (Docker daemon, 3.14 dep support), 7 (PyHPO), 17 (GSC+ license/format).

**Execution model:** all `uv`/`pytest`/`python`/`clineval` commands run inside the container (`docker compose run --rm clineval …`) per the "Execution Environment" section; git commits run on the host. No host Python/uv is installed.

**2. Placeholder scan:** No "TBD/implement later" in code. The single deliberate placeholder is `tasks/report_generation` (spec-mandated Module B stub). `download_gsc.py`'s URL/format carry explicit "verify before use" notes (a runtime license/format gate from the spec), not code placeholders — the converter is fully implemented and tested against a committed sample.

**3. Type consistency:** Metric names (`tier1_exact`, `tier2_semantic`, `tier3_clinical`) are identical across metrics, evaluator test, report renderer, and CLI. `Ontology` methods (`resolve`, `ic`, `similarity`, `bma`, `related`, `version`, `ic_basis`) are used consistently by metrics (8/9), alignment (10), and CLI (16). `align_records` returns `(records, OntologyAlignment)` consumed by the CLI and rendered by the template. `TermResolution.status ∈ {primary, alt_id, obsolete}` matches `align_records`' branches. Extractor `.model` attribute feeds the CLI's `cached:<model>` label, asserted in the report test.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-clineval-module-a-hpo-extraction.md`.
