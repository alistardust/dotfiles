"""AC-C5 winner-parity gate for the reconcile consolidation.

Chunk 3 retires reconcile's duplicate *integer* ranking loop and routes winner
selection through the single two-phase engine (``select_version``). This gate is
the regression guard that made that safe: for every should-match gold case, the
engine must pick the SAME winner the retired integer scorer
(``score_match_with_version``, exercised via :func:`tests.gold.runner.score_case`)
would have picked, under the case's preferences.

Two divergences on the genuinely-unavailable cases are INTENDED and asserted
explicitly: there the "winner" is moot because neither path should confidently
commit anything, and the engine surfaces the outcome for review (or produces no
clean winner) rather than guessing.
"""
from __future__ import annotations

from types import SimpleNamespace

from tuneshift.matching.preferences import scoring_intent
from tuneshift.matching.selection import select_version

from tests.gold.dataset import gold_cases
from tests.gold.runner import score_case


def _source(case) -> SimpleNamespace:
    return SimpleNamespace(
        title=case.source_title,
        artist=case.source_artist,
        album=case.source_album,
        duration_seconds=case.source_duration_seconds,
        isrc=None,
        platform_id=None,
        available=None,
        audio_modes=[],
    )


def _candidate(cand) -> SimpleNamespace:
    return SimpleNamespace(
        title=cand.title,
        artist=cand.artist,
        album=cand.album,
        duration_seconds=cand.duration_seconds,
        isrc=None,
        platform_id=cand.platform_id,
        available=None,
        audio_modes=[],
    )


def _engine_selection(case):
    prefer, avoid = scoring_intent(list(case.prefer_classes), list(case.avoid_classes))
    all_durations = [
        c.duration_seconds for c in case.candidates if c.duration_seconds is not None
    ]
    return select_version(
        _source(case),
        [_candidate(c) for c in case.candidates],
        prefer=prefer,
        avoid=avoid,
        all_durations=all_durations or None,
    )


def test_engine_winner_matches_integer_ranking_on_should_match_cases():
    """The engine picks the labeled correct release for every should-match case,
    identical to the retired integer ranking (recall == 1.0 both ways)."""
    mismatches = []
    for case in gold_cases():
        if case.expected_platform_id is None:
            continue
        integer = score_case(case)
        selection = _engine_selection(case)
        engine_winner = (
            selection.winner.platform_id if selection.winner is not None else None
        )
        # The integer path already resolves every should-match case correctly
        # (recall 1.0); the engine must agree with it AND with the label.
        if not (
            engine_winner
            == integer.selected_platform_id
            == case.expected_platform_id
        ):
            mismatches.append(
                (case.id, engine_winner, integer.selected_platform_id,
                 case.expected_platform_id)
            )
    assert not mismatches, (
        "winner-parity broke on should-match cases "
        "(case, engine, integer, expected): " + repr(mismatches)
    )


def test_unavailable_cases_are_never_confidently_committed():
    """On genuinely-unavailable cases neither path confidently commits: the
    integer classifier says not_found and the engine either produces no clean
    winner or flags the outcome for review (the two intended divergences)."""
    for case in gold_cases():
        if case.expected_platform_id is not None:
            continue
        integer = score_case(case)
        selection = _engine_selection(case)
        assert integer.classification == "not_found", case.id
        assert (
            selection.winner is None or selection.needs_review
        ), f"{case.id}: engine confidently committed an unavailable track"
