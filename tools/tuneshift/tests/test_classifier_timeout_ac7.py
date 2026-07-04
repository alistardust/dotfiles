"""FL2 AC7: bare enrich never hangs -- wall-clock timeout + real reachability.

The classifier's ``complete`` was bounded only by urllib/SDK socket-inactivity
timeouts, so a stalled backend could hang ``enrich`` indefinitely, and
``available`` reported True merely because an env var was set. AC7: hard
per-call wall-clock ceiling with an actionable error, and ``available`` that
reflects real reachability.
"""

from __future__ import annotations

import time

import pytest

from tuneshift.sequencer.classifier import (
    TrackClassifier,
    _resolve_llm_timeout,
    _TimeoutBackend,
)


def test_timeout_backend_raises_on_hang() -> None:
    class _Hang:
        def complete(self, *_a, **_k):
            time.sleep(5)

    wrapped = _TimeoutBackend(_Hang(), 0.1)
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="did not respond"):
        wrapped.complete("prompt", "model")
    assert time.monotonic() - start < 2  # abandoned fast, not after 5s


def test_timeout_backend_passes_through_result_and_attrs() -> None:
    class _Fast:
        selected_model = "m1"

        def complete(self, *_a, **_k):
            return "ok"

    wrapped = _TimeoutBackend(_Fast(), 5)
    assert wrapped.complete("p", "m") == "ok"
    assert wrapped.selected_model == "m1"  # attribute passthrough


def test_timeout_backend_reraises_inner_error() -> None:
    class _Boom:
        def complete(self, *_a, **_k):
            raise ValueError("backend blew up")

    wrapped = _TimeoutBackend(_Boom(), 5)
    with pytest.raises(ValueError, match="backend blew up"):
        wrapped.complete("p", "m")


def test_available_false_when_backend_unreachable() -> None:
    class _Unreachable:
        def ping(self):
            return False

        def complete(self, *_a, **_k):
            return ""

    classifier = TrackClassifier(backend=_Unreachable(), model="m")
    assert classifier.available is False


def test_available_true_when_backend_reachable() -> None:
    class _Reachable:
        def ping(self):
            return True

        def complete(self, *_a, **_k):
            return ""

    classifier = TrackClassifier(backend=_Reachable(), model="m")
    assert classifier.available is True


def test_available_true_when_no_probe_possible() -> None:
    class _NoPing:
        def complete(self, *_a, **_k):
            return ""

    classifier = TrackClassifier(backend=_NoPing(), model="m")
    assert classifier.available is True


def test_reachability_probe_is_cached() -> None:
    class _CountingPing:
        def __init__(self):
            self.calls = 0

        def ping(self):
            self.calls += 1
            return True

        def complete(self, *_a, **_k):
            return ""

    backend = _CountingPing()
    classifier = TrackClassifier(backend=backend, model="m")
    assert classifier.available
    assert classifier.available
    assert backend.calls == 1  # probed once, cached


def test_timeout_env_override(monkeypatch) -> None:
    monkeypatch.setenv("TUNESHIFT_LLM_TIMEOUT", "12")
    assert _resolve_llm_timeout() == 12.0
    monkeypatch.setenv("TUNESHIFT_LLM_TIMEOUT", "garbage")
    assert _resolve_llm_timeout() == 30.0
    monkeypatch.setenv("TUNESHIFT_LLM_TIMEOUT", "0")
    assert _resolve_llm_timeout() == 30.0
