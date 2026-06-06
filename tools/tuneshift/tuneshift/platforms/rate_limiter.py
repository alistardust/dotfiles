import time


class RateLimiter:
    """Simple rate limiter with blocking and non-blocking APIs."""

    def __init__(
        self,
        max_per_second: float = 4.0,
        *,
        calls_per_second: float | None = None,
    ):
        if calls_per_second is not None:
            max_per_second = calls_per_second
        self._min_interval = 1.0 / max_per_second
        self._last_call = 0.0

    def acquire(self) -> bool:
        """Try to acquire permission for a call without blocking."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            return False
        self._last_call = now
        return True

    def wait_time(self) -> float:
        """Return the remaining delay before the next call is allowed."""
        now = time.monotonic()
        elapsed = now - self._last_call
        return max(0.0, self._min_interval - elapsed)

    def wait(self) -> None:
        """Block until the next call is allowed."""
        delay = self.wait_time()
        if delay > 0:
            time.sleep(delay)
        self._last_call = time.monotonic()
