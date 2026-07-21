"""NCBI E-utilities esummary client: PMID -> {title, journal, year}.

Attaches per-paper metadata to retrieved PMIDs. An ``NCBI_API_KEY`` (passed as
``api_key``) raises the rate limit; the HttpClient excludes it from the cache key.
"""

from __future__ import annotations

from clineval.pipeline.clients.http import HttpClient


def _year(pubdate: str) -> int | None:
    """Year from an esummary ``pubdate`` ('1996 Feb' -> 1996); None if not numeric."""
    if not pubdate:
        return None
    head = pubdate.strip().split(" ")[0].split("/")[0]
    return int(head) if head.isdigit() else None


def parse_esummary(raw: dict) -> dict[str, dict]:
    """Map each PMID to ``{title, journal, year}`` from an esummary JSON response."""
    result = raw.get("result", {}) if isinstance(raw, dict) else {}
    out: dict[str, dict] = {}
    for pmid in result.get("uids", []):
        rec = result.get(pmid, {})
        out[str(pmid)] = {
            "title": rec.get("title", ""),
            "journal": rec.get("fulljournalname", "") or rec.get("source", ""),
            "year": _year(rec.get("pubdate", "")),
        }
    return out


class EutilsClient:
    def __init__(
        self,
        http: HttpClient,
        api_key: str | None = None,
        base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._base = base_url

    def summaries(self, pmids: list[str], batch: int = 200) -> dict[str, dict]:
        """Return ``{pmid: {title, journal, year}}`` for pmids, batched; api_key added if set."""
        out: dict[str, dict] = {}
        for i in range(0, len(pmids), batch):
            params = {"db": "pubmed", "retmode": "json", "id": ",".join(pmids[i : i + batch])}
            if self._api_key:
                params["api_key"] = self._api_key
            out.update(parse_esummary(self._http.get_json(self._base, "/esummary.fcgi", params=params)))
        return out
