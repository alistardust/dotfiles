"""Tests for identity matching utilities."""

from tuneshift.identity.matching import (
    duration_matches,
    match_title,
    normalize_artist_for_search,
    normalize_title_for_search,
)


class TestDurationMatches:
    def test_exact_match(self):
        assert duration_matches(263000, 263000) is True

    def test_within_tolerance(self):
        assert duration_matches(263000, 265000, tolerance_ms=10000) is True

    def test_outside_tolerance(self):
        assert duration_matches(263000, 280000, tolerance_ms=10000) is False

    def test_none_reference(self):
        assert duration_matches(None, 263000) is True

    def test_none_candidate(self):
        assert duration_matches(263000, None) is True


class TestNormalizeTitleForSearch:
    def test_removes_parenthetical_remaster(self):
        assert "remaster" not in normalize_title_for_search("Heroes (2017 Remaster)")

    def test_preserves_core_title(self):
        assert "heroes" in normalize_title_for_search("Heroes (2017 Remaster)").lower()

    def test_strips_whitespace(self):
        result = normalize_title_for_search("  Heroes  ")
        assert result == result.strip()


class TestNormalizeArtistForSearch:
    def test_removes_the_prefix(self):
        result = normalize_artist_for_search("The Beatles")
        assert not result.lower().startswith("the ")

    def test_preserves_name(self):
        assert "beatles" in normalize_artist_for_search("The Beatles").lower()


class TestMatchTitle:
    def test_exact_match_is_high(self):
        score = match_title("Heroes", "Heroes")
        assert score >= 0.95

    def test_partial_match(self):
        score = match_title("Heroes", "Heroes (2017 Remaster)")
        assert 0.5 < score < 1.0

    def test_no_match_is_low(self):
        score = match_title("Heroes", "Starman")
        assert score < 0.5
