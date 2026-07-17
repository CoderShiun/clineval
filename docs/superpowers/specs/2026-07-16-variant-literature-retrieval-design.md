# ClinEval — Variant Literature Retrieval (Phase 1) — Design Spec

- **Status:** Draft (2026-07-16), pending approval → implementation plan
- **Scope:** Phase 1 of the variant→literature evidence pipeline plus the ClinEval
  retrieval-evaluation task that scores it. Stages 1–2 (normalize + retrieve) and the
  retrieval eval only. **No extraction (stage 3), ranking (stage 4), review (stage 5), or UI.**
- **Positioning:** ClinEval remains an **evaluator / validation rig**. This work adds (a) a
  real, external, multi-stage **retrieval pipeline** as a new *system under test*, and (b) a
  new ClinEval **task** (`variant_retrieval`) that measures it against a known-answer truth
  set. The retrieval-eval result is the validation artifact for the business question
  *"can we drop HGMD?"*.

> **Disclaimer:** General technical/educational design reference, **not** legal or
> regulatory-compliance advice. Dataset/database licences, external-API contracts, and
> regulatory clauses change. Confirm the HGMD licence's data-retention terms before relying
> on any HGMD-derived benchmark, confirm each external API's current terms/endpoints before
> use, and consult qualified regulatory/quality professionals against current official texts.

---

## 0. Two hard rules that override convenience everywhere

1. **No patient data touches this pipeline.** It operates on variant coordinates only (public
   genomic information). The Phase-1 truth sets (RYR1/Wermers; optionally an HGMD-derived
   panel gold) are public or de-identified variant→PMID mappings — never patient-linked.
2. **Nothing is fabricated.** Not evidence labels, not classifications, and not an
   API-response field that has not been verified against a live response. No opaque,
   HGMD-style single "pathogenic/DM" label is ever emitted. (Phase 1 emits no evidence
   labels at all — it retrieves and scores. Decomposition/citation is a Phase-2/3 concern,
   pre-committed here so nothing built now blocks it.)

---

## 1. Scope & Definition of Done

**In scope (this build):**
- **The pipeline (system under test), stages 1–2** under `clineval/pipeline/`:
  - Stage 1 `normalize_and_expand(variant)` → synonym set + `resolved` flag + xrefs + provenance.
  - Stage 2 `retrieve(forms)` → deduplicated PMID union + per-paper metadata + matched-form provenance.
  - Thin API clients (VariantValidator, myvariant.info, LitVar2, NCBI E-utilities; PubTator3 optional),
    each isolating one external API's quirks.
  - Cross-cutting: request caching (SQLite), throttling + retry-with-backoff, NCBI API key.
- **The ClinEval task** `variant_retrieval` under `clineval/tasks/variant_retrieval/`:
  - Retrieval metric (recall / precision / F1 + yield/novel), reusing ClinEval's promoted set-P/R/F1.
  - A `PipelineRetriever` / `CachedRetriever` / `DatasetRetriever` system-under-test adapter
    (mirroring the existing extractor pattern).
  - Dataset loaders: `RYR1BenchmarkLoader` (public) + a generic HGMD-panel gold loader.
  - Task-specific Markdown report renderer + template.
- **Minimal, additive core changes** to remove two HPO-specific couplings (see §3).
- **Truth sets:** the RYR1/Wermers benchmark (primary) and the schema + loader for an
  HGMD-derived panel gold (drop-in second dataset).
- **Deliverable:** one command runs the retrieval eval across the RYR1 truth set and writes a
  Markdown report with per-variant + aggregate recall/precision/F1, a missed-evidence
  breakdown, an unresolved-variant list, and a comparison row against the HGMD/Wermers baseline.
- pytest suite, offline & deterministic (mocks against saved API fixtures; committed cached
  retrieval outputs), under the repo's existing 98% coverage gate.

**Out of scope (YAGNI — do NOT build now):**
- Stage 3 (match-gate + extraction), stage 4 (rank & summarize + ClinVar signal presentation),
  stage 5 (ScS review + capture).
- Any UI / dashboard / web app.
- Full-text acquisition (PMC OA or paywalled). Phase 1 measures the abstract-only recall ceiling;
  it does not try to raise it.
- Self-hosted VariantValidator (Docker) — deferred to pre-production; hosted REST for Phase 1.
- Audit snapshotting / full versioned persistence (Phase 3). Phase 1 persistence = request
  cache + committed cached outputs only.
- AutoPM3 evaluation (Phase 2).
- Emitting any evidence summary or classification label.

**Definition of Done:** see §14 checklist (mirrors the brief's §9).

---

## 2. The two systems, one repo

The brief's core mental model is *two distinct systems sharing one repository*. The tree makes
that split visible:

```
clineval/
├── clineval/
│   ├── core/                         # UNCHANGED except two small additive edits (§3)
│   │   ├── schema.py                 # + optional alignment, + provenance field
│   │   ├── metric.py                 # + promoted set_prf() (reused by both tasks)
│   │   ├── dataset.py                # (unchanged)
│   │   ├── evaluator.py              # alignment arg becomes optional (§3)
│   │   ├── report.py                 # (unchanged — stays HPO-specific)
│   │   └── ontology/                 # (unchanged — HPO-only, untouched)
│   │
│   ├── pipeline/                     # ★ THE PIPELINE — system under test (NEW)
│   │   ├── models.py                 # VariantForms, RetrievalResult, PaperRef, PipelineProvenance
│   │   ├── synonyms.py               # recall-critical LOCAL logic (protein/genomic variforms)
│   │   ├── normalize.py              # Stage 1: normalize_and_expand(...)
│   │   ├── retrieve.py               # Stage 2: retrieve(...)
│   │   ├── cache.py                  # SQLite request cache (deterministic replay)
│   │   ├── throttle.py               # rate limiter + retry-with-backoff
│   │   └── clients/                  # one module per external API (isolates its quirks)
│   │       ├── http.py               # shared cached+throttled GET
│   │       ├── variantvalidator.py
│   │       ├── myvariant_client.py
│   │       ├── litvar.py
│   │       ├── pubtator.py           # optional in Phase 1
│   │       └── eutils.py             # E-utilities metadata (+ API key)
│   │
│   ├── tasks/
│   │   ├── hpo_extraction/           # (unchanged; Tier1 refactored to call core set_prf)
│   │   └── variant_retrieval/        # ★ THE HARNESS ADAPTER — new ClinEval task (NEW)
│   │       ├── __init__.py           # imports metrics (registers on import)
│   │       ├── metrics.py            # RetrievalMetric (recall/precision/F1 + yield/novel)
│   │       ├── retriever.py          # PipelineRetriever / CachedRetriever / DatasetRetriever
│   │       ├── datasets.py           # RYR1BenchmarkLoader + HgmdGoldLoader
│   │       └── report.py             # render_retrieval_report(result) -> Markdown
│   │
│   ├── regulatory/
│   │   └── mapping.py                # + RETRIEVAL_ROWS + get_retrieval_mapping_rows()
│   ├── templates/
│   │   ├── report.md.j2              # (unchanged)
│   │   └── retrieval_report.md.j2    # NEW
│   └── cli.py                        # + `retrieval-eval` subcommand (run command untouched)
│
├── datasets/
│   ├── download_ryr1.py             # build RYR1 gold JSONL (git-ignored output)
│   └── README.md                    # + RYR1 + HGMD-gold sections
├── examples/data/
│   ├── ryr1_gold.jsonl              # committed: RYR1 variant→gold PMIDs (public IDs)
│   └── cached_retrieval.jsonl       # committed: cached pipeline outputs (offline eval)
└── tests/
    ├── fixtures/api_samples/        # saved live responses from the Task 0 spike
    └── test_*.py                    # new tests (offline, deterministic)
```

**Why a top-level `pipeline/` and not inside the task folder** (as `hpo_extraction/extractor.py`
is): the pipeline is a real, growing subsystem (stages 1→5) and the *product*, whereas the task
folder is the *harness that scores it*. Keeping them separate makes the product/harness split
and the regulatory seam (stages 1–4 vs stage 5) legible, and lets the pipeline be imported and
used without pulling in ClinEval's eval machinery.

**Data flow (Phase 1):**
`RYR1BenchmarkLoader → records (gold PMIDs) → Retriever fills system_output (retrieved PMIDs)
via the pipeline → Evaluator runs the variant_retrieval metric → EvaluationResult →
render_retrieval_report → Markdown`.

The retriever *is* the pipeline seen through ClinEval's `Extractor`-shaped hole: `extract(record)`
→ run stages 1–2 on the record's variant → return retrieved PMIDs into `system_output`.

---

## 3. Core changes — minimal, additive, regression-safe

Two HPO-specific couplings block a second task from reusing the core cleanly. Both fixes are
additive (existing HPO path and its tests keep passing under the 98% coverage gate).

**3.1 `EvaluationResult.alignment` is required and HPO-specific.**
`OntologyAlignment` models HPO version alignment; a retrieval task has no ontology. Fix:
- `core/schema.py`: `alignment: OntologyAlignment | None = None` (was required).
- `core/schema.py`: add `provenance: dict[str, Any] = field(default_factory=dict)` to
  `EvaluationResult` — a task-agnostic slot for run provenance (tool versions, cache stats).
  This is the retrieval-side home for the IVDR "what did the tools show, at which versions"
  record, analogous to what `OntologyAlignment` captures for HPO.
- `core/evaluator.py`: `evaluate(..., alignment: OntologyAlignment | None = None,
  provenance: dict | None = None)`. HPO callers pass `alignment=`; retrieval callers pass
  `provenance=`.

**3.2 Set-based P/R/F1 must be *reused*, not copied.**
`_exact_prf` (private, in `hpo_extraction/metrics.py`) is exactly the retrieval metric. Per the
brief's "do not reimplement metrics ClinEval already provides":
- Promote it to `core/metric.py` as `set_prf(gold: list[str], pred: list[str]) -> dict[str,float]`
  (keys `precision`, `recall`, `f1`), preserving the documented empty-set convention verbatim.
- Refactor `Tier1ExactMetric` to call `core.metric.set_prf` (behaviour identical; existing
  Tier-1 tests must stay green).
- `RetrievalMetric` calls the same `set_prf`.

**No change to `core/report.py`.** It stays HPO-specific (it looks up `tier1_exact` /
`tier2_semantic` / `tier3_clinical`). The retrieval task ships its own renderer
(`tasks/variant_retrieval/report.py`) — this is already the repo's stated pattern (each task
configures the report layer with its own template + lookups; the report layer is not an
unmodified-reuse seam).

---

## 4. Stage 1 — Normalize & expand IDs (`pipeline/normalize.py`, `pipeline/synonyms.py`)

**Purpose.** Turn one canonical variant into *every string form a paper might use to name it*.
**Half an API call, half local logic** — the API gives biology; local logic generates the naming
variations that cause missed papers.

**Input.** Canonical HGVS with transcript (e.g. `NM_000540.3:c.1840C>T`); build (default `GRCh38`).

**Output** (`VariantForms` dataclass):
```python
VariantForms(
    input="NM_000540.3:c.1840C>T",
    forms=[...],            # sorted, deduped synonym set (c., p. variants, g., VCF, rsID)
    resolved=True,          # False if protein consequence couldn't be derived
    xrefs={"rsid": "...", "clinvar": {...}, "gnomad": {...}},   # reused later (stage 4)
    gene="RYR1",
    notes=[...],            # human-readable flags (validation warnings, "protein-only", etc.)
    provenance=PipelineProvenance(vv_version="4.0.1...", vvdb_version="vvdb_2025_3", ...),
)
```

### 4.1 VariantValidator contract — VERIFIED against a live response (2026-07-16)

Live call: `GET https://rest.variantvalidator.org/VariantValidator/variantvalidator/GRCh38/NM_000540.3:c.1840C>T/all`
(`Content-Type: application/json`). Confirmed shape for the brief's example variant:

- **Top level:** one key per variant hit (the HGVS string, e.g. `"NM_000540.3:c.1840C>T"`), plus
  `"flag"` (string, e.g. `"gene_variant"`) and `"metadata"` (dict). Iterate items; a hit is a
  `dict` containing `"hgvs_transcript_variant"` (this correctly skips `flag`/`metadata`).
- **Per hit — confirmed keys:**
  - `hgvs_transcript_variant` → `"NM_000540.3:c.1840C>T"` (c. form).
  - `hgvs_predicted_protein_consequence` → `{tlr, slr, lrg_tlr, lrg_slr}` where
    `tlr = "NP_000531.2:p.(Arg614Cys)"`, `slr = "NP_000531.2:p.(R614C)"`.
    **⚠ These are accession-prefixed and parenthesized** — see §4.2.
  - `primary_assembly_loci` → `{grch37, grch38, hg19, hg38}`, each
    `{hgvs_genomic_description: "NC_000019.10:g.38457545C>T", vcf: {chr, pos, ref, alt}}`.
    (grch37≡hg19, grch38≡hg38 → dedup via the set.)
  - `gene_symbol` → `"RYR1"`; `validation_warnings` → `[]` when clean.
- **`metadata`** → `{variantvalidator_version, variantvalidator_hgvs_version, vvdb_version,
  vvseqrepo_db, vvta_version}`. **Capture as provenance** (the retrieval analog of the pinned
  HPO/pyhpo versions). Example: `vvdb_version: "vvdb_2025_3"`.
- **rsID is NOT in the VV response** — it comes from myvariant (§4.3).

The brief's reference skeleton keys (`tlr`/`slr`, `primary_assembly_loci.*.hgvs_genomic_description`)
are therefore **correct**; the corrections are the prefix-stripping/variform generation (§4.2)
and capturing `metadata` for provenance.

### 4.2 Synonym generation — the recall-critical local logic (`synonyms.py`)

VV yields `NP_000531.2:p.(Arg614Cys)`; papers write `p.Arg614Cys`, `Arg614Cys`, `R614C`,
`p.R614C`, `p.(R614C)`. `synonyms.py` is pure (no network) and generates, from the VV protein
`tlr`/`slr`:
- three-letter and single-letter forms (`p.Arg614Cys` ↔ `p.R614C`), via a fixed AA 3↔1 table;
- with and without the `p.` prefix; with and without parentheses;
- with the accession stripped (bare) **and** kept (prefixed).

From `hgvs_transcript_variant` it keeps the full `c.` form; genomic `g.` and a `chr-pos-ref-alt`
VCF-style string come from `primary_assembly_loci`. (Legacy/non-MANE transcript numbering is a
known recall gap — VV's `/all` returns the submitted transcript here; multi-transcript expansion
is noted as a future lever, not built in Phase 1.)

### 4.3 myvariant.info (`clients/myvariant_client.py`)

Confirmed client methods (per the brief, and myvariant is reachable — `/v1/metadata` → 200):
`getvariant(_id, fields=[...])`, `querymany(...)`, `set_caching()`. One `getvariant` backfills
`dbsnp.rsid` (→ add rsID to `forms`) and pulls `clinvar` + `gnomad_genome` (→ `xrefs`, reused in
stage 4 later). Failures are non-fatal: append a note, continue.

### 4.4 The trap — flag, do not drop

If no `p.`-form resolves (splice/intronic like `c.####+#G>A`, indels, protein-only variants),
set `resolved=False`, append a note ("no protein consequence — route to manual, keep in set"),
and **keep the variant in the set** with whatever forms it has (at minimum the input `c.` and
any genomic form). Silently dropping unnormalizable variants inflates recall and loses the hard,
clinically interesting cases. RYR1 has several — the tests assert they are flagged, not dropped.

---

## 5. Stage 2 — Retrieve literature (`pipeline/retrieve.py`)

**Purpose.** Turn the synonym set into a candidate PMID set, maximizing recall.

**Input.** `VariantForms` (plus, optionally, a LitVar canonical variant ID).

**Process.**
1. Query **LitVar2** for each form (or for the resolved LitVar variant ID) → collect PMIDs, and
   record which `matched_form` produced each PMID (recall debugging + audit trail).
2. Optionally query **PubTator3** for entity annotations (Phase-1 optional; behind a flag).
3. Deduplicate PMIDs (union).
4. Attach per-PMID metadata (title, journal, year) via **NCBI E-utilities** `esummary`
   (batched, with API key + throttle).

**Output** (`RetrievalResult` dataclass):
```python
RetrievalResult(
    variant="NM_000540.3:c.1840C>T",
    pmids=["...", "..."],
    papers=[PaperRef(pmid, title, journal, year, matched_form), ...],
    provenance=PipelineProvenance(...),   # tool versions + which endpoints/params were hit
)
```

**Recall ceiling (documented, expected).** LitVar2/PubTator3 index title + abstract + PMC
open-access full text only. Variants named only in paywalled full text or supplementary material
are missed. This is the known gap vs HGMD and *measuring its size is the point of the eval* —
it is not a bug and must not be "fixed" by silently padding results.

**Endpoint paths are TO-VERIFY (Task 0).** LitVar2 and PubTator3 NCBI endpoints have moved; a
naive guess 404'd during design probing. The Task 0 spike confirms the current paths from the
live API and saves fixtures; no unverified path is hardcoded as truth.

---

## 6. Cross-cutting: clients, caching, throttling (`pipeline/clients/`, `cache.py`, `throttle.py`)

- **`clients/http.py`** — a single cached + throttled `get_json(url, params, ...)` all clients
  share. Cache-first; on miss, throttle → request → retry-with-backoff on 429/5xx → store.
- **`cache.py`** — `RequestCache(db_path)` over `sqlite3` (stdlib). Key = stable hash of
  `(base_url, path, sorted params)`. Value = response JSON + status + fetched-at timestamp.
  Git-ignored. Makes **live** reruns cheap and deterministic (the regression-gate requirement).
- **`throttle.py`** — token-bucket limiter (NCBI: 3 req/s without key, ~10 with key) + exponential
  backoff. NCBI **API key** read from env (`NCBI_API_KEY`); absent → lower rate + a logged warning
  (non-fatal).
- **Two cache layers, distinct roles:**
  1. *Request cache (SQLite, git-ignored)* — accelerates/《determinizes》 live runs.
  2. *Cached retrieval outputs (`examples/data/cached_retrieval.jsonl`, committed)* — per-variant
     pipeline output replayed by `CachedRetriever`, so the **eval and the whole test suite run
     fully offline** (mirrors `examples/data/cached_predictions.jsonl` for HPO). This is what
     makes the retrieval eval a deterministic CI regression gate.

All failures are **logged, not fatal** (brief §9): a variant whose retrieval partially fails is
recorded with a note and whatever it retrieved, never dropped.

---

## 7. Metrics (`tasks/variant_retrieval/metrics.py`)

One metric, `RetrievalMetric` (`name = "retrieval_prf"`, registered under `"variant_retrieval"`),
**document-level = variant-level, macro-averaged** across variants — the "document" is the variant
(`record.id = variant_id`, `gold_reference = should_find_pmids`, `system_output = retrieved PMIDs`).

Per variant (via the promoted `core.metric.set_prf`, plus counts):
`precision, recall, f1, gold_n, retrieved_n, found_n (TP), missed_n (FN), extra_n (FP)`.

Aggregate: macro-averaged `precision/recall/f1`, micro totals (pooled TP/FP/FN), and `mean_yield`
(mean retrieved_n). `details` carries, per variant, the **missed PMIDs** (the clinically important
FNs) and the **unresolved-variant flags** (from stage 1).

**Recall is the headline; precision is reported with a caveat.** With no ranking in Phase 1
(stage 4 is Phase 3) and a gold set of *primary references only*, a retriever that correctly
returns a true-but-non-"primary" paper is charged a false positive — so raw set-precision
structurally understates a good retriever. The report leads with **recall** (did we miss known
evidence — the real "can we drop HGMD?" question), shows **yield** and **novel/extra counts**
alongside, and labels precision as context, not a verdict. This mirrors how Wermers reported it.

Empty-set convention: identical to HPO's `set_prf` (both-empty → 1.0). Benchmark variants always
have ≥1 gold PMID, so the degenerate case does not arise in practice but is handled for safety.

---

## 8. Truth sets & dataset schema

**Per-variant record (JSONL, ClinEval `PredictionRecord`-shaped):**
```json
{
  "id": "NM_000540.3:c.1840C>T",
  "input_text": "NM_000540.3:c.1840C>T",
  "gold_reference": ["12345678", "23456789"],
  "metadata": {"gene": "RYR1", "source": "wermers_2024_ryr1"}
}
```
(`id`/`input_text` = canonical HGVS; `gold_reference` = known gold PMIDs; `system_output`
filled by the retriever at run time. Phase-2+ adds `per_paper_gold_labels`, `decisive_set` to
`metadata` — additive.)

**Primary truth — HGMD-derived gold, built from the lab's local HGMD dump**
(`datasets/build_hgmd_gold.py` → git-ignored `datasets/hgmd_gold/*.jsonl`, loaded by
`HgmdGoldLoader` or by path). The lab has a full local HGMD Postgres (schema confirmed
2026-07-16), so the per-variant answer key is extracted directly: per variant (`acc_num`),
gold PMIDs = `allmut.pmid` ∪ split(`allmut.pmidall`, `|`) ∪ `extrarefs.pmid`; canonical id =
`allmut.refseq || ':c.' || allmut.hgvs` (refseq is version-qualified; `hgvs` carries no `c.`
prefix). Filter by gene (`= ANY(:panel)`) and tag (default `DM, DM?`). **The same query yields
RYR1 (the pilot) and the full panel** — only the gene filter changes. This retires the earlier
"does Wermers publish per-variant PMIDs?" risk entirely.

**Frozen snapshot, licence-independent by design.** The gold is a *snapshot* of a specific HGMD
release (stamp `--hgmd-release`; a `*.meta.json` sidecar records it) — deliberately fixed so
scores stay comparable over time (a benchmark that moved each HGMD season could not be a
regression gate). The **pipeline never calls HGMD**, so licence expiry has zero effect on
production. Retention of the snapshot after the licence lapses is a **licence-terms question for
quality/legal**; if retention is disallowed, the benchmark migrates to ClinVar + the ScS-review
flywheel (drop-in datasets) with no code change. The HGMD `tag` is stored in gold metadata for
**internal stratification only** and is never emitted as an authoritative label.

**Cross-check truth — RYR1 / Wermers et al. 2024** (optional). The published head-to-head
(HGMD Pro / Mastermind / ClinVar / LitVar2 on 50 RYR1 variants; ~194 / ~401 / ~372 papers
respectively — vendor-published, read critically) is now only an *aggregate sanity check*: does
the free stack land in the same ballpark on RYR1? No dependency on its supplement.

**Committed demo fixture** — `examples/data/ryr1_gold.jsonl` is a **small synthetic** RYR1-shaped
gold (public/illustrative PMIDs, `source: "synthetic_demo"`) that powers offline tests and the
zero-setup demo. It is **not** the HGMD gold (which is never committed). This mirrors GSC+:
downloader/builder output is git-ignored; a synthetic fixture is committed.

**Sequencing:** build the HGMD gold now while licensed (RYR1 + panel in one run); validate and
iterate the pipeline on RYR1 (small, inspectable, Wermers-comparable); then run the identical
eval on the panel gold — that run is the real "can we drop HGMD?" answer.

---

## 9. Report (`tasks/variant_retrieval/report.py`, `templates/retrieval_report.md.j2`)

Jinja2 → Markdown. Sections:
1. **Run metadata** — dataset, N variants, retriever mode (live pipeline / cached / dataset),
   VariantValidator version + `vvdb_version`, cache hit-rate, NCBI-key present?, timestamp (injected).
2. **Aggregate scores** — macro recall/precision/F1, micro totals, mean yield — **recall highlighted**.
3. **Per-variant table** — variant, gene, gold_n, retrieved_n, found, missed, recall, precision.
4. **Missed-evidence detail** — per variant, the FN gold PMIDs (the clinically important misses).
5. **Unresolved variants** — those flagged `resolved=False` (proves "flag, don't drop").
6. **HGMD/Wermers baseline comparison** — a static reference row next to our free-stack numbers.
7. **Regulatory Evidence Mapping** — retrieval subset (§10).
8. **Disclaimer.**

---

## 10. Regulatory mapping additions (`regulatory/mapping.py`)

Additive `RETRIEVAL_ROWS` + `get_retrieval_mapping_rows()` (HPO `REGULATORY_ROWS` untouched),
carrying the existing `DISCLAIMER`. Draft rows (ISO 15189:2022 numbering):

| ClinEval evidence | EU AI Act | IVDR | ISO 15189:2022 |
|---|---|---|---|
| Retrieval recall vs known references | Art 15 (accuracy) | Annex XIII analytical performance / performance evaluation | 7.3.3 validation of examination methods |
| Yield / precision context | Art 15 (appropriate accuracy metrics) | performance evaluation | 7.3.3 validation |
| Evidence snapshot / tool-version provenance | Art 12 (logging & traceability) | technical documentation | Clause 8 (control of records) |
| Unresolved-variant flagging (no silent drop) | Art 15 (robustness) | risk / performance evidence | 7.3.7 ensuring validity of results |

---

## 11. CLI (`cli.py`)

New Typer subcommand, leaving `run` (HPO) untouched:
```
clineval retrieval-eval \
  --dataset <ryr1|path.jsonl> \
  --report reports/retrieval.md \
  [--source cached|live] \
  [--cache examples/data/cached_retrieval.jsonl] \
  [--request-cache .cache/requests.sqlite] \
  [--genome-build GRCh38] \
  [--pubtator]                # optional stage-2 augmentation
```
Default `--source cached` (offline, real numbers, zero setup — mirrors HPO's cached default).
`--source live` runs the real pipeline (needs network + `NCBI_API_KEY`) and can refresh the cache.

---

## 12. Testing (TDD, pytest, offline & deterministic)

- **Task 0 spike** saves one live response per API to `tests/fixtures/api_samples/`. All client
  unit tests **mock the HTTP layer** and assert parsing against those fixtures — no live calls in
  the suite.
- Coverage: `synonyms` (3↔1 AA, prefix/paren variants); stage-1 normalize (fixture-mocked VV +
  myvariant; **hard-case flag-not-drop** assertions); stage-2 retrieve (fixture-mocked LitVar +
  esummary; dedup; matched-form provenance); `cache` (hit/miss/round-trip); `throttle`
  (backoff/limit, time injected); `set_prf` promotion (identical to old `_exact_prf`); Tier-1
  still green after refactor; `RetrievalMetric` (recall/precision/F1 + counts + missed detail);
  loaders; report rendering (expected sections from a known `EvaluationResult`); retrieval
  regulatory table; CLI smoke (`retrieval-eval --dataset ryr1 --source cached` writes a report).
- Live paths (`--source live`, Task 0) are **not** in the offline suite; an opt-in marker guards
  any live integration test.
- Everything runs in Docker (`docker compose run --rm clineval uv run pytest ...`) under the
  existing `--cov-fail-under=98` gate.

---

## 13. Tooling & conventions (inherited from the repo)

- **Everything runs in Docker / docker compose. Nothing on the host.** Python 3.14 base, uv,
  `>=` floors (no upper pins), ruff (line-length 100). All English.
- **New runtime deps (floors, no upper pins):** `myvariant`, `biopython` (for `Bio.Entrez`;
  or direct E-utilities via the existing HTTP client — decided in the plan), `pandas` (per the
  brief's dependency list, for the results table). `requests`/`httpx` for HTTP. `sqlite3` is stdlib.
- **PUBLIC data only. No PHI.** Permissive licences only. HGMD-derived gold is git-ignored and
  never committed. MIT `LICENSE` unchanged.
- Docs/specs/plans in `docs/superpowers/`. `reports/`, `.cache/`, `datasets/ryr1_benchmark/`,
  `datasets/hgmd_gold/` git-ignored.

---

## 14. Definition of Done (Phase 1) & risks to verify

**Done when:**
- [ ] `normalize_and_expand(variant)` returns a verified synonym set + `resolved` flag for the
      RYR1 truth variants and **flags (does not drop)** the hard cases (splice/intronic/indel/protein-only).
- [ ] VariantValidator response keys confirmed against ≥1 live response (**done 2026-07-16**, §4.1)
      and captured as a fixture.
- [ ] `retrieve(forms)` returns a deduplicated PMID union with per-paper metadata + matched-form provenance.
- [ ] `clineval retrieval-eval --dataset ryr1` outputs per-variant + aggregate recall/precision/F1
      via ClinEval's promoted metric layer, plus missed-evidence + unresolved-variant sections.
- [ ] A results table compares free-stack recall/precision to the HGMD/Wermers baseline.
- [ ] All external calls cached; throttled with an NCBI API key; failures logged, not fatal.
- [ ] No patient data; no UI; no stage 3/4/5 code.

**Risks / to verify during implementation:**
- **Truth set — RESOLVED.** Built directly from the lab's local HGMD dump
  (`build_hgmd_gold.py`); no dependency on the Wermers supplement. Verify the `refseq:c.hgvs`
  strings VariantValidator accepts (some HGMD del/ins forms carry explicit bases; the pipeline
  flags any it can't normalize — it does not drop them).
- **LitVar2 / PubTator3 endpoints** — confirm current paths live (Task 0); do not assume.
- **HGMD data-retention terms** — legal/quality confirmation before long-term reliance on the
  frozen snapshot; production is unaffected either way (pipeline never calls HGMD).
- **Precision interpretation** — sparse primary-only gold understates set-precision; report
  recall-forward (§7).
- **Hosted VariantValidator latency/flakiness** — mitigated by the request cache; self-host deferred.
- **Corporate egress** — confirmed working 2026-07-16 (myvariant + E-utilities → 200).
- **Coverage gate** — new optional core branches (alignment/provenance None-paths) must be
  exercised by retrieval tests to hold ≥98%.
```
