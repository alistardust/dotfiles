"""Tests for matching.py normalization, scoring, classification."""
from tidal_importer.matching import (
    normalize_title,
    normalize_artist,
    is_remaster,
    score_match,
    classify_results,
)


class TestNormalizeTitle:
    def test_strips_remastered_parens(self):
        assert normalize_title("Mr. Tambourine Man (Remastered)") == "mr. tambourine man"

    def test_strips_deluxe_edition(self):
        assert normalize_title("Forever Changes (Deluxe Edition)") == "forever changes"

    def test_strips_year_remaster(self):
        assert normalize_title("Abbey Road (2019 Remaster)") == "abbey road"

    def test_strips_mono_stereo(self):
        assert normalize_title("Revolver (Mono)") == "revolver"

    def test_strips_expanded(self):
        assert normalize_title("Pet Sounds (Expanded Edition)") == "pet sounds"

    def test_multiple_parentheticals(self):
        assert normalize_title("Song (Remastered) (Deluxe Edition)") == "song"

    def test_basic_casefold(self):
        assert normalize_title("Eight Miles High") == "eight miles high"

    def test_unicode_normalization(self):
        assert normalize_title("Cafe\u0301") == "caf\u00e9"

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_only_parens(self):
        assert normalize_title("(Remastered)") == ""

    def test_preserves_non_edition_parens(self):
        assert normalize_title("(Sittin' On) The Dock of the Bay") == "(sittin' on) the dock of the bay"


class TestNormalizeArtist:
    def test_strips_the_prefix(self):
        assert normalize_artist("The Byrds") == "byrds"

    def test_ampersand_to_and(self):
        assert normalize_artist("Crosby, Stills & Nash") == "crosby, stills and nash"

    def test_preserves_the_in_middle(self):
        assert normalize_artist("Band of the Hand") == "band of the hand"

    def test_multiple_ampersands(self):
        assert normalize_artist("A & B & C") == "a and b and c"

    def test_empty_string(self):
        assert normalize_artist("") == ""

    def test_mamas_and_papas(self):
        assert normalize_artist("The Mamas & the Papas") == "mamas and the papas"


class TestIsRemaster:
    def test_remastered_parens(self):
        assert is_remaster("Mr. Tambourine Man (Remastered)") is True

    def test_year_remaster(self):
        assert is_remaster("Abbey Road (2019 Remaster)") is True

    def test_plain_album(self):
        assert is_remaster("Mr. Tambourine Man") is False

    def test_remaster_in_title(self):
        assert is_remaster("Remastered Classics") is True

    def test_empty(self):
        assert is_remaster("") is False


class TestScoreMatch:
    def test_exact_match_all_fields_100(self):
        assert score_match(
            "Mr. Tambourine Man", "The Byrds", "Mr. Tambourine Man",
            "Mr. Tambourine Man", "The Byrds", "Mr. Tambourine Man",
        ) == 100

    def test_title_artist_match_remastered_album(self):
        result = score_match(
            "Mr. Tambourine Man", "The Byrds", "Mr. Tambourine Man",
            "Mr. Tambourine Man", "The Byrds", "Mr. Tambourine Man (Remastered)",
        )
        assert result == 100  # 50 + 30 + 20 (album exact after normalization)

    def test_title_only_wrong_artist(self):
        result = score_match(
            "Mr. Tambourine Man", "The Byrds", "Mr. Tambourine Man",
            "Mr. Tambourine Man", "Bob Dylan", "Bringing It All Back Home",
        )
        assert result == 50  # title only

    def test_no_album_in_source(self):
        result = score_match(
            "White Rabbit", "Jefferson Airplane", None,
            "White Rabbit", "Jefferson Airplane", "Surrealistic Pillow",
        )
        assert result == 80  # 50 + 30, no album scoring

    def test_fuzzy_title_high_ratio(self):
        result = score_match(
            "Andmoreagain", "Love", "Forever Changes",
            "And More Again", "Love", "Forever Changes",
        )
        assert result >= 70  # fuzzy title + exact artist + exact album

    def test_nothing_matches(self):
        result = score_match(
            "Watermelon Sugar", "Harry Styles", "Fine Line",
            "Bohemian Rhapsody", "Queen", "A Night at the Opera",
        )
        assert result == 0

    def test_empty_source_fields(self):
        result = score_match("", "", None, "Song", "Artist", "Album")
        assert isinstance(result, int)


class TestClassifyResults:
    def test_high_single_clear_winner(self):
        assert classify_results([90, 50, 30]) == "high"

    def test_high_single_result(self):
        assert classify_results([85]) == "high"

    def test_ambiguous_two_high_scores(self):
        assert classify_results([90, 85]) == "ambiguous"

    def test_ambiguous_top_below_80(self):
        assert classify_results([65, 40]) == "ambiguous"

    def test_not_found_low_scores(self):
        assert classify_results([40, 20]) == "not_found"

    def test_not_found_empty(self):
        assert classify_results([]) == "not_found"

    def test_boundary_80_69(self):
        assert classify_results([80, 69]) == "high"

    def test_boundary_80_70(self):
        assert classify_results([80, 70]) == "ambiguous"

    def test_top_exactly_50(self):
        assert classify_results([50]) == "ambiguous"

    def test_top_exactly_49(self):
        assert classify_results([49]) == "not_found"
