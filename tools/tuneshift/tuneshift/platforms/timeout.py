"""Bounded wall-clock timeout for network calls (BUG-4).

Platform HTTP clients (tidalapi, musicbrainzngs) expose no reliable per-call
timeout, so a single stalled connection can hang a resolve run indefinitely.
This mirrors the LLM path's explicit wall-clock timeout: the call runs on a
shared worker thread and is abandoned (from the caller's view) after ``timeout``
seconds, raising :class:`PlatformTimeout`. The underlying thread is not force
killed (Python cannot), but the caller stops waiting and the resolve worker's
transient-retry path takes over.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Callable, TypeVar

T = TypeVar("T")

# Default bound for a single platform call. Overridable like TUNESHIFT_LLM_TIMEOUT.
DEFAULT_NETWORK_TIMEOUT = 45.0

# One shared pool for all platform calls; daemon threads so a stuck call never
# blocks interpreter exit.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ts-net")


class PlatformTimeout(TimeoutError):
    """A platform network call exceeded its wall-clock budget."""


def network_timeout() -> float:
    """Configured per-call network timeout (seconds)."""
    raw = os.environ.get("TUNESHIFT_NETWORK_TIMEOUT")
    if not raw:
        return DEFAULT_NETWORK_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_NETWORK_TIMEOUT
    return value if value > 0 else DEFAULT_NETWORK_TIMEOUT


def call_with_timeout(fn: Callable[[], T], *, timeout: float | None = None) -> T:
    """Run ``fn`` with a wall-clock timeout, raising PlatformTimeout on expiry.

    Inner exceptions raised by ``fn`` propagate unchanged.
    """
    budget = network_timeout() if timeout is None else timeout
    future = _EXECUTOR.submit(fn)
    try:
        return future.result(timeout=budget)
    except FuturesTimeout as exc:
        future.cancel()
        raise PlatformTimeout(
            f"platform call exceeded {budget:.1f}s wall-clock timeout"
        ) from exc
