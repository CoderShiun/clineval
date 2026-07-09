"""Run a task's registered metrics over records and package the result."""

from __future__ import annotations

from clineval.core.metric import EvalContext, get_metrics
from clineval.core.schema import EvaluationResult, OntologyAlignment, PredictionRecord


def evaluate(
    task: str,
    records: list[PredictionRecord],
    context: EvalContext,
    *,
    dataset: str,
    model: str,
    timestamp: str,
    alignment: OntologyAlignment,
) -> EvaluationResult:
    """Evaluate ``records`` with every metric registered under ``task``."""
    metrics = get_metrics(task)
    results = [m.compute(records, context) for m in metrics]
    return EvaluationResult(
        task=task,
        dataset=dataset,
        n_documents=len(records),
        model=model,
        timestamp=timestamp,
        metrics=results,
        alignment=alignment,
        records=records,
    )
