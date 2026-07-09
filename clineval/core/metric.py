"""Metric base class, evaluation context, and a task-keyed registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from clineval.core.schema import MetricResult, PredictionRecord


class EvalContext:
    """Shared state passed to every metric (loaded ontology + config)."""

    def __init__(self, ontology: object | None = None, config: dict | None = None) -> None:
        self.ontology = ontology
        self.config = config or {}


class Metric(ABC):
    """A metric computes a MetricResult over a list of records."""

    name: str = "metric"

    @abstractmethod
    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        raise NotImplementedError


_REGISTRY: dict[str, list[type[Metric]]] = {}


def register_metric(task: str) -> Callable[[type[Metric]], type[Metric]]:
    """Class decorator: register a Metric subclass under a task name."""

    def decorator(cls: type[Metric]) -> type[Metric]:
        bucket = _REGISTRY.setdefault(task, [])
        if cls not in bucket:
            bucket.append(cls)
        return cls

    return decorator


def get_metrics(task: str) -> list[Metric]:
    """Instantiate the metrics registered for a task."""
    return [cls() for cls in _REGISTRY.get(task, [])]


def macro_average(
    per_doc: dict[str, dict[str, float]], keys: list[str]
) -> dict[str, float]:
    """Mean of each key across documents (0.0 for each key if no documents)."""
    n = len(per_doc)
    if n == 0:
        return {k: 0.0 for k in keys}
    return {k: sum(d.get(k, 0.0) for d in per_doc.values()) / n for k in keys}
