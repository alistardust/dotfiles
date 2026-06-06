"""Tests for the TuneShift rate limiter."""

from __future__ import annotations

import pytest

from tuneshift.platforms.rate_limiter import RateLimiter


class TestRateLimiterAcquire:
    def test_allows_first_request(self) -> None:
        limiter = RateLimiter(max_per_second=2.0)

        assert limiter.acquire() is True

    def test_blocks_until_interval_elapses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        timestamps = iter([10.0, 10.1, 10.6])
        monkeypatch.setattr(
            "tuneshift.platforms.rate_limiter.time.monotonic",
            lambda: next(timestamps),
        )
        limiter = RateLimiter(max_per_second=2.0)

        assert limiter.acquire() is True
        assert limiter.acquire() is False
        assert limiter.acquire() is True


class TestRateLimiterWait:
    def test_reports_remaining_wait_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("tuneshift.platforms.rate_limiter.time.monotonic", lambda: 10.1)
        limiter = RateLimiter(max_per_second=4.0)
        limiter._last_call = 10.0

        assert limiter.wait_time() == pytest.approx(0.15)

    def test_wait_sleeps_until_next_slot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sleep_calls: list[float] = []
        timestamps = iter([10.1, 10.25])
        monkeypatch.setattr(
            "tuneshift.platforms.rate_limiter.time.monotonic",
            lambda: next(timestamps),
        )
        monkeypatch.setattr(
            "tuneshift.platforms.rate_limiter.time.sleep",
            lambda delay: sleep_calls.append(delay),
        )
        limiter = RateLimiter(max_per_second=4.0)
        limiter._last_call = 10.0

        limiter.wait()

        assert sleep_calls == [pytest.approx(0.15)]
        assert limiter._last_call == pytest.approx(10.25)

    def test_wait_does_not_sleep_when_request_is_available(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sleep_calls: list[float] = []
        timestamps = iter([10.4, 10.4])
        monkeypatch.setattr(
            "tuneshift.platforms.rate_limiter.time.monotonic",
            lambda: next(timestamps),
        )
        monkeypatch.setattr(
            "tuneshift.platforms.rate_limiter.time.sleep",
            lambda delay: sleep_calls.append(delay),
        )
        limiter = RateLimiter(max_per_second=4.0)
        limiter._last_call = 10.0

        limiter.wait()

        assert sleep_calls == []
        assert limiter._last_call == pytest.approx(10.4)


def test_calls_per_second_alias_overrides_max_per_second() -> None:
    limiter = RateLimiter(max_per_second=1.0, calls_per_second=4.0)

    assert limiter._min_interval == pytest.approx(0.25)
