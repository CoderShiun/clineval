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

### Where does "0.25 → 0.42" actually come from? (the math)

The score is built in **two steps**: score each document 0–1, then average the documents.

**Step 1 — score each document.** Every document gets three numbers:

- **Precision** = *of the terms the system predicted, how many were correct.*
- **Recall** = *of the correct (gold) terms, how many the system found.*
- **F1** = one balanced number combining them: `F1 = 2 × Precision × Recall / (Precision + Recall)`.

In the tutorial each document has exactly **one** gold term, so F1 is simply 1 (got it) or 0 (didn't):

| Doc | What the system did | Exact F1 |
|---|---|---|
| tut01 | predicted the exact term | **1.0** |
| tut02 | predicted the *parent* term, not the exact one | **0.0** |
| tut03 | predicted a made-up id | **0.0** |
| tut04 | predicted nothing | **0.0** |

> *(When a document has several terms, F1 is a fraction. E.g. gold = 2 terms, the system gets 1
> right and adds nothing extra → Precision 1/1 = 1.0, Recall 1/2 = 0.5, F1 = 0.67. That's why the
> bigger demo has scores like 0.5 and 0.67, not just 0 and 1.)*

**Step 2 — average the documents.** The overall score is just the mean of the per-document F1s
(this is called a *macro-average*):

```
Exact overall F1 = (1.0 + 0.0 + 0.0 + 0.0) / 4 = 0.25
```

**The semantic score repeats Step 2 with partial credit.** Instead of "exact match = 1, else 0,"
it gives partial credit for how *close* the predicted term sits in the HPO tree. tut02 predicted
the *parent* of the right term, so instead of 0 it earns **0.68**:

```
Semantic overall F1 = (1.0 + 0.68 + 0.0 + 0.0) / 4 = 0.42
```

So **"exact 0.25 → semantic 0.42" is the same four documents scored two ways.** The *only*
document that moved is tut02 (0.00 → 0.68), and that single near-miss lifts the average by
**0.17**. That gap is the message: "a chunk of what exact-match calls 'wrong' is actually
clinically close."

### Is a score good or bad? What's "good enough"?

F1 runs from **0** (everything wrong) to **1** (perfect). Rough reference points for HPO
extraction, to calibrate your intuition:

| F1 | Rough reading |
|---|---|
| **< 0.3** | Poor — e.g. a raw LLM with no help hallucinates badly (~0.12 in published tests). |
| **0.5 – 0.7** | Moderate. |
| **0.7 – 0.8** | Good — competitive with dedicated tools (PhenoTagger ≈ 0.74–0.77; an LLM with retrieval help ≈ 0.80). |
| **> 0.8** | Strong. |

The tutorial's **0.25 is deliberately low** — it's a 4-document toy with one hit, one near-miss,
one hallucination, and one miss. It is not meant to look like a real system. (The bigger bundled
demo, ~0.62 exact / ~0.73 semantic, is a more realistic "decent model" level.)

**But there is no universal passing grade.** "Good enough" is something *you* decide for *your*
use case, ideally *before* you run. In a clinical / regulated setting the single F1 matters less
than:

- the **exact → semantic gap** (are the errors near-misses or hallucinations?),
- **zero missed high-IC (rare) phenotypes** — a missed rare finding can change a diagnosis,
- **few or zero spurious / hallucinated terms.**

ClinEval gives you all of these numbers; *you* set the acceptance thresholds based on intended
use and risk. "We defined criteria, then measured against them" is exactly the evidence a
regulated validation needs — and it's why the report maps each metric to the regulatory clauses.

---

## 6. What is GSC+, and how do I use it?

**GSC+** (also written *BiolarkGSC+*) is a **benchmark answer key**: 228 PubMed abstracts that
experts manually annotated with the correct HPO terms (Lobo et al., 2017). It's the standard
yardstick in this field — evaluating on GSC+ makes your numbers comparable to published tools.

**Important:** GSC+ gives you the **gold standard only** (the answer key). It does **not** include
predictions — you still run *your own* system over those 228 abstracts to produce them (exactly
the point from §2: even with a gold corpus, you still need a "student" to take the exam).

**How to use it:**

1. **Download + convert it** to ClinEval's format (writes `datasets/gsc_plus/gsc_plus.jsonl`,
   which is git-ignored):
   ```bash
   docker compose run --rm clineval uv run python datasets/download_gsc.py
   ```
2. **Get predictions** from the system you're testing over those abstracts, then grade with
   `--dataset gsc`:
   ```bash
   # live model:
   docker compose run --rm clineval uv run clineval run --dataset gsc \
       --live --base-url http://host.docker.internal:1234/v1 --report reports/gsc.md
   # or a saved predictions cache:
   docker compose run --rm clineval uv run clineval run --dataset gsc \
       --cache my_gsc_predictions.jsonl --report reports/gsc.md
   ```

> ⚠️ **Verify before you rely on it.** The download URL and the assumed on-disk layout are marked
> "verify before use" in `datasets/download_gsc.py` — confirm GSC+'s current source and its
> **license**, and adjust the converter if the real file layout differs. Treat this as
> "wire it up and check," not a guaranteed one-command download.

---

## 7. Now make it your own

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

## 8. Where to go next

- **Full command reference** (every flag, dataset sources, cache format, troubleshooting):
  [`USAGE.md`](USAGE.md)
- **Run the automated tests:** `docker compose run --rm clineval uv run pytest`
- **Notebook walkthrough:** `examples/hpo_extraction_demo.ipynb`
