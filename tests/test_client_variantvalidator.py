import json
from pathlib import Path

from clineval.pipeline.clients.http import HttpClient
from clineval.pipeline.clients.variantvalidator import VariantValidatorClient, parse_vv_response

FIXTURE = Path("tests/fixtures/api_samples/variantvalidator_ryr1.json")


def test_parse_vv_extracts_confirmed_keys():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    p = parse_vv_response(raw)
    assert p.c_form == "NM_000540.3:c.1840C>T"
    assert p.protein_tlr == "NP_000531.2:p.(Arg614Cys)"
    assert p.protein_slr == "NP_000531.2:p.(R614C)"
    assert p.gene == "RYR1"
    # Exact dedup across builds + chr-prefix stripping (grch37==hg19, grch38==hg38).
    assert set(p.vcf_tuples) == {("19", "38948185", "C", "T"), ("19", "38457545", "C", "T")}
    assert all(not chrom.startswith("chr") for chrom, *_ in p.vcf_tuples)
    assert len(p.genomic_forms) == 2
    # Per-build coords retained so Stage 1 can pick the correct build.
    assert p.vcf_by_build["grch38"] == ("19", "38457545", "C", "T")
    assert p.vcf_by_build["grch37"] == ("19", "38948185", "C", "T")
    assert any("g.38457545C>T" in g for g in p.genomic_forms)
    assert p.vvdb_version.startswith("vvdb_")
    assert p.warnings == []


def test_parse_vv_ignores_flag_and_missing_metadata():
    # 'flag' (str) is skipped; no 'metadata' -> version fields default to "".
    raw = {
        "flag": "gene_variant",
        "SOME:c.1A>T": {
            "hgvs_transcript_variant": "SOME:c.1A>T",
            "hgvs_predicted_protein_consequence": {"tlr": "NP:p.(X1Y)", "slr": "NP:p.(X1Y)"},
            "primary_assembly_loci": {},
            "gene_symbol": "X",
            "validation_warnings": ["a warning"],
        },
    }
    p = parse_vv_response(raw)
    assert p.c_form == "SOME:c.1A>T" and p.gene == "X" and p.warnings == ["a warning"]
    assert p.vvdb_version == "" and p.genomic_forms == [] and p.vcf_tuples == []


def test_parse_vv_no_hit_returns_empty_with_metadata():
    # No variant hit (only flag/metadata) -> the loop falls through to an empty parse,
    # but version metadata is still captured.
    p = parse_vv_response({"flag": "warning", "metadata": {"vvdb_version": "vvdb_y"}})
    assert p.c_form == "" and p.gene == "" and p.genomic_forms == [] and p.vcf_tuples == []
    assert p.vvdb_version == "vvdb_y"


def test_parse_vv_locus_without_vcf_block():
    # A genomic locus with a description but no 'vcf' -> keep the g. form, add no tuple.
    raw = {
        "X:c.1A>T": {
            "hgvs_transcript_variant": "X:c.1A>T",
            "hgvs_predicted_protein_consequence": {},
            "primary_assembly_loci": {"grch38": {"hgvs_genomic_description": "NC:g.1A>T"}},
            "gene_symbol": "X",
            "validation_warnings": [],
        }
    }
    p = parse_vv_response(raw)
    assert p.genomic_forms == ["NC:g.1A>T"] and p.vcf_tuples == [] and p.vcf_by_build == {}


def test_vv_client_fetch_calls_http_url_encoded_and_parses():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    seen = {}

    def transport(url, params, headers):
        seen["url"] = url
        return raw

    client = VariantValidatorClient(HttpClient(transport=transport))
    p = client.fetch("NM_000540.3:c.1840C>T", "GRCh38")
    assert p.c_form == "NM_000540.3:c.1840C>T"
    assert "/GRCh38/" in seen["url"] and "%3A" in seen["url"]   # hgvs URL-encoded in the path


def test_vv_client_fetch_url_encodes_intronic_special_chars():
    # Splice/intronic variants carry ':' '+' '>' — all must be percent-encoded in the path.
    seen = {}

    def transport(url, params, headers):
        seen["url"] = url
        return {"flag": "warning"}   # no hit; we only assert on the URL here

    VariantValidatorClient(HttpClient(transport=transport)).fetch("NM_000540.3:c.1840+1G>A")
    assert "%3A" in seen["url"] and "%2B" in seen["url"] and "%3E" in seen["url"]
