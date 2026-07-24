"""variant_retrieval metric: set P/R/F1 (macro + micro) + yield + missed detail.

These are scores of CONCORDANCE WITH HGMD, not coverage of the true literature: the gold is
HGMD's curated citation list (broad — primary + additional + extra refs, not primary-only), so
recall has a hard ceiling at HGMD and precision charges any paper outside HGMD's list (some of
which may be correct papers HGMD omitted) as a false positive. Macro AND micro are both reported
(the report shows both) so a skewed gold-size distribution can't be read from one number alone.
Variant-level = document level; reuses the shared ``core.metric.set_prf``.
"""

from __future__ import annotations

from clineval.core.metric import (
    EvalContext,
    Metric,
    harmonic,
    macro_average,
    register_metric,
    set_prf,
)
from clineval.core.schema import MetricResult, PredictionRecord


@register_metric("variant_retrieval")
class RetrievalMetric(Metric):
    """Per-variant recall/precision/F1 over PMID sets: macro + micro, HGMD-concordance."""

    name = "retrieval_prf"

    def compute(self, records: list[PredictionRecord], context: EvalContext) -> MetricResult:
        """Macro + micro P/R/F1 + mean_yield over scored variants; details = missed +
        unresolved + degraded (degraded variants are excluded from the aggregates)."""
        per_doc: dict[str, dict[str, float]] = {}
        missed: dict[str, list[str]] = {}
        unresolved: list[str] = []
        degraded: list[str] = []
        tp = fp = fn = 0
        for r in records:
            if r.metadata.get("retrieval_status", "ok") != "ok":
                # Retrieval failed (API error) or was uncovered (cache miss): its zero is a
                # retrieval artifact, not evidence, so EXCLUDE it from the scored aggregates.
                degraded.append(r.id)
                continue
            gold, pred = set(r.gold_reference), set(r.system_output)
            d_tp, d_fn, d_fp = len(gold & pred), len(gold - pred), len(pred - gold)
            per_doc[r.id] = {
                **set_prf(r.gold_reference, r.system_output),
                "gold_n": float(len(gold)), "retrieved_n": float(len(pred)),
                "found_n": float(d_tp), "missed_n": float(d_fn), "extra_n": float(d_fp),
            }
            if gold - pred:
                missed[r.id] = sorted(gold - pred)   # the clinically important false negatives
            if r.metadata.get("resolved") is False:
                unresolved.append(r.id)              # flagged (not dropped) in Stage 1
            tp, fp, fn = tp + d_tp, fp + d_fp, fn + d_fn

        aggregate = macro_average(per_doc, ["precision", "recall", "f1"])
        aggregate["mean_yield"] = (
            sum(d["retrieved_n"] for d in per_doc.values()) / len(per_doc) if per_doc else 0.0
        )
        micro_p = tp / (tp + fp) if (tp + fp) else 0.0
        micro_r = tp / (tp + fn) if (tp + fn) else 0.0
        aggregate["micro_precision"] = micro_p
        aggregate["micro_recall"] = micro_r
        aggregate["micro_f1"] = harmonic(micro_p, micro_r)   # reuse the shared harmonic
        return MetricResult(
            name=self.name, aggregate=aggregate, per_document=per_doc,
            details={"missed": missed, "unresolved": unresolved, "degraded": degraded},
        )
