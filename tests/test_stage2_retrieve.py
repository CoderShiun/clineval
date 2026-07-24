from clineval.pipeline.models import PipelineProvenance, VariantForms
from clineval.pipeline.retrieve import retrieve


def _forms(rsid="rs118192172"):
    base = ["NM_000540.3:c.1840C>T", "p.R614C", "p.Arg614Cys", "R614C", "Arg614Cys"]
    if rsid:
        base.append(rsid)
    return VariantForms(
        input="NM_000540.3:c.1840C>T", forms=base, resolved=True,
        xrefs={"rsid": rsid, "clinvar": None, "gnomad": None},
        gene="RYR1", provenance=PipelineProvenance(vv_version="4.0", vvdb_version="vvdb_2025_3"),
    )


class _FakeLitVar:
    def __init__(self, candidates=None, pubs=None, fail_autocomplete=False, fail_publications=False):
        self._candidates = candidates or []      # returned by autocomplete for any query
        self._pubs = pubs or {}                  # litvar_id -> [pmids]
        self._fail_autocomplete = fail_autocomplete
        self._fail_publications = fail_publications
        self.queries = []                        # every query actually asked (pins query-gen)
        self.publication_ids = []

    def autocomplete(self, query):
        self.queries.append(query)
        if self._fail_autocomplete:
            raise RuntimeError("litvar autocomplete down")
        return list(self._candidates)

    def publications(self, litvar_id):
        self.publication_ids.append(litvar_id)
        if self._fail_publications:
            raise RuntimeError("litvar publications down")
        return list(self._pubs.get(litvar_id, []))


class _FakeEutils:
    def __init__(self, fail=False):
        self._fail = fail

    def summaries(self, pmids, batch=200):
        if self._fail:
            raise RuntimeError("eutils down")
        return {p: {"title": f"T{p}", "journal": "J", "year": 2020} for p in pmids}


def test_retrieve_unions_ids_gates_collisions_and_attaches_metadata():
    candidates = [
        {"_id": "litvar@rs118192172##", "rsid": "rs118192172", "gene": ["RYR1"], "hgvs": "p.R614C"},
        {"_id": "litvar@#6261#p.R614C", "rsid": None, "gene": ["RYR1"], "hgvs": "p.R614C"},
        {"_id": "litvar@rs999##", "rsid": "rs999", "gene": ["RYR1"], "hgvs": "p.C35R"},  # COLLISION
    ]
    pubs = {
        "litvar@rs118192172##": ["111", "222"],   # rsID-keyed record
        "litvar@#6261#p.R614C": ["222", "333"],   # gene-keyed record (different set -> recall)
        "litvar@rs999##": ["999"],                 # a different variant -> must be excluded
    }
    litvar = _FakeLitVar(candidates=candidates, pubs=pubs)
    result = retrieve(_forms(), litvar=litvar, eutils=_FakeEutils())
    assert set(result.pmids) == {"111", "222", "333"}          # union of the matched ids
    assert "999" not in result.pmids                           # collision gated out
    assert "litvar@rs999##" not in litvar.publication_ids      # gated BEFORE fetching its papers
    by = {p.pmid: p for p in result.papers}
    assert by["111"].matched_form == "rs118192172"             # provenance: trusted rsID id
    assert by["222"].matched_form == "rs118192172"             # shared PMID -> rsID id wins (first)
    assert "RYR1" in by["333"].matched_form                     # provenance: gene+protein query
    assert by["111"].title == "T111" and by["111"].year == 2020  # metadata attached
    assert set(result.provenance.sources) == {"litvar2", "eutils"}
    assert result.provenance.vvdb_version == "vvdb_2025_3"
    assert result.status == "ok"
    # Pin the EXACT autocomplete queries generated (gene + accession-stripped p./c. + rsID) —
    # the fake records what it was asked, so a regression in query generation fails loudly.
    assert set(litvar.queries) == {
        "RYR1 c.1840C>T", "RYR1 p.R614C", "RYR1 p.Arg614Cys", "RYR1 rs118192172"
    }


def test_retrieve_non_missense_variant_gets_cdna_query():
    # Production-shaped forms for a splice/intronic variant: accession-qualified c. (NO bare
    # 'c.'), genomic, VCF — no protein, no rsID. The accession-stripped cDNA query must fire,
    # else the variant gets no gene-keyed retrieval path at all.
    forms = VariantForms(
        input="NM_000540.3:c.1840+1G>A",
        forms=["NM_000540.3:c.1840+1G>A", "NC_000019.10:g.38457546G>A", "19-38457546-G-A"],
        resolved=False, xrefs={"rsid": None, "clinvar": None, "gnomad": None},
        gene="RYR1", provenance=PipelineProvenance(),
    )
    litvar = _FakeLitVar(
        candidates=[{"_id": "litvar@#6261#c.1840+1G>A", "rsid": None, "gene": ["RYR1"],
                     "hgvs": "c.1840+1G>A"}],
        pubs={"litvar@#6261#c.1840+1G>A": ["555"]},
    )
    result = retrieve(forms, litvar=litvar, eutils=_FakeEutils())
    assert litvar.queries == ["RYR1 c.1840+1G>A"]     # only the accession-stripped cDNA query
    assert result.pmids == ["555"]


def test_intronic_no_rsid_variant_queries_litvar_end_to_end():
    # The real non-missense gap, driven through normalize -> retrieve on PRODUCTION forms:
    # an intronic variant with no rsID. Regression guard against the "dead c. branch" bug
    # (a unit test on hand-crafted bare-'c.' forms would have masked it).
    from clineval.pipeline.clients.variantvalidator import VVParsed
    from clineval.pipeline.normalize import normalize_and_expand

    parsed = VVParsed(
        c_form="NM_000540.3:c.1840+1G>A", protein_tlr="", protein_slr="",
        genomic_forms=["NC_000019.10:g.38457546G>A"],
        vcf_tuples=[("19", "38457546", "G", "A")],
        vcf_by_build={"grch38": ("19", "38457546", "G", "A"), "hg38": ("19", "38457546", "G", "A")},
        gene="RYR1", vvdb_version="vvdb_2025_3",
    )

    class _VV:
        def fetch(self, hgvs, build="GRCh38"):
            return parsed

    class _MV:
        def lookup(self, hgvs, assembly=None):
            return {"rsid": None, "clinvar": None, "gnomad": None}

    forms = normalize_and_expand("NM_000540.3:c.1840+1G>A", vv=_VV(), mv=_MV())
    assert forms.resolved is False and not forms.xrefs["rsid"]      # non-missense, no rsID
    litvar = _FakeLitVar(
        candidates=[{"_id": "litvar@#6261#c.1840+1G>A", "rsid": None, "gene": ["RYR1"],
                     "hgvs": "c.1840+1G>A"}],
        pubs={"litvar@#6261#c.1840+1G>A": ["777"]},
    )
    result = retrieve(forms, litvar=litvar, eutils=_FakeEutils())
    assert "RYR1 c.1840+1G>A" in litvar.queries                     # gap closed in production shape
    assert result.pmids == ["777"]


def test_retrieve_records_litvar_failure_and_marks_degraded():
    # A LitVar outage must NOT look like "no papers": status=degraded, a note explains it,
    # and litvar2 is not claimed as a source that returned data.
    litvar = _FakeLitVar(fail_autocomplete=True)
    result = retrieve(_forms(rsid=None), litvar=litvar, eutils=_FakeEutils())
    assert result.pmids == []
    assert result.status == "degraded"
    assert any("litvar autocomplete failed" in n for n in result.notes)
    assert "litvar2" not in result.provenance.sources


def test_retrieve_marks_degraded_when_stage1_failed():
    # A Stage-1 (VariantValidator) failure leaves no gene/rsID, so NO LitVar call is made —
    # its empty result must still be flagged degraded, not scored as a real zero.
    forms = VariantForms(
        input="NM_000540.3:c.1840C>T", forms=["NM_000540.3:c.1840C>T"], resolved=False,
        xrefs={"rsid": None, "clinvar": None, "gnomad": None}, gene="",
        provenance=PipelineProvenance(), normalization_failed=True,
    )
    litvar = _FakeLitVar()
    result = retrieve(forms, litvar=litvar, eutils=_FakeEutils())
    assert litvar.queries == [] and result.pmids == []            # nothing even attempted
    assert result.status == "degraded"                             # but flagged, not "ok"


def test_retrieve_records_publications_failure():
    litvar = _FakeLitVar(pubs={"litvar@rs118192172##": ["111"]}, fail_publications=True)
    result = retrieve(_forms(), litvar=litvar, eutils=_FakeEutils())
    assert result.pmids == []                                   # the one id's fetch failed
    assert result.status == "degraded"
    assert any("litvar publications failed" in n for n in result.notes)
    assert "litvar2" in result.provenance.sources              # autocomplete still succeeded


def test_retrieve_non_fatal_on_eutils_failure():
    litvar = _FakeLitVar(pubs={"litvar@rs118192172##": ["111"]})
    result = retrieve(_forms(), litvar=litvar, eutils=_FakeEutils(fail=True))
    assert result.pmids == ["111"]                             # PMIDs kept despite metadata failure
    assert result.papers[0].title == "" and result.papers[0].matched_form == "rs118192172"
    assert any("metadata" in n.lower() for n in result.notes)
    assert "eutils" not in result.provenance.sources           # not claimed when it failed


def test_retrieve_without_rsid_uses_gene_matches_only():
    candidates = [{"_id": "litvar@#6261#p.R614C", "rsid": None, "gene": ["RYR1"], "hgvs": "p.R614C"}]
    litvar = _FakeLitVar(candidates=candidates, pubs={"litvar@#6261#p.R614C": ["222"]})
    result = retrieve(_forms(rsid=None), litvar=litvar, eutils=_FakeEutils())
    assert result.pmids == ["222"]
    assert all("rs118192172" not in i for i in litvar.publication_ids)   # no rsID id constructed


def test_retrieve_without_gene_uses_rsid_only():
    forms = _forms()
    forms.gene = ""                                            # VV gave no gene -> no autocomplete
    litvar = _FakeLitVar(
        candidates=[{"_id": "should-not-match", "rsid": "rsZ", "gene": ["X"], "hgvs": "p.Z1A"}],
        pubs={"litvar@rs118192172##": ["111"]},
    )
    result = retrieve(forms, litvar=litvar, eutils=_FakeEutils())
    assert result.pmids == ["111"] and litvar.publication_ids == ["litvar@rs118192172##"]


def test_retrieve_empty_when_nothing_matches():
    candidates = [{"_id": "x", "rsid": "rsZ", "gene": ["OTHER"], "hgvs": "p.Z1A"}]  # different variant
    result = retrieve(_forms(rsid=None), litvar=_FakeLitVar(candidates=candidates), eutils=_FakeEutils())
    assert result.pmids == [] and result.papers == []


def test_retrieve_gate_tolerates_hgvs_format_divergence():
    # LitVar returns 'p.(R614C)' but our forms carry 'p.R614C' — the normalized gate must
    # still match (else a gene-only variant silently gets ZERO papers). No rsID here so
    # the hgvs gate is the sole path.
    candidates = [{"_id": "litvar@#6261#p.R614C", "rsid": None, "gene": ["RYR1"], "hgvs": "p.(R614C)"}]
    litvar = _FakeLitVar(candidates=candidates, pubs={"litvar@#6261#p.R614C": ["222"]})
    assert retrieve(_forms(rsid=None), litvar=litvar, eutils=_FakeEutils()).pmids == ["222"]


def test_retrieve_ignores_candidate_without_id():
    # A matching candidate lacking '_id' can't be fetched -> contributes nothing.
    candidates = [{"rsid": "rs118192172", "gene": ["RYR1"], "hgvs": "p.R614C"}]   # no _id
    litvar = _FakeLitVar(candidates=candidates, pubs={"litvar@rs118192172##": ["111"]})
    result = retrieve(_forms(), litvar=litvar, eutils=_FakeEutils())
    assert result.pmids == ["111"] and litvar.publication_ids == ["litvar@rs118192172##"]


def test_retrieve_empty_with_neither_rsid_nor_gene():
    forms = _forms(rsid=None)
    forms.gene = ""
    result = retrieve(forms, litvar=_FakeLitVar(), eutils=_FakeEutils())
    assert result.pmids == [] and result.papers == []
