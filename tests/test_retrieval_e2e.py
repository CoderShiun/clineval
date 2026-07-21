import pytest

import clineval.tasks.variant_retrieval  # noqa: F401  (registers the retrieval metric)
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
from clineval.tasks.variant_retrieval.datasets import RYR1BenchmarkLoader
from clineval.tasks.variant_retrieval.report import render_retrieval_report
from clineval.tasks.variant_retrieval.retriever import CachedRetriever


def test_end_to_end_cached_offline():
    # loader -> cached retriever -> metric -> report, entirely offline on committed fixtures.
    records = RYR1BenchmarkLoader().load()
    retriever = CachedRetriever("examples/data/cached_retrieval.jsonl")
    for rec in records:
        rec.system_output = retriever.extract(rec)
    result = evaluate("variant_retrieval", records, EvalContext(),
                      dataset="ryr1", model="cached", timestamp="2026-07-16T00:00:00+00:00")
    md = render_retrieval_report(result)
    assert "Variant Literature Retrieval Report" in md
    metric = result.metric("retrieval_prf")
    # Pin the headline: 2 of 3 seeds fully retrieved, the intronic one missed -> macro
    # recall 2/3, micro 3/4. A no-op retriever (all []) would score 0 and fail this.
    assert metric.aggregate["recall"] == pytest.approx(2 / 3)
    assert metric.aggregate["micro_recall"] == 0.75
    assert metric.per_document["NM_000540.3:c.1840C>T"]["recall"] == 1.0
    # flag-not-drop: the intronic seed is flagged unresolved AND still scored (kept in the
    # denominator and counted as a miss), never silently dropped.
    assert result.n_documents == 3 and len(metric.per_document) == 3
    assert "NM_000540.3:c.1840+1G>A" in metric.details["unresolved"]
    assert metric.details["missed"]["NM_000540.3:c.1840+1G>A"] == ["99000004"]
    # Every committed demo gold PMID is synthetic (licence firewall): the 8-digit reserved
    # range above the real-PMID ceiling, so no real curated ID can pass this guard.
    assert all(int(p) >= 99000000 for r in records for p in r.gold_reference)
    # ...and so is every PMID in the committed CACHE fixture (now in system_output).
    assert all(int(p) >= 99000000 for r in records for p in r.system_output)
