"""Tests for the album matching scorer and classifier."""
from tuneshift.matching.album import (
    classify_album_results,
    score_album_match,
)
from tuneshift.models import AlbumResult


def _album(title, artist="Artist", track_count=0, release_year=None):
    return AlbumResult(
        platform_id="x", title=title, artist=artist,
        track_count=track_count, release_year=release_year,
    )


class TestScoreAlbumMatch:
    def test_exact_title_and_artist_is_near_zero(self):
        d = score_album_match("Rumours", "Fleetwood Mac", _album("Rumours", "Fleetwood Mac"))
        assert d.total < 0.05

    def test_wrong_artist_is_worse_than_right_artist(self):
        good = score_album_match("Rumours", "Fleetwood Mac", _album("Rumours", "Fleetwood Mac"))
        bad = score_album_match("Rumours", "Fleetwood Mac", _album("Rumours", "A Tribute Band"))
        assert bad.total > good.total

    def test_standard_edition_preferred_over_deluxe(self):
        standard = score_album_match("Rumours", "Fleetwood Mac", _album("Rumours", "Fleetwood Mac"))
        deluxe = score_album_match(
            "Rumours", "Fleetwood Mac", _album("Rumours (Deluxe Edition)", "Fleetwood Mac")
        )
        assert deluxe.total > standard.total

    def test_missing_year_and_track_count_are_neutral(self):
        # No year/track-count on either side must not add distance.
        d = score_album_match("Rumours", "Fleetwood Mac", _album("Rumours", "Fleetwood Mac"))
        names = {s.name for s in d.signals if s.weight > 0}
        assert "album:year" not in names
        assert "album:track_count" not in names

    def test_matching_year_beats_distant_year(self):
        close = score_album_match(
            "Rumours", "Fleetwood Mac",
            _album("Rumours", "Fleetwood Mac", release_year=1977), source_year=1977,
        )
        far = score_album_match(
            "Rumours", "Fleetwood Mac",
            _album("Rumours", "Fleetwood Mac", release_year=2013), source_year=1977,
        )
        assert far.total > close.total

    def test_ranking_picks_best_candidate(self):
        candidates = [
            _album("Rumours (Live)", "Fleetwood Mac"),
            _album("Rumours", "Fleetwood Mac"),
            _album("Greatest Hits", "Fleetwood Mac"),
        ]
        scored = sorted(
            candidates, key=lambda a: score_album_match("Rumours", "Fleetwood Mac", a).total
        )
        assert scored[0].title == "Rumours"


class TestClassifyAlbumResults:
    def test_empty_is_not_found(self):
        assert classify_album_results([]) == "not_found"

    def test_perfect_best_is_high(self):
        assert classify_album_results([0.0, 0.9]) == "high"

    def test_poor_best_is_not_found(self):
        assert classify_album_results([0.9]) == "not_found"

    def test_mid_best_is_medium_or_low(self):
        assert classify_album_results([0.3, 0.9]) in {"medium", "low"}
