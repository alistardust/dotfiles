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
from tuneshift.matching.selection import ActivePreference, IdentityLock, select_version
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


# --- Task 3.3: IdentityLock short-circuit (AC-S2 / AC-L1) ---


def test_locked_available_release_wins_over_better_scoring_unlocked():
    source = _track("src", "Buddy", "De La Soul", "3 Feet High and Rising")
    # perfect string match, but NOT the locked release:
    generic = _track("A", "Buddy", "De La Soul", "3 Feet High and Rising", available=True)
    # the locked Native Tongues Decision version — worse string match, but pinned:
    native = _track("B", "Buddy", "De La Soul", "Native Tongues Decision", available=True)

    lock = IdentityLock(platform_id="B")
    result = select_version(source, [generic, native], lock=lock)

    assert result.winner is native
    assert result.lock_applied is True
    assert result.decided_by == "lock"


def test_locked_unavailable_surfaces_for_review_never_substituted():
    source = _track("src", "Buddy", "De La Soul", "3 Feet High and Rising")
    generic = _track("A", "Buddy", "De La Soul", "3 Feet High and Rising", available=True)
    native = _track("B", "Buddy", "De La Soul", "Native Tongues Decision", available=False)

    lock = IdentityLock(platform_id="B")
    result = select_version(source, [generic, native], lock=lock)

    # Never silently substitute the available generic release for the locked one.
    assert result.winner is None
    assert result.needs_review is True
    assert result.review_reason == "locked_unavailable"
    assert result.lock_applied is True


def test_lock_matches_by_isrc_even_when_platform_id_changed():
    # AC-L1 composite identity: a lock resolves by ISRC when the platform id moved.
    source = _track("src", "Buddy", "De La Soul", "3 Feet High and Rising", isrc="USABC1234567")
    moved = _track("NEW_ID", "Buddy", "De La Soul", "Native Tongues Decision",
                   available=True, isrc="USABC1234567")

    lock = IdentityLock(platform_id="OLD_ID", isrc="USABC1234567")
    result = select_version(source, [moved], lock=lock)

    assert result.winner is moved
    assert result.lock_applied is True


def test_locked_release_missing_surfaces_for_review_no_silent_pick():
    source = _track("src", "Buddy", "De La Soul", "3 Feet High and Rising")
    other = _track("A", "Buddy", "De La Soul", "3 Feet High and Rising", available=True)

    lock = IdentityLock(platform_id="GONE", isrc="USZZZ9999999")
    result = select_version(source, [other], lock=lock)

    # The locked identity is absent from candidates: never silently pick another
    # (self-heal with same-identity candidates lands in Chunk 5, AC-L3).
    assert result.winner is None
    assert result.needs_review is True
    assert result.review_reason == "locked_missing"


# --- Task 3.4: ambiguity surface (AC-S3) ---


def test_near_tie_without_preference_flags_review_not_guessed():
    # Two genuinely comparable versions, no preference to break the tie: the
    # engine surfaces it for review instead of silently guessing.
    source = _track("src", "Flower Power", "The Band", "Album One")
    a = SimpleNamespace(platform_id="A", title="Flower Power", artist="The Band",
                        album="Album One", isrc=None, duration_seconds=200, available=True,
                        audio_modes=[])
    b = SimpleNamespace(platform_id="B", title="Flower Power", artist="The Band",
                        album="Album One", isrc=None, duration_seconds=200, available=True,
                        audio_modes=[])
    result = select_version(source, [a, b])

    assert result.needs_review is True
    assert result.review_reason == "ambiguous"


def test_clear_winner_beyond_delta_not_flagged():
    source = _track("src", "Flower Power", "The Band", "Album One", duration=200)
    good = _track("A", "Flower Power", "The Band", "Album One", available=True, duration=200)
    poor = _track("B", "Different Song Entirely", "Someone Else", "Other", available=True,
                  duration=20)
    result = select_version(source, [good, poor])

    assert result.winner is good
    assert result.needs_review is False


def test_preference_resolved_near_tie_is_not_ambiguous():
    # A near-tie that a soft preference resolves by precedence is decided, not a
    # guess -> no review flag.
    source = SimpleNamespace(platform_id="src", title="Flower Power", artist="The Band",
                             album="Album One", isrc=None, duration_seconds=200,
                             audio_modes=[])
    stereo = SimpleNamespace(platform_id="A", title="Flower Power", artist="The Band",
                             album="Album One", isrc=None, duration_seconds=200,
                             available=True, audio_modes=["STEREO"])
    atmos = SimpleNamespace(platform_id="B", title="Flower Power", artist="The Band",
                            album="Album One", isrc=None, duration_seconds=200,
                            available=True, audio_modes=["DOLBY_ATMOS"])
    active = [ActivePreference(SPATIAL, PreferenceRef(
        "spatial", Strength.PREFER, "dolby_atmos", "playlist"))]
    result = select_version(source, [stereo, atmos], active=active)

    assert result.winner is atmos
    assert result.decided_by == "spatial"
    assert result.needs_review is False


# --- Task 3.5: no confident live/cover/karaoke match (AC-S4) ---


def _rec(pid, title, *, album, dur, available=True):
    return SimpleNamespace(platform_id=pid, title=title, artist="Christina Aguilera",
                           album=album, isrc=None, duration_seconds=dur,
                           available=available, audio_modes=[])


def test_live_version_down_ranked_out_of_winning_vs_studio():
    # "I Turn to You" studio intent; a live re-recording must not win when the
    # studio version is available.
    source = _rec("src", "I Turn to You", album="Christina Aguilera", dur=260)
    studio = _rec("A", "I Turn to You", album="Christina Aguilera", dur=260)
    live = _rec("B", "I Turn to You (Live - Anniversary Version)", album="Live", dur=265)
    result = select_version(source, [live, studio])

    assert result.winner is studio
    assert result.needs_review is False


def test_only_live_available_never_records_confident():
    # When the ONLY candidate is a version-mismatch (live vs studio intent) it is
    # surfaced for review, never recorded as a confident match (AC-S4).
    source = _rec("src", "I Turn to You", album="Christina Aguilera", dur=260)
    live = _rec("B", "I Turn to You (Live - Anniversary Version)", album="Live", dur=265)
    result = select_version(source, [live])

    assert result.needs_review is True
    assert result.review_reason == "version_mismatch"


def test_karaoke_never_wins_over_studio():
    source = _rec("src", "I Want It That Way", album="Millennium", dur=213)
    studio = _rec("A", "I Want It That Way", album="Millennium", dur=213)
    karaoke = _rec("B", "I Want It That Way (Karaoke Version)", album="Karaoke Hits", dur=210)
    result = select_version(source, [karaoke, studio])

    assert result.winner is studio
    assert result.needs_review is False


def test_tier_restricted_candidate_not_selected_over_playable():
    # A premium/tier-gated exact match must not win over a playable (if slightly
    # worse) release: tier_restricted is an unplayable state, filtered in Phase 1
    # exactly like available=False (review finding, Chunk 3 gate).
    source = _track("src", "Wonderwall", "Oasis", "(What's the Story) Morning Glory?")
    gated = TrackResult(
        platform_id="A", title="Wonderwall", artist="Oasis",
        album="(What's the Story) Morning Glory?", tier_restricted=True,
    )
    playable = _track("B", "Wonderwall", "Oasis", "Time Flies... 1994-2009", available=True)

    result = select_version(source, [gated, playable])

    assert result.winner is playable
    assert [fc.candidate for fc in result.filtered] == [gated]
    assert result.filtered[0].reason == "unavailable"


def test_identity_lock_isrc_match_is_case_insensitive():
    # ISRCs are case-insensitive everywhere else in the codebase; a lock must
    # heal across a platform re-ID that differs only in ISRC casing (review
    # finding, Chunk 3 gate).
    source = _track("src", "Song", "Artist", "Album")
    reidentified = _track(
        "NEW", "Song", "Artist", "Album", available=True, isrc="usabc1234567"
    )
    lock = IdentityLock(platform_id="OLD", isrc="USABC1234567")

    result = select_version(source, [reidentified], lock=lock)

    assert result.lock_applied is True
    assert result.winner is reidentified
    assert result.needs_review is False
