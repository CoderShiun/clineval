"""Stage 1: one canonical variant -> every string form a paper might use to name it.

Half an API call, half local logic. VariantValidator gives the biology (transcript /
protein / genomic mappings); ``synonyms`` generates the naming variations that actually
cause missed papers; myvariant backfills the rsID (critical for LitVar) + ClinVar/gnomAD.

Two rules: (1) query myvariant by the BUILD-CORRECT genomic coords + assembly (a c. HGVS
won't resolve there, and wrong-build coords would return a WRONG rsID); (2) FLAG (never
drop) a variant whose protein consequence can't be derived — see ``resolved``.
"""

from __future__ import annotations

from typing import Any

from clineval.pipeline.clients.myvariant_client import MyVariantClient
from clineval.pipeline.clients.variantvalidator import VariantValidatorClient
from clineval.pipeline.models import PipelineProvenance, VariantForms
from clineval.pipeline.synonyms import protein_variants, vcf_form

# Genome build -> myvariant.info assembly label.
_ASSEMBLY = {"grch38": "hg38", "hg38": "hg38", "grch37": "hg19", "hg19": "hg19"}


def normalize_and_expand(
    hgvs_c: str,
    genome_build: str = "GRCh38",
    *,
    vv: VariantValidatorClient,
    mv: MyVariantClient,
) -> VariantForms:
    """Expand one canonical variant into its synonym set + xrefs + a resolution flag."""
    forms: set[str] = {hgvs_c}
    notes: list[str] = []

    parsed = vv.fetch(hgvs_c, genome_build)
    if parsed.c_form:
        forms.add(parsed.c_form)
    # tlr and slr yield identical synonym sets (protein_variants emits both letter
    # forms); iterating both is a cheap safety net if VV ever populates only one.
    for prot in (parsed.protein_tlr, parsed.protein_slr):
        forms.update(protein_variants(prot))
    forms.update(parsed.genomic_forms)
    for chrom, pos, ref, alt in parsed.vcf_tuples:
        forms.add(vcf_form(chrom, pos, ref, alt))
    for warning in parsed.warnings:
        notes.append(f"VariantValidator warning: {warning}")

    # rsID + xrefs from myvariant, queried by the requested build's genomic coords.
    # Coords and assembly are drawn from the SAME build key, so they can never
    # mismatch; an unknown build (no assembly mapping) skips the query rather than
    # risk a wrong-build lookup (which would return a WRONG rsID).
    xrefs: dict[str, Any] = {"rsid": None, "clinvar": None, "gnomad": None}
    build_key = genome_build.lower()
    tup = parsed.vcf_by_build.get(build_key)
    assembly = _ASSEMBLY.get(build_key)
    if tup and assembly:
        try:
            chrom, pos, ref, alt = tup
            mv_out = mv.lookup(f"chr{chrom}:g.{pos}{ref}>{alt}", assembly=assembly)
            xrefs = {"rsid": mv_out.get("rsid"), "clinvar": mv_out.get("clinvar"),
                     "gnomad": mv_out.get("gnomad")}
            if mv_out.get("rsid"):
                forms.add(mv_out["rsid"])
        except Exception as exc:  # defense in depth: an xref lookup must not abort Stage 1
            notes.append(f"myvariant lookup failed: {exc}")

    resolved = any(f.startswith("p.") for f in forms)
    if not resolved:
        notes.append("no protein consequence (splice/intronic/indel?) — route to manual, keep in set")

    return VariantForms(
        input=hgvs_c,
        forms=sorted(forms),
        resolved=resolved,
        xrefs=xrefs,
        gene=parsed.gene,
        notes=notes,
        provenance=PipelineProvenance(
            vv_version=parsed.vv_version,
            vvdb_version=parsed.vvdb_version,
            vvta_version=parsed.vvta_version,
            sources=["variantvalidator", "myvariant"],
        ),
    )
