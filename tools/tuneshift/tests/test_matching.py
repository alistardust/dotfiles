"""tests/test_matching.py"""
import pytest
from tuneshift.matching import (
    normalize_title,
    normalize_artist,
    score_match,
    classify_results,
    is_remaster,
    duration_proximity_bonus,
)


def test_normalize_title_strips_remaster() -> None:
    assert normalize_title("Heroes (Remastered 2017)") == "heroes"


def test_normalize_title_strips_deluxe() -> None:
    assert normalize_title("Ziggy Stardust (Deluxe Edition)") == "ziggy stardust"


def test_normalize_title_empty() -> None:
    assert normalize_title("") == ""


def test_normalize_artist_strips_the() -> None:
    assert normalize_artist("The Beatles") == "beatles"


def test_normalize_artist_ampersand() -> None:
    assert normalize_artist("Simon & Garfunkel") == "simon and garfunkel"


def test_normalize_artist_empty() -> None:
    assert normalize_artist("") == ""


def test_score_exact_match() -> None:
    score = score_match("Heroes", "David Bowie", "Heroes", "Heroes", "David Bowie", "Heroes")
    assert score == 100


def test_score_no_album() -> None:
    score = score_match("Heroes", "David Bowie", None, "Heroes", "David Bowie", "Best Of")
    assert score == 80


def test_score_wrong_artist() -> None:
    score = score_match("Heroes", "David Bowie", None, "Heroes", "Wallflowers", "Bringing Down")
    assert score < 60


def test_classify_high_confidence() -> None:
    assert classify_results([90, 50, 40]) == "high"


def test_classify_ambiguous() -> None:
    assert classify_results([85, 82]) == "ambiguous"


def test_classify_not_found() -> None:
    assert classify_results([30, 20]) == "not_found"
    assert classify_results([]) == "not_found"


def test_is_remaster() -> None:
    assert is_remaster("Heroes (2017 Remastered)")
    assert not is_remaster("Heroes")


def test_is_remaster_empty() -> None:
    assert not is_remaster("")


@pytest.mark.parametrize("raw,expected", [
    ("Louder (feat. Icona Pop)", "louder"),
    ("Revolution! (ft. Someone)", "revolution!"),
    ("Together (with Dua Lipa)", "together"),
    ("Hello (featuring Adele)", "hello"),
    ("Normal Title", "normal title"),
    ("Title [feat. Artist]", "title"),
    ("Already (Deluxe Remastered) (feat. X)", "already"),
])
def test_normalize_title_strips_featured_artists(raw, expected):
    assert normalize_title(raw) == expected


@pytest.mark.parametrize("candidate,canonical,expected", [
    (200, 200, 10),      # exact match
    (195, 200, 10),      # within 5%
    (180, 200, 5),       # within 15% (10% diff)
    (150, 200, 0),       # too different (25% diff)
    (None, 200, 0),      # missing candidate duration
    (200, None, 0),      # missing canonical duration
])
def test_duration_proximity_bonus(candidate, canonical, expected):
    assert duration_proximity_bonus(candidate, canonical) == expected
