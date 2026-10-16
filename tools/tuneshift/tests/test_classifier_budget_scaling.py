"""Batch-scaled LLM budgets and honest Ollama failures.

``classify`` was the only ``complete`` caller that never passed ``max_tokens``,
so a 20-track batch asked for the same 4096-token default a single track gets.
The wall-clock budget had the same shape: one 30s ceiling regardless of batch
size. Ollama then reported truncation as an ordinary success through
``result.get("response", "")``, so the only visible symptom was a JSON parse
warning pointing at the wrong layer.

Measured on qwen3:30b-a3b at batch 20: 4096 tokens truncates
(``done_reason="length"``, 0/20 parsed) while 16k finishes on ``stop`` and
parses 20/20, at 8.5 s/track. Thinking must stay enabled: with it off the model
reasons in the visible channel and returns no parseable JSON at all.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import pytest

from tuneshift.sequencer import classifier
from tuneshift.sequencer.classifier import (
    LLMTruncationError,
    OllamaBackend,
    TrackClassifier,
    _llm_timeout_for,
    _llm_tokens_for,
    _resolve_llm_tokens,
    _TimeoutBackend,
)

_MEASURED_BATCH = 20
_TRUNCATING_BUDGET = 4096
_MEASURED_SECONDS_PER_TRACK = 8.5
_MEASURED_TOKENS_PER_TRACK = 16_000 // _MEASURED_BATCH


def _tracks(count: int) -> list[dict[str, str]]:
    return [{"title": f"t{i}", "artist": "a"} for i in range(count)]


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _stub_ollama(
    monkeypatch: pytest.MonkeyPatch, generate_body: dict[str, Any]
) -> dict[str, Any]:
    """Serve /api/tags and /api/generate, recording the generate request."""
    seen: dict[str, Any] = {}

    def fake_urlopen(target: Any, *_a: object, **kwargs: object) -> _FakeResponse:
        url = str(getattr(target, "full_url", target))
        if url.endswith("/api/tags"):
            return _FakeResponse({"models": [{"name": "m"}]})
        seen["payload"] = json.loads(target.data)
        seen["timeout"] = kwargs.get("timeout")
        return _FakeResponse(generate_body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


class TestBudgetsScaleWithBatchSize:
    """A batch of N must not be given a single call's budget."""

    def test_token_budget_grows_with_the_batch(self) -> None:
        assert _llm_tokens_for(_MEASURED_BATCH) > _llm_tokens_for(1)

    def test_measured_batch_clears_the_budget_that_truncated(self) -> None:
        # 4096 was measured to truncate at batch 20; 16k was measured to work.
        assert _llm_tokens_for(_MEASURED_BATCH) > _TRUNCATING_BUDGET
        assert _llm_tokens_for(_MEASURED_BATCH) >= 16000

    def test_small_batches_keep_the_existing_floor(self) -> None:
        assert _llm_tokens_for(1) == _TRUNCATING_BUDGET
        assert _llm_timeout_for(1) == 30.0

    def test_a_zero_length_batch_still_gets_the_floor(self) -> None:
        assert _llm_tokens_for(0) == _TRUNCATING_BUDGET
        assert _llm_timeout_for(0) == 30.0

    def test_timeout_budget_clears_the_measured_wall_clock(self) -> None:
        assert _llm_timeout_for(_MEASURED_BATCH) >= (
            _MEASURED_SECONDS_PER_TRACK * _MEASURED_BATCH
        )

    def test_scaling_holds_well_past_the_measured_batch(self) -> None:
        # Anchored to the measured rates, not to the helper's own arithmetic.
        big = _MEASURED_BATCH * 5
        assert _llm_tokens_for(big) >= _MEASURED_TOKENS_PER_TRACK * big
        assert _llm_timeout_for(big) >= _MEASURED_SECONDS_PER_TRACK * big

    def test_token_floor_is_env_overridable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TUNESHIFT_LLM_TOKENS", "9001")
        assert _resolve_llm_tokens() == 9001
        monkeypatch.setenv("TUNESHIFT_LLM_TOKENS", "garbage")
        assert _resolve_llm_tokens() == _TRUNCATING_BUDGET
        monkeypatch.setenv("TUNESHIFT_LLM_TOKENS", "0")
        assert _resolve_llm_tokens() == _TRUNCATING_BUDGET


class TestClassifyPassesTheScaledBudgets:
    """The wiring, not just the arithmetic: classify must actually send them."""

    @staticmethod
    def _spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []

        def fake_complete(
            _self: object,
            _prompt: str,
            _model: str,
            max_tokens: int = 4096,
            *,
            timeout_seconds: float | None = None,
        ) -> str:
            calls.append({"max_tokens": max_tokens, "timeout": timeout_seconds})
            return '[{"title": "t0", "artist": "a", "energy": 0.5}]'

        monkeypatch.setattr(_TimeoutBackend, "complete", fake_complete)
        return calls

    def test_batch_classify_asks_for_more_than_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._spy(monkeypatch)
        TrackClassifier(backend=object(), model="m").classify(
            _tracks(_MEASURED_BATCH)
        )
        assert calls[0]["max_tokens"] == _llm_tokens_for(_MEASURED_BATCH)
        assert calls[0]["max_tokens"] > _TRUNCATING_BUDGET

    def test_batch_classify_sends_a_scaled_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._spy(monkeypatch)
        TrackClassifier(backend=object(), model="m").classify(
            _tracks(_MEASURED_BATCH)
        )
        assert calls[0]["timeout"] == _llm_timeout_for(_MEASURED_BATCH)
        assert calls[0]["timeout"] > 30.0

    def test_single_track_classify_is_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._spy(monkeypatch)
        TrackClassifier(backend=object(), model="m").classify(_tracks(1))
        assert calls[0]["max_tokens"] == _TRUNCATING_BUDGET
        assert calls[0]["timeout"] == 30.0


class TestTruncationStopsTheRetryLoop:
    """Retrying an identical request cannot undo a token ceiling."""

    @staticmethod
    def _counting_backend(
        monkeypatch: pytest.MonkeyPatch, exc: Exception
    ) -> list[int]:
        attempts: list[int] = []

        def fake_complete(*_a: object, **_k: object) -> str:
            attempts.append(1)
            raise exc

        monkeypatch.setattr(_TimeoutBackend, "complete", fake_complete)
        return attempts

    def test_truncation_breaks_after_one_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = self._counting_backend(
            monkeypatch, LLMTruncationError("hit the ceiling")
        )
        out = TrackClassifier(backend=object(), model="m").classify(_tracks(2))
        assert out == []
        assert len(attempts) == 1

    def test_other_failures_still_use_every_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = self._counting_backend(monkeypatch, RuntimeError("transient"))
        monkeypatch.setattr(classifier.time, "sleep", lambda _s: None)
        out = TrackClassifier(backend=object(), model="m").classify(
            _tracks(2), max_retries=3
        )
        assert out == []
        assert len(attempts) == 3

    def test_the_break_is_logged_with_the_actionable_message(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._counting_backend(
            monkeypatch,
            LLMTruncationError(
                "m hit the 4096-token ceiling. Raise TUNESHIFT_LLM_TOKENS."
            ),
        )
        with caplog.at_level("ERROR"):
            TrackClassifier(backend=object(), model="m").classify(_tracks(2))
        assert "Classification stopped" in caplog.text
        assert "TUNESHIFT_LLM_TOKENS" in caplog.text

    def test_truncation_is_catchable_as_runtime_error(self) -> None:
        """Existing call sites catch RuntimeError; they must keep working."""
        assert issubclass(LLMTruncationError, RuntimeError)


class TestTimeoutOverride:
    def test_override_replaces_the_construction_time_budget(self) -> None:
        class _Slow:
            def complete(self, *_a: object, **_k: object) -> str:
                time.sleep(5)
                return "late"

        wrapped = _TimeoutBackend(_Slow(), 10.0)
        start = time.monotonic()
        with pytest.raises(TimeoutError, match="did not respond"):
            wrapped.complete("p", "m", 4096, timeout_seconds=0.1)
        assert time.monotonic() - start < 2

    def test_override_can_be_more_generous_than_the_default(self) -> None:
        """A batch budget must be allowed to exceed the single-call floor.

        Taking a min here would reinstate the defect: the construction-time
        value sizes one call, and the whole point is that it is too small for
        a batch.
        """

        class _Brief:
            def complete(self, *_a: object, **_k: object) -> str:
                time.sleep(0.3)
                return "ok"

        wrapped = _TimeoutBackend(_Brief(), 0.05)
        assert wrapped.complete("p", "m", 4096, timeout_seconds=5.0) == "ok"

    def test_the_inner_backend_never_sees_the_timeout_argument(self) -> None:
        seen: dict[str, Any] = {}

        class _Recorder:
            def complete(self, *args: object, **kwargs: object) -> str:
                seen["args"] = args
                seen["kwargs"] = kwargs
                return "ok"

        _TimeoutBackend(_Recorder(), 5.0).complete(
            "p", "m", 4096, timeout_seconds=9.0
        )
        assert seen["args"] == ("p", "m", 4096)
        assert seen["kwargs"] == {}


class TestOllamaReportsTruncationHonestly:
    """A truncated generation is a failure, not an empty success."""

    def test_length_stop_raises_naming_the_ceiling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_ollama(
            monkeypatch,
            {"response": '[{"title": "t0"', "done_reason": "length"},
        )
        with pytest.raises(RuntimeError, match="token generation ceiling"):
            OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)

    def test_the_raised_error_names_the_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_ollama(
            monkeypatch, {"response": "partial", "done_reason": "length"}
        )
        with pytest.raises(RuntimeError, match="TUNESHIFT_LLM_TOKENS"):
            OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)

    def test_an_empty_response_raises_rather_than_returning_blank(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_ollama(monkeypatch, {"response": "", "done_reason": "stop"})
        with pytest.raises(RuntimeError, match="empty response"):
            OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)

    def test_a_whitespace_only_response_also_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_ollama(monkeypatch, {"response": "   \n ", "done_reason": "stop"})
        with pytest.raises(RuntimeError, match="empty response"):
            OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)

    def test_a_normal_completion_still_returns_its_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_ollama(monkeypatch, {"response": "[]", "done_reason": "stop"})
        out = OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)
        assert out == "[]"

    def test_a_missing_done_reason_is_not_treated_as_truncation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_ollama(monkeypatch, {"response": "[]"})
        out = OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)
        assert out == "[]"

    def test_truncation_raises_even_when_the_partial_text_parses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cut-off array can still be valid JSON and silently lose tracks."""
        _stub_ollama(
            monkeypatch,
            {"response": '[{"title": "t0"}]', "done_reason": "length"},
        )
        with pytest.raises(RuntimeError, match="token generation ceiling"):
            OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)


class TestOllamaRequestShape:
    def test_thinking_is_never_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Measured: thinking off yields prose and zero parseable JSON.

        An explicit ``think: True`` stays legal; only disabling is pinned.
        """
        seen = _stub_ollama(monkeypatch, {"response": "[]", "done_reason": "stop"})
        OllamaBackend(host="http://localhost:11434").complete("p", "m", 4096)
        payload = seen["payload"]
        assert payload.get("think") is not False
        assert payload.get("options", {}).get("think") is not False

    def test_the_requested_budget_reaches_num_predict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _stub_ollama(monkeypatch, {"response": "[]", "done_reason": "stop"})
        OllamaBackend(host="http://localhost:11434").complete("p", "m", 16000)
        assert seen["payload"]["options"]["num_predict"] == 16000

    def test_socket_budget_clears_a_long_generation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stream=False sends nothing until done, so the read must outlast it."""
        seen = _stub_ollama(monkeypatch, {"response": "[]", "done_reason": "stop"})
        OllamaBackend(host="http://localhost:11434").complete("p", "m", 16000)
        assert seen["timeout"] > _llm_timeout_for(_MEASURED_BATCH)

    def test_small_budgets_keep_the_existing_socket_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _stub_ollama(monkeypatch, {"response": "[]", "done_reason": "stop"})
        OllamaBackend(host="http://localhost:11434").complete("p", "m", 60)
        assert seen["timeout"] == 300.0


class TestUnparseableRepliesAreVisible:
    def test_a_reply_that_parses_to_nothing_is_logged_each_attempt(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Truncation aside, prose replies used to retry three times in silence."""

        def fake_complete(*_a: object, **_k: object) -> str:
            return "I think the first track is quite upbeat, because..."

        monkeypatch.setattr(_TimeoutBackend, "complete", fake_complete)
        with caplog.at_level("WARNING", logger=classifier.__name__):
            results = TrackClassifier(backend=object(), model="m").classify(
                _tracks(2)
            )
        assert results == []
        assert sum("parsed to nothing" in r.message for r in caplog.records) == 3
