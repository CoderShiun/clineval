"""Shared HTTP JSON getter: cache-first, throttled, retried. Transport injectable.

Every API client calls ``HttpClient.get_json``, so the cross-cutting concerns live
here once:

- **Caching** — cache-first (miss -> fetch -> store), keyed by the *logical* request.
  Secret query params (``api_key``) are excluded from the key, so rotating a key does
  not bust the cache and no secret is hashed into it.
- **Rate limiting** — ``limiter.acquire()`` before each live call.
- **Retry** — exponential backoff on TRANSIENT errors only (network / 429 / 5xx). The
  transport classifies failures: it raises ``TransientHTTPError`` for retryable ones
  and lets permanent failures (other 4xx, decode errors) propagate immediately.

The ``transport`` seam — ``(url, params, headers) -> JSON`` — is injected in tests so
no network is touched; the default calls ``requests``.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from clineval.pipeline.cache import RequestCache, make_key
from clineval.pipeline.throttle import RateLimiter, retry_with_backoff


class TransientHTTPError(Exception):
    """A retryable failure: a network error, HTTP 429, or a 5xx response."""


def _requests_transport(url: str, params: dict, headers: dict) -> Any:
    """Default transport: GET ``url`` and return parsed JSON.

    Classifies failures so only transient ones are retried: network errors, 429, and
    5xx become ``TransientHTTPError``; other 4xx propagate as a permanent HTTPError.
    """
    import requests

    try:
        resp = requests.get(url, params=params or None, headers=headers or None, timeout=45)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,   # connection dropped mid-body -> retryable
    ) as exc:
        raise TransientHTTPError(f"network error for {url}: {exc}") from exc
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientHTTPError(f"HTTP {resp.status_code} for {url}")
    resp.raise_for_status()  # other 4xx -> permanent HTTPError (not retried)
    return resp.json()


class HttpClient:
    """Cache-first, throttled, retried JSON HTTP client with an injectable transport."""

    def __init__(
        self,
        *,
        cache: RequestCache | None = None,
        limiter: RateLimiter | None = None,
        transport: Callable[[str, dict, dict], Any] | None = None,
        cache_exclude: tuple[str, ...] = ("api_key",),
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._cache = cache
        self._limiter = limiter
        self._transport = transport or _requests_transport
        self._cache_exclude = set(cache_exclude)
        self._retries = retries
        self._sleep = sleep

    def get_json(
        self, base_url: str, path: str, params: dict | None = None, headers: dict | None = None
    ) -> Any:
        """GET ``base_url`` + ``path`` (cache-first, throttled, retried); return parsed JSON."""
        params = params or {}
        # Cache key = the LOGICAL request: exclude secret params (api_key) so rotating
        # a key doesn't invalidate the cache and no secret is hashed into the key.
        cache_params = {k: v for k, v in params.items() if k not in self._cache_exclude}
        key = make_key(base_url, path, cache_params)

        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        if self._limiter is not None:
            self._limiter.acquire()

        url = base_url.rstrip("/") + "/" + path.lstrip("/") if path else base_url
        # Retries are spaced by the backoff sleep (>= base_delay), not the limiter;
        # base_delay exceeds the NCBI min-interval and _last isn't advanced during
        # retries, so the next fresh request still cannot burst over the rate limit.
        result = retry_with_backoff(
            lambda: self._transport(url, params, headers or {}),
            retries=self._retries,
            sleep=self._sleep,
            exceptions=(TransientHTTPError,),
        )

        if self._cache is not None:
            self._cache.put(key, result)
        return result
