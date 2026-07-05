"""Chunk 2 Task 2.6: base scoring criteria are the single source of truth (AC-C5).

The historical scoring sequence (title, artist, album, isrc, version — which
itself covers the edition and lyric residual signals — and duration) is now
expressed once, as an ordered list of base scoring criteria that delegate to
the exact ``penalties`` builders. ``score_track_match`` builds its ``Distance``
from that list, so there is a single scoring sequence, not two that can drift.

Parity contract (AC-C5, winner-parity): with default preferences the registry
must reproduce today's engine decomposition byte-for-byte. This test locks:

1. the registered criteria and their order;
2. ``score_signals`` == ``score_track_match(...).signals`` (a single scoring
   sequence that cannot drift into two implementations).
"""

from __future__ import annotations

from dataclasses import dataclass

from tuneshift.matching import score_track_match
from tuneshift.matching.base_scoring import (
    default_scoring_criteria,
    score_signals,
)


@dataclass
class _Track:
    title: str = ""
    artist: str = ""
    album: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None


_PAIRS = [
    (
        _Track("Buddy", "De La Soul", "3 Feet High and Rising", "USABC1234567", 240),
        _Track("Buddy", "De La Soul", "3 Feet High and Rising", "USABC1234567", 240),
    ),
    (
        _Track("I Turn to You", "Christina Aguilera", "Christina Aguilera", None, 258),
        _Track("I Turn to You (Live - Anniversary Version)", "Christina Aguilera",
                "Live Anniversary", None, 295),
    ),
    (
        _Track("Wouldn't It Be Nice", "The Beach Boys", "Pet Sounds", None, 152),
        _Track("Wouldn't It Be Nice (Remastered)", "The Beach Boys",
                "Pet Sounds (Original Mono & Stereo Mix)", None, 153),
    ),
    (
        _Track("Everybody (Backstreet's Back)", "Backstreet Boys", "Backstreet's Back", None, 224),
        _Track("Everybody (Backstreet's Back) - Radio Edit", "Backstreet Boys",
                "90s 100 Hits", None, 208),
    ),
]


def test_default_criteria_registered_in_order():
    names = [c.name for c in default_scoring_criteria()]
    assert names == ["title", "artist", "album", "isrc", "version", "duration"]


def test_score_signals_matches_score_track_match_signal_list():
    # The registry-driven scorer and the engine entry point must be identical.
    for src, cand in _PAIRS:
        expected = list(score_track_match(src, cand).signals)
        got = score_signals(src, cand)
        assert got == expected, f"signal list diverged for {src.title!r} -> {cand.title!r}"


def test_default_prefs_emit_only_base_scoring_signals():
    # With no active preference, only the base scoring groups appear — no
    # preference criterion perturbs the distance (winner-parity, AC-C5).
    src, cand = _PAIRS[0]
    prefixes = {s.name.split(":", 1)[0] for s in score_signals(src, cand)}
    assert prefixes <= {"title", "artist", "album", "isrc", "version", "duration"}
