"""Chunk 2 Task 2.1: the typed Criterion protocol + registry (AC-C1).

Every matchable/preferable field becomes a registered typed unit — extractor,
comparator, score-projection, hard-cap policy. Adding a criterion is
registration + config, NO bespoke scoring code. The parity-critical contract is
"no verdict => no signal": a criterion with no active preference referencing it
returns None from to_signal and contributes NOTHING to the Distance.
"""

from __future__ import annotations

import pytest

from tuneshift.matching.criteria import (
    Criterion,
    CriterionRegistry,
    CriterionValue,
    HardCapPolicy,
    Strength,
    Verdict,
)
from tuneshift.matching.engine import Distance
from tuneshift.matching.penalties import SignalPenalty


class _DummyGenreCriterion:
    """A minimal criterion over a track's `genre` attribute for the test."""

    name = "genre"
    hard_cap = HardCapPolicy.NONE

    def extract(self, meta: object) -> CriterionValue | None:
        genre = getattr(meta, "genre", None)
        if not genre:
            return None
        return CriterionValue(raw=genre, tokens=frozenset({str(genre).lower()}),
                              structured=True)

    def compare(
        self,
        source: CriterionValue,
        candidate: CriterionValue,
        strength: Strength | None,
    ) -> Verdict:
        if strength is None:
            return Verdict.NO_VERDICT
        if strength is Strength.PREFER:
            return (
                Verdict.SOFT_BONUS
                if source.tokens & candidate.tokens
                else Verdict.SOFT_PENALTY
            )
        return Verdict.NEUTRAL

    def to_signal(self, verdict: Verdict) -> SignalPenalty | None:
        if verdict is Verdict.SOFT_PENALTY:
            return SignalPenalty("genre", -5, 1.0, 5)
        if verdict is Verdict.SOFT_BONUS:
            return SignalPenalty("genre", 5, 0.0, 5)
        return None


class _Meta:
    def __init__(self, genre=None):
        self.genre = genre


def test_registry_registers_and_retrieves() -> None:
    reg = CriterionRegistry()
    crit = _DummyGenreCriterion()
    reg.register(crit)
    assert reg.get("genre") is crit
    assert "genre" in reg
    assert [c.name for c in reg] == ["genre"]


def test_registry_rejects_duplicate_names() -> None:
    reg = CriterionRegistry()
    reg.register(_DummyGenreCriterion())
    with pytest.raises(ValueError, match="genre"):
        reg.register(_DummyGenreCriterion())


def test_dummy_criterion_flows_end_to_end_through_distance() -> None:
    """A registered criterion projects into a real Distance untouched — proving
    the registry EXTENDS the weighted engine rather than rewriting it (AC-C1)."""
    crit: Criterion = _DummyGenreCriterion()
    src = crit.extract(_Meta(genre="rock"))
    cand = crit.extract(_Meta(genre="pop"))
    verdict = crit.compare(src, cand, Strength.PREFER)
    assert verdict is Verdict.SOFT_PENALTY

    distance = Distance()
    signal = crit.to_signal(verdict)
    assert signal is not None
    distance.add(signal)
    assert distance.has_signal("genre")
    assert distance.total > 0.0


def test_no_active_preference_emits_no_signal() -> None:
    """The parity contract: a criterion with no active preference (strength=None)
    yields NO_VERDICT and to_signal None, leaving Distance.signals byte-identical
    to the no-criterion case (AC-C1 / AC-C5 winner-parity)."""
    crit = _DummyGenreCriterion()
    src = crit.extract(_Meta(genre="rock"))
    cand = crit.extract(_Meta(genre="pop"))

    verdict = crit.compare(src, cand, None)
    assert verdict is Verdict.NO_VERDICT
    assert crit.to_signal(verdict) is None

    baseline = Distance()
    with_unreferenced = Distance()
    signal = crit.to_signal(verdict)
    if signal is not None:  # must not happen
        with_unreferenced.add(signal)
    assert with_unreferenced.signals == baseline.signals
    assert with_unreferenced.total == baseline.total


def test_unextractable_value_is_none() -> None:
    """A field absent on the metadata extracts to None (=> engine skips it)."""
    crit = _DummyGenreCriterion()
    assert crit.extract(_Meta(genre=None)) is None


def test_hard_verdict_emits_no_soft_signal() -> None:
    """Hard verdicts cap the recommendation (via hard_cap); they never score as
    a soft SignalPenalty (AC-C2 preview)."""
    class _RequireCrit(_DummyGenreCriterion):
        hard_cap = HardCapPolicy.REJECT

        def compare(self, source, candidate, strength):
            if strength is Strength.REQUIRE:
                return (
                    Verdict.HARD_PASS
                    if source.tokens & candidate.tokens
                    else Verdict.HARD_REJECT
                )
            return Verdict.NO_VERDICT

    crit = _RequireCrit()
    src = crit.extract(_Meta(genre="rock"))
    cand = crit.extract(_Meta(genre="pop"))
    verdict = crit.compare(src, cand, Strength.REQUIRE)
    assert verdict is Verdict.HARD_REJECT
    assert crit.to_signal(verdict) is None
