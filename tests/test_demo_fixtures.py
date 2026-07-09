"""End-to-end check on the committed demo fixtures: the offline synthetic run
must show a positive exact->semantic F1 gap and exercise every taxonomy category.
This locks the portfolio headline against fixture rot."""

import clineval.tasks.hpo_extraction  # noqa: F401  (registers metrics)
from clineval.core.dataset import JSONLDatasetLoader
from clineval.core.evaluator import evaluate
from clineval.core.metric import EvalContext
from clineval.tasks.hpo_extraction import adapters
from clineval.tasks.hpo_extraction.extractor import CachedExtractor


def test_committed_fixtures_show_gap_and_all_taxonomy(ontology):
    records = JSONLDatasetLoader("examples/data/synthetic_mini.jsonl").load()
    for r in records:
        adapters.normalize_record(r)
    extractor = CachedExtractor("examples/data/cached_predictions.jsonl")
    for r in records:
        r.system_output = extractor.extract(r)
        adapters.normalize_record(r)
    records, alignment = adapters.align_records(records, ontology)
    result = evaluate(
        "hpo_extraction", records, EvalContext(ontology=ontology),
        dataset="synthetic", model=f"cached:{extractor.model}",
        timestamp="2026-07-09T00:00:00+00:00", alignment=alignment,
    )
    exact_f1 = result.metric("tier1_exact").aggregate["f1"]
    sem_f1 = result.metric("tier2_semantic").aggregate["sem_f1"]
    assert exact_f1 < sem_f1  # semantic partial credit lifts F1 above exact
    tax = result.metric("tier3_clinical").aggregate
    for key in ("missed", "wrong_granularity", "wrong_term", "spurious"):
        assert tax[key] > 0, f"taxonomy category {key} should be exercised"
