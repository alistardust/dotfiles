"""Tests for version preference scoring in matching."""
import pytest
from tuneshift.matching import version_penalty, score_match_with_version


class TestVersionPenalty:
    """version_penalty returns a 0-30 penalty for undesirable versions."""

    def test_original_studio_no_penalty(self):
        assert version_penalty("Goodbye Yellow Brick Road", "Goodbye Yellow Brick Road") == 0

    def test_live_album_penalized(self):
        penalty = version_penalty("Saturday Night's Alright for Fighting", "Live at Madison Square Garden")
        assert penalty >= 20

    def test_live_in_title_penalized(self):
        penalty = version_penalty("Saturday Night's Alright for Fighting (Live)", "Goodbye Yellow Brick Road")
        assert penalty >= 20

    def test_remaster_small_penalty(self):
        penalty = version_penalty("Rocket Man", "Goodbye Yellow Brick Road (2014 Remaster)")
        assert 5 <= penalty <= 15

    def test_deluxe_edition_small_penalty(self):
        penalty = version_penalty("Your Song", "Elton John (Deluxe Edition)")
        assert 5 <= penalty <= 15

    def test_greatest_hits_compilation_penalized(self):
        penalty = version_penalty("Tiny Dancer", "Greatest Hits")
        assert penalty >= 10

    def test_various_artists_penalized(self):
        penalty = version_penalty("I'm Still Standing", "Now That's What I Call Music! 2")
        assert penalty >= 15

    def test_tribute_penalized(self):
        penalty = version_penalty("Your Song", "Revamp: Reimagining the Songs of Elton John")
        assert penalty >= 15

    def test_remix_in_title_penalized(self):
        penalty = version_penalty("Rocket Man (Remix)", "Diamonds")
        assert penalty >= 15

    def test_acoustic_version_small_penalty(self):
        penalty = version_penalty("Your Song (Acoustic Version)", "Elton John")
        assert 5 <= penalty <= 15


class TestScoreMatchWithVersion:
    """score_match_with_version combines similarity + version preference."""

    def test_studio_original_scores_higher_than_live(self):
        studio_score = score_match_with_version(
            "Rocket Man", "Elton John", None,
            "Rocket Man (I Think It's Going to Be a Long, Long Time)", "Elton John", "Honky Chateau"
        )
        live_score = score_match_with_version(
            "Rocket Man", "Elton John", None,
            "Rocket Man (I Think It's Going to Be a Long, Long Time) - Live", "Elton John", "Live at Wembley"
        )
        assert studio_score > live_score

    def test_original_album_scores_higher_than_compilation(self):
        original_score = score_match_with_version(
            "Tiny Dancer", "Elton John", None,
            "Tiny Dancer", "Elton John", "Madman Across the Water"
        )
        compilation_score = score_match_with_version(
            "Tiny Dancer", "Elton John", None,
            "Tiny Dancer", "Elton John", "Greatest Hits"
        )
        assert original_score > compilation_score

    def test_remaster_scores_between_original_and_live(self):
        original_score = score_match_with_version(
            "Your Song", "Elton John", None,
            "Your Song", "Elton John", "Elton John"
        )
        remaster_score = score_match_with_version(
            "Your Song", "Elton John", None,
            "Your Song (Remastered 2017)", "Elton John", "Elton John (Remastered)"
        )
        live_score = score_match_with_version(
            "Your Song", "Elton John", None,
            "Your Song (Live)", "Elton John", "Live in Australia"
        )
        assert original_score >= remaster_score > live_score

    def test_returns_0_to_100_range(self):
        score = score_match_with_version(
            "Your Song", "Elton John", None,
            "Your Song", "Elton John", "Elton John"
        )
        assert 0 <= score <= 100
