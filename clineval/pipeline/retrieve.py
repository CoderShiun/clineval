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
    """Gene + each protein / cDNA / rsID form (accession stripped) for LitVar autocomplete,
    e.g. 'RYR1 p.R614C', 'RYR1 c.1840+1G>A', 'RYR1 rs118192172'.

    The cDNA/rsID queries give NON-missense variants (splice/intronic/indel — no protein form)
    a gene-keyed retrieval path they would otherwise lack entirely. Production forms are
    accession-qualified (``NM_..:c.``, ``NP_..:p.``), so the accession is stripped to the bare
    c./p. core (the same normalization ``_protein_core`` applies on the gate side) — otherwise
    ``startswith('c.')`` would never fire on a real form. The _is_match gate still filters every
    candidate, so broadening the queries can only add genuine matches, never collisions.
    """
    if not forms.gene:
        return set()
    return {
        f"{forms.gene} {f.split(':', 1)[-1]}"       # strip transcript/genomic accession
        for f in forms.forms
        if "(" not in f
        and (f.split(":", 1)[-1].startswith(("p.", "c.")) or f.startswith("rs"))
    }


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
    litvar_ok = False                  # at least one LitVar call succeeded
    litvar_failed = False              # at least one LitVar call raised (retrieval degraded)

    rsid = forms.xrefs.get("rsid")
    if rsid:
        matched_ids[f"litvar@{rsid}##"] = rsid   # trusted, coordinate-derived rsID id

    for query in sorted(_autocomplete_queries(forms)):   # sorted -> reproducible provenance
        try:
            cands = litvar.autocomplete(query)
        except Exception as exc:   # non-fatal, but RECORDED — never a silent zero
            notes.append(f"litvar autocomplete failed for {query!r}: {exc}")
            litvar_failed = True
            continue
        litvar_ok = True
        for cand in cands:
            if _is_match(cand, forms) and cand.get("_id"):
                matched_ids.setdefault(cand["_id"], query)

    matched_pmid: dict[str, str] = {}   # pmid -> the form/query that first surfaced it
    for litvar_id, matched_form in matched_ids.items():
        try:
            pubs = litvar.publications(litvar_id)
        except Exception as exc:   # non-fatal, but RECORDED
            notes.append(f"litvar publications failed for {litvar_id}: {exc}")
            litvar_failed = True
            continue
        litvar_ok = True
        for pmid in pubs:
            matched_pmid.setdefault(pmid, matched_form)

    pmids = list(matched_pmid)
    meta: dict[str, dict] = {}
    if pmids:
        try:
            meta = eutils.summaries(pmids)
        except Exception as exc:  # metadata is best-effort: keep the PMIDs, note the failure
            notes.append(f"esummary metadata fetch failed: {exc}")
    eutils_used = bool(meta)   # claim eutils only if it actually returned metadata

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
    sources: list[str] = []
    if litvar_ok:                    # only claim a source that actually returned data
        sources.append("litvar2")
    if eutils_used:
        sources.append("eutils")
    prov = PipelineProvenance(
        vv_version=forms.provenance.vv_version,
        vvdb_version=forms.provenance.vvdb_version,
        vvta_version=forms.provenance.vvta_version,
        sources=sources,
    )
    # Degraded if a LitVar call failed OR Stage 1 itself failed (a VV outage leaves no gene/rsID,
    # so no LitVar call is even attempted — its empty result must not be scored as a real zero).
    status = "degraded" if (litvar_failed or forms.normalization_failed) else "ok"
    return RetrievalResult(
        variant=forms.input, pmids=pmids, papers=papers, provenance=prov, notes=notes, status=status
    )
