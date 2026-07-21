"""Run a task's registered metrics over records and package the result."""

from __future__ import annotations

from typing import Any

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
    alignment: OntologyAlignment | None = None,
    provenance: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Evaluate ``records`` with every metric registered under ``task``.

    ``alignment`` is for ontology tasks (HPO); non-ontology tasks (e.g. variant
    retrieval) pass ``provenance`` instead. Both are optional and independent.
    """
    metrics = get_metrics(task)
    if not metrics:
        raise ValueError(
            f"no metrics registered for task {task!r} — import the task package "
            "(e.g. `import clineval.tasks.hpo_extraction`) so its metrics register"
        )
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
        provenance=provenance or {},
    )
