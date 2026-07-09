"""Fetch GSC+ (BiolarkGSC+) and convert it to ClinEval's JSONL schema.

Output (git-ignored): datasets/gsc_plus/gsc_plus.jsonl with one record per line:
{"id", "input_text", "gold_reference": ["HP:0000000", ...]}.

The download URL and license MUST be confirmed before use (see datasets/README.md).
The converter is intentionally small and isolated so that, if the real GSC+ layout
differs from the assumed one, only ``convert`` and the test fixture need adjusting.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Verify this against the official GSC+ distribution before running download().
GSC_PLUS_URL = "https://github.com/lasigeBioTM/IHP/raw/master/GSC%2B.zip"
DEFAULT_DEST = "datasets/gsc_plus"


def convert(raw_dir: str, out_path: str) -> int:
    """Convert an extracted GSC+ directory to normalized JSONL. Returns record count.

    Assumes: for each document ``<ID>.txt`` (the abstract) there are annotation
    rows in ``annotations.tsv`` with tab-separated columns
    ``id, start, end, hpo_id, mention``. Adjust here if the real layout differs.
    """
    from clineval.tasks.hpo_extraction.adapters import normalize_hpo_id

    raw = Path(raw_dir)
    gold: dict[str, list[str]] = defaultdict(list)
    ann_file = raw / "annotations.tsv"
    if ann_file.exists():
        for row in ann_file.read_text(encoding="utf-8").splitlines():
            row = row.strip()
            if not row:
                continue
            parts = row.split("\t")
            if len(parts) < 4:
                continue
            doc_id, hpo_raw = parts[0], parts[3]
            nid = normalize_hpo_id(hpo_raw)
            if nid and nid not in gold[doc_id]:
                gold[doc_id].append(nid)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8") as fh:
        for txt in sorted(raw.glob("*.txt")):
            doc_id = txt.stem
            record = {
                "id": doc_id,
                "input_text": txt.read_text(encoding="utf-8").strip(),
                "gold_reference": gold.get(doc_id, []),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    total_ann = sum(len(v) for v in gold.values())
    if count and total_ann == 0:
        raise ValueError(
            "download_gsc.convert: parsed 0 HPO annotations from "
            f"{raw_dir!r} though .txt docs were found — the annotation format/path "
            "likely does not match the assumed 'annotations.tsv' layout; see the "
            "module docstring."
        )
    return count


def download(dest: str = DEFAULT_DEST) -> None:
    """Download + extract GSC+ into ``dest`` and convert to gsc_plus.jsonl.

    Network fetch is intentionally explicit so licensing can be reviewed first.
    """
    import io
    import urllib.request
    import zipfile

    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading GSC+ from {GSC_PLUS_URL} ...")
    # URL must be verified before use — see module docstring.
    with urllib.request.urlopen(GSC_PLUS_URL, timeout=60) as resp:  # noqa: S310
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest_dir / "raw")
    n = convert(str(dest_dir / "raw"), str(dest_dir / "gsc_plus.jsonl"))
    print(f"Wrote {n} records to {dest_dir / 'gsc_plus.jsonl'}")


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DEST)
