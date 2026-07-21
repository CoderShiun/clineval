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
    def __init__(self, candidates=None, pubs=None):
        self._candidates = candidates or []      # returned by autocomplete for any query
        self._pubs = pubs or {}                  # litvar_id -> [pmids]
        self.publication_ids = []

    def autocomplete(self, query):
        return list(self._candidates)

    def publications(self, litvar_id):
        self.publication_ids.append(litvar_id)
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
