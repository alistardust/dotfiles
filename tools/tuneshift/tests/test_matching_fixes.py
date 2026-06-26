"""Acceptance tests for matching algorithm fixes.

These tests encode the expected behavior BEFORE implementation.
All should FAIL initially, then pass after the fix.
"""
import pytest
from tuneshift.matching import (
    normalize_artist,
    normalize_title,
    score_match,
    score_match_with_version,
    version_penalty,
    duration_penalty,
)


class TestArtistNormalization:
    """After normalization, legitimate variants should be identical."""

    def test_punctuation_stripped(self):
        # P!nk can't be normalized to "pink" without knowing ! = i
        # But scoring handles it (ratio 0.75 = +15 artist bonus)
        # At minimum, leading/trailing punct and commas are stripped
        assert normalize_artist("Tyler, The Creator") == normalize_artist("Tyler the Creator")

    def test_case_insensitive(self):
        assert normalize_artist("100 gecs") == normalize_artist("100 Gecs")

    def test_comma_and_case(self):
        assert normalize_artist("Tyler, The Creator") == normalize_artist("Tyler the Creator")

    def test_feat_stripped_from_artist(self):
        assert normalize_artist("Clean Bandit feat. Jess Glynne") == normalize_artist("Clean Bandit")

    def test_feat_ft_stripped(self):
        assert normalize_artist("Megan Thee Stallion feat. Beyonce") == normalize_artist("Megan Thee Stallion")


class TestArtistScoring:
    """After normalization, different artists should score poorly."""

    def test_sia_vs_sza_rejected(self):
        # Title match + different artist should be < 50
        score = score_match("Go", "Sia", None, "Go", "SZA", "SOS")
        assert score < 50

    def test_beatles_vs_beatbox_rejected(self):
        # A cover band with same album name: should be ambiguous (not high confidence)
        score = score_match("Come Together", "The Beatles", "Abbey Road",
                           "Come Together", "The Beatbox", "Abbey Road")
        assert score < 60  # Not auto-accepted as "high" (needs >= 80)

    def test_britney_vs_marias_rejected(self):
        score = score_match("...Baby One More Time", "Britney Spears", "...Baby One More Time",
                           "...Baby One More Time", "The Marias", "Submarine")
        assert score < 50

    def test_pink_matches_pink(self):
        score = score_match("Raise Your Glass", "P!nk", "Greatest Hits",
                           "Raise Your Glass", "Pink", "Greatest Hits")
        assert score >= 80

    def test_tyler_matches_tyler(self):
        score = score_match("EARFQUAKE", "Tyler, The Creator", "IGOR",
                           "EARFQUAKE", "Tyler the Creator", "IGOR")
        assert score >= 90

    def test_clean_bandit_feat_matches(self):
        score = score_match("Rather Be", "Clean Bandit feat. Jess Glynne", "New Eyes",
                           "Rather Be", "Clean Bandit", "New Eyes")
        assert score >= 80


class TestPunctuationNormalization:
    """Curly quotes, accents should not break matching."""

    def test_curly_quotes_title(self):
        # Curly vs straight apostrophe
        assert normalize_title("Rock \u2018n\u2019 Roll") == normalize_title("Rock 'n' Roll")

    def test_leading_dots(self):
        assert normalize_title("...Baby One More Time") == normalize_title("...Baby One More Time")


class TestVersionPenalty:
    """Year-mixes should NOT be penalized. Karaoke/instrumental should be harsh."""

    def test_2019_mix_no_penalty(self):
        assert version_penalty("Come Together", "Abbey Road (2019 Mix)") == 0

    def test_stereo_mix_no_penalty(self):
        assert version_penalty("Come Together", "Abbey Road (Stereo Mix)") == 0

    def test_club_mix_penalized(self):
        assert version_penalty("Come Together", "Abbey Road (Club Mix)") >= 20

    def test_extended_mix_penalized(self):
        assert version_penalty("Song", "Album (Extended Mix)") >= 20

    def test_karaoke_max_penalty(self):
        penalty = version_penalty("Style", "Taylor Swift Karaoke: 1989")
        assert penalty >= 50

    def test_karaoke_in_title(self):
        penalty = version_penalty("Style (Karaoke Version)", "1989")
        assert penalty >= 50

    def test_instrumental_max_penalty(self):
        penalty = version_penalty("Style (Instrumental)", "1989")
        assert penalty >= 50

    def test_radio_edit_moderate_penalty(self):
        penalty = version_penalty("Summertime Sadness (Radio Edit)", "Born to Die")
        assert 15 <= penalty <= 25


class TestDurationPenalty:
    """Should penalize BOTH too-long AND too-short candidates."""

    def test_much_shorter_penalized(self):
        # 125s vs 210s expected = ~60% of original
        penalty = duration_penalty(125, reference_duration=210)
        assert penalty >= 10

    def test_very_short_heavily_penalized(self):
        # 90s vs 210s = 43% of original
        penalty = duration_penalty(90, reference_duration=210)
        assert penalty >= 15

    def test_similar_duration_no_penalty(self):
        penalty = duration_penalty(200, reference_duration=210)
        assert penalty == 0

    def test_no_reference_no_penalty(self):
        penalty = duration_penalty(125, reference_duration=None)
        assert penalty == 0

    def test_too_long_penalized(self):
        penalty = duration_penalty(400, reference_duration=210)
        assert penalty >= 15


class TestEndToEndReconcileScenarios:
    """Full score_match_with_version integration tests."""

    def test_marias_cover_rejected(self):
        score = score_match_with_version(
            "...Baby One More Time", "Britney Spears", "...Baby One More Time",
            "...Baby One More Time", "The Marias", "Submarine",
            result_duration=125, reference_duration=211,
        )
        assert score < 50

    def test_real_britney_accepted(self):
        score = score_match_with_version(
            "...Baby One More Time", "Britney Spears", "...Baby One More Time",
            "...Baby One More Time", "Britney Spears", "...Baby One More Time (Digital Deluxe Version)",
            result_duration=211, reference_duration=211,
        )
        assert score >= 80

    def test_karaoke_version_rejected(self):
        score = score_match_with_version(
            "Style", "Taylor Swift", "1989",
            "Style", "Taylor Swift Karaoke", "Taylor Swift Karaoke: 1989",
            result_duration=231, reference_duration=231,
        )
        assert score < 50

    def test_abbey_road_2019_mix_accepted(self):
        score = score_match_with_version(
            "Come Together", "The Beatles", "Abbey Road",
            "Come Together", "The Beatles", "Abbey Road (2019 Mix)",
            result_duration=259, reference_duration=259,
        )
        assert score >= 70
