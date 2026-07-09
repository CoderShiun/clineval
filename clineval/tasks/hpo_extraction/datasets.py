"""Dataset loaders for Module A.

GSC+ is fetched and converted to our JSONL schema by ``datasets/download_gsc.py``
(kept out of git). This loader reads that converted file. BioCreative VIII Track 3
is a documented fast-follow: add a ``BioCreativeLoader`` here as its own PR.
"""

from __future__ import annotations

from pathlib import Path

from clineval.core.dataset import DatasetLoader, JSONLDatasetLoader
from clineval.core.schema import PredictionRecord
from clineval.tasks.hpo_extraction.adapters import normalize_hpo_ids


class GscPlusLoader(DatasetLoader):
    """Load GSC+ (BiolarkGSC+) from the converted JSONL produced by the downloader."""

    def __init__(self, root: str = "datasets/gsc_plus") -> None:
        self.path = Path(root) / "gsc_plus.jsonl"

    def load(self) -> list[PredictionRecord]:
        if not self.path.exists():
            raise FileNotFoundError(
                f"GSC+ not found at {self.path}. Fetch it first: "
                "`python datasets/download_gsc.py` (confirm the source license first)."
            )
        records = JSONLDatasetLoader(str(self.path)).load()
        for rec in records:
            rec.gold_reference = normalize_hpo_ids(rec.gold_reference)
        return records
