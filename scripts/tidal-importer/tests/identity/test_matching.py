"""Tests for identity resolution fuzzy matching."""

import pytest

from tidal_importer.identity.matching import (
    duration_matches,
    match_title,
    normalize_artist_for_search,
    normalize_title_for_search,
)


class TestNormalization:
    def test_title_strips_remaster(self):
        assert normalize_title_for_search("Dancing Queen (Remastered 2001)") == "dancing queen"

    def test_title_strips_feat(self):
        assert normalize_title_for_search("Song (feat. Artist)") == "song"

    def test_artist_strips_the(self):
        assert normalize_artist_for_search("The Beatles") == "beatles"

    def test_artist_strips_feat(self):
        assert normalize_artist_for_search("Kendrick Lamar feat. SZA") == "kendrick lamar"

    def test_artist_ampersand(self):
        assert normalize_artist_for_search("Simon & Garfunkel") == "simon and garfunkel"


class TestMatchTitle:
    def test_exact_match(self):
        assert match_title("Dancing Queen", "Dancing Queen") >= 0.95

    def test_case_insensitive(self):
        assert match_title("dancing queen", "Dancing Queen") >= 0.95

    def test_remaster_suffix(self):
        assert match_title("Dancing Queen", "Dancing Queen (Remastered 2001)") >= 0.90

    def test_similar_but_different(self):
        assert match_title("September", "Serpentine Fire") < 0.85

    def test_completely_different(self):
        assert match_title("Dancing Queen", "Bohemian Rhapsody") < 0.50


class TestDurationMatches:
    def test_exact(self):
        assert duration_matches(231000, 231000) is True

    def test_within_tolerance(self):
        assert duration_matches(231000, 236000) is True

    def test_outside_tolerance(self):
        assert duration_matches(231000, 260000) is False

    def test_none_reference(self):
        assert duration_matches(None, 231000) is True

    def test_none_candidate(self):
        assert duration_matches(231000, None) is True
