"""Deterministic era-rule enforcement + honest messaging in review (Task 2)."""

from tuneshift.composer.models import PlaylistConcept
from tuneshift.composer.reviewer import review_playlist
from tuneshift.sequencer.metadata import TrackMetadata


def _t(tid, title, artist):
    return TrackMetadata(track_id=tid, title=title, artist=artist)


def test_era_rule_flags_out_of_range_tracks():
    tracks = [_t(1, "All I Wanna Do", "Sheryl Crow"), _t(2, "Old Song", "X")]
    concept = PlaylistConcept(theme="Girl Power", hard_rules=["released 1993-2003"])
    year_lookup = {1: 1993, 2: 1975}

    findings = review_playlist(
        tracks, concept=concept, artist_lookup={}, year_lookup=year_lookup
    )
    descs = " ".join(f.description for f in findings)
    assert "Old Song" in descs          # 1975 out of range -> flagged
    assert "All I Wanna Do" not in descs  # 1993 in range -> not flagged


def test_era_rule_unknown_when_year_missing():
    tracks = [_t(1, "Mystery", "X")]
    concept = PlaylistConcept(theme="t", hard_rules=["released 1993-2003"])
    findings = review_playlist(
        tracks, concept=concept, artist_lookup={}, year_lookup={1: None}
    )
    assert any("year" in f.description.lower() and f.severity <= 0.3 for f in findings)


def test_non_artist_rule_no_longer_says_artist_not_in_library():
    tracks = [_t(1, "Song", "Artist")]
    concept = PlaylistConcept(theme="t", hard_rules=["released 1993-2003"])
    findings = review_playlist(
        tracks, concept=concept, artist_lookup={}, year_lookup={1: 1980}
    )
    assert all("artist not in library" not in f.description for f in findings)


def test_thematic_rule_reports_needs_llm_once_not_per_track():
    tracks = [_t(1, "A", "X"), _t(2, "B", "Y"), _t(3, "C", "Z")]
    concept = PlaylistConcept(theme="t", hard_rules=["not about wanting a man"])
    findings = review_playlist(tracks, concept=concept, artist_lookup={})
    thematic = [f for f in findings if "thematic" in f.description.lower()]
    assert len(thematic) == 1  # once per rule, not once per track
    assert all("artist not in library" not in f.description for f in findings)
