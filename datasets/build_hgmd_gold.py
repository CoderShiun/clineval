"""Build the HGMD-derived gold set (variant -> associated PMIDs) for ClinEval.

INTERNAL / LICENSED DATA — READ THIS FIRST
------------------------------------------
The output is HGMD's curated variant->literature associations, used ONLY as an
internal benchmark answer key. It is git-ignored and must never be committed or
redistributed. The ClinEval pipeline itself never calls HGMD — this script only
builds *evaluation truth*, once, while the licence is active. Treat the output as
a frozen snapshot of a specific HGMD release (stamp --hgmd-release into it), not a
live source. See datasets/README.md and the design spec for the full rationale.

WHAT IT DOES
------------
Produces one JSON line per **canonical variant** (not per HGMD accession — two
accessions describing the same variant are merged, so record ids stay unique, as
ClinEval's loader requires). For each variant it unions the associated PMIDs from
three places in HGMD:

    allmut.pmid            (the primary citation)
  ∪ split(allmut.pmidall) (pipe-delimited additional PMIDs)
  ∪ extrarefs.pmid        (extra literature references)

Canonical variant id = allmut.refseq || ':c.' || allmut.hgvs (verified: refseq is
version-qualified, hgvs carries no 'c.' prefix). The HGMD tag (DM/DM?/...) is stored
in metadata for internal stratified analysis ONLY — it is never emitted by the
pipeline as an authoritative label.

CONNECTION
----------
Standard libpq env vars (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD) or --dsn.
For a baked HGMD image that trusts only loopback, share the DB container's network
namespace and connect over 127.0.0.1 (no password) — see datasets/README.md.

USAGE (baked image, verified)
-----------------------------
    docker run --rm --network container:hgmd_postgres \
        -e PGHOST=127.0.0.1 -e PGDATABASE=midas_hgmd -e PGUSER=postgres \
        -v "$PWD":/app -w /app python:3.12-slim \
        sh -c "pip install --quiet 'psycopg[binary]' && \
               python datasets/build_hgmd_gold.py --genes RYR1 --hgmd-release 2026.2 \
                   --out datasets/hgmd_gold/ryr1_gold.jsonl"

    # whole panel from a gene-list file (one gene symbol per line):
    #   ... python datasets/build_hgmd_gold.py --genes-file datasets/panel_genes.txt ...
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# One row per canonical variant. PMIDs are unioned from primary + pipe-split pmidall
# + extrarefs, across every HGMD accession that maps to the same refseq:c.hgvs.
_QUERY = """
WITH base AS (
    SELECT acc_num, gene, tag,
           (refseq || ':c.' || hgvs)   AS variant_hgvs,
           NULLIF(btrim(pmid), 'NULL') AS primary_pmid,
           pmidall
    FROM allmut
    WHERE gene = ANY(%(genes)s)
      AND tag  = ANY(%(tags)s)
      AND btrim(refseq) NOT IN ('', 'NULL')
      AND btrim(hgvs)   NOT IN ('', 'NULL')
),
pm AS (
    SELECT acc_num, primary_pmid AS pmid FROM base WHERE primary_pmid ~ '^[0-9]+$'
    UNION
    SELECT b.acc_num, btrim(x)
      FROM base b, LATERAL unnest(string_to_array(b.pmidall, '|')) AS x
      WHERE btrim(x) ~ '^[0-9]+$'
    UNION
    SELECT e.acc_num, btrim(e.pmid)
      FROM extrarefs e JOIN base b ON b.acc_num = e.acc_num
      WHERE btrim(e.pmid) ~ '^[0-9]+$'
)
SELECT b.variant_hgvs,
       b.gene,
       array_agg(DISTINCT b.acc_num ORDER BY b.acc_num)                         AS acc_nums,
       array_agg(DISTINCT b.tag ORDER BY b.tag)                                 AS tags,
       array_agg(DISTINCT p.pmid ORDER BY p.pmid)                               AS gold_pmids,
       array_agg(DISTINCT b.primary_pmid) FILTER (WHERE b.primary_pmid ~ '^[0-9]+$') AS primary_pmids
FROM base b JOIN pm p ON p.acc_num = b.acc_num
GROUP BY b.variant_hgvs, b.gene
ORDER BY b.gene, b.variant_hgvs;
"""

# Distinct in-scope canonical variants (denominator). Variants absent from the gold
# are exactly those with no citable PMID anywhere — reported, not silently dropped.
_BASE_COUNT_QUERY = """
SELECT count(DISTINCT (refseq || ':c.' || hgvs))
FROM allmut
WHERE gene = ANY(%(genes)s) AND tag = ANY(%(tags)s)
  AND btrim(refseq) NOT IN ('', 'NULL') AND btrim(hgvs) NOT IN ('', 'NULL');
"""


def _row_to_record(variant_hgvs, gene, acc_nums, tags, gold_pmids, primary_pmids) -> dict:
    """Turn one aggregated query row into a ClinEval gold record. Pure — unit-tested."""
    pmids = [str(p) for p in gold_pmids if p]
    return {
        "id": variant_hgvs,
        "input_text": variant_hgvs,
        "gold_reference": pmids,
        "metadata": {
            "gene": gene,
            "source": "hgmd",
            "hgmd_accs": list(acc_nums or []),
            "primary_pmids": [str(p) for p in (primary_pmids or [])],
            "tags": list(tags or []),  # internal stratification ONLY; never a label
            "n_pmids": len(pmids),
        },
    }


def fetch_gold_records(cur, genes: list[str], tags: list[str]) -> list[dict]:
    """Run the gold query on an open cursor and return ClinEval gold records."""
    cur.execute(_QUERY, {"genes": genes, "tags": tags})
    return [_row_to_record(*row) for row in cur.fetchall()]


def _read_genes(args: argparse.Namespace) -> list[str]:
    if args.genes_file:
        text = Path(args.genes_file).read_text(encoding="utf-8")
        genes = [g.strip() for g in text.splitlines() if g.strip() and not g.startswith("#")]
    else:
        genes = [g.strip() for g in (args.genes or "").split(",") if g.strip()]
    if not genes:
        sys.exit("Error: no genes given. Use --genes RYR1[,GENE2,...] or --genes-file PATH.")
    return genes


def _connect(dsn: str | None):
    try:
        import psycopg
    except ImportError:
        sys.exit(
            "Error: psycopg is not installed. Run this script with:\n"
            "  uv run --with 'psycopg[binary]' python datasets/build_hgmd_gold.py ...\n"
            "or add the 'hgmd' extra: uv sync --extra hgmd"
        )
    return psycopg.connect(dsn) if dsn else psycopg.connect()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build the HGMD-derived ClinEval gold set.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--genes", help="Comma-separated gene symbols, e.g. RYR1,DMD.")
    g.add_argument("--genes-file", help="Path to a file with one gene symbol per line.")
    ap.add_argument("--tags", default="DM,DM?", help="HGMD tags to include (default: DM,DM?).")
    ap.add_argument("--out", default="datasets/hgmd_gold/gold.jsonl", help="Output JSONL path.")
    ap.add_argument("--dsn", default=None, help="libpq DSN; omit to use PG* env vars.")
    ap.add_argument("--hgmd-release", default="", help="HGMD release label to stamp (e.g. 2026.2).")
    args = ap.parse_args(argv)

    genes = _read_genes(args)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    with _connect(args.dsn) as conn, conn.cursor() as cur:
        records = fetch_gold_records(cur, genes, tags)
        cur.execute(_BASE_COUNT_QUERY, {"genes": genes, "tags": tags})
        base_count = cur.fetchone()[0] or 0
        try:
            cur.execute(
                "SELECT max(new_date) FROM allmut WHERE gene = ANY(%(genes)s)", {"genes": genes}
            )
            max_new_date = cur.fetchone()[0]
        except Exception:
            max_new_date = None

    no_pmid = max(0, base_count - len(records))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    distinct_pmids = {p for rec in records for p in rec["gold_reference"]}
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hgmd_release": args.hgmd_release,
        "genes": genes,
        "tags": tags,
        "n_variants": len(records),
        "n_distinct_pmids": len(distinct_pmids),
        "variants_with_no_pmid_excluded": int(no_pmid),
        "max_new_date": str(max_new_date) if max_new_date else None,
        "note": "Frozen HGMD-derived benchmark snapshot. Internal/licensed — do not redistribute.",
    }
    Path(str(out_path) + ".meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        f"Wrote {out_path}  ({len(records)} variants, {len(distinct_pmids)} distinct PMIDs, "
        f"tags={tags})\n  {no_pmid} in-scope variant(s) had no citable PMID and were excluded "
        f"(reported in {out_path.name}.meta.json).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
