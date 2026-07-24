"""SQLite-backed request cache: deterministic, offline-replayable API responses.

Keyed by (base_url, path, sorted params). Values are any JSON-serialisable payload
— a dict for most responses, or a list (e.g. LitVar2 autocomplete returns an array).
Persisting to SQLite makes live reruns cheap and lets the retrieval eval replay
offline, which is what makes it a deterministic regression gate.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def make_key(base_url: str, path: str, params: dict | None) -> str:
    """Stable sha256 over (base_url, path, params); param order is irrelevant.

    base_url/path/params occupy distinct JSON fields, so no value can collide
    across fields; only a true sha256 collision could map two different requests
    to one key.
    """
    payload = json.dumps(
        {"b": base_url, "p": path, "q": params or {}}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RequestCache:
    """Keyed JSON store over sqlite3 (stdlib). ``stats()`` exposes hit/miss counts for
    optional observability — they are NOT carried into the IVDR provenance snapshot.

    Single-threaded: one connection per process (sqlite's default
    ``check_same_thread=True``). The Phase-1 pipeline is sequential — do not share
    a RequestCache across threads. Stored values must be JSON-serialisable and must
    not be JSON ``null``: a stored ``null`` is indistinguishable from a miss (none
    of the pipeline's APIs return a bare ``null`` body). Use as a context manager,
    or call ``close()``, to release the connection deterministically.
    """

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.commit()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Return the cached JSON value for ``key``, or None on a miss.

        A stored JSON ``null`` cannot be told apart from a miss; callers must not
        cache ``null`` bodies (see the class docstring).
        """
        row = self._conn.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            self._misses += 1
            return None
        self._hits += 1
        return json.loads(row[0])

    def put(self, key: str, value: Any) -> None:
        """Store a JSON-serialisable value under ``key`` (overwrites any prior value).

        Raises ``TypeError`` if ``value`` is not JSON-serialisable.
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def stats(self) -> tuple[int, int]:
        """Return (hits, misses) accumulated since construction (per-process)."""
        return self._hits, self._misses

    def close(self) -> None:
        """Close the underlying sqlite connection (releases the file lock)."""
        self._conn.close()

    def __enter__(self) -> RequestCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        # Belt-and-suspenders for callers that don't close() explicitly (avoids a
        # ResourceWarning for the unclosed sqlite connection). Guarded in case
        # __init__ failed before assigning _conn.
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()
