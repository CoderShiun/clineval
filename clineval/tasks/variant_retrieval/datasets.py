"""Truth-set loaders for the variant_retrieval task.

Both loaders read the shared JSONL record schema and coerce PMIDs to strings so
gold references compare cleanly against the retriever's string PMIDs. The RYR1
loader points at a small *synthetic* committed fixture (zero-setup demo); the HGMD
loader points at git-ignored, licence-gated benchmark truth built by the lab.
"""

from __future__ import annotations

from pathlib import Path

from clineval.core.dataset import DatasetLoader, JSONLDatasetLoader
from clineval.core.schema import PredictionRecord


def _coerce_pmids(records: list[PredictionRecord]) -> list[PredictionRecord]:
    """Coerce each record's gold PMIDs to strings, in place.

    Safe to mutate: ``JSONLDatasetLoader`` builds fresh records and lists on every
    ``load()``, so there is no shared state to alias.
    """
    for rec in records:
        rec.gold_reference = [str(p) for p in rec.gold_reference]
    return records


class RYR1BenchmarkLoader(DatasetLoader):
    """RYR1 demo benchmark: variant -> known gold PMIDs (committed, synthetic, public IDs)."""

    def __init__(self, path: str = "examples/data/ryr1_gold.jsonl") -> None:
        self.path = path

    def load(self) -> list[PredictionRecord]:
        return _coerce_pmids(JSONLDatasetLoader(self.path).load())


class HgmdGoldLoader(DatasetLoader):
    """Lab HGMD-derived panel gold (git-ignored; never committed). Drop-in second dataset."""

    def __init__(self, path: str = "datasets/hgmd_gold/ryr1_gold.jsonl") -> None:
        self.path = path

    def load(self) -> list[PredictionRecord]:
        if not Path(self.path).exists():
            raise FileNotFoundError(
                f"HGMD gold not found at {self.path}. Export it from HGMD while the "
                "licence is active (see datasets/README.md), then re-run. The pipeline "
                "itself never calls HGMD — this is benchmark truth only."
            )
        return _coerce_pmids(JSONLDatasetLoader(self.path).load())
