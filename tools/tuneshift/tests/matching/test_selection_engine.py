"""Chunk 3 Task 3.1: two-phase select_version engine (§6, AC-S1).

Phase 1 is a HARD filter: a candidate that is explicitly unavailable
(``available is False``) or fails an active require/forbid is eliminated BEFORE
scoring. Phase 2 scores the survivors via the single scoring source
(``score_signals`` -> ``Distance``) and the lowest distance wins.

The AC-S1 gold behaviour: a perfect-string but UNAVAILABLE release must never
be selected over an available (if slightly worse) one. This is the exact
failure mode behind "it says the track doesn't exist / picked the dead ID".
"""

from __future__ import annotations

from tuneshift.matching.selection import select_version
from tuneshift.models import TrackResult


def _track(pid, title, artist, album, *, available=None, isrc=None, duration=None):
    return TrackResult(
        platform_id=pid,
        title=title,
        artist=artist,
        album=album,
        duration_seconds=duration,
        isrc=isrc,
        available=available,
    )


def test_unavailable_top_scorer_passed_over_for_available_lower_scorer():
    source = _track("src", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?")
    # A: byte-perfect match but explicitly unavailable.
    a = _track("A", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?", available=False)
    # B: same song, different (compilation) album -> slightly worse score, available.
    b = _track("B", "Wonderwall", "Oasis", "Time Flies... 1994-2009", available=True)

    result = select_version(source, [a, b])

    assert result.winner is b
    assert [fc.candidate for fc in result.filtered] == [a]
    assert result.filtered[0].reason == "unavailable"
    # B is the only survivor scored.
    assert [c for c, _ in result.ranked] == [b]


def test_available_perfect_match_still_wins_over_worse_available():
    source = _track("src", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?")
    a = _track("A", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?", available=True)
    b = _track("B", "Wonderwall", "Oasis", "Time Flies... 1994-2009", available=True)

    result = select_version(source, [a, b])

    assert result.winner is a
    assert result.filtered == []
    # Ranked best-first by distance (lower is better).
    assert result.ranked[0][0] is a
    assert result.ranked[0][1].total <= result.ranked[1][1].total


def test_unknown_availability_is_not_filtered():
    # available=None means "unknown", never "blocked" (models.py contract).
    source = _track("src", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?")
    a = _track("A", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?", available=None)

    result = select_version(source, [a])

    assert result.winner is a
    assert result.filtered == []


def test_empty_candidate_set_yields_no_winner():
    source = _track("src", "Wonderwall", "Oasis", "Morning Glory")
    result = select_version(source, [])
    assert result.winner is None
    assert result.winner_distance is None
    assert result.ranked == []
