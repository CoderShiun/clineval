"""Shared, task-agnostic data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PredictionRecord:
    """One evaluation unit. For Module A, gold_reference/system_output are HPO IDs."""

    id: str
    input_text: str
    gold_reference: list[str]
    system_output: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricResult:
    """Output of a single Metric across the dataset."""

    name: str
    aggregate: dict[str, float]
    per_document: dict[str, dict[str, float]] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OntologyAlignment:
    """Record of HPO version-alignment applied before scoring."""

    hpo_version: str
    ic_basis: str
    alt_ids_resolved: int
    obsolete_flagged: int
    obsolete_ids: list[str]
    policy: str
    unknown_flagged: int = 0
    unknown_ids: list[str] = field(default_factory=list)
    pyhpo_version: str = ""


@dataclass
class EvaluationResult:
    """Everything the report renderer needs."""

    task: str
    dataset: str
    n_documents: int
    model: str
    timestamp: str
    metrics: list[MetricResult]
    alignment: OntologyAlignment
    records: list[PredictionRecord] = field(default_factory=list)

    def metric(self, name: str) -> MetricResult | None:
        for m in self.metrics:
            if m.name == name:
                return m
        return None
