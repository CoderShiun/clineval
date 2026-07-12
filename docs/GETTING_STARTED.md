# ClinEval — Getting Started (plain-language guide)

New to ClinEval? Read this first. It explains the idea in everyday terms and lets you run a
tiny example. For the full command reference, see [`USAGE.md`](USAGE.md).

---

## 1. The one idea to grasp first: ClinEval is a *grader*, not an *extractor*

Think of an exam:

| Exam | ClinEval |
|---|---|
| The exam question | The clinical text |
| The **answer key** | The **gold standard** — the correct HPO terms for that text |
| A **student's answers** | The **predictions** — the HPO terms *your system* produced |
| The **grader** | **ClinEval** — compares the answers to the key and writes a report card |

**ClinEval never reads the clinical text and produces HPO terms itself.** It only compares two
things that *you* give it: the gold standard (the answer key) and the predictions (the answers
to be graded). Its job is to tell you *how good the predictions are* and *what kind of mistakes
they make*.

---

## 2. "If we already have the gold standard, why do we still need an LLM?"

Because the gold standard is the **answer key**, not the **student**. Someone still has to *take
the exam* — i.e. actually read the text and produce HPO terms. That "someone" is the **system
you are testing**, and today that is usually an **LLM** (but it could be any HPO-extraction tool,
a vendor product, an older NLP tagger, etc.).

- The **LLM produces the predictions.**
- **ClinEval grades those predictions** against the gold standard.

Without predictions there is nothing to grade. So you always need *some* system to produce them —
the LLM is that system. It is the **thing being evaluated**, not a part of ClinEval.

> **You only need a *running* LLM if you want ClinEval to produce predictions on the spot.** If
> your system already ran and you saved its outputs, ClinEval does **not** run any LLM — it just
> reads your saved predictions and grades them.

---

## 3. "Do I need to download data before I start?"

It depends what you want to do:

| Goal | Download needed? |
|---|---|
| Just try it / learn how it works | **No** — bundled example data works offline (see §5). |
| Benchmark on the standard **GSC+** corpus | **Yes** — fetch it first with `datasets/download_gsc.py` (and check its license). |
| Test **your own** system on **your own** text | **No download**, but you prepare two files yourself: the gold standard and the predictions. |

So: to learn, start with the bundled example below — zero downloads, zero setup.

---

## 4. Cached vs Live mode

Both modes answer the same question ("where do the predictions come from?") differently:

| | **Cached** (default) | **Live** (`--live`) |
|---|---|---|
| Predictions come from | a file you already have | a model called *right now* |
| Needs a model server running? | No | Yes (e.g. LM Studio) |
| Speed | Fast | Slower (real model calls) |
| Same result every time? | Yes (deterministic) | Not necessarily (the model can vary) |
| Analogy | Grading a stack of **already-submitted** answer sheets | Having the student **sit the exam right now** |

**Typical workflow:** run **Live** once to get a model's predictions → save them as a **Cache**
file → from then on re-generate reports from the cache (reproducible, and no model needed). The
bundled demo uses a cache that was produced exactly this way.

There's also a third option, `--predictions-from-dataset`, where you put the predictions *inside*
the gold file (a `system_output` field next to `gold_reference`) — handy when you have one file
containing both.

---

## 5. Hands-on: run a tiny example and see the four things that can happen

Two small files ship with the repo so you can learn the report by example:

- `examples/data/tutorial_gold.jsonl` — the **answer key** (4 short documents)
- `examples/data/tutorial_predictions.jsonl` — a hand-written **student's answers** that
  deliberately shows the four outcome types

Run it (offline, no model needed):

```bash
docker compose run --rm clineval uv run clineval run \
  --dataset examples/data/tutorial_gold.jsonl \
  --cache examples/data/tutorial_predictions.jsonl \
  --report reports/tutorial.md
```

Open `reports/tutorial.md`. Here is what each document demonstrates and the score it earns:

| Doc | Gold (answer key) | Prediction (student's answer) | What happened | Exact F1 | Semantic F1 |
|---|---|---|---|---|---|
| tut01 | Seizure `HP:0001250` | Seizure `HP:0001250` | ✅ **Perfect** — exact match | 1.00 | 1.00 |
| tut02 | Perimembranous VSD `HP:0011682` | Ventricular septal defect `HP:0001629` (its **parent**) | 🟡 **Near-miss** — right area, wrong precision | 0.00 | 0.68 |
| tut03 | Microcephaly `HP:0000252` | `HP:9999999` (a **made-up ID**) | ❌ **Hallucination** — invented a code | 0.00 | 0.00 |
| tut04 | Short stature `HP:0004322` | *(nothing)* | ❌ **Miss** — said nothing | 0.00 | 0.00 |

Overall the report shows **exact F1 0.25 → semantic F1 0.42 (+0.17)**, and this error taxonomy:

- **Missed: 2** — the gold term was never produced (tut03's microcephaly, tut04's short stature)
- **Wrong granularity: 1** — a parent/child of the right term (tut02)
- **Spurious: 1** — an unrelated/invented term (tut03)
- **Unknown/unrecognized IDs: 1 (HP:9999999)** — the made-up code is caught and flagged

**This is the whole point of ClinEval.** A single exact score (0.25) would tell you "mostly
wrong" and stop there. But the three errors are *completely different problems*:

- tut02 is a **near-miss** — the model understood the finding but wasn't specific enough. That's
  a small, easy fix (ask for more specific terms). Exact match hides this; the **+0.17 semantic
  gap** reveals it.
- tut03 is a **hallucination** — the model invented an HPO code that doesn't exist. That's a
  serious, different problem, and ClinEval flags it explicitly.
- tut04 is a **plain miss** — the model didn't find the phenotype at all.

Separating "close but not exact" from "completely wrong" from "made it up" is what a single F1
number can't do — and what makes this useful for evaluating a clinical system.

---

## 6. Now make it your own

1. **Gold file** — copy `tutorial_gold.jsonl` and replace it with *your* documents and their
   correct HPO terms (one JSON object per line; look terms up at
   [hpo.jax.org](https://hpo.jax.org)):
   ```json
   {"id": "case-001", "input_text": "…clinical text…", "gold_reference": ["HP:0001250"]}
   ```
2. **Predictions** — run *your* system over the same documents and save its HPO outputs, either
   as a cache file (copy `tutorial_predictions.jsonl`), or by calling a live model with `--live`,
   or by adding a `system_output` field to the gold file and using `--predictions-from-dataset`.
3. **Run it** and read the report card.

> ⚠️ **Public / de-identified data only — never put patient data (PHI) into a dataset, cache, or
> report.** Everything runs on your machine (on-prem); nothing is sent anywhere on the default
> offline path.

---

## 7. Where to go next

- **Full command reference** (every flag, dataset sources, cache format, troubleshooting):
  [`USAGE.md`](USAGE.md)
- **Run the automated tests:** `docker compose run --rm clineval uv run pytest`
- **Notebook walkthrough:** `examples/hpo_extraction_demo.ipynb`
