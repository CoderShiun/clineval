import pytest

from clineval.pipeline.cache import RequestCache
from clineval.pipeline.clients.http import HttpClient, TransientHTTPError


def test_cache_hit_skips_transport(tmp_path):
    calls: list[str] = []

    def transport(url, params, headers):
        calls.append(url)
        return {"ok": True, "url": url}

    client = HttpClient(cache=RequestCache(str(tmp_path / "c.sqlite")), transport=transport)
    a = client.get_json("https://x", "/p", {"q": "1"})
    b = client.get_json("https://x", "/p", {"q": "1"})   # served from cache
    assert a == b == {"ok": True, "url": "https://x/p"}
    assert calls == ["https://x/p"]                        # transport called exactly once


def test_no_cache_calls_transport_each_time():
    calls: list[str] = []
    client = HttpClient(transport=lambda u, p, h: calls.append(u) or {"n": len(calls)})
    client.get_json("https://x", "/p")
    client.get_json("https://x", "/p")
    assert len(calls) == 2


def test_url_is_joined_with_single_slash():
    seen = {}

    def transport(url, params, headers):
        seen["url"] = url
        return {}

    HttpClient(transport=transport).get_json("https://x/", "/a/b")
    assert seen["url"] == "https://x/a/b"


def test_empty_path_uses_base_url_unchanged():
    seen = {}

    def transport(url, params, headers):
        seen["url"] = url
        return {}

    HttpClient(transport=transport).get_json("https://x/api", "")
    assert seen["url"] == "https://x/api"


def test_transport_returns_lists_too():
    # LitVar2 autocomplete returns a JSON array; get_json must pass it through.
    client = HttpClient(transport=lambda u, p, h: [{"_id": "litvar@rs1##"}])
    assert client.get_json("https://x", "/autocomplete") == [{"_id": "litvar@rs1##"}]


def test_limiter_is_acquired_before_transport():
    order: list[str] = []

    class SpyLimiter:
        def acquire(self):
            order.append("acquire")

    def transport(url, params, headers):
        order.append("transport")
        return {}

    HttpClient(limiter=SpyLimiter(), transport=transport).get_json("https://x", "/p")
    assert order == ["acquire", "transport"]


def test_api_key_excluded_from_cache_key_but_sent_to_transport(tmp_path):
    seen_params: list[dict] = []

    def transport(url, params, headers):
        seen_params.append(dict(params))
        return {"r": 1}

    client = HttpClient(cache=RequestCache(str(tmp_path / "c.sqlite")), transport=transport)
    client.get_json("https://e", "/s", {"id": "1", "api_key": "KEY_A"})
    # Same logical request, different api_key -> must be a CACHE HIT (no 2nd transport call).
    client.get_json("https://e", "/s", {"id": "1", "api_key": "KEY_B"})
    assert len(seen_params) == 1                              # cached despite differing api_key
    assert seen_params[0] == {"id": "1", "api_key": "KEY_A"}  # full params (incl. key) still sent


def test_retries_on_transient_error_then_succeeds():
    n = {"c": 0}

    def transport(url, params, headers):
        n["c"] += 1
        if n["c"] < 3:
            raise TransientHTTPError("503")
        return {"ok": True}

    client = HttpClient(transport=transport, sleep=lambda s: None)   # no real sleeping
    assert client.get_json("https://x", "/p") == {"ok": True}
    assert n["c"] == 3


def test_permanent_error_propagates_without_retry():
    n = {"c": 0}

    def transport(url, params, headers):
        n["c"] += 1
        raise ValueError("permanent 404")

    client = HttpClient(transport=transport, sleep=lambda s: None)
    with pytest.raises(ValueError):
        client.get_json("https://x", "/p")
    assert n["c"] == 1                                        # non-transient -> not retried


def test_transient_error_exhausts_retries_and_does_not_cache(tmp_path):
    n = {"c": 0}

    def failing(url, params, headers):
        n["c"] += 1
        raise TransientHTTPError("always 503")

    cache = RequestCache(str(tmp_path / "c.sqlite"))
    with pytest.raises(TransientHTTPError):
        HttpClient(cache=cache, transport=failing, sleep=lambda s: None).get_json("https://x", "/p")
    assert n["c"] == 4                                        # initial + 3 retries, then re-raised
    # The failed request wrote nothing to the cache, so a fresh (now-succeeding)
    # transport is actually invoked -> proves no failed response was cached.
    ok = HttpClient(cache=cache, transport=lambda u, p, h: {"ok": True}, sleep=lambda s: None)
    assert ok.get_json("https://x", "/p") == {"ok": True}


def test_cache_hit_returns_before_acquiring_limiter(tmp_path):
    acquired = {"n": 0}
    calls = {"c": 0}

    class SpyLimiter:
        def acquire(self):
            acquired["n"] += 1

    def transport(url, params, headers):
        calls["c"] += 1
        return {"v": 1}

    client = HttpClient(
        cache=RequestCache(str(tmp_path / "c.sqlite")), limiter=SpyLimiter(), transport=transport
    )
    client.get_json("https://x", "/p")       # miss: acquires the limiter + fetches
    client.get_json("https://x", "/p")       # hit: returns before touching the limiter
    assert calls["c"] == 1 and acquired["n"] == 1


def test_requests_transport_classifies_errors(monkeypatch):
    # The real transport turns network errors / 429 / 5xx into a retryable
    # TransientHTTPError, but lets other 4xx propagate as permanent.
    import requests

    from clineval.pipeline.clients.http import _requests_transport

    class FakeResp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError(str(self.status_code))

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(200, {"ok": 1}))
    assert _requests_transport("http://x", {}, {}) == {"ok": 1}

    for transient_status in (429, 500, 503):
        monkeypatch.setattr(requests, "get", lambda *a, s=transient_status, **k: FakeResp(s))
        with pytest.raises(TransientHTTPError):
            _requests_transport("http://x", {}, {})

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(404))   # permanent
    with pytest.raises(requests.exceptions.HTTPError):
        _requests_transport("http://x", {}, {})

    def make_raiser(exc_cls):
        def raiser(*a, **k):
            raise exc_cls("transient network failure")

        return raiser

    for exc_cls in (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    ):
        monkeypatch.setattr(requests, "get", make_raiser(exc_cls))
        with pytest.raises(TransientHTTPError):
            _requests_transport("http://x", {}, {})
