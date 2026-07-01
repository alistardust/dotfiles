"""Tests for the enrichment retry utility."""

from __future__ import annotations

import time
from urllib.error import HTTPError, URLError

import pytest

from tuneshift.enrichment.retry import (
    PermanentAPIError,
    RetryConfig,
    RetryStats,
    TransientAPIError,
    is_permanent,
    is_transient,
    retry_api_call,
)


def _http_error(code: int, headers: dict | None = None) -> HTTPError:
    return HTTPError("http://x", code, "err", headers or {}, None)


# --- Error classification ---


def test_transient_codes_classified():
    for code in (429, 500, 502, 503, 504):
        assert is_transient(_http_error(code))
        assert not is_permanent(_http_error(code))


def test_permanent_codes_classified():
    for code in (401, 403, 404):
        assert is_permanent(_http_error(code))
        assert not is_transient(_http_error(code))


def test_network_errors_transient():
    assert is_transient(URLError("timeout"))
    assert is_transient(TimeoutError())
    assert is_transient(ConnectionError())
    assert is_transient(OSError("network unreachable"))


def test_transient_permanent_exception_types():
    assert is_transient(TransientAPIError("rate limited"))
    assert is_permanent(PermanentAPIError("not found"))


def test_object_not_found_is_permanent():
    class ObjectNotFound(Exception):
        pass

    assert is_permanent(ObjectNotFound("track 123 not found"))
    assert not is_transient(ObjectNotFound("track 123 not found"))


def test_musicbrainz_503_string_transient():
    assert is_transient(Exception("HTTP Error 503: Service Unavailable"))


def test_musicbrainz_network_error_by_type_name():
    class NetworkError(Exception):
        pass

    assert is_transient(NetworkError("connection failed"))


def test_tidal_too_many_requests_transient_despite_message():
    """tidalapi relabels 429 TooManyRequests as 'Album unavailable' (album.py).

    The classifier must recognize it as transient by type name, not message.
    """
    class TooManyRequests(Exception):
        pass

    exc = TooManyRequests("Album unavailable")
    assert is_transient(exc)
    assert not is_permanent(exc)


def test_tidal_too_many_requests_not_permanent_even_with_notfound_message():
    """A rate limit must never be classified permanent, even if its message
    happens to contain NotFound-like text."""
    class TooManyRequests(Exception):
        pass

    exc = TooManyRequests("resource NotFound while rate limited")
    assert not is_permanent(exc)
    assert is_transient(exc)


# --- Retry behavior ---


def test_succeeds_on_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_api_call(fn, config=RetryConfig(max_retries=3))
    assert result == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds():
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise _http_error(429)
        return "recovered"

    config = RetryConfig(max_retries=3, base_delay=0.01)
    stats = RetryStats()
    result = retry_api_call(fn, config=config, stats=stats)
    assert result == "recovered"
    assert len(attempts) == 3
    assert stats.retries == 2


def test_permanent_error_no_retry():
    attempts = []

    def fn():
        attempts.append(1)
        raise _http_error(404)

    stats = RetryStats()
    with pytest.raises(HTTPError):
        retry_api_call(fn, config=RetryConfig(max_retries=3), stats=stats)
    assert len(attempts) == 1
    assert stats.permanent_failures == 1


def test_retries_exhausted_raises():
    attempts = []

    def fn():
        attempts.append(1)
        raise _http_error(503)

    config = RetryConfig(max_retries=2, base_delay=0.01)
    stats = RetryStats()
    with pytest.raises(HTTPError):
        retry_api_call(fn, config=config, stats=stats)
    # initial + 2 retries = 3 attempts
    assert len(attempts) == 3
    assert stats.transient_failures == 1


def test_non_transient_non_permanent_raises_immediately():
    attempts = []

    def fn():
        attempts.append(1)
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        retry_api_call(fn, config=RetryConfig(max_retries=3))
    assert len(attempts) == 1


def test_zero_retries_skips_on_failure():
    attempts = []

    def fn():
        attempts.append(1)
        raise _http_error(429)

    with pytest.raises(HTTPError):
        retry_api_call(fn, config=RetryConfig(max_retries=0))
    assert len(attempts) == 1


def test_exponential_backoff_progression(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    attempts = []

    def fn():
        attempts.append(1)
        raise _http_error(503)

    config = RetryConfig(max_retries=3, base_delay=1.0, jitter_factor=0.0)
    with pytest.raises(HTTPError):
        retry_api_call(fn, config=config)
    # delays: 1, 2, 4 (no jitter)
    assert sleeps == [1.0, 2.0, 4.0]


def test_jitter_within_bounds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    def fn():
        raise _http_error(503)

    config = RetryConfig(max_retries=1, base_delay=10.0, jitter_factor=0.25)
    with pytest.raises(HTTPError):
        retry_api_call(fn, config=config)
    # First retry: base 10s +/- 25% = [7.5, 12.5]
    assert 7.5 <= sleeps[0] <= 12.5


def test_header_aware_wait(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    reset_time = time.time() + 30
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 2:
            raise TransientAPIError(
                "rate limited",
                status_code=429,
                headers={"X-RateLimit-Reset": str(reset_time)},
            )
        return "ok"

    config = RetryConfig(max_retries=3, per_track_timeout=300)
    stats = RetryStats()
    result = retry_api_call(fn, config=config, stats=stats)
    assert result == "ok"
    # Should wait ~30s (reset time), not exponential backoff
    assert 25 <= sleeps[0] <= 31
    assert stats.rate_limit_waits == 1


def test_per_track_timeout_cap(monkeypatch):
    # Simulate sleeps advancing the monotonic clock so the timeout triggers
    clock = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["t"])

    def fake_sleep(s):
        clock["t"] += s

    monkeypatch.setattr(time, "sleep", fake_sleep)

    attempts = []

    def fn():
        attempts.append(1)
        raise TransientAPIError(
            "rate limited",
            headers={"X-RateLimit-Reset": str(time.time() + 10000)},
        )

    # per_track_timeout small; reset header wants huge wait -> capped, then times out
    config = RetryConfig(max_retries=10, per_track_timeout=5.0)
    stats = RetryStats()
    with pytest.raises(TransientAPIError):
        retry_api_call(fn, config=config, stats=stats)
    # Should not run all 10 retries; timeout caps total wait
    assert len(attempts) < 11


def test_stats_summary_formats():
    stats = RetryStats(retries=5, rate_limit_waits=2, total_wait_seconds=12.5)
    summary = stats.summary()
    assert "retries: 5" in summary
    assert "rate limit waits: 2" in summary
    assert "12.5s" in summary


def test_stats_summary_empty():
    assert RetryStats().summary() == "no issues"
