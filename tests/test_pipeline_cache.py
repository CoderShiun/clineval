import sqlite3

import pytest

from clineval.pipeline.cache import RequestCache, make_key


def test_make_key_is_deterministic_and_order_independent():
    # Same inputs -> same key; param order must not matter (keys are sorted).
    k = make_key("https://x", "/p", {"a": 1, "b": 2})
    assert k == make_key("https://x", "/p", {"b": 2, "a": 1})
    # A sha256 hex digest.
    assert len(k) == 64 and all(c in "0123456789abcdef" for c in k)


def test_make_key_is_sensitive_to_every_input():
    base = make_key("https://x", "/p", {"a": 1})
    assert make_key("https://x", "/p", {"a": 2}) != base       # param value differs
    assert make_key("https://x", "/p", {"x": 1}) != base       # param key NAME differs
    assert make_key("https://x", "/p", {"a": 1, "c": 9}) != base  # extra param present
    assert make_key("https://x", "/q", {"a": 1}) != base       # path differs
    assert make_key("https://y", "/p", {"a": 1}) != base       # base_url differs


def test_make_key_none_params_equals_empty_dict():
    # A GET with no params must hash the same whether callers pass None or {}.
    assert make_key("https://x", "/p", None) == make_key("https://x", "/p", {})


def test_cache_round_trip_and_stats(tmp_path):
    cache = RequestCache(str(tmp_path / "c.sqlite"))
    assert cache.get("k") is None                      # miss -> None
    cache.put("k", {"hello": "world"})
    assert cache.get("k") == {"hello": "world"}         # hit
    assert cache.stats() == (1, 1)                      # (hits, misses)


def test_cache_round_trips_lists_not_only_dicts(tmp_path):
    # LitVar2 autocomplete returns a JSON ARRAY; the cache must store/return it.
    cache = RequestCache(str(tmp_path / "c.sqlite"))
    payload = [{"_id": "litvar@rs118192172##", "pmids_count": 86}]
    cache.put("litvar", payload)
    assert cache.get("litvar") == payload


def test_cache_overwrite_replaces_value(tmp_path):
    cache = RequestCache(str(tmp_path / "c.sqlite"))
    cache.put("k", {"v": 1})
    cache.put("k", {"v": 2})
    assert cache.get("k") == {"v": 2}


def test_cache_persists_across_reconnect(tmp_path):
    # A frozen snapshot must survive a process restart (offline replay / regression gate).
    path = str(tmp_path / "c.sqlite")
    RequestCache(path).put("k", {"kept": True})
    reopened = RequestCache(path)                        # new connection, same db file
    assert reopened.get("k") == {"kept": True}


def test_cache_creates_missing_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c.sqlite"
    cache = RequestCache(str(nested))                   # parents auto-created
    cache.put("k", {"ok": 1})
    assert nested.exists() and cache.get("k") == {"ok": 1}


def test_cache_stats_accumulate_across_many_ops(tmp_path):
    cache = RequestCache(str(tmp_path / "c.sqlite"))
    cache.get("absent1")            # miss
    cache.get("absent2")            # miss
    cache.put("k", {"v": 1})
    cache.get("k")                  # hit
    cache.get("k")                  # hit
    cache.get("k")                  # hit
    assert cache.stats() == (3, 2)  # hits and misses accumulate independently


def test_put_rejects_non_json_serialisable_value(tmp_path):
    cache = RequestCache(str(tmp_path / "c.sqlite"))
    with pytest.raises(TypeError):
        cache.put("k", object())    # not JSON-serialisable -> TypeError
    # json.dumps raises before execute/commit, so no partial row is written.
    assert cache.get("k") is None


def test_api_key_is_not_recoverable_from_key_or_stored_value(tmp_path):
    # A secret passed as a query param must be one-way-hashed into the key (never
    # plaintext) and must never be persisted in the stored value.
    secret = "SECRET_NCBI_KEY_123"
    key = make_key("https://eutils", "/esummary.fcgi", {"id": "1", "api_key": secret})
    assert secret not in key
    cache = RequestCache(str(tmp_path / "c.sqlite"))
    cache.put(key, {"result": {"uids": ["1"]}})   # response body only, no secret
    stored_key, stored_value = cache._conn.execute("SELECT key, value FROM cache").fetchone()
    assert secret not in stored_key and secret not in stored_value


def test_close_and_context_manager(tmp_path):
    path = str(tmp_path / "c.sqlite")
    with RequestCache(path) as cache:
        cache.put("k", {"v": 1})
        assert cache.get("k") == {"v": 1}
    # After the context exits the connection is closed; reusing it raises.
    with pytest.raises(sqlite3.ProgrammingError):
        cache.get("k")
    # Data was committed, so a fresh cache on the same file still reads it.
    assert RequestCache(path).get("k") == {"v": 1}


def test_del_closes_connection_and_is_guarded(tmp_path):
    c = RequestCache(str(tmp_path / "c.sqlite"))
    conn = c._conn
    c.__del__()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")             # the finalizer closed the connection
    # Safe even if __init__ never assigned _conn (object built via __new__).
    RequestCache.__new__(RequestCache).__del__()
