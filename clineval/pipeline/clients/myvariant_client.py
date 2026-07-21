"""myvariant.info wrapper: backfill rsID + pull ClinVar/gnomAD xrefs (non-fatal).

Stage 1 uses this to add the rsID (critical for LitVar retrieval) and to carry
ClinVar/gnomAD cross-references for reuse downstream. Any failure is logged and
degrades to all-None rather than aborting normalization.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_FIELDS = ["dbsnp.rsid", "clinvar", "gnomad_genome"]


class MyVariantClient:
    def __init__(self, mv: object | None = None) -> None:
        if mv is None:
            import myvariant

            mv = myvariant.MyVariantInfo()
            mv.set_caching()  # local persistence = free caching
        self._mv = mv

    def lookup(self, hgvs: str, assembly: str | None = None) -> dict:
        """Return ``{rsid, clinvar, gnomad}``; all-None (logged) if the lookup fails.

        Pass ``assembly`` ("hg38"/"hg19") when querying by genomic (``chr:g.``) coords
        so myvariant resolves against the right build; omit it for rsID queries.
        """
        kwargs: dict = {"fields": _FIELDS}
        if assembly:
            kwargs["assembly"] = assembly
        try:
            res = self._mv.getvariant(hgvs, **kwargs) or {}
        except Exception as exc:  # non-fatal: log + return empties
            log.warning("myvariant lookup failed for %s: %s", hgvs, exc)
            return {"rsid": None, "clinvar": None, "gnomad": None}
        return {
            "rsid": (res.get("dbsnp") or {}).get("rsid"),
            "clinvar": res.get("clinvar"),
            "gnomad": res.get("gnomad_genome"),
        }
