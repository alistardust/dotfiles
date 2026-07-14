"""Injectable, degradable LLM concept judge (Task 4)."""

from tuneshift.composer.concept_llm import (
    TrackCtx,
    build_concept_judge,
)


class _FakeBackend:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def complete(self, prompt, model, max_tokens=4096):
        self.calls += 1
        return self._payload


def test_judge_parses_batched_verdicts():
    backend = _FakeBackend('{"1": "violates", "2": "complies"}')
    judge = build_concept_judge(backend=backend, model="m")
    out = judge("not about wanting a man", [
        TrackCtx(1, "Need a Man", "X", ["romance"], "wanting a partner"),
        TrackCtx(2, "Independent", "Y", ["empowerment"], "self-reliance"),
    ])
    assert out == {1: "violates", 2: "complies"}
    assert backend.calls == 1  # one batched call, not one per track


def test_judge_extracts_json_from_wrapped_prose():
    backend = _FakeBackend('Sure! Here you go:\n{"1": "unsure"}\nHope that helps.')
    judge = build_concept_judge(backend=backend, model="m")
    assert judge("rule", [TrackCtx(1, "T", "A", [], None)]) == {1: "unsure"}


def test_judge_degrades_to_unsure_on_bad_output():
    judge = build_concept_judge(backend=_FakeBackend("not json"), model="m")
    assert judge("rule", [TrackCtx(1, "T", "A", [], None)]) == {1: "unsure"}


def test_judge_unknown_verdict_becomes_unsure():
    backend = _FakeBackend('{"1": "maybe", "2": "violates"}')
    judge = build_concept_judge(backend=backend, model="m")
    out = judge("rule", [TrackCtx(1, "A", "X"), TrackCtx(2, "B", "Y")])
    assert out == {1: "unsure", 2: "violates"}


def test_judge_missing_track_becomes_unsure():
    backend = _FakeBackend('{"1": "complies"}')
    judge = build_concept_judge(backend=backend, model="m")
    out = judge("rule", [TrackCtx(1, "A", "X"), TrackCtx(2, "B", "Y")])
    assert out == {1: "complies", 2: "unsure"}


def test_judge_raising_backend_degrades_all_to_unsure():
    class _Boom:
        def complete(self, *a, **k):
            raise RuntimeError("backend down")

    judge = build_concept_judge(backend=_Boom(), model="m")
    out = judge("rule", [TrackCtx(1, "A", "X"), TrackCtx(2, "B", "Y")])
    assert out == {1: "unsure", 2: "unsure"}


def test_make_concept_judge_returns_none_when_no_backend(monkeypatch):
    from tuneshift.composer import concept_llm
    monkeypatch.setattr(concept_llm, "_select_backend", lambda: None)
    assert concept_llm.make_concept_judge() is None


def test_make_concept_judge_returns_callable_when_backend_present(monkeypatch):
    from tuneshift.composer import concept_llm
    backend = _FakeBackend('{"1": "complies"}')
    monkeypatch.setattr(concept_llm, "_select_backend", lambda: (backend, "m"))
    judge = concept_llm.make_concept_judge()
    assert judge is not None
    assert judge("rule", [TrackCtx(1, "A", "X")]) == {1: "complies"}
