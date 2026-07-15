"""Fetch GSC+ (BiolarkGSC+) and convert it to ClinEval's JSONL schema.

Source: the GSC+ gold-standard corpus is distributed inside the PhenoTagger
project's ``data/corpus.zip`` (``corpus/GSC/GSCplus_dev_gold.tsv`` and
``GSCplus_test_gold.tsv``). GSC+ is 228 PubMed abstracts manually annotated with
HPO terms (Lobo et al., 2017); PhenoTagger splits it into a dev and a test file,
which this script combines.

Format of each GSCplus_*_gold.tsv (PubTator-style, blank-line separated blocks):

    <PMID>
    <title + abstract text on one line>
    <start>\t<end>\t<mention>\t<HP:id>
    <start>\t<end>\t<mention>\t<HP:id>
    ...
    <blank line>

Output (git-ignored): ``datasets/gsc_plus/gsc_plus.jsonl`` with one record per line:
``{"id", "input_text", "gold_reference": ["HP:0000000", ...]}``.

Licensing: the corpus is publicly redistributed via PhenoTagger (NCBI). Confirm
the licence terms for *your* use before relying on it; ClinEval downloads it at
runtime and never commits the data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# GSC+ ships inside PhenoTagger's corpus.zip (public, NCBI). See module docstring.
GSC_PLUS_URL = "https://raw.githubusercontent.com/ncbi-nlp/PhenoTagger/master/data/corpus.zip"
DEFAULT_DEST = "datasets/gsc_plus"


def _parse_gscplus_file(path: Path, normalize_hpo_id) -> list[dict]:
    """Parse one PubTator-style GSCplus_*_gold.tsv into record dicts."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    records: list[dict] = []
    for block in text.strip("\n").split("\n\n"):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        pmid = lines[0].strip()
        # Text lines have no tab; annotation lines are tab-delimited.
        text_lines = [ln.strip() for ln in lines[1:] if "\t" not in ln]
        ann_lines = [ln for ln in lines[1:] if "\t" in ln]
        gold: list[str] = []
        for ln in ann_lines:
            nid = None
            for col in ln.split("\t"):  # HPO id is the last column; scan to be robust
                nid = normalize_hpo_id(col)
                if nid:
                    break
            if nid and nid not in gold:
                gold.append(nid)
        records.append(
            {"id": pmid, "input_text": " ".join(text_lines), "gold_reference": gold}
        )
    return records


def convert(raw_dir: str, out_path: str) -> int:
    """Convert extracted GSC+ ``GSCplus_*_gold.tsv`` files to normalized JSONL.

    Searches ``raw_dir`` recursively for ``GSCplus_*_gold.tsv`` (dev + test),
    combines them (deduping by PMID), and writes one JSON record per document.
    Returns the record count.
    """
    from clineval.tasks.hpo_extraction.adapters import normalize_hpo_id

    files = sorted(Path(raw_dir).rglob("GSCplus_*_gold.tsv"))
    records: list[dict] = []
    seen: set[str] = set()
    for f in files:
        for rec in _parse_gscplus_file(f, normalize_hpo_id):
            if rec["id"] in seen:
                continue
            seen.add(rec["id"])
            records.append(rec)

    if not records:
        raise ValueError(
            f"download_gsc.convert: found no GSCplus_*_gold.tsv documents under "
            f"{raw_dir!r} — the extracted layout likely does not match; see the "
            "module docstring."
        )
    if sum(len(r["gold_reference"]) for r in records) == 0:
        raise ValueError(
            f"download_gsc.convert: parsed 0 HPO annotations from {raw_dir!r} though "
            "documents were found — the annotation format likely does not match; see "
            "the module docstring."
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)


def download(dest: str = DEFAULT_DEST) -> None:
    """Download + extract the corpus and convert GSC+ to gsc_plus.jsonl."""
    import io
    import urllib.request
    import zipfile

    dest_dir = Path(dest)
    raw = dest_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    print(f"Downloading GSC+ (via PhenoTagger corpus) from {GSC_PLUS_URL} ...")
    with urllib.request.urlopen(GSC_PLUS_URL, timeout=120) as resp:  # noqa: S310
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(raw)
    n = convert(str(raw), str(dest_dir / "gsc_plus.jsonl"))
    print(f"Wrote {n} GSC+ documents to {dest_dir / 'gsc_plus.jsonl'}")


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DEST)
