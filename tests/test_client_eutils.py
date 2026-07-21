import json
from pathlib import Path

from clineval.pipeline.clients.eutils import EutilsClient, parse_esummary
from clineval.pipeline.clients.http import HttpClient

ESUM = Path("tests/fixtures/api_samples/esummary_ryr1.json")


def test_parse_esummary_from_fixture():
    meta = parse_esummary(json.loads(ESUM.read_text(encoding="utf-8")))
    assert meta
    sample = next(iter(meta.values()))
    assert set(sample) == {"title", "journal", "year"}
    assert sample["year"] is None or isinstance(sample["year"], int)


def test_parse_esummary_journal_fallback_and_year():
    # 'source' is the fallback when 'fulljournalname' is absent; year = first pubdate token.
    raw = {"result": {"uids": ["1"], "1": {"title": "T", "source": "JShort", "pubdate": "1996 Feb"}}}
    assert parse_esummary(raw)["1"] == {"title": "T", "journal": "JShort", "year": 1996}
    # non-numeric / empty pubdate -> year None; fulljournalname preferred over source.
    raw2 = {"result": {"uids": ["2"], "2": {"fulljournalname": "J", "source": "x", "pubdate": ""}}}
    assert parse_esummary(raw2)["2"] == {"title": "", "journal": "J", "year": None}
    # non-numeric leading pubdate token -> year None
    raw3 = {"result": {"uids": ["3"], "3": {"pubdate": "no-date"}}}
    assert parse_esummary(raw3)["3"]["year"] is None


def test_parse_esummary_empty_or_malformed():
    assert parse_esummary({}) == {}
    assert parse_esummary({"result": {"uids": []}}) == {}
    assert parse_esummary([]) == {}                  # non-dict input -> {} (defensive)


def test_eutils_summaries_adds_db_retmode_and_api_key():
    raw = json.loads(ESUM.read_text(encoding="utf-8"))
    seen = []

    def transport(url, params, headers):
        seen.append(dict(params))
        return raw

    client = EutilsClient(HttpClient(transport=transport), api_key="KEY")
    out = client.summaries(["99000001", "99000002"])
    assert out
    assert seen[0]["db"] == "pubmed" and seen[0]["retmode"] == "json"
    assert seen[0]["id"] == "99000001,99000002" and seen[0]["api_key"] == "KEY"


def test_eutils_summaries_batches_large_lists_without_api_key():
    seen = []

    def transport(url, params, headers):
        seen.append(params["id"])
        assert "api_key" not in params           # none supplied -> not sent
        return {"result": {"uids": []}}

    EutilsClient(HttpClient(transport=transport)).summaries([str(i) for i in range(5)], batch=2)
    assert seen == ["0,1", "2,3", "4"]           # 5 ids, batch 2 -> 3 requests


def test_eutils_summaries_empty_input_makes_no_request():
    calls = []
    client = EutilsClient(HttpClient(transport=lambda u, p, h: calls.append(1) or {}))
    assert client.summaries([]) == {} and calls == []


def test_eutils_summaries_merges_records_across_batches():
    responses = {
        "0,1": {"result": {"uids": ["0", "1"], "0": {"title": "t0"}, "1": {"title": "t1"}}},
        "2": {"result": {"uids": ["2"], "2": {"title": "t2"}}},
    }
    client = EutilsClient(HttpClient(transport=lambda u, p, h: responses[p["id"]]))
    out = client.summaries(["0", "1", "2"], batch=2)
    assert set(out) == {"0", "1", "2"}                 # records from BOTH batches merged
    assert out["0"]["title"] == "t0" and out["2"]["title"] == "t2"


def test_eutils_api_key_excluded_from_cache_identity(tmp_path):
    from clineval.pipeline.cache import RequestCache

    calls = []

    def transport(url, params, headers):
        calls.append(dict(params))
        return {"result": {"uids": ["1"], "1": {"title": "T"}}}

    cache = RequestCache(str(tmp_path / "c.sqlite"))
    EutilsClient(HttpClient(cache=cache, transport=transport), api_key="A").summaries(["1"])
    EutilsClient(HttpClient(cache=cache, transport=transport), api_key="B").summaries(["1"])
    # Same logical request, different api_key -> the 2nd is a cache hit (api_key not in key).
    assert len(calls) == 1 and calls[0]["api_key"] == "A"
