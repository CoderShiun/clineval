# Datasets

ClinEval does **not** commit third-party corpora. Fetch GSC+ with the downloader.

## GSC+ / BiolarkGSC+

228 PubMed abstracts manually annotated with HPO concepts (Lobo et al., 2017).

```bash
# Downloads + converts to datasets/gsc_plus/gsc_plus.jsonl (git-ignored). Verified: 228 docs.
docker compose run --rm clineval uv run python datasets/download_gsc.py
# Then evaluate your system's predictions on it (live model, or a predictions cache):
docker compose run --rm clineval uv run clineval run --dataset gsc \
    --live --base-url http://host.docker.internal:1234/v1 --report reports/gsc.md
```

**Source:** GSC+ ships inside the PhenoTagger project's public `data/corpus.zip`
(`corpus/GSC/GSCplus_{dev,test}_gold.tsv`, PubTator format); `download_gsc.py` points
at it and combines the dev + test files into the 228-document corpus. **Confirm the
corpus licence terms for your use** — ClinEval downloads it at runtime and never
commits the data. The parser is covered by `tests/fixtures/gsc_sample/`.

Remember GSC+ is the **gold standard only** — you still supply predictions from the
system you are evaluating (`--live` or a `--cache` file).

## HGMD-derived gold (variant_retrieval task) — INTERNAL / LICENSED, never committed

The variant→literature benchmark's answer key. Built **once, while your HGMD licence is
active**, into a **frozen snapshot** (`datasets/hgmd_gold/*.jsonl`, git-ignored). The
ClinEval pipeline itself **never calls HGMD** — this is evaluation truth only.

For each variant it unions the associated PMIDs from `allmut.pmid` + the pipe-delimited
`allmut.pmidall` + `extrarefs.pmid`, keyed by `acc_num`, and writes ClinEval's gold schema.

### Data provenance — what comes from where

There are **two inputs with two very different roles** (nothing is fabricated):

| Input | Role | Appears in the output JSON? |
|---|---|---|
| **HGMD database** | Supplies **all the data** — the variants and the PMIDs | **Yes — every field.** |
| **A gene list** (`--genes` / `--genes-file`) | A **selector** — decides *which genes* to pull | **No** — it only chooses which HGMD rows come out. |

Shopping-list analogy: the gene list is the *shopping list* (which genes), HGMD is the *store*
(the actual variants + papers), and the JSON is the *groceries you brought home* — everything in
it came from the store. Every *data* field — the variant and its PMIDs — originates in HGMD
(the record also carries two bookkeeping fields not shown below: a constant `source: "hgmd"`
and a computed `n_pmids`):

```jsonc
{"id": "NM_000540.3:c.1840C>T",      // ← allmut.refseq + allmut.hgvs
 "gold_reference": ["<pmid>", ...],   // ← allmut.pmid ∪ split(allmut.pmidall) ∪ extrarefs.pmid
 "metadata": {"gene": "RYR1",         // ← allmut.gene  (HGMD's own column — NOT the gene list)
              "hgmd_accs": ["CM..."],  // ← HGMD accession(s)
              "primary_pmids": [...],  // ← allmut.pmid
              "tags": ["DM"]}}         // ← allmut.tag  (internal stratification only)
```
Two HGMD accessions describing the same canonical variant are **merged into one record** (PMIDs
unioned) so record ids stay unique, as ClinEval's loader requires.

### Providing the gene list

Gene **symbols only**, one per line — HGNC symbols matching HGMD's `gene` column. Use
`--genes RYR1,CACNA1S` for a handful, or `--genes-file <path>` for many. The list can come from
anywhere (a hand-written file, a panel export, …). Example: derive it from gene-panel TSVs whose
first column is the symbol (with a header row):
```bash
awk -F'\t' 'FNR>1 && $1!="" {print $1}' my_panels/*.tsv \
  | grep -E '^[A-Za-z0-9][A-Za-z0-9._-]*$' | sort -u > datasets/panel_genes.txt
```
Genes absent from HGMD (or spelled with a different alias) simply contribute no variants — the
count is reported in the meta sidecar, never an error.

**Connecting.** The builder uses standard libpq env vars (`PGHOST/PGPORT/PGDATABASE/PGUSER`,
and `PGPASSWORD` when required). Two common setups:

- **Baked HGMD image (e.g. `*/hgmd:2026.2-postgres`, db `midas_hgmd`) — recommended, verified.**
  These images ship the DB inside the image, so `POSTGRES_PASSWORD` is ignored and `pg_hba.conf`
  usually `trust`s only loopback (`127.0.0.1`). Share the DB container's network namespace so the
  builder connects over the trusted loopback — **no password, no DB change:**
  ```bash
  # <db-container> is the running HGMD container name (e.g. hgmd_postgres).
  docker run --rm --network container:hgmd_postgres \
      -e PGHOST=127.0.0.1 -e PGDATABASE=midas_hgmd -e PGUSER=postgres \
      -v "$PWD":/app -w /app python:3.12-slim \
      sh -c "pip install --quiet 'psycopg[binary]' && \
             python datasets/build_hgmd_gold.py --genes RYR1 --hgmd-release 2026.2 \
                 --out datasets/hgmd_gold/ryr1_gold.jsonl"
  # Whole panel (one gene symbol per line in the file):
  #   ... python datasets/build_hgmd_gold.py --genes-file datasets/panel_genes.txt \
  #         --hgmd-release 2026.2 --out datasets/hgmd_gold/panel_gold.jsonl
  ```
- **A DB you have a password for.** Connect over TCP from the clineval container:
  ```bash
  docker compose run --rm \
      -e PGHOST=host.docker.internal -e PGDATABASE=midas_hgmd -e PGUSER=hgmd_user -e PGPASSWORD=... \
      clineval uv run --with 'psycopg[binary]' \
      python datasets/build_hgmd_gold.py --genes RYR1 --hgmd-release 2026.2 \
          --out datasets/hgmd_gold/ryr1_gold.jsonl
  ```
  (If the baked image trusts only loopback, first set a password once via
  `docker exec hgmd_postgres psql -U postgres -c "ALTER USER hgmd_user PASSWORD '...'";`.)

Then, once the retrieval pipeline is implemented, score the free stack against the gold:
```bash
docker compose run --rm clineval uv run clineval retrieval-eval \
    --dataset datasets/hgmd_gold/ryr1_gold.jsonl --source cached --report reports/retrieval.md
```
(Verified 2026-07-17 against `hgmd:2026.2-postgres`: RYR1 → 1,505 variants / 596 PMIDs;
full Routine panel (2,760 genes) → 347,008 variants / 92,230 PMIDs.)

A `*.jsonl.meta.json` sidecar records the HGMD release, gene/tag filters, variant + distinct-PMID
counts, and how many in-scope variants had **no** citable PMID (excluded, not silently dropped).

**Licence & compliance.** PMIDs and variant coordinates are public, but the *selection* of
papers per variant is HGMD's curated work product — keep the output **internal, git-ignored,
never redistributed**. Confirm your licence's data-retention terms before relying on the
snapshot long-term. The HGMD tag (DM/DM?/…) is stored in metadata for **internal stratification
only** and must never be emitted by the pipeline as an authoritative label. Once the licence
lapses you simply stop refreshing the snapshot; production is unaffected (it never used HGMD),
and the benchmark migrates to ClinVar + the ScS-review flywheel.

## BioCreative VIII Track 3

Documented fast-follow (not in this MVP). Add a `BioCreativeLoader` in
`clineval/tasks/hpo_extraction/datasets.py` as its own PR.
