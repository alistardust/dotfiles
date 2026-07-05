"""Chunk 2 Task 2.2: the four strengths behave distinctly (AC-C2).

require/forbid are hard filters (phase-1 elimination); prefer/avoid are soft
(phase-2 score). A criterion gets this routing for free from
``resolve_strength_verdict`` + ``TokenCriterion`` — "adding a criterion is
config, not bespoke scoring code" (AC-C1). Each strength is asserted on the
SAME candidate set: a source preferring "atmos", candidate A carrying atmos,
candidate B carrying stereo.
"""

from __future__ import annotations

import pytest

from tuneshift.matching.criteria import (
    HardCapPolicy,
    Strength,
    TokenCriterion,
    Verdict,
    resolve_strength_verdict,
)


class _Meta:
    def __init__(self, modes):
        self.audio_modes = modes


ATMOS = _Meta(["DOLBY_ATMOS"])
STEREO = _Meta(["STEREO"])


def _crit(hard_cap=HardCapPolicy.NONE):
    return TokenCriterion(
        name="spatial",
        field_name="audio_modes",
        target="dolby_atmos",
        weight=10,
        hard_cap=hard_cap,
    )


@pytest.mark.parametrize(
    "strength,present_verdict,absent_verdict",
    [
        (Strength.REQUIRE, Verdict.HARD_PASS, Verdict.HARD_REJECT),
        (Strength.FORBID, Verdict.HARD_REJECT, Verdict.HARD_PASS),
        (Strength.PREFER, Verdict.SOFT_BONUS, Verdict.SOFT_PENALTY),
        (Strength.AVOID, Verdict.SOFT_PENALTY, Verdict.SOFT_BONUS),
    ],
)
def test_resolve_strength_verdict(strength, present_verdict, absent_verdict) -> None:
    assert resolve_strength_verdict(strength, satisfied=True) is present_verdict
    assert resolve_strength_verdict(strength, satisfied=False) is absent_verdict


def test_no_strength_is_no_verdict() -> None:
    assert resolve_strength_verdict(None, satisfied=True) is Verdict.NO_VERDICT
    assert resolve_strength_verdict(None, satisfied=False) is Verdict.NO_VERDICT


@pytest.mark.parametrize(
    "strength,verdict_for_atmos,verdict_for_stereo",
    [
        (Strength.REQUIRE, Verdict.HARD_PASS, Verdict.HARD_REJECT),
        (Strength.FORBID, Verdict.HARD_REJECT, Verdict.HARD_PASS),
        (Strength.PREFER, Verdict.SOFT_BONUS, Verdict.SOFT_PENALTY),
        (Strength.AVOID, Verdict.SOFT_PENALTY, Verdict.SOFT_BONUS),
    ],
)
def test_token_criterion_routes_each_strength(
    strength, verdict_for_atmos, verdict_for_stereo
) -> None:
    crit = _crit()
    src = crit.extract(ATMOS)
    atmos = crit.extract(ATMOS)
    stereo = crit.extract(STEREO)
    assert crit.compare(src, atmos, strength) is verdict_for_atmos
    assert crit.compare(src, stereo, strength) is verdict_for_stereo


def test_soft_verdicts_emit_signal_hard_verdicts_do_not() -> None:
    crit = _crit(hard_cap=HardCapPolicy.REJECT)
    # soft
    assert crit.to_signal(Verdict.SOFT_PENALTY) is not None
    assert crit.to_signal(Verdict.SOFT_BONUS) is not None
    # hard verdicts cap the recommendation, they do not score as a soft signal
    assert crit.to_signal(Verdict.HARD_REJECT) is None
    assert crit.to_signal(Verdict.HARD_PASS) is None
    # not referenced
    assert crit.to_signal(Verdict.NO_VERDICT) is None
    assert crit.to_signal(Verdict.NEUTRAL) is None


def test_soft_penalty_hurts_bonus_helps_distance() -> None:
    from tuneshift.matching.engine import Distance

    crit = _crit()
    penalized = Distance()
    penalized.add(crit.to_signal(Verdict.SOFT_PENALTY))
    rewarded = Distance()
    rewarded.add(crit.to_signal(Verdict.SOFT_BONUS))
    assert penalized.total > rewarded.total


def test_criterion_not_referenced_yields_no_verdict() -> None:
    crit = _crit()
    src = crit.extract(ATMOS)
    cand = crit.extract(STEREO)
    assert crit.compare(src, cand, None) is Verdict.NO_VERDICT
