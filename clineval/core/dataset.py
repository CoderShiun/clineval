"""Task-agnostic dataset loading."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from clineval.core.schema import PredictionRecord


def _validate_id_list(values: list, field: str, path: str, n: int, rid: str) -> None:
    """Every element of an id list (gold_reference/system_output) must be a string or int.

    Rejects None/objects/floats/bools loudly — otherwise a downstream ``str(p)`` would
    silently launder them into phantom ids like ``"None"`` that can never be matched,
    deflating recall and corrupting the gold with no error.
    """
    for elem in values:
        if not (isinstance(elem, str) or (isinstance(elem, int) and not isinstance(elem, bool))):
            raise ValueError(
                f"{path} line {n}: record {rid!r} field {field!r} contains a non-string/int "
                f"element {elem!r} (type {type(elem).__name__}); ids must be strings or integers"
            )


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
        seen_ids: set[str] = set()
        with open(self.path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{self.path} line {n}: invalid JSON ({exc})") from exc
                if not isinstance(obj, dict):
                    raise ValueError(f"{self.path} line {n}: each line must be a JSON object")
                if "id" not in obj:
                    raise ValueError(f"{self.path} line {n}: missing required field 'id'")
                if "gold_reference" not in obj:
                    raise ValueError(
                        f"{self.path} line {n}: record {obj.get('id', '?')!r} is "
                        "missing required field 'gold_reference'"
                    )
                if not isinstance(obj["gold_reference"], list):
                    raise ValueError(
                        f"{self.path} line {n}: record {obj.get('id', '?')!r} field "
                        "'gold_reference' must be a list, got "
                        f"{type(obj['gold_reference']).__name__}"
                    )
                _validate_id_list(
                    obj["gold_reference"], "gold_reference", self.path, n, str(obj.get("id", "?"))
                )
                if "system_output" in obj and not isinstance(obj["system_output"], list):
                    raise ValueError(
                        f"{self.path} line {n}: record {obj.get('id', '?')!r} field "
                        "'system_output' must be a list, got "
                        f"{type(obj['system_output']).__name__}"
                    )
                if "system_output" in obj and isinstance(obj["system_output"], list):
                    _validate_id_list(
                        obj["system_output"], "system_output", self.path, n,
                        str(obj.get("id", "?")),
                    )
                if "metadata" in obj and not isinstance(obj["metadata"], dict):
                    raise ValueError(
                        f"{self.path} line {n}: record {obj.get('id', '?')!r} field "
                        "'metadata' must be an object, got "
                        f"{type(obj['metadata']).__name__}"
                    )
                rid = str(obj["id"])
                if rid in seen_ids:
                    raise ValueError(
                        f"{self.path} line {n}: duplicate record id {rid!r} "
                        "(record ids must be unique)"
                    )
                seen_ids.add(rid)
                record = PredictionRecord(
                    id=rid,
                    input_text=obj.get("input_text", ""),
                    gold_reference=list(obj["gold_reference"]),
                    system_output=list(obj.get("system_output", [])),
                    metadata=dict(obj.get("metadata", {})),
                )
                records.append(record)
        return records
