"""Tests for the engine-native score_track_match entry point."""
from dataclasses import dataclass

from tuneshift.matching import score_track_match
from tuneshift.matching.engine import Recommendation, recommend


@dataclass
class T:
    title: str = ""
    artist: str = ""
    album: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None


def test_perfect_match_zero_distance_and_auto():
    # NB: avoid album/title text that trips legacy version regexes (e.g. the
    # "at the" substring matches _LIVE_RE — a known false positive that Chunk 4
    # version-safety will fix; Chunk 2 preserves it for byte-parity).
    src = T("Bohemian Rhapsody", "Queen", "Studio Album", "GBUM71029604", 355)
    cand = T("Bohemian Rhapsody", "Queen", "Studio Album", "GBUM71029604", 355)
    d = score_track_match(src, cand)
    assert d.total == 0.0
    assert recommend(d) is Recommendation.AUTO


def test_karaoke_candidate_is_rejected_despite_title_match():
    src = T("Bohemian Rhapsody", "Queen", "A Night at the Opera")
    cand = T("Bohemian Rhapsody (Karaoke Version)", "Queen", "Karaoke Hits")
    d = score_track_match(src, cand)
    assert d.has_signal("version:karaoke")
    assert recommend(d) is Recommendation.REJECT


def test_live_candidate_carries_version_signal():
    src = T("Heroes", "David Bowie", '"Heroes"')
    cand = T("Heroes (Live)", "David Bowie", "Stage")
    d = score_track_match(src, cand)
    names = [s.name for s in d.signals]
    assert "version:live" in names


def test_wrong_artist_increases_distance():
    src = T("Yesterday", "The Beatles", "Help!")
    cand = T("Yesterday", "Some Cover Band", "Tribute Hits")
    d = score_track_match(src, cand)
    # tribute keyword + artist mismatch -> not an auto accept
    assert recommend(d) is not Recommendation.AUTO


def test_points_matches_legacy_base_when_no_version_or_duration():
    from tuneshift.matching import score_match
    src = T("Song Title", "Artist", "Album")
    cand = T("Song Titel", "Artist", "Album")
    d = score_track_match(src, cand)
    # no version/duration signals fire, isrc absent -> raw point sum equals
    # the legacy object-form base score
    legacy = score_match(src, cand)
    assert d.points == legacy
