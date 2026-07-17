# ClinEval Knowledge Base

A **plain-language reference** for everyone working on ClinEval — including non-specialists.
It explains the terms and the recurring "why?" questions in everyday language, with one running
example (a real RYR1 variant). It is not legal, regulatory, or clinical advice.

- **Running example:** the RYR1 variant `NM_000540.3:c.1840C>T`, also known as `p.(Arg614Cys)` /
  `p.(R614C)` / `NC_000019.10:g.38457545C>T` / `rs193922747`. (All four names point to the *same*
  variant — see [HGVS](#hgvs) below.)

---

## The one big idea: two different things

Almost every confusion clears up once you separate these two:

| | **The pipeline** (the product) | **The gold set / benchmark** (the measuring stick) |
|---|---|---|
| What it is | The tool that takes a variant and finds its literature | A fixed list of variants with the *known correct* papers |
| When it runs | Live, on demand — always searches *current* literature | Only when we want to *grade* the pipeline |
| Does it change? | Always up to date | Deliberately **frozen**, so scores stay comparable over time |
| Needs a licence? | No — free public APIs only | Bootstrapped from HGMD once; then free sources |

Analogy: the pipeline is a **search engine** (always searching the live web); the gold set is a
**fixed exam with an answer key** you use to grade the search engine. You reuse the same exam for
years — that's the point of an exam.

**ClinEval** is the *exam-grader* (the evaluation harness). The **pipeline** is the *thing being
graded*. They live in one repository but are different systems.

---

## Glossary

### Variant
A specific change in a person's DNA compared to the reference genome — e.g. one DNA letter (base)
swapped for another. The thing we're trying to find literature about. A variant is **one physical
change**, but it has **many names** (see next).

### HGVS
The **standard naming system** for a variant, from the *Human Genome Variation Society*. It is
*descriptive* — the name spells out the change. The same variant can be described from different
reference points, and the prefix tells you which:

| Prefix | Example | What it describes |
|---|---|---|
| **g.** (genomic) | `NC_000019.10:g.38457545C>T` | Absolute position on the chromosome (the "street address") |
| **c.** (coding DNA) | `NM_000540.3:c.1840C>T` | Position inside a gene's transcript (needs a transcript) |
| **p.** (protein) | `p.(Arg614Cys)` = `p.(R614C)` | What the change does to the protein (the effect) |

`c.` is the form your lab and HGMD use as the canonical input. `p.` comes in a 3-letter
(`Arg614Cys`) and a 1-letter (`R614C`) style — papers use both.

**Key facts people ask about:**
- **One variant → many names.** Not one name per variant. Different papers name the *same* variant
  differently, which is the core problem the pipeline solves.
- **If you know one name, you can get the others — but via a translation tool, not automatically.**
  That tool is [VariantValidator](#variantvalidator), and doing this translation is exactly what
  **Stage 1** of the pipeline is for.
- **A gene can have several transcripts**, so one variant can have several valid `c.` names
  (e.g. `c.1840C>T` on one transcript, `c.1825C>T` on another).
- **Not every variant has every name.** A brand-new variant may have no rsID yet; a deep-intronic
  variant may have no meaningful protein (`p.`) form. Those "missing name" cases are the **hard
  cases** the pipeline flags (never silently drops).

### Transcript
A gene's official "reading" — the sequence used to number a `c.` variant. Written like
`NM_000540.3` (an NCBI RefSeq ID; `.3` is the version). A gene can have several transcripts, which
is why the same variant can have several `c.` names. A `c.` name only makes sense **paired with a
transcript** (`NM_000540.3:c.1840C>T`).

### dbSNP / rsID
**dbSNP** is NCBI's free public **catalogue of known variants**. Each catalogued variant gets an
**rs number** (e.g. `rs193922747`) — a **catalogue/library number**. Unlike HGVS, an rsID does
*not* describe the change; it's just a stable ID pointing to a database entry.
- **rsID is NOT HGVS** — it's a separate naming system.
- If you have the rsID you can **look up** the variant's other names in dbSNP.
- **Why it matters here:** many papers (especially population/GWAS studies) cite a variant *only*
  by its rsID, so the pipeline fetches the rsID too, to search under that name as well.

### PMID
**PubMed ID** — the unique number of a scientific paper in PubMed (e.g. `8477729`). PMIDs are
public identifiers. Our gold set is "variant → list of the *correct* PMIDs," and the pipeline's
job is to return those PMIDs.

### Gene
A stretch of DNA that codes for something (usually a protein). Our running gene, **RYR1**
(ryanodine receptor 1), is linked to malignant hyperthermia and congenital myopathies. Genes have
symbols (RYR1) and transcripts (NM_000540.3).

### HGMD
**Human Gene Mutation Database** — a large, manually-curated (and **licensed / paid**) database
linking variants to disease and to the literature. It's the tool the lab is dropping over cost,
and — during Phase 1 — the source of our benchmark answer key. **The pipeline never calls HGMD;**
HGMD is used *once*, internally, to build the gold set. See the [FAQ](#faq) for the licence details.

### ClinVar
A **free, public** database of variants and their clinical significance (pathogenic / benign /
etc.), with a review status and supporting literature. It's ACMG-aligned and updates continuously.
In production it provides the **classification signal**; long-term it's a **free replacement** for
HGMD as a gold-set source.

### LitVar2
A **free NCBI service** that maps a variant to the PubMed papers mentioning it. The pipeline's
**Stage 2** queries LitVar2 for each variant name to collect candidate PMIDs. It indexes titles,
abstracts, and open-access full text only — so papers that mention a variant *only* in paywalled
full text are missed. Measuring how often that happens is a key point of the evaluation.

### PubTator3
Another **free NCBI service** that annotates papers with the biological entities (genes, variants,
diseases) they mention. An optional Stage-2 add-on.

### VariantValidator
A **free service** that validates a variant's HGVS name and translates it across forms — it takes
`NM_000540.3:c.1840C>T` and returns the protein form, the genomic form, other transcripts, etc.
This is the engine behind **Stage 1** ("one name in → all the names out").

### myvariant.info
A **free service** that aggregates cross-references for a variant in one call — notably the
**rsID**, plus ClinVar and gnomAD data. Stage 1 uses it to backfill the rsID and pull those
cross-references.

### GSC+ (BiolarkGSC+)
A **gold-standard corpus**: 228 PubMed abstracts that experts **hand-annotated with phenotype
terms** (Lobo et al., 2017). *GSC = Gold Standard Corpus; the "+" is an extended version.* It is
the **answer key for the repo's existing HPO-extraction task** (Module A) — the same role the
HGMD gold plays for the new variant-retrieval task. It ships inside the public PhenoTagger project
and is downloaded (not committed) by `datasets/download_gsc.py`.

### HPO (Human Phenotype Ontology)
A standard vocabulary of human symptoms/traits (e.g. "seizure" → `HP:0001250`). The repo's
*first* task extracts HPO terms from clinical text; **GSC+** is its benchmark. (Different task from
variant retrieval, but the same "grade a system against a gold set" pattern.)

### ACMG / AMP classification
The standard framework clinical scientists use to classify a variant (Pathogenic → Benign) from
evidence. Our pipeline doesn't make the call — it hands the scientist **ranked, cited literature**
so *they* can apply ACMG/AMP.

### Gold set / benchmark / truth set
Three names for the same thing: a **fixed list of variants with their known-correct answers** (for
us, the correct PMIDs). We grade the pipeline by comparing what it returns against this. It is
deliberately **frozen** so results are reproducible and comparable over time.

### Recall / precision / F1
How we score retrieval, per variant:
- **Recall** — of the papers we *should* have found, how many did we find? *(Did we miss known
  evidence? This is our headline number.)*
- **Precision** — of the papers we *returned*, how many were correct?
- **F1** — a single number balancing the two.
In Phase 1, **recall is what matters most**; precision is read with care (explained in the spec).

### The flywheel
The self-improving loop: when a scientist classifies a variant (Phase 3), the system records
*which papers were decisive*. Each decision becomes a **new gold-set row** — so the benchmark
grows over time from the lab's own work, no external licence needed.

### Wermers 2024 (the RYR1 benchmark)
A published study comparing HGMD / Mastermind / ClinVar / LitVar2 on **50 RYR1 variants**. We use
it as an **aggregate sanity check** — does our free stack land in the same ballpark? RYR1 is our
**pilot gene**, not the final scope (see FAQ).

---

## FAQ

### Why RYR1? Is it the only gene we care about?
**No — RYR1 is a pilot / proving ground, not the scope.** You validate a method on a small,
well-understood slice before running it on everything (like calibrating an assay on a control
sample first). RYR1 is ideal because there's a published benchmark (Wermers) to compare against and
it's full of hard cases. Once the pipeline works on RYR1, you point the *same* code at your whole
panel — the gold-set query changes one line (`gene = 'RYR1'` → `gene = ANY(panel)`). **The panel is
the product; RYR1 is the test tube.**

### What happens when the HGMD licence expires? Do I have to keep updating the gold set?
**Nothing breaks, and no — you don't have to keep updating it.**
- The **pipeline never used HGMD**, so its expiry has zero effect on production.
- A **benchmark is meant to be frozen and reused** — the same exam grades the pipeline validly for
  years. You do *not* need to refresh it to keep evaluating.
- If you ever *want* fresher ground truth, you rebuild the gold from **free sources** — **ClinVar**
  (free, always current, carries supporting PMIDs) and the **flywheel** (your own reviewed cases).
  HGMD is just the richest *starting* source you have today.

### Can I reuse the same gold set forever? What about new variants?
Yes, reuse it forever — that's the point of a benchmark. New variants are handled in **two
different places**:
- **Production:** automatic. Hand the *live* pipeline any new variant (or an old variant with a new
  paper) and it finds it in real time. Nothing to update.
- **Benchmark:** you only add new variants if you want to *re-measure* on newer truth — and you do
  that from ClinVar + flywheel, never HGMD.

### Is it OK to use HGMD as the gold set in an open-source repo?
Yes, because **code and data are separate**:
- The **builder script** (`build_hgmd_gold.py`) is just SQL + Python with *no HGMD data* — fine to
  open-source.
- The **HGMD-derived gold data** stays **private, git-ignored, never committed/redistributed**.
Using a licensed database to build a **private benchmark for internal validation** is a normal,
permitted use; *redistribution* is the red line, and we don't cross it. (Confirm the specifics with
whoever manages your HGMD licence.)

### If ClinVar and the flywheel are free, why use HGMD at all?
Because **the goal is to prove we can replace HGMD**, and to prove that you must measure the free
stack against *HGMD's own answers*. HGMD is both **the thing you're replacing** and **the reference
standard for proving the replacement works** — like calibrating a cheaper instrument against the
gold-standard one before retiring it. Using ClinVar alone would only prove "we match ClinVar," which
is weaker than the question actually being asked ("do we miss anything HGMD would have caught?").
After the decision is made, the gold set migrates to ClinVar + flywheel and HGMD is gone.

### If I know one name for a variant, do I know all of them?
In principle yes — the `g.` / `c.` / `p.` HGVS names and the rsID all point to the same variant —
**but** getting from one to the others needs a **translation tool** ([VariantValidator](#variantvalidator)
for HGVS, dbSNP/[myvariant](#myvariantinfo) for the rsID) and sometimes a choice (*which
transcript?*). And not every variant has every name (novel variants may lack an rsID; intronic ones
may lack a protein form). Turning one name into *all* the names a paper might use is precisely the
job of **Stage 1**.

### What's the difference between "the pipeline" and "ClinEval"?
The **pipeline** finds literature for a variant (the product). **ClinEval** grades the pipeline
against a gold set (the exam-grader). Same repo, two jobs. See [the one big idea](#the-one-big-idea-two-different-things).

---

## See also
- Design spec: `docs/superpowers/specs/2026-07-16-variant-literature-retrieval-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-16-variant-literature-retrieval.md`
- Building the HGMD gold: `datasets/build_hgmd_gold.py` and `datasets/README.md`
