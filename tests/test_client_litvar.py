import json
from pathlib import Path

from clineval.pipeline.clients.http import HttpClient
from clineval.pipeline.clients.litvar import LitVarClient, parse_litvar_pmids

PUB = Path("tests/fixtures/api_samples/litvar_publications_ryr1.json")
AUTO = Path("tests/fixtures/api_samples/litvar_autocomplete_ryr1.json")


def test_parse_litvar_pmids_from_publications_fixture():
    raw = json.loads(PUB.read_text(encoding="utf-8"))
    pmids = parse_litvar_pmids(raw)
    assert len(pmids) >= 1
    assert pmids == list(dict.fromkeys(pmids))                  # deduped, order preserved
    assert all(isinstance(p, str) and p.isdigit() for p in pmids)


def test_parse_litvar_pmids_dedupes_coerces_and_handles_missing():
    assert parse_litvar_pmids({"pmids": [123, 123, 456]}) == ["123", "456"]
    assert parse_litvar_pmids({"pmids": []}) == []
    assert parse_litvar_pmids({}) == []                         # missing key -> []
    assert parse_litvar_pmids({"pmids": [12, "not-a-pmid", 34]}) == ["12", "34"]  # junk dropped
    assert parse_litvar_pmids([]) == []                         # non-dict body -> [] (defensive)


def test_litvar_publications_calls_http_url_encoded_and_parses():
    raw = json.loads(PUB.read_text(encoding="utf-8"))
    seen = {}

    def transport(url, params, headers):
        seen["url"] = url
        return raw

    client = LitVarClient(HttpClient(transport=transport))
    pmids = client.publications("litvar@rs118192172##")
    assert pmids and all(p.isdigit() for p in pmids)
    assert "/variant/get/" in seen["url"] and seen["url"].endswith("/publications")
    assert "%40" in seen["url"] and "%23%23" in seen["url"]     # '@' and '##' URL-encoded


def test_litvar_autocomplete_returns_candidates():
    raw = json.loads(AUTO.read_text(encoding="utf-8"))
    seen = {}

    def transport(url, params, headers):
        seen["params"] = params
        return raw

    cands = LitVarClient(HttpClient(transport=transport)).autocomplete("RYR1 p.R614C")
    assert isinstance(cands, list) and cands and "_id" in cands[0]
    assert seen["params"] == {"query": "RYR1 p.R614C"}


def test_litvar_autocomplete_non_list_response_returns_empty():
    # A non-list (error) body -> [] (defensive).
    client = LitVarClient(HttpClient(transport=lambda u, p, h: {"detail": "not available"}))
    assert client.autocomplete("q") == []


def test_litvar_publications_non_fatal_on_error():
    def boom(url, params, headers):
        raise ValueError("permanent 404")

    assert LitVarClient(HttpClient(transport=boom)).publications("litvar@x##") == []


def test_litvar_autocomplete_non_fatal_on_error():
    def boom(url, params, headers):
        raise ValueError("boom")

    assert LitVarClient(HttpClient(transport=boom)).autocomplete("q") == []
