"""Token bucket rate limiter with circuit breaker."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RateLimitConfig:
    requests_per_second: float
    max_backoff_seconds: float = 30.0
    circuit_breaker_threshold: int = 3
    circuit_breaker_recovery_seconds: float = 60.0


class RateLimiter:
    """Token bucket rate limiter with circuit breaker."""

    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._interval = 1.0 / config.requests_per_second
        self._last_request_time: float = 0.0
        self._consecutive_failures: int = 0
        self._circuit_opened_at: float | None = None

    @property
    def circuit_state(self) -> CircuitState:
        if self._consecutive_failures >= self.config.circuit_breaker_threshold:
            if self._circuit_opened_at is None:
                return CircuitState.OPEN
            elapsed = time.monotonic() - self._circuit_opened_at
            if elapsed >= self.config.circuit_breaker_recovery_seconds:
                return CircuitState.HALF_OPEN
            return CircuitState.OPEN
        return CircuitState.CLOSED

    def is_available(self) -> bool:
        state = self.circuit_state
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def acquire(self) -> float:
        """Acquire permission to make a request. Returns wait time in seconds."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed >= self._interval:
            self._last_request_time = now
            return 0.0
        wait = self._interval - elapsed
        self._last_request_time = now + wait
        return wait

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config.circuit_breaker_threshold:
            if self._circuit_opened_at is None:
                self._circuit_opened_at = time.monotonic()

    def get_backoff(self, attempt: int) -> float:
        """Get exponential backoff duration for given attempt number."""
        backoff = (2 ** (attempt - 1)) * self._interval
        return min(backoff, self.config.max_backoff_seconds)
