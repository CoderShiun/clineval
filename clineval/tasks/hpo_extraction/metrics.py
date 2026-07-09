"""Module A metrics: Tier 1 (exact), Tier 2 (semantic), Tier 3 (clinical).

Tiers 2 and 3 (added in later tasks) read the loaded ontology from
``context.ontology``; Tier 1 needs no ontology.
"""

from __future__ import annotations

from clineval.core.metric import EvalContext, Metric, macro_average, register_metric
from clineval.core.schema import MetricResult, PredictionRecord


def harmonic(precision: float, recall: float) -> float:
    """Harmonic mean; 0.0 when both are 0."""
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _exact_prf(gold: list[str], pred: list[str]) -> dict[str, float]:
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


@register_metric("hpo_extraction")
class Tier1ExactMetric(Metric):
    """Exact-match precision/recall/F1 on HPO concept IDs (document-level macro)."""

    name = "tier1_exact"

    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        per_doc = {r.id: _exact_prf(r.gold_reference, r.system_output) for r in records}
        aggregate = macro_average(per_doc, ["precision", "recall", "f1"])
        return MetricResult(name=self.name, aggregate=aggregate, per_document=per_doc)
