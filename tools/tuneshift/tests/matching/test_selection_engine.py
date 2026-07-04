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

from types import SimpleNamespace

from tuneshift.matching.criteria import Strength, TokenCriterion
from tuneshift.matching.precedence import PreferenceRef
from tuneshift.matching.selection import ActivePreference, select_version
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


# --- Task 3.2: soft preferences + precedence conflict resolution (AC-C4/C7) ---

SPATIAL = TokenCriterion(name="spatial", field_name="audio_modes", target="dolby_atmos")
EDITION = TokenCriterion(name="edition", field_name="edition_modes", target="remaster")


def _rel(pid, *, audio_modes, edition_modes, available=True):
    # Identical title/artist/album/isrc/duration so BASE scores are equal and the
    # soft preferences are the only differentiator (isolates the AC-C7 mechanism).
    return SimpleNamespace(
        platform_id=pid,
        title="Flowers",
        artist="Miley Cyrus",
        album="Endless Summer Vacation",
        isrc=None,
        duration_seconds=200,
        available=available,
        audio_modes=audio_modes,
        edition_modes=edition_modes,
    )


_SOURCE = _rel("src", audio_modes=[], edition_modes=[])
_ATMOS_REMASTER = _rel("atmos_remaster", audio_modes=["DOLBY_ATMOS"], edition_modes=["remaster"])
_STEREO_ORIGINAL = _rel("stereo_original", audio_modes=["STEREO"], edition_modes=[])


def _active(order, scope="playlist"):
    refs = {
        "spatial": ActivePreference(SPATIAL, PreferenceRef("spatial", Strength.PREFER, "dolby_atmos", scope)),
        "edition": ActivePreference(EDITION, PreferenceRef("edition", Strength.AVOID, "remaster", scope)),
    }
    return [refs[name] for name in order]


def test_two_playlists_different_precedence_pick_different_winners():
    candidates = [_ATMOS_REMASTER, _STEREO_ORIGINAL]
    # Playlist A: spatial outranks edition -> prefer-atmos dominates -> Atmos wins.
    a = select_version(_SOURCE, candidates, active=_active(["spatial", "edition"]))
    assert a.winner is _ATMOS_REMASTER
    assert a.decided_by == "spatial"
    # Playlist B: edition outranks spatial -> avoid-remaster dominates -> original wins.
    b = select_version(_SOURCE, candidates, active=_active(["edition", "spatial"]))
    assert b.winner is _STEREO_ORIGINAL
    assert b.decided_by == "edition"


def test_single_soft_pref_biases_winner_by_weighted_score():
    # No conflict: one pref, atmos is strictly favoured -> lower distance -> wins.
    active = [ActivePreference(SPATIAL, PreferenceRef("spatial", Strength.PREFER, "dolby_atmos", "playlist"))]
    result = select_version(_SOURCE, [_STEREO_ORIGINAL, _ATMOS_REMASTER], active=active)
    assert result.winner is _ATMOS_REMASTER


def test_conflict_never_picks_candidate_neither_pref_wanted():
    # A neutral release (no atmos, no remaster => NO_VERDICT on both prefs) has the
    # SAME base score as the contested pair. A naive weighted sum where the opposing
    # prefs cancel could let it win; precedence must eliminate it (AC-C7).
    neutral = _rel("neutral_comp", audio_modes=[], edition_modes=[])
    # neutral listed FIRST so a stable weighted sort would surface it on a tie.
    candidates = [neutral, _ATMOS_REMASTER, _STEREO_ORIGINAL]
    result = select_version(_SOURCE, candidates, active=_active(["spatial", "edition"]))
    assert result.winner is _ATMOS_REMASTER
    assert result.winner is not neutral
