"""Chunk 2 Task 2.4: per-playlist precedence + conflict resolution (AC-C4/C7).

Precedence order for a playlist is derived from the preference cascade: a
track-scoped preference outranks a playlist-scoped one, which outranks a
global one; within a scope the declared order is preserved. When two soft
preferences pull toward different candidates, the conflict is resolved by that
precedence order — the higher-precedence criterion DOMINATES (lexicographic
elimination, never weighted averaging that could pick a candidate neither
preference wanted) — and the decision is fully traced.

Gold conflict (real axes): ``prefer spatial=atmos`` favours a 2024 Atmos
remaster while ``prefer release-context=original`` favours the stereo original.
The winner flips with the precedence order, and both outcomes are explained.
"""

from __future__ import annotations

from tuneshift.matching.criteria import Strength, Verdict
from tuneshift.matching.precedence import (
    ConflictDecision,
    PreferenceRef,
    derive_precedence,
    resolve_conflict,
)


def _ref(criterion, target, scope, strength=Strength.PREFER):
    return PreferenceRef(criterion=criterion, strength=strength, target=target, scope=scope)


def test_derive_precedence_orders_track_over_playlist_over_global():
    precedence = derive_precedence(
        global_refs=[_ref("spatial", "atmos", "global")],
        playlist_refs=[_ref("release_context", "original", "playlist")],
        track_refs=[_ref("edition", "remaster", "track")],
    )
    assert [p.criterion for p in precedence] == ["edition", "release_context", "spatial"]
    assert [p.scope for p in precedence] == ["track", "playlist", "global"]


def test_derive_precedence_preserves_declared_order_within_scope():
    precedence = derive_precedence(
        global_refs=[],
        playlist_refs=[
            _ref("spatial", "atmos", "playlist"),
            _ref("release_context", "original", "playlist"),
        ],
        track_refs=[],
    )
    assert [p.criterion for p in precedence] == ["spatial", "release_context"]


def test_conflict_higher_precedence_dominates_atmos_over_original():
    # Two candidates: A = Atmos remaster, B = stereo original.
    verdicts = {
        "atmos_remaster": {
            "spatial": Verdict.SOFT_BONUS,
            "release_context": Verdict.SOFT_PENALTY,
        },
        "stereo_original": {
            "spatial": Verdict.SOFT_PENALTY,
            "release_context": Verdict.SOFT_BONUS,
        },
    }
    precedence = [_ref("spatial", "atmos", "playlist"), _ref("release_context", "original", "playlist")]
    decision = resolve_conflict(verdicts, precedence)
    assert isinstance(decision, ConflictDecision)
    assert decision.winner == "atmos_remaster"
    assert not decision.unresolved
    assert decision.decided_by == "spatial"
    # Trace names the deciding criterion and both candidates' verdicts on it.
    assert decision.trace[0].criterion == "spatial"
    assert decision.trace[0].favored == ["atmos_remaster"]


def test_conflict_flips_when_precedence_flips():
    verdicts = {
        "atmos_remaster": {
            "spatial": Verdict.SOFT_BONUS,
            "release_context": Verdict.SOFT_PENALTY,
        },
        "stereo_original": {
            "spatial": Verdict.SOFT_PENALTY,
            "release_context": Verdict.SOFT_BONUS,
        },
    }
    precedence = [_ref("release_context", "original", "playlist"), _ref("spatial", "atmos", "playlist")]
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "stereo_original"
    assert decision.decided_by == "release_context"


def test_conflict_no_averaging_never_picks_unwanted_candidate():
    # C is neutral on both axes; a weighted-average scheme might let it sneak in.
    verdicts = {
        "atmos_remaster": {"spatial": Verdict.SOFT_BONUS, "release_context": Verdict.SOFT_PENALTY},
        "stereo_original": {"spatial": Verdict.SOFT_PENALTY, "release_context": Verdict.SOFT_BONUS},
        "neutral_comp": {"spatial": Verdict.NEUTRAL, "release_context": Verdict.NEUTRAL},
    }
    precedence = [_ref("spatial", "atmos", "playlist"), _ref("release_context", "original", "playlist")]
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "atmos_remaster"


def test_conflict_unresolved_when_precedence_cannot_distinguish():
    verdicts = {
        "a": {"spatial": Verdict.SOFT_BONUS},
        "b": {"spatial": Verdict.SOFT_BONUS},
    }
    precedence = [_ref("spatial", "atmos", "playlist")]
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner is None
    assert decision.unresolved
    assert set(decision.contenders) == {"a", "b"}
