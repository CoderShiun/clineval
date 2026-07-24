"""myvariant.info wrapper: backfill rsID + pull ClinVar/gnomAD xrefs.

Stage 1 uses this to add the rsID (critical for LitVar retrieval) and to carry
ClinVar/gnomAD cross-references for reuse downstream. It RAISES on transport failure;
Stage 1 (``normalize_and_expand``) catches and notes it, so "myvariant unavailable"
is recorded distinctly from "myvariant returned no rsID" (a successful all-None lookup).
"""

from __future__ import annotations

_FIELDS = ["dbsnp.rsid", "clinvar", "gnomad_genome"]


class MyVariantClient:
    def __init__(self, mv: object | None = None) -> None:
        if mv is None:
            import myvariant

            mv = myvariant.MyVariantInfo()
            try:
                mv.set_caching()  # local persistence = free caching (best-effort)
            except Exception:
                # Caching needs optional biothings deps (anysqlite/hishel). If absent, run
                # UNCACHED rather than crash the whole live run — correctness is unaffected.
                pass
        self._mv = mv

    def lookup(self, hgvs: str, assembly: str | None = None) -> dict:
        """Return ``{rsid, clinvar, gnomad}`` (rsid None if not found); raises on failure.

        Pass ``assembly`` ("hg38"/"hg19") when querying by genomic (``chr:g.``) coords
        so myvariant resolves against the right build; omit it for rsID queries.
        """
        kwargs: dict = {"fields": _FIELDS}
        if assembly:
            kwargs["assembly"] = assembly
        res = self._mv.getvariant(hgvs, **kwargs) or {}
        return {
            "rsid": (res.get("dbsnp") or {}).get("rsid"),
            "clinvar": res.get("clinvar"),
            "gnomad": res.get("gnomad_genome"),
        }
