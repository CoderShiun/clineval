"""System-under-test adapters: the pipeline seen through ClinEval's Extractor hole.

Each adapter fills a record's ``system_output`` with retrieved PMIDs: ``PipelineRetriever``
runs Stages 1-2 live, ``CachedRetriever`` replays committed outputs (offline, deterministic
regression gate), and ``DatasetRetriever`` scores predictions already present in the record.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable

from clineval.core.schema import PredictionRecord
from clineval.pipeline.models import RetrievalResult, VariantForms


class DatasetRetriever:
    """Score the PMIDs already present in each record's ``system_output``."""

    mode = "dataset"

    def extract(self, record: PredictionRecord) -> list[str]:
        return list(record.system_output)


class CachedRetriever:
    """Replay committed pipeline outputs keyed by variant id (offline, deterministic)."""

    def __init__(self, path: str) -> None:
        self.mode = f"cached:{path}"
        self._by_id: dict[str, dict] = {}
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"malformed cache line {n} in {path}: {exc}") from exc
                if not isinstance(obj, dict):
                    raise ValueError(f"malformed cache line {n} in {path}: not a JSON object")
                if "id" not in obj:
                    raise ValueError(f"malformed cache line {n} in {path}: missing required 'id'")
                self._by_id[str(obj["id"])] = obj

    def covers(self, record_id: str) -> bool:
        return record_id in self._by_id

    def extract(self, record: PredictionRecord) -> list[str]:
        obj = self._by_id.get(record.id, {})
        if "resolved" in obj:
            record.metadata["resolved"] = obj["resolved"]
        if "notes" in obj:
            record.metadata["notes"] = list(obj["notes"])   # copy, don't alias the cache's list
        return [str(p) for p in obj.get("pmids", [])]


class PipelineRetriever:
    """Run Stages 1->2 live for each record's variant, recording provenance into metadata."""

    mode = "live"

    def __init__(
        self,
        normalize_fn: Callable[[str], VariantForms],
        retrieve_fn: Callable[[VariantForms], RetrievalResult],
    ) -> None:
        self._normalize = normalize_fn
        self._retrieve = retrieve_fn

    def extract(self, record: PredictionRecord) -> list[str]:
        forms = self._normalize(record.id)
        record.metadata["resolved"] = forms.resolved
        record.metadata["notes"] = list(forms.notes)
        result = self._retrieve(forms)
        record.metadata["notes"].extend(result.notes)
        # Evidence snapshot: the retrieval-side provenance (versions + [litvar2, eutils])
        # unioned with the Stage-1 sources, so the IVDR record names ALL the tools used.
        prov = asdict(result.provenance)
        prov["sources"] = list(dict.fromkeys([*forms.provenance.sources, *result.provenance.sources]))
        record.metadata["provenance"] = prov
        return list(result.pmids)
