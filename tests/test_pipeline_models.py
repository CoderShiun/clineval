from clineval.pipeline.models import PaperRef, PipelineProvenance, RetrievalResult, VariantForms


def test_pipeline_provenance_defaults_and_isolation():
    p = PipelineProvenance()
    assert (p.vv_version, p.vvdb_version, p.vvta_version) == ("", "", "")
    assert p.sources == []
    # A mutable default must be per-instance, not shared across instances.
    p.sources.append("variantvalidator")
    assert PipelineProvenance().sources == []


def test_paper_ref_defaults():
    ref = PaperRef(pmid="123")
    assert ref.title == "" and ref.journal == "" and ref.matched_form == ""
    assert ref.year is None


def test_variant_forms_defaults_are_independent():
    a = VariantForms(input="x", forms=[], resolved=False, xrefs={})
    assert a.gene == "" and a.notes == [] and a.normalization_failed is False
    a.notes.append("flagged")
    a.provenance.sources.append("vv")
    b = VariantForms(input="y", forms=[], resolved=True, xrefs={})
    # Each instance gets its OWN notes list and its OWN PipelineProvenance
    # (field(default_factory=...)), so mutating one never leaks into another.
    assert b.notes == []
    assert b.provenance.sources == []
    assert isinstance(b.provenance, PipelineProvenance) and b.provenance is not a.provenance


def test_retrieval_result_holds_papers_with_isolated_defaults():
    result = RetrievalResult(
        variant="NM_000540.3:c.1840C>T",
        pmids=["99000001"],
        papers=[
            PaperRef(pmid="99000001", title="segregation study", journal="Anesthesiology",
                     year=1996, matched_form="p.R614C")
        ],
        provenance=PipelineProvenance(vvdb_version="vvdb_2025_3", sources=["litvar2"]),
    )
    assert result.papers[0].matched_form == "p.R614C"
    assert result.papers[0].year == 1996
    assert result.provenance.vvdb_version == "vvdb_2025_3"
    assert result.notes == []
    # Two default-constructed results do not share notes or provenance state.
    r1 = RetrievalResult(variant="v", pmids=[], papers=[])
    r1.notes.append("partial")
    r2 = RetrievalResult(variant="v", pmids=[], papers=[])
    assert r2.notes == []
    assert r2.provenance.sources == [] and r2.provenance is not r1.provenance
