"""Politeness layer: a token-spaced rate limiter + exponential-backoff retry.

Both take injected ``clock``/``sleep`` callables so tests are deterministic (no real
time passes). Used by the shared HTTP client to respect NCBI rate limits (~3 req/s
without an API key, ~10 with one) and to survive transient 429/5xx responses.
"""

from __future__ import annotations

import time
from typing import Any, Callable


class RateLimiter:
    """Space successive ``acquire()`` calls at least ``1/rate`` seconds apart.

    ``rate_per_sec <= 0`` disables limiting. ``clock``/``sleep`` are injectable so
    tests need not pass real wall-clock time. Not thread-safe: a single-consumer
    minimum-interval spacer (no burst capacity), which is the safe choice for polite
    NCBI access — it can never burst over the limit.
    """

    def __init__(
        self,
        rate_per_sec: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def acquire(self) -> None:
        """Wait (via ``sleep``) until the minimum interval since the last call elapsed."""
        if self._last is not None:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()


def retry_with_backoff(
    fn: Callable[[], Any],
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Any:
    """Call ``fn()``; on one of ``exceptions``, retry with exponential backoff.

    Sleeps ``base_delay * 2**(attempt-1)`` before each retry (no cap or jitter) and
    re-raises the last exception after ``retries`` retries; exceptions not in
    ``exceptions`` propagate immediately without retrying. Callers should pass a
    NARROW tuple of transient errors (network/timeout/429/5xx) — the broad default
    ``(Exception,)`` would also retry deterministic failures (4xx) and bugs.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except exceptions:
            attempt += 1
            if attempt > retries:
                raise
            sleep(base_delay * (2 ** (attempt - 1)))
