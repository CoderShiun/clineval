"""Task-agnostic dataset loading."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from clineval.core.schema import PredictionRecord


class DatasetLoader(ABC):
    """A dataset loader yields PredictionRecords for evaluation."""

    @abstractmethod
    def load(self) -> list[PredictionRecord]:
        raise NotImplementedError


class JSONLDatasetLoader(DatasetLoader):
    """Load user-supplied records from a JSON Lines file.

    Each line: {"id", "input_text", "gold_reference", [optional] "system_output",
    [optional] "metadata"}.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> list[PredictionRecord]:
        records: list[PredictionRecord] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                records.append(
                    PredictionRecord(
                        id=str(obj["id"]),
                        input_text=obj.get("input_text", ""),
                        gold_reference=list(obj["gold_reference"]),
                        system_output=list(obj.get("system_output", [])),
                        metadata=dict(obj.get("metadata", {})),
                    )
                )
        return records
