import pytest

from clineval.core.report import render_report
from clineval.core.schema import (
    EvaluationResult,
    MetricResult,
    OntologyAlignment,
    PredictionRecord,
)


def _result():
    tier1 = MetricResult(
        name="tier1_exact",
        aggregate={"precision": 0.5, "recall": 0.5, "f1": 0.5},
        per_document={"r1": {"precision": 0.5, "recall": 0.5, "f1": 0.5}},
    )
    tier2 = MetricResult(
        name="tier2_semantic",
        aggregate={"sem_precision": 0.8, "sem_recall": 0.8, "sem_f1": 0.8,
                   "sem_precision_icw": 0.8, "sem_recall_icw": 0.8, "sem_f1_icw": 0.8,
                   "bma": 0.8},
        per_document={"r1": {"sem_f1": 0.8, "bma": 0.8}},
    )
    tier3 = MetricResult(
        name="tier3_clinical",
        aggregate={"missed": 1.0, "spurious": 1.0, "wrong_granularity": 1.0, "wrong_term": 0.0},
        details={"flags": [{"record": "r1", "type": "missed_high_ic",
                            "hpo_id": "HP:0011682", "ic": 5.1}]},
    )
    align = OntologyAlignment(
        "2025-01-01", "omim", 2, 1, ["HP:0000999"], "policy text",
        unknown_flagged=2, unknown_ids=["HP:9999999"],
    )
    return EvaluationResult(
        task="hpo_extraction", dataset="synthetic", n_documents=1, model="cached:qwen",
        timestamp="2026-07-09T00:00:00+00:00", metrics=[tier1, tier2, tier3],
        alignment=align,
        records=[PredictionRecord(id="r1", input_text="", gold_reference=["HP:0011682"],
                                  system_output=["HP:0001629"])],
    )


def test_report_contains_key_sections():
    md = render_report(_result())
    assert "# ClinEval Report" in md
    assert "Regulatory Evidence Mapping" in md
    assert "Ontology Alignment" in md
    assert "ISO 15189:2022" in md
    assert "cached:qwen" in md          # model provenance
    assert "omim" in md                 # IC basis recorded
    # exact-vs-semantic gap highlighted (0.80 - 0.50 = 0.30)
    assert "0.300" in md or "0.30" in md
    assert "missed_high_ic" in md
    assert "not legal" in md.lower()    # disclaimer
    assert "(HP:0000999)" in md                 # obsolete ids shown
    assert "Unknown/unrecognized IDs:" in md
    assert "(HP:9999999)" in md                 # unknown ids shown
    assert "\n- **Unknown/unrecognized IDs:**" in md  # own line
    assert "\n- **Policy:**" in md              # Policy stays on its own line


def test_report_ends_with_trailing_newline():
    md = render_report(_result())
    assert md.endswith("\n")


def test_report_renders_none_when_no_flags():
    result = _result()
    tier3 = result.metric("tier3_clinical")
    tier3.details = {"flags": []}
    md = render_report(result)
    assert "## Clinical-significance flags\n\nNone.\n" in md


def test_metric_raises_when_required_metric_missing():
    result = _result()
    result.metrics = [m for m in result.metrics if m.name != "tier2_semantic"]
    with pytest.raises(ValueError, match="tier2_semantic"):
        render_report(result)
