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
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{self.path} line {n}: invalid JSON ({exc})") from exc
                try:
                    record = PredictionRecord(
                        id=str(obj["id"]),
                        input_text=obj.get("input_text", ""),
                        gold_reference=list(obj["gold_reference"]),
                        system_output=list(obj.get("system_output", [])),
                        metadata=dict(obj.get("metadata", {})),
                    )
                except KeyError as exc:
                    if exc.args and exc.args[0] == "gold_reference":
                        raise ValueError(
                            f"{self.path} line {n}: record {obj.get('id', '?')!r} is "
                            "missing required field 'gold_reference'"
                        ) from exc
                    raise
                records.append(record)
        return records
