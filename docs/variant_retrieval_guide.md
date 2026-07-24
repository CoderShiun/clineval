# Variant Literature Retrieval — Guide (Phase 1)

A complete, plain-language guide to ClinEval's `variant_retrieval` feature: **what it is for,
how it works, how to run it, and — most importantly — how to read its results correctly
without over-trusting them.**

> **One-line summary.** Given a genomic variant, an open pipeline retrieves candidate primary
> literature (PubMed IDs) from free public services, and ClinEval scores how well that pipeline
> **reproduces HGMD's curated citation list** — the validation experiment for replacing HGMD's
> (licensed) literature-curation function with something open and auditable.

---

## 1. Why this exists (the goal)

Clinical variant interpretation relies on knowing *which papers* describe a given variant. HGMD
provides this as a curated, licensed product. If a lab drops that licence, it loses the curation.

The question this feature answers is narrow and concrete:

> **Can a pipeline built only from free public APIs recover the literature HGMD would have cited
> for a variant — well enough to replace it?**

To answer it we need two things:

1. **A pipeline** that, from a variant, returns candidate PMIDs (the *system under test*).
2. **A benchmark** — a known-answer "gold" of the correct PMIDs per variant — plus a way to
   score the pipeline against it (the *evaluation harness*).

The gold is built from a lab's own licensed HGMD database, **once**, as a frozen internal
benchmark. The pipeline itself **never calls HGMD** — it uses only VariantValidator,
myvariant.info, LitVar2, and NCBI E-utilities.

Two hard rules govern everything here:

- **No patient data.** Only variant coordinates (HGVS) ever enter the pipeline.
- **Nothing fabricated.** No invented evidence labels, no HGMD tags emitted as authoritative
  output, no committed licensed data. Committed demo data is synthetic (see §7).

---

## 2. What it measures — and what it does *not*

This is the single most important section. **The scores are "concordance with HGMD," not
"coverage of the true literature."**

The gold *is* HGMD's curated citation list. So when the report says **recall = 0.75**, it means:

> "The pipeline reproduced 75% of the PMIDs HGMD listed for these variants."

It does **not** mean "the pipeline found 75% of all the evidence that exists." Three consequences
follow, and the report states them next to every number:

| Property | Consequence |
|---|---|
| **Hard ceiling at HGMD** | Recall can never exceed 1.0, and a *correct* paper HGMD didn't list earns no credit. |
| **Precision is not "accuracy"** | A retrieved paper outside HGMD's list is charged as a false positive — even if it is a correct paper HGMD simply omitted. |
| **Necessary, not sufficient** | High concordance is required to trust the pipeline as a replacement, but doesn't by itself prove the pipeline is *as complete as reality*. |

So the headline numbers **bound** how well the free pipeline reproduces HGMD's bibliography; they
are a strong regression/validation signal, but the final "can we drop HGMD?" decision needs one
more step (§8, the adjudication study).

### Macro vs micro — both are shown, on purpose

- **Macro recall** = the average of per-variant recall. It weights every variant equally, so it is
  dominated by the many single-citation variants (the easy ones).
- **Micro recall** = total gold PMIDs found ÷ total gold PMIDs. It weights every citation equally,
  so it better reflects "what share of *all* known citations did we find."

They can diverge substantially when a dataset mixes easy single-paper variants with hard
many-paper ones. **Read them together; neither alone is "the" number.**

---

## 3. How it works (the two stages + the harness)

```
          VARIANT (HGVS)                         GOLD (HGMD-derived, frozen)
                │                                          │
        ┌───────▼─────────┐   ┌──────────────────┐         │
Stage 1 │ normalize_and_  │   │  Stage 2         │         │
        │ expand          │──▶│  retrieve        │──PMIDs──┤
        │ (all name forms │   │  (LitVar2 union  │         │
        │  + rsID + xrefs)│   │   behind a gate) │         ▼
        └─────────────────┘   └──────────────────┘   ┌──────────────┐
             pipeline = system under test            │ RetrievalMetric │  → report
                                                      │ recall/precision│
                                                      └──────────────┘
```

**Stage 1 — `normalize_and_expand`.** A variant is named many ways in the literature
(`p.R614C`, `p.Arg614Cys`, `c.1840C>T`, genomic coordinates, an rsID). VariantValidator provides
the biological mappings; a local synonym generator produces every naming form; myvariant.info
backfills the rsID (critical for LitVar) and ClinVar/gnomAD cross-refs. Key safeguards:

- The rsID is **derived from coordinates, never guessed** (a wrong rsID would retrieve a different
  variant's papers).
- A variant with no protein consequence (splice/intronic/indel) is **flagged, never dropped**.
- If VariantValidator itself fails for one variant, that variant is **flagged as degraded** and the
  batch continues (one outage never silently becomes a "0" — see §5).

**Stage 2 — `retrieve`.** The forms are resolved to LitVar2 variant record(s), then their PMIDs are
unioned. A **variant-match gate** ensures a returned paper genuinely refers to *this* variant (by
rsID, or gene + normalized HGVS), guarding against same-gene/different-position collisions. Paper
metadata (title/journal/year) is fetched from E-utilities (non-fatal). Every external failure is
recorded, not swallowed.

**The harness.** `RetrievalMetric` computes set-based recall/precision/F1 per variant, macro- and
micro-averaged, plus mean yield; it lists missed PMIDs, unresolved variants, and any variant whose
retrieval was degraded (which it **excludes from the scores**). `render_retrieval_report` turns all
of that into the Markdown report.

---

## 4. How to run it

Everything runs in Docker; no host Python needed.

### The offline demo (zero setup, synthetic data)

```bash
docker compose run --rm clineval uv run clineval retrieval-eval \
    --dataset ryr1 --source cached --report reports/retrieval.md
```

This replays committed **synthetic** pipeline outputs against a committed **synthetic** gold — fully
offline and deterministic. Use it to see the report format and the metric behavior. (Its PMIDs are
placeholders ≥ `99000000`, so the numbers are illustrative, not real.)

### The `--source` modes

| Mode | What it does | When to use |
|---|---|---|
| `cached` | Replays committed pipeline outputs from a JSONL cache. Offline, deterministic. | Regression testing; the demo. |
| `live` | Runs Stage 1→2 against the real public APIs. Needs network. | The actual measurement. |
| `dataset` | Scores `system_output` already present in the gold JSONL. | You produced predictions elsewhere. |

### The real measurement (live pipeline vs your HGMD gold)

1. **Build the gold once**, while your HGMD licence is active (writes to the git-ignored
   `datasets/hgmd_gold/`). `--hgmd-release` is required so the snapshot is auditable:

   ```bash
   docker run --rm --network container:hgmd_postgres \
       -e PGHOST=127.0.0.1 -e PGDATABASE=midas_hgmd -e PGUSER=postgres \
       -v "$PWD":/app -w /app python:3.12-slim \
       sh -c "pip install --quiet 'psycopg[binary]' && \
              python datasets/build_hgmd_gold.py --genes RYR1 --hgmd-release 2026.2 \
                  --out datasets/hgmd_gold/ryr1_gold.jsonl"
   ```

   The builder writes a `.meta.json` sidecar next to the gold with its **SHA-256, the DB version,
   the HGMD release, and per-gene variant counts** (including any requested gene that matched zero
   variants — an alias/case miss). See [`../datasets/README.md`](../datasets/README.md).

2. **Run the pipeline against it.** Set `NCBI_API_KEY` to raise NCBI rate limits (it is sent with
   requests but never written to the request cache key):

   ```bash
   docker compose run --rm -e NCBI_API_KEY=$NCBI_API_KEY clineval uv run clineval retrieval-eval \
       --dataset datasets/hgmd_gold/ryr1_gold.jsonl --source live --report reports/retrieval.md
   ```

Full flag reference: [`USAGE.md` §14](USAGE.md).

---

## 5. Reading the report correctly

The report has these sections. Read them **in this order** and heed the caveats.

1. **Header** — dataset, variant count, retriever, timestamp (= the retrieval date for live runs),
   and a **Provenance** line (tool/DB versions, cache hit-rate, degraded count).
2. **Concordance with HGMD** — the macro + micro recall/precision/F1 table, preceded by the
   "what this measures" caveat (§2). It states **how many variants were scored** vs the total, so a
   run with excluded variants can't be misread.
3. **Per-variant breakdown** — gold/retrieved/found/missed/recall/precision per scored variant.
4. **Missed evidence** — the specific gold PMIDs the pipeline failed to retrieve (the clinically
   important false negatives).
5. **Unresolved variants** — variants with no protein consequence (splice/intronic/indel), flagged
   and kept, routed to manual review.
6. **Retrieval integrity** — variants whose retrieval was **degraded** (an API failure) or
   **uncovered** (a cache miss). These are **excluded from the scores** above, because their empty
   result is a retrieval artifact, not evidence that no literature exists. *If this section lists
   variants, re-run them before trusting the aggregates.*
7. **Regulatory Evidence Mapping** — each metric mapped to EU AI Act / IVDR / ISO 15189:2022 clauses,
   with a non-legal-advice disclaimer.

### How **not** to over-trust a number

- ❌ "Recall 0.75 means we find 75% of the evidence." → ✅ It means we reproduce 75% of *HGMD's list*.
- ❌ "Low precision means the pipeline is noisy." → ✅ Some 'false positives' may be correct papers
  HGMD omitted; precision is a *concordance* measure, not an accuracy measure.
- ❌ "The macro number is the score." → ✅ Compare macro and micro; a large gap tells you the
  variant-size distribution is skewing one of them.
- ❌ "All the zeros are misses." → ✅ Check the **Retrieval integrity** section first — a zero there
  is an outage/cache miss, already excluded from the aggregates.

---

## 6. Reproducibility & auditability

A score is only trustworthy if you can reproduce and audit it.

- **Deterministic offline path.** `--source cached` over committed fixtures is byte-stable.
- **Frozen gold.** The gold is a snapshot of a specific HGMD release; its sidecar records the
  release label, DB version, and a **content SHA-256** so a report's claimed gold can be verified.
- **Evidence snapshot.** Live runs record the tool/DB versions and the sources consulted in the
  report's Provenance line; the timestamp is the retrieval date (PubMed/LitVar grow over time).
- **Honest failures.** API/normalization failures are recorded (degraded), never silently scored —
  so a low number is never an undetected outage.

---

## 7. Trust & safety (the licence firewall)

- **The pipeline never calls HGMD.** It uses only free public APIs.
- **Committed data is synthetic.** `examples/data/ryr1_gold.jsonl` and `cached_retrieval.jsonl` use
  placeholder PMIDs ≥ `99000000`, marked `source: "synthetic_demo"`. The invariant is: *no
  real-range PMID or HGMD accession in any committed file.*
- **Real gold is git-ignored.** `datasets/hgmd_gold/` (HGMD's curated selections) is never committed
  or redistributed — it is licensed. The builder refuses to run without a `--hgmd-release` label.
- **No fabrication.** The report renders only computed numbers plus a clearly-disclaimed regulatory
  mapping; it never invents evidence labels or emits HGMD tags as authoritative output.

---

## 8. Limitations & the next step

- **Concordance ≠ completeness (§2).** To turn "reproduces 75% of HGMD's list" into "captures the
  evidence," run an **adjudication study**: sample ~50 variants, and for each manually classify the
  pipeline's *extra* (non-gold) PMIDs as correct or not, and estimate how many correct papers HGMD
  itself omitted. That yields the two numbers that actually answer "can we drop HGMD?" — the
  pipeline's true precision and the evidence it finds *beyond* HGMD. This is a clinical-judgment
  task, deliberately not automated.
- **Phase 1 scope.** No ranking, no ClinVar-classification signal, no UI. Precision is therefore
  read with care (there is no top-k cutoff).
- **rsID retrieval.** The rsID-keyed LitVar id is constructed from a fixed scheme
  (`litvar@{rsid}##`), always keyed by the correct **coordinate-derived** rsID — so it can never
  return another variant's papers. Edge case: if LitVar returns an *error* (rather than an empty
  list) for a valid rsID it hasn't indexed, that variant is conservatively marked **degraded**
  (excluded and surfaced, never scored as a wrong result) — a safe, conservative failure mode.

---

## 9. Where things live (for developers)

```
clineval/pipeline/                      the system under test (never calls HGMD)
├── normalize.py                          Stage 1: variant -> all name forms + rsID + xrefs
├── retrieve.py                           Stage 2: LitVar union behind the variant-match gate
├── synonyms.py                           protein/cDNA/VCF naming-form generation
├── cache.py / throttle.py                request cache (SQLite) + rate limiter/retry
└── clients/                              VariantValidator, myvariant, LitVar2, E-utilities
clineval/tasks/variant_retrieval/       the evaluation harness
├── metrics.py                            RetrievalMetric (recall/precision/F1, macro+micro)
├── retriever.py                          Dataset/Cached/Pipeline retriever adapters
├── datasets.py                           RYR1 (synthetic) + HGMD gold loaders
└── report.py                             render_retrieval_report
clineval/templates/retrieval_report.md.j2  the report template
clineval/regulatory/mapping.py           evidence -> EU AI Act / IVDR / ISO 15189 rows
datasets/build_hgmd_gold.py              builds the git-ignored HGMD gold (licensed; run once)
examples/data/*.jsonl                    committed SYNTHETIC demo gold + cached outputs
```

Run the tests (offline, deterministic, enforced coverage):

```bash
docker compose run --rm clineval uv run pytest
```

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Error: --source must be cached, live, or dataset.` | Typo in `--source`. |
| `Error: … not found …` on `--dataset hgmd` | The HGMD gold isn't built. Build it (§4) while the licence is active. |
| Report shows `degraded_variants=N/M` + a warning | N variants had an API failure or cache miss; they're excluded from the scores. Re-run (check network / `NCBI_API_KEY`). |
| `WARNING: … variants matched cache …` | Your `--cache` doesn't cover the dataset ids; align them or use `--source live`. |
| Builder: `WARNING: … gene(s) matched ZERO variants` | An alias/case mismatch against HGMD's `gene` column; check the symbol spelling. |
| All scores are `0.000` with an empty per-variant table | Likely every variant was degraded — see the Retrieval integrity section and re-run. |

---

*This document is a general technical/educational reference, not legal or regulatory-compliance
advice. Confirm dataset licence terms before use, and consult qualified regulatory/quality
professionals against the current official texts before relying on any output as validation
evidence.*
