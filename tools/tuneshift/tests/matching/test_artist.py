"""Tests for the artist matching scorer and classifier."""
from tuneshift.matching.artist import (
    classify_artist_results,
    score_artist_match,
)
from tuneshift.models import ArtistResult


def _artist(name, popularity=None, genres=None, followers=None):
    return ArtistResult(
        platform_id="x", name=name,
        popularity=popularity, genres=genres or [], followers=followers,
    )


class TestScoreArtistMatch:
    def test_exact_name_is_near_zero(self):
        assert score_artist_match("Radiohead", _artist("Radiohead")).total < 0.05

    def test_wrong_name_is_worse(self):
        good = score_artist_match("Radiohead", _artist("Radiohead"))
        bad = score_artist_match("Radiohead", _artist("Coldplay"))
        assert bad.total > good.total

    def test_missing_enrichment_is_neutral(self):
        d = score_artist_match("Radiohead", _artist("Radiohead"))
        weighted = {s.name for s in d.signals if s.weight > 0}
        assert "artist:genre" not in weighted
        assert "artist:popularity" not in weighted

    def test_genre_overlap_corroborates(self):
        with_overlap = score_artist_match(
            "Radiohead", _artist("Radiohead", genres=["rock", "alternative"]),
            source_genres=["rock"],
        )
        without_overlap = score_artist_match(
            "Radiohead", _artist("Radiohead", genres=["jazz"]),
            source_genres=["rock"],
        )
        assert without_overlap.total > with_overlap.total

    def test_popularity_breaks_ties_between_same_name(self):
        popular = score_artist_match("The Band", _artist("The Band", popularity=90))
        obscure = score_artist_match("The Band", _artist("The Band", popularity=5))
        assert popular.total < obscure.total

    def test_name_dominates_over_enrichment(self):
        # A wrong name with great enrichment must still lose to a right name.
        wrong_but_popular = score_artist_match(
            "Radiohead", _artist("Coldplay", popularity=100, genres=["rock"]),
            source_genres=["rock"],
        )
        right_bare = score_artist_match("Radiohead", _artist("Radiohead"))
        assert right_bare.total < wrong_but_popular.total


class TestClassifyArtistResults:
    def test_empty_is_not_found(self):
        assert classify_artist_results([]) == "not_found"

    def test_perfect_best_is_high(self):
        assert classify_artist_results([0.0, 0.8]) == "high"

    def test_poor_best_is_not_found(self):
        assert classify_artist_results([0.9]) == "not_found"
