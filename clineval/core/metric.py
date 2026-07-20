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
        if cls in bucket:
            return cls
        if any(existing.name == cls.name for existing in bucket):
            raise ValueError(
                f"metric name {cls.name!r} is already registered for task {task!r}"
            )
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


def harmonic(precision: float, recall: float) -> float:
    """Harmonic mean of precision and recall; 0.0 when both are 0."""
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def set_prf(gold: list[str], pred: list[str]) -> dict[str, float]:
    """Set-based precision/recall/F1 over string IDs (PMIDs, HPO IDs, ...).

    The shared, task-agnostic scorer reused by every set-membership task (HPO
    term extraction, variant→PMID retrieval, ...) so the maths lives in one place.

    Empty-set convention (matches scikit-learn's default ``zero_division=0``): a
    side scores 1.0 only when BOTH gold and prediction are empty (correctly
    predicting "nothing here"); a one-sided empty case (one side empty, the other
    not) scores 0.0 on the affected metric rather than being excluded.
    """
    gold_set, pred_set = set(gold), set(pred)
    tp = len(gold_set & pred_set)
    if not pred_set:
        precision = 1.0 if not gold_set else 0.0
    else:
        precision = tp / len(pred_set)
    if not gold_set:
        recall = 1.0 if not pred_set else 0.0
    else:
        recall = tp / len(gold_set)
    return {"precision": precision, "recall": recall, "f1": harmonic(precision, recall)}
