import pytest

from clineval.core.schema import PredictionRecord
from clineval.pipeline.models import PipelineProvenance, RetrievalResult, VariantForms
from clineval.tasks.variant_retrieval.retriever import CachedRetriever, DatasetRetriever, PipelineRetriever


def test_dataset_retriever_passes_through():
    rec = PredictionRecord(id="v", input_text="v", gold_reference=["1"], system_output=["1", "2"])
    r = DatasetRetriever()
    out = r.extract(rec)
    assert out == ["1", "2"] and out is not rec.system_output and r.mode == "dataset"


def test_cached_retriever_replays_and_sets_metadata(tmp_path):
    p = tmp_path / "cache.jsonl"
    p.write_text(
        '{"id": "v1", "pmids": ["1", "2"], "resolved": false, "notes": ["hard case"]}\n'
        "\n"  # blank line ignored
        '{"id": "v2", "pmids": ["3"], "resolved": true}\n',
        encoding="utf-8",
    )
    r = CachedRetriever(str(p))
    assert r.covers("v1") and not r.covers("zzz")

    rec1 = PredictionRecord(id="v1", input_text="v1", gold_reference=["1"])
    assert r.extract(rec1) == ["1", "2"]
    assert rec1.metadata["resolved"] is False and rec1.metadata["notes"] == ["hard case"]

    rec2 = PredictionRecord(id="v2", input_text="v2", gold_reference=["3"])   # resolved, no notes
    assert r.extract(rec2) == ["3"]
    assert rec2.metadata.get("resolved") is True and "notes" not in rec2.metadata

    miss = PredictionRecord(id="zzz", input_text="zzz", gold_reference=[])    # not in cache
    assert r.extract(miss) == []


def test_cached_retriever_does_not_alias_the_cache_notes(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text('{"id": "v1", "pmids": ["1"], "notes": ["a"]}\n', encoding="utf-8")
    r = CachedRetriever(str(p))
    rec = PredictionRecord(id="v1", input_text="v1", gold_reference=[])
    r.extract(rec)
    rec.metadata["notes"].append("mutated")          # must not corrupt the cache
    rec2 = PredictionRecord(id="v1", input_text="v1", gold_reference=[])
    r.extract(rec2)
    assert rec2.metadata["notes"] == ["a"]


@pytest.mark.parametrize(
    "line, match",
    [
        ("{not valid json}", "malformed cache line 1"),
        ("[1, 2, 3]", "not a JSON object"),
        ('{"pmids": ["1"]}', "missing required 'id'"),
    ],
)
def test_cached_retriever_rejects_malformed_lines(tmp_path, line, match):
    p = tmp_path / "c.jsonl"
    p.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        CachedRetriever(str(p))


def test_pipeline_retriever_runs_both_stages_and_records_provenance():
    def normalize_fn(hgvs):
        return VariantForms(
            input=hgvs, forms=["p.R614C"], resolved=True, xrefs={"rsid": "rs1"}, notes=["stage1 note"],
            provenance=PipelineProvenance(vvdb_version="vvdb_2025_3", sources=["variantvalidator", "myvariant"]),
        )

    def retrieve_fn(forms):
        return RetrievalResult(
            variant=forms.input, pmids=["111", "222"], papers=[], notes=["stage2 note"],
            provenance=PipelineProvenance(vvdb_version="vvdb_2025_3", sources=["litvar2", "eutils"]),
        )

    r = PipelineRetriever(normalize_fn, retrieve_fn)
    assert r.mode == "live"
    rec = PredictionRecord(
        id="NM_000540.3:c.1840C>T", input_text="NM_000540.3:c.1840C>T", gold_reference=["111"]
    )
    assert r.extract(rec) == ["111", "222"]
    assert rec.metadata["resolved"] is True
    assert rec.metadata["notes"] == ["stage1 note", "stage2 note"]        # both stages' notes
    assert rec.metadata["provenance"]["vvdb_version"] == "vvdb_2025_3"
    # Evidence snapshot names ALL tools used (normalization + retrieval), no duplicates.
    assert rec.metadata["provenance"]["sources"] == ["variantvalidator", "myvariant", "litvar2", "eutils"]
