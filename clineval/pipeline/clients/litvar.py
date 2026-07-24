"""LitVar2 client: resolve a variant to LitVar id(s), then fetch its PMIDs.

Flow confirmed in the Task-0 spike (the old ``/search/`` path is gone):
- autocomplete: ``GET /variant/autocomplete/?query=<text>`` -> ``[{_id, rsid, gene,
  name, hgvs, pmids_count}, ...]``
- publications: ``GET /variant/get/<url-encoded _id>/publications`` ->
  ``{pmids: [int], pmcids: [str], pmids_count}``

A variant can have several ``_id`` (an rsID-keyed one and a gene-keyed one) with
different PMID sets; Stage 2 unions across them for recall. This client provides the
two primitives and RAISES on transport failure — Stage 2 (``retrieve``) decides what
is non-fatal and records the failure, so an API outage is never silently indistinguishable
from "this variant has no literature."
"""

from __future__ import annotations

from urllib.parse import quote

from clineval.pipeline.clients.http import HttpClient

LITVAR2_BASE = "https://www.ncbi.nlm.nih.gov/research/litvar2-api"


def parse_litvar_pmids(raw: dict) -> list[str]:
    """Extract deduped, order-preserved string PMIDs from a publications response."""
    pmids = raw.get("pmids") if isinstance(raw, dict) else None
    seen: set[str] = set()
    out: list[str] = []
    for pmid in pmids or []:
        s = str(pmid)
        if s.isdigit() and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class LitVarClient:
    def __init__(self, http: HttpClient, base_url: str = LITVAR2_BASE) -> None:
        self._http = http
        self._base = base_url

    def autocomplete(self, query: str) -> list[dict]:
        """Resolve a free-text query to LitVar variant candidates (raises on transport failure).

        A non-list (error) body is treated as no candidates ([]), but a transport
        exception propagates so the caller can record the degradation.
        """
        raw = self._http.get_json(self._base, "/variant/autocomplete/", params={"query": query})
        return raw if isinstance(raw, list) else []

    def publications(self, litvar_id: str) -> list[str]:
        """Return the deduped PMIDs for a LitVar variant id (raises on transport failure)."""
        raw = self._http.get_json(
            self._base, f"/variant/get/{quote(litvar_id, safe='')}/publications"
        )
        return parse_litvar_pmids(raw)
