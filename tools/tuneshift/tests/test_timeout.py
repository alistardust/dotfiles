"""Tests for the bounded wall-clock timeout helper (BUG-4)."""

import time

import pytest

from tuneshift.platforms.timeout import PlatformTimeout, call_with_timeout


def test_call_with_timeout_returns_value_when_fast():
    assert call_with_timeout(lambda: 42, timeout=1.0) == 42


def test_call_with_timeout_raises_platform_timeout_when_slow():
    def slow():
        time.sleep(2.0)
        return "never"

    with pytest.raises(PlatformTimeout):
        call_with_timeout(slow, timeout=0.1)


def test_call_with_timeout_propagates_inner_exception():
    def boom():
        raise ValueError("inner")

    with pytest.raises(ValueError, match="inner"):
        call_with_timeout(boom, timeout=1.0)
