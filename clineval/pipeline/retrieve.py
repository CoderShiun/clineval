"""Stage 2: synonym set -> deduplicated PMID union + per-paper metadata + provenance.

Resolves the variant to LitVar id(s) behind a variant-match GATE (guards against
same-gene/different-position collisions — the rs193922747-vs-rs118192172 class of
error), unions publications across the matched ids (the rsID-keyed and gene-keyed
LitVar records carry different PMID sets — both, for recall), attaches per-paper
metadata via E-utilities (non-fatal — a metadata failure keeps the PMIDs), and
records which form/query surfaced each PMID.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from clineval.pipeline.models import PaperRef, PipelineProvenance, RetrievalResult, VariantForms

if TYPE_CHECKING:
    from clineval.pipeline.clients.eutils import EutilsClient
    from clineval.pipeline.clients.litvar import LitVarClient


def _autocomplete_queries(forms: VariantForms) -> set[str]:
    """Gene + each bare 'p.' protein form, e.g. 'RYR1 p.R614C' (LitVar autocomplete)."""
    if not forms.gene:
        return set()
    return {f"{forms.gene} {f}" for f in forms.forms if f.startswith("p.") and "(" not in f}


def _protein_core(s: str) -> str:
    """Strip accession / 'p.' / parens to a bare core ('NP_..:p.(R614C)' -> 'R614C').

    Lets the gate compare a LitVar hgvs against our forms tolerantly, so a format
    divergence (parens, accession, 1-vs-3-letter is already covered by both forms
    being generated) doesn't silently reject a genuine match.
    """
    s = s.split(":", 1)[-1]
    if s.startswith("p."):
        s = s[2:]
    return s.strip("()")


def _is_match(cand: dict, forms: VariantForms) -> bool:
    """Is a LitVar autocomplete candidate genuinely THIS variant (not a collision)?"""
    rsid = forms.xrefs.get("rsid")
    # A coordinate-derived rsID (Stage 1, build-correct) identifies this locus. Residual
    # risk: a genuinely multiallelic rs would also carry a second allele's papers — an
    # inherent property of rsID-keyed retrieval, accepted for Phase 1.
    if rsid and cand.get("rsid") == rsid:
        return True
    genes = cand.get("gene") or []
    if not (forms.gene and forms.gene in genes):
        return False
    cores = {_protein_core(f) for f in forms.forms}
    return _protein_core(cand.get("hgvs", "")) in cores


def retrieve(forms: VariantForms, *, litvar: LitVarClient, eutils: EutilsClient) -> RetrievalResult:
    """Retrieve the deduplicated PMID union + per-paper metadata for one variant."""
    notes: list[str] = []
    matched_ids: dict[str, str] = {}   # litvar_id -> the form/query that surfaced it

    rsid = forms.xrefs.get("rsid")
    if rsid:
        matched_ids[f"litvar@{rsid}##"] = rsid   # trusted, coordinate-derived rsID id

    for query in sorted(_autocomplete_queries(forms)):   # sorted -> reproducible provenance
        for cand in litvar.autocomplete(query):
            if _is_match(cand, forms) and cand.get("_id"):
                matched_ids.setdefault(cand["_id"], query)

    matched_pmid: dict[str, str] = {}   # pmid -> the form/query that first surfaced it
    for litvar_id, matched_form in matched_ids.items():
        for pmid in litvar.publications(litvar_id):
            matched_pmid.setdefault(pmid, matched_form)

    pmids = list(matched_pmid)
    meta: dict[str, dict] = {}
    eutils_used = False
    if pmids:
        try:
            meta = eutils.summaries(pmids)
            eutils_used = True
        except Exception as exc:  # metadata is best-effort: keep the PMIDs, note the failure
            notes.append(f"esummary metadata fetch failed: {exc}")

    papers = [
        PaperRef(
            pmid=pmid,
            title=meta.get(pmid, {}).get("title", ""),
            journal=meta.get(pmid, {}).get("journal", ""),
            year=meta.get(pmid, {}).get("year"),
            matched_form=matched_pmid[pmid],
        )
        for pmid in pmids
    ]
    prov = PipelineProvenance(
        vv_version=forms.provenance.vv_version,
        vvdb_version=forms.provenance.vvdb_version,
        vvta_version=forms.provenance.vvta_version,
        sources=["litvar2", "eutils"] if eutils_used else ["litvar2"],
    )
    return RetrievalResult(variant=forms.input, pmids=pmids, papers=papers, provenance=prov, notes=notes)
