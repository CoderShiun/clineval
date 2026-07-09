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


_SEM_KEYS = [
    "sem_precision", "sem_recall", "sem_f1",
    "sem_precision_icw", "sem_recall_icw", "sem_f1_icw", "bma",
]


def _best(ontology, term_id: str, group: list[str], method: str) -> float:
    return max((ontology.similarity(term_id, g, method=method) for g in group), default=0.0)


def _semantic_doc(ontology, gold: list[str], pred: list[str], method: str) -> dict[str, float]:
    if not gold and not pred:
        return {k: 1.0 for k in _SEM_KEYS}

    if pred:
        sem_p = sum(_best(ontology, p, gold, method) for p in pred) / len(pred)
    else:
        sem_p = 1.0 if not gold else 0.0
    if gold:
        sem_r = sum(_best(ontology, g, pred, method) for g in gold) / len(gold)
    else:
        sem_r = 1.0 if not pred else 0.0

    def ic_weighted(items: list[str], other: list[str]) -> float:
        num = den = 0.0
        for x in items:
            weight = ontology.ic(x)
            num += weight * _best(ontology, x, other, method)
            den += weight
        return num / den if den else 0.0

    if pred:
        sem_p_icw = ic_weighted(pred, gold)
    else:
        sem_p_icw = 1.0 if not gold else 0.0
    if gold:
        sem_r_icw = ic_weighted(gold, pred)
    else:
        sem_r_icw = 1.0 if not pred else 0.0

    return {
        "sem_precision": sem_p,
        "sem_recall": sem_r,
        "sem_f1": harmonic(sem_p, sem_r),
        "sem_precision_icw": sem_p_icw,
        "sem_recall_icw": sem_r_icw,
        "sem_f1_icw": harmonic(sem_p_icw, sem_r_icw),
        "bma": (sem_p + sem_r) / 2,
    }


@register_metric("hpo_extraction")
class Tier2SemanticMetric(Metric):
    """Semantic / hierarchy-aware P/R/F1 (best-match on Lin) + IC-weighted + BMA."""

    name = "tier2_semantic"

    def compute(
        self, records: list[PredictionRecord], context: EvalContext
    ) -> MetricResult:
        method = context.config.get("similarity_method", "lin")
        per_doc = {
            r.id: _semantic_doc(context.ontology, r.gold_reference, r.system_output, method)
            for r in records
        }
        aggregate = macro_average(per_doc, _SEM_KEYS)
        return MetricResult(name=self.name, aggregate=aggregate, per_document=per_doc)
