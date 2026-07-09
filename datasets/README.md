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
