import pytest

from clineval.pipeline.throttle import RateLimiter, retry_with_backoff


class FakeClock:
    """Deterministic monotonic clock whose sleep advances the clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_rate_limiter_first_call_does_not_wait():
    fc = FakeClock()
    RateLimiter(2.0, clock=fc.clock, sleep=fc.sleep).acquire()
    assert fc.slept == []


def test_rate_limiter_spaces_back_to_back_calls():
    fc = FakeClock()
    lim = RateLimiter(2.0, clock=fc.clock, sleep=fc.sleep)  # 2/sec -> 0.5s apart
    lim.acquire()   # t=0, no wait
    lim.acquire()   # immediate -> must sleep the 0.5s interval
    assert fc.slept == [0.5]


def test_rate_limiter_no_wait_when_enough_time_elapsed():
    fc = FakeClock()
    lim = RateLimiter(2.0, clock=fc.clock, sleep=fc.sleep)
    lim.acquire()
    fc.advance(1.0)          # more than the 0.5s interval has passed
    lim.acquire()
    assert fc.slept == []    # no wait needed


def test_rate_limiter_zero_rate_disables_limiting():
    fc = FakeClock()
    lim = RateLimiter(0, clock=fc.clock, sleep=fc.sleep)
    lim.acquire()
    lim.acquire()
    assert fc.slept == []


def test_rate_limiter_negative_rate_disables_limiting():
    # rate < 0 must behave like 0 (disabled) with no ZeroDivisionError.
    fc = FakeClock()
    lim = RateLimiter(-5, clock=fc.clock, sleep=fc.sleep)
    lim.acquire()
    lim.acquire()
    assert fc.slept == []


def test_rate_limiter_no_drift_across_three_calls():
    # After sleeping, _last is re-read post-sleep, so each interval is measured from
    # when the call actually proceeded -> a 3rd immediate call waits a full interval
    # again (no drift, and never faster than target).
    fc = FakeClock()
    lim = RateLimiter(2.0, clock=fc.clock, sleep=fc.sleep)  # 0.5s apart
    lim.acquire()   # t=0
    lim.acquire()   # sleeps 0.5 -> t=0.5
    lim.acquire()   # immediate -> sleeps 0.5 again (measured from t=0.5)
    assert fc.slept == [0.5, 0.5]


def test_retry_succeeds_first_try_without_sleeping():
    slept: list[float] = []
    assert retry_with_backoff(lambda: "ok", sleep=slept.append) == "ok"
    assert slept == []


def test_retry_eventually_succeeds_with_exponential_backoff():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    slept: list[float] = []
    result = retry_with_backoff(flaky, base_delay=0.1, sleep=slept.append, exceptions=(ValueError,))
    assert result == "ok" and calls["n"] == 3
    assert slept == [0.1, 0.2]   # exponential: base*2^0, then base*2^1


def test_retry_reraises_after_exhausting_retries():
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry_with_backoff(
            always_fail, retries=2, base_delay=0.0, sleep=lambda s: None, exceptions=(ValueError,)
        )
    assert calls["n"] == 3   # initial attempt + 2 retries


def test_retry_default_retries_does_three_backoffs_then_raises():
    # Pins the headline default: retries=3 -> 4 total calls, sleeps [b, 2b, 4b].
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise ValueError("x")

    slept: list[float] = []
    with pytest.raises(ValueError):
        retry_with_backoff(always_fail, base_delay=0.1, sleep=slept.append, exceptions=(ValueError,))
    assert calls["n"] == 4                    # initial attempt + default 3 retries
    assert slept == [0.1, 0.2, 0.4]           # base*2^0, base*2^1, base*2^2


def test_retry_does_not_catch_unlisted_exceptions():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise KeyError("not retried")

    with pytest.raises(KeyError):
        retry_with_backoff(fn, sleep=lambda s: None, exceptions=(ValueError,))
    assert calls["n"] == 1   # a non-listed exception propagates immediately, no retry
