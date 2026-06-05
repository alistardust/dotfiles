"""Tests for rate limiter with circuit breaker."""

import time

import pytest

from tidal_importer.identity.rate_limiter import (
    CircuitState,
    RateLimiter,
    RateLimitConfig,
)


@pytest.fixture
def fast_limiter():
    config = RateLimitConfig(
        requests_per_second=100.0,
        max_backoff_seconds=1.0,
        circuit_breaker_threshold=3,
        circuit_breaker_recovery_seconds=0.1,
    )
    return RateLimiter(config)


@pytest.fixture
def slow_limiter():
    config = RateLimitConfig(
        requests_per_second=1.0,
        max_backoff_seconds=30.0,
        circuit_breaker_threshold=3,
        circuit_breaker_recovery_seconds=60.0,
    )
    return RateLimiter(config)


class TestTokenBucket:
    def test_allows_first_request(self, fast_limiter):
        assert fast_limiter.acquire() == 0.0

    def test_rate_limits(self, slow_limiter):
        slow_limiter.acquire()
        assert slow_limiter.acquire() > 0.0


class TestCircuitBreaker:
    def test_starts_closed(self, fast_limiter):
        assert fast_limiter.circuit_state == CircuitState.CLOSED

    def test_opens_after_threshold(self, fast_limiter):
        for _ in range(3):
            fast_limiter.record_failure()
        assert fast_limiter.circuit_state == CircuitState.OPEN

    def test_open_blocks_requests(self, fast_limiter):
        for _ in range(3):
            fast_limiter.record_failure()
        assert fast_limiter.is_available() is False

    def test_half_open_after_recovery(self, fast_limiter):
        for _ in range(3):
            fast_limiter.record_failure()
        time.sleep(0.15)
        assert fast_limiter.circuit_state == CircuitState.HALF_OPEN

    def test_success_closes_circuit(self, fast_limiter):
        for _ in range(3):
            fast_limiter.record_failure()
        time.sleep(0.15)
        fast_limiter.record_success()
        assert fast_limiter.circuit_state == CircuitState.CLOSED

    def test_success_resets_count(self, fast_limiter):
        fast_limiter.record_failure()
        fast_limiter.record_failure()
        fast_limiter.record_success()
        fast_limiter.record_failure()
        assert fast_limiter.circuit_state == CircuitState.CLOSED


class TestBackoff:
    def test_exponential(self, fast_limiter):
        b1 = fast_limiter.get_backoff(1)
        b2 = fast_limiter.get_backoff(2)
        assert b2 == b1 * 2

    def test_capped(self, fast_limiter):
        assert fast_limiter.get_backoff(20) <= fast_limiter.config.max_backoff_seconds
