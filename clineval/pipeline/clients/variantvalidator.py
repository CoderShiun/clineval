"""VariantValidator REST client. Isolates VV's nested per-transcript JSON shape.

Keys confirmed against a live response (Task-0 findings + design spec §4.1): the
top level is one variant-HGVS key plus ``flag`` (str) and ``metadata`` (dict); the
per-hit protein consequence is accession-prefixed (``NP_...:p.(Arg614Cys)``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

from clineval.pipeline.clients.http import HttpClient


@dataclass
class VVParsed:
    c_form: str = ""
    protein_tlr: str = ""
    protein_slr: str = ""
    genomic_forms: list[str] = field(default_factory=list)
    vcf_tuples: list[tuple[str, str, str, str]] = field(default_factory=list)
    # Per-build VCF coords (build key -> tuple), so a consumer can pick the correct
    # build (e.g. Stage 1 querying myvariant by assembly). vcf_tuples stays flattened
    # + deduped for synonym generation, where the build doesn't matter.
    vcf_by_build: dict[str, tuple[str, str, str, str]] = field(default_factory=dict)
    gene: str = ""
    warnings: list[str] = field(default_factory=list)
    vv_version: str = ""
    vvdb_version: str = ""
    vvta_version: str = ""


def parse_vv_response(raw: dict) -> VVParsed:
    """Extract the confirmed keys from a VariantValidator ``/all`` response."""
    meta = raw.get("metadata") or {}
    p = VVParsed(
        vv_version=str(meta.get("variantvalidator_version", "")),
        vvdb_version=str(meta.get("vvdb_version", "")),
        vvta_version=str(meta.get("vvta_version", "")),
    )
    for hit in raw.values():
        # Skips 'flag' (a str) and 'metadata' (a dict without hgvs_transcript_variant).
        if not isinstance(hit, dict) or "hgvs_transcript_variant" not in hit:
            continue
        p.c_form = hit.get("hgvs_transcript_variant", "") or ""
        prot = hit.get("hgvs_predicted_protein_consequence") or {}
        p.protein_tlr = prot.get("tlr", "") or ""
        p.protein_slr = prot.get("slr", "") or ""
        p.gene = hit.get("gene_symbol", "") or ""
        p.warnings = list(hit.get("validation_warnings", []) or [])
        for build_key, locus in (hit.get("primary_assembly_loci") or {}).items():
            desc = locus.get("hgvs_genomic_description")
            if desc and desc not in p.genomic_forms:
                p.genomic_forms.append(desc)
            vcf = locus.get("vcf") or {}
            if vcf:
                chrom = str(vcf.get("chr", "")).removeprefix("chr")
                tup = (chrom, str(vcf.get("pos", "")), str(vcf.get("ref", "")), str(vcf.get("alt", "")))
                p.vcf_by_build[build_key] = tup
                if tup not in p.vcf_tuples:
                    p.vcf_tuples.append(tup)
        break  # the first real hit is the submitted variant
    return p


class VariantValidatorClient:
    def __init__(self, http: HttpClient, base_url: str = "https://rest.variantvalidator.org") -> None:
        self._http = http
        self._base = base_url

    def fetch(self, hgvs: str, build: str = "GRCh38") -> VVParsed:
        # The HGVS goes in the path and contains ':' and '>', so URL-encode it.
        path = f"/VariantValidator/variantvalidator/{build}/{quote(hgvs)}/all"
        raw = self._http.get_json(self._base, path, headers={"Content-Type": "application/json"})
        return parse_vv_response(raw)
