from clineval.pipeline.clients.variantvalidator import VVParsed
from clineval.pipeline.models import VariantForms
from clineval.pipeline.normalize import normalize_and_expand


class _FakeVV:
    def __init__(self, parsed):
        self._p = parsed
        self.called = None

    def fetch(self, hgvs, build="GRCh38"):
        self.called = (hgvs, build)
        return self._p


class _FakeMV:
    def __init__(self, rsid="rs118192172"):
        self._rsid = rsid
        self.calls = []

    def lookup(self, hgvs, assembly=None):
        self.calls.append((hgvs, assembly))
        return {"rsid": self._rsid, "clinvar": {"sig": "Pathogenic"}, "gnomad": {"af": 0.0}}


def _missense_parsed():
    return VVParsed(
        c_form="NM_000540.3:c.1840C>T",
        protein_tlr="NP_000531.2:p.(Arg614Cys)",
        protein_slr="NP_000531.2:p.(R614C)",
        genomic_forms=["NC_000019.10:g.38457545C>T", "NC_000019.9:g.38948185C>T"],
        vcf_tuples=[("19", "38457545", "C", "T"), ("19", "38948185", "C", "T")],
        vcf_by_build={
            "grch38": ("19", "38457545", "C", "T"), "hg38": ("19", "38457545", "C", "T"),
            "grch37": ("19", "38948185", "C", "T"), "hg19": ("19", "38948185", "C", "T"),
        },
        gene="RYR1", vvdb_version="vvdb_2025_3",
    )


def test_missense_resolves_and_expands():
    vv, mv = _FakeVV(_missense_parsed()), _FakeMV()
    out = normalize_and_expand("NM_000540.3:c.1840C>T", vv=vv, mv=mv)
    assert isinstance(out, VariantForms)
    assert out.resolved is True and out.gene == "RYR1"
    forms = set(out.forms)
    assert "NM_000540.3:c.1840C>T" in forms
    assert "p.Arg614Cys" in forms and "R614C" in forms          # protein synonyms
    assert "NC_000019.10:g.38457545C>T" in forms                 # genomic
    assert "19-38457545-C-T" in forms                            # VCF form
    assert "rs118192172" in forms                                # rsID backfilled
    # myvariant queried with the CORRECT-build (GRCh38) coords + hg38 assembly.
    assert mv.calls == [("chr19:g.38457545C>T", "hg38")]
    assert out.xrefs["rsid"] == "rs118192172"
    assert out.xrefs["clinvar"] == {"sig": "Pathogenic"}
    assert out.xrefs["gnomad"] == {"af": 0.0}
    assert out.provenance.vvdb_version == "vvdb_2025_3"
    assert set(out.provenance.sources) == {"variantvalidator", "myvariant"}   # both ran
    assert vv.called == ("NM_000540.3:c.1840C>T", "GRCh38")


def test_grch37_uses_hg19_assembly_and_coords():
    mv = _FakeMV()
    normalize_and_expand("NM_000540.3:c.1840C>T", "GRCh37", vv=_FakeVV(_missense_parsed()), mv=mv)
    assert mv.calls == [("chr19:g.38948185C>T", "hg19")]         # GRCh37 coords + hg19 assembly


def test_protein_only_hard_case_flagged_not_dropped():
    parsed = VVParsed(
        c_form="NM_000540.3:c.1840+1G>A", protein_tlr="", protein_slr="",
        genomic_forms=["NC_000019.10:g.38457546G>A"],
        vcf_tuples=[("19", "38457546", "G", "A")],
        vcf_by_build={"grch38": ("19", "38457546", "G", "A"), "hg38": ("19", "38457546", "G", "A")},
        gene="RYR1", warnings=["intronic variant"], vvdb_version="vvdb_2025_3",
    )
    out = normalize_and_expand("NM_000540.3:c.1840+1G>A", vv=_FakeVV(parsed), mv=_FakeMV(rsid=None))
    assert out.resolved is False
    assert "NM_000540.3:c.1840+1G>A" in out.forms                # kept, NOT dropped
    assert any("manual" in n.lower() for n in out.notes)
    assert any("intronic" in n.lower() for n in out.notes)       # VV warning surfaced


def test_empty_vv_cform_still_keeps_input_and_flags():
    # VV returned no hit (empty parse: no gene, no c_form) -> input HGVS kept, and flagged as a
    # NORMALIZATION FAILURE (degraded downstream), NOT mislabeled a splice/intronic "route to
    # manual" biology case and NOT scored as a real zero.
    out = normalize_and_expand("NM_X:c.1A>T", vv=_FakeVV(VVParsed()), mv=_FakeMV(rsid=None))
    assert out.forms == ["NM_X:c.1A>T"]           # only the input; empty c_form not added
    assert out.resolved is False and out.normalization_failed is True
    assert any("no mappable variant" in n.lower() for n in out.notes)
    assert not any("route to manual" in n.lower() for n in out.notes)


def test_missing_build_coords_skips_myvariant_gracefully():
    parsed = _missense_parsed()
    parsed.vcf_by_build = {}                                      # e.g. VV returned no VCF
    mv = _FakeMV()
    out = normalize_and_expand("NM_000540.3:c.1840C>T", vv=_FakeVV(parsed), mv=mv)
    assert mv.calls == []                                         # myvariant not called
    assert out.resolved is True and out.xrefs["rsid"] is None


def test_unknown_build_skips_rather_than_guessing_assembly():
    # Coords present under a build we can't map to an assembly -> skip (never send
    # wrong-build coords with a guessed assembly).
    parsed = _missense_parsed()
    parsed.vcf_by_build = {"t2t": ("19", "999", "C", "T")}
    mv = _FakeMV()
    out = normalize_and_expand("NM_X:c.1A>T", "t2t", vv=_FakeVV(parsed), mv=mv)
    assert mv.calls == [] and out.xrefs["rsid"] is None
    assert out.provenance.sources == ["variantvalidator"]        # myvariant skipped -> not claimed


def test_variantvalidator_failure_is_non_fatal_at_stage1():
    # A VV outage on one variant must not crash the batch: keep the variant (flag-don't-drop),
    # note the failure, and skip expansion.
    class _BoomVV:
        def fetch(self, hgvs, build="GRCh38"):
            raise RuntimeError("VV 500")

    out = normalize_and_expand("NM_000540.3:c.1840C>T", vv=_BoomVV(), mv=_FakeMV())
    assert out.resolved is False
    assert out.normalization_failed is True                       # -> Stage 2 marks it degraded
    assert "NM_000540.3:c.1840C>T" in out.forms                   # kept, not dropped
    assert any("variantvalidator failed" in n.lower() for n in out.notes)


def test_myvariant_exception_is_caught_at_stage1():
    class _RaisingMV:
        def lookup(self, hgvs, assembly=None):
            raise RuntimeError("mv blew up")

    out = normalize_and_expand("NM_000540.3:c.1840C>T", vv=_FakeVV(_missense_parsed()), mv=_RaisingMV())
    assert out.resolved is True and out.xrefs["rsid"] is None     # still normalizes
    assert any("myvariant" in n.lower() for n in out.notes)
    assert out.provenance.sources == ["variantvalidator"]        # myvariant failed -> not claimed
