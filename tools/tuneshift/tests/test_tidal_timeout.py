"""Tests for Tidal per-call wall-clock timeout (BUG-4)."""

import time

import pytest

from tuneshift.platforms.tidal import _retry
from tuneshift.platforms.timeout import PlatformTimeout


def test_retry_times_out_a_hanging_call(monkeypatch):
    monkeypatch.setenv("TUNESHIFT_NETWORK_TIMEOUT", "0.1")

    def hang():
        time.sleep(5.0)

    start = time.monotonic()
    with pytest.raises(PlatformTimeout):
        _retry(hang, max_retries=0)
    assert time.monotonic() - start < 2.0  # did not actually wait 5s


def test_retry_still_returns_fast_value():
    assert _retry(lambda: "ok") == "ok"
