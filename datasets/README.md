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

## BioCreative VIII Track 3

Documented fast-follow (not in this MVP). Add a `BioCreativeLoader` in
`clineval/tasks/hpo_extraction/datasets.py` as its own PR.
