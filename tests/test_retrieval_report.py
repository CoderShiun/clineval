import pytest

import clineval.tasks.variant_retrieval  # noqa: F401  (registers the retrieval metric)
from clineval.core.metric import EvalContext
from clineval.core.schema import EvaluationResult, MetricResult, PredictionRecord
from clineval.tasks.variant_retrieval.metrics import RetrievalMetric
from clineval.tasks.variant_retrieval.report import render_retrieval_report


def _result(missed=None, unresolved=None):
    mr = MetricResult(
        name="retrieval_prf",
        aggregate={"precision": 0.8, "recall": 0.75, "f1": 0.77, "mean_yield": 2.0,
                   "micro_precision": 0.8, "micro_recall": 0.75, "micro_f1": 0.77},
        per_document={"v1": {"precision": 0.67, "recall": 1.0, "f1": 0.8, "gold_n": 2.0,
                             "retrieved_n": 3.0, "found_n": 2.0, "missed_n": 0.0, "extra_n": 1.0},
                      "v2": {"precision": 1.0, "recall": 0.5, "f1": 0.67, "gold_n": 2.0,
                             "retrieved_n": 1.0, "found_n": 1.0, "missed_n": 1.0, "extra_n": 0.0}},
        details={"missed": {"v2": ["4"]} if missed is None else missed,
                 "unresolved": ["v2"] if unresolved is None else unresolved},
    )
    return EvaluationResult(
        task="variant_retrieval", dataset="ryr1", n_documents=2, model="cached",
        timestamp="2026-07-16T00:00:00+00:00", metrics=[mr],
        records=[PredictionRecord(id="v1", input_text="v1", gold_reference=["1", "2"]),
                 PredictionRecord(id="v2", input_text="v2", gold_reference=["3", "4"])],
        provenance={"vvdb_version": "vvdb_2025_3", "cache_hit_rate": "2/2"},
    )


def test_report_has_key_sections():
    md = render_retrieval_report(_result())
    assert "# ClinEval — Variant Literature Retrieval Report" in md
    # Macro AND micro recall both shown and both bolded (equal prominence, not "the" number).
    assert md.count("**0.750**") >= 2
    assert "Missed evidence" in md and "v2" in md      # missed-evidence detail
    assert "Unresolved variants" in md                 # flag-not-drop section
    assert "vvdb_2025_3" in md                          # provenance snapshot
    assert "IVDR" in md                                 # regulatory mapping
    assert "not legal" in md.lower()                   # disclaimer
    # Full per-variant row pins column order (a precision<->recall swap would fail).
    assert "| v2 | 2 | 1 | 1 | 1 | 0.50 | 1.00 |" in md
    # Honest framing is a requirement, not decoration: concordance-not-coverage + the ceiling.
    assert "concordance with hgmd" in md.lower()
    assert "hard ceiling" in md.lower()
    assert "All variants retrieved cleanly" in md      # retrieval-integrity section (none degraded)
    # The provenance-present path must keep a blank line before the next heading (M1 fix).
    assert "cache_hit_rate=2/2\n\n## Concordance with HGMD" in md


def test_report_flags_degraded_retrieval():
    # A variant excluded from scoring for degraded retrieval must be surfaced (with the
    # exclusion stated), not read as "no literature exists".
    result = _result()
    result.metrics[0].details["degraded"] = ["v2"]
    md = render_retrieval_report(result)
    assert "DEGRADED retrieval" in md and "- v2" in md
    assert "excluded from the scores above" in md


def test_report_handles_clean_run_with_no_gaps():
    # Empty missed + unresolved must render the reassuring "None" branches, not crash.
    md = render_retrieval_report(_result(missed={}, unresolved=[]))
    assert "every gold reference was retrieved" in md
    assert "all variants normalized" in md


def test_report_renders_without_provenance():
    # No provenance -> the {% if provenance %} block is skipped, heading spacing intact.
    result = _result()
    result.provenance = {}
    md = render_retrieval_report(result)
    assert "**Provenance:**" not in md
    assert "\n\n## Concordance with HGMD" in md


def test_report_renders_from_real_metric_output():
    # End-to-end: run the actual metric and render, locking the metric->template key
    # contract so a renamed aggregate/per-doc key can't silently break real reports.
    records = [
        PredictionRecord(id="v1", input_text="v1", gold_reference=["1", "2"],
                         system_output=["1", "2", "9"], metadata={"resolved": True}),
        PredictionRecord(id="v2", input_text="v2", gold_reference=["3", "4"],
                         system_output=["3"], metadata={"resolved": False}),
    ]
    metric = RetrievalMetric().compute(records, EvalContext())
    result = EvaluationResult(
        task="variant_retrieval", dataset="ryr1", n_documents=2, model="cached",
        timestamp="2026-07-16T00:00:00+00:00", metrics=[metric], records=records,
        provenance={"vvdb_version": "vvdb_2025_3"},
    )
    md = render_retrieval_report(result)
    assert "**0.750**" in md                       # macro recall from the real metric
    assert "| v2 |" in md and "Missed evidence" in md and "v2" in md  # v2 missed PMID 4
    assert "Unresolved variants" in md and "v2" in md


def test_report_raises_without_metric():
    result = EvaluationResult(
        task="variant_retrieval", dataset="d", n_documents=0, model="m",
        timestamp="t", metrics=[],
    )
    with pytest.raises(ValueError, match="retrieval_prf"):
        render_retrieval_report(result)
