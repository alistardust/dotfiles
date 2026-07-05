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
    spatial = _ref("spatial", "atmos", "playlist")
    origin = _ref("release_context", "original", "playlist")
    verdicts = {
        "atmos_remaster": {
            spatial: Verdict.SOFT_BONUS,
            origin: Verdict.SOFT_PENALTY,
        },
        "stereo_original": {
            spatial: Verdict.SOFT_PENALTY,
            origin: Verdict.SOFT_BONUS,
        },
    }
    precedence = [spatial, origin]
    decision = resolve_conflict(verdicts, precedence)
    assert isinstance(decision, ConflictDecision)
    assert decision.winner == "atmos_remaster"
    assert not decision.unresolved
    assert decision.decided_by == "spatial"
    # Trace names the deciding criterion and both candidates' verdicts on it.
    assert decision.trace[0].criterion == "spatial"
    assert decision.trace[0].favored == ["atmos_remaster"]


def test_conflict_flips_when_precedence_flips():
    spatial = _ref("spatial", "atmos", "playlist")
    origin = _ref("release_context", "original", "playlist")
    verdicts = {
        "atmos_remaster": {
            spatial: Verdict.SOFT_BONUS,
            origin: Verdict.SOFT_PENALTY,
        },
        "stereo_original": {
            spatial: Verdict.SOFT_PENALTY,
            origin: Verdict.SOFT_BONUS,
        },
    }
    precedence = [origin, spatial]
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "stereo_original"
    assert decision.decided_by == "release_context"


def test_conflict_no_averaging_never_picks_unwanted_candidate():
    # C is neutral on both axes; a weighted-average scheme might let it sneak in.
    spatial = _ref("spatial", "atmos", "playlist")
    origin = _ref("release_context", "original", "playlist")
    verdicts = {
        "atmos_remaster": {spatial: Verdict.SOFT_BONUS, origin: Verdict.SOFT_PENALTY},
        "stereo_original": {spatial: Verdict.SOFT_PENALTY, origin: Verdict.SOFT_BONUS},
        "neutral_comp": {spatial: Verdict.NEUTRAL, origin: Verdict.NEUTRAL},
    }
    precedence = [spatial, origin]
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "atmos_remaster"


def test_conflict_unresolved_when_precedence_cannot_distinguish():
    spatial = _ref("spatial", "atmos", "playlist")
    verdicts = {
        "a": {spatial: Verdict.SOFT_BONUS},
        "b": {spatial: Verdict.SOFT_BONUS},
    }
    precedence = [spatial]
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner is None
    assert decision.unresolved
    assert set(decision.contenders) == {"a", "b"}


def test_same_criterion_different_scope_track_overrides_global():
    """Regression (Chunk 2 review, finding 2): two active preferences on the
    SAME criterion at different scopes must remain distinct so precedence can
    enforce the track override. Global prefers ``original``; the track pref
    prefers ``remaster``. The track scope outranks global, so the remaster wins
    — and the outcome must NOT depend on dict/merge ordering."""

    track_remaster = _ref("release_context", "remaster", "track")
    global_original = _ref("release_context", "original", "global")
    precedence = derive_precedence(
        global_refs=[global_original],
        playlist_refs=[],
        track_refs=[track_remaster],
    )
    # After derive, refs carry corrected scope; key verdicts by those refs.
    track_ref, global_ref = precedence[0], precedence[1]
    verdicts = {
        "remaster_2024": {track_ref: Verdict.SOFT_BONUS, global_ref: Verdict.SOFT_PENALTY},
        "original_1998": {track_ref: Verdict.SOFT_PENALTY, global_ref: Verdict.SOFT_BONUS},
    }
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "remaster_2024"
    assert decision.decided_by == "release_context"


def test_same_criterion_conflict_is_order_independent():
    """The two same-criterion refs must not clobber each other regardless of the
    order the verdict sub-dict is built in (the exact merge-order bug found)."""

    track_remaster = _ref("release_context", "remaster", "track")
    global_original = _ref("release_context", "original", "global")
    precedence = derive_precedence(
        global_refs=[global_original],
        playlist_refs=[],
        track_refs=[track_remaster],
    )
    track_ref, global_ref = precedence[0], precedence[1]

    rem_then_orig = {
        "remaster_2024": {track_ref: Verdict.SOFT_BONUS, global_ref: Verdict.SOFT_PENALTY},
        "original_1998": {track_ref: Verdict.SOFT_PENALTY, global_ref: Verdict.SOFT_BONUS},
    }
    orig_then_rem = {
        "remaster_2024": {global_ref: Verdict.SOFT_PENALTY, track_ref: Verdict.SOFT_BONUS},
        "original_1998": {global_ref: Verdict.SOFT_BONUS, track_ref: Verdict.SOFT_PENALTY},
    }
    assert resolve_conflict(rem_then_orig, precedence).winner == "remaster_2024"
    assert resolve_conflict(orig_then_rem, precedence).winner == "remaster_2024"
