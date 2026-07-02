"""Tests for matching.similarity and matching.penalties.

The point projections (``SignalPenalty.points``) are asserted against the
*frozen* legacy integer contributions so the beets-style penalty layer stays
byte-parity with the historical scorer. Ratio-band fixtures assert the ratio
they rely on so the intent survives if similarity ever changes.
"""
import pytest

from tuneshift.matching import normalize as norm
from tuneshift.matching import penalties as pen
from tuneshift.matching import similarity as sim


def nt(s: str) -> str:
    return norm.normalize_title(s)


def na(s: str) -> str:
    return norm.normalize_artist(s)


# --- similarity ---

def test_ratio_identical():
    assert sim.ratio("hello", "hello") == 1.0


def test_ratio_disjoint():
    assert sim.ratio("abc", "xyz") == 0.0


def test_ratio_empty_both():
    assert sim.ratio("", "") == 1.0


# --- title signal ---

def test_title_exact():
    s = pen.title_signal(nt("Bohemian Rhapsody"), nt("Bohemian Rhapsody"))
    assert s.points == 50
    assert s.penalty == 0.0
    assert s.weight == 50


def test_title_high_tier():
    a, b = nt("Song Title"), nt("Song Titel")
    assert sim.ratio(a, b) > 0.85
    assert pen.title_signal(a, b).points == 30


@pytest.mark.parametrize("raw_a, raw_b", [("Yesterday", "Yesteryear"), ("Track", "Trakc")])
def test_title_mid_tier(raw_a, raw_b):
    a, b = nt(raw_a), nt(raw_b)
    assert 0.70 <= sim.ratio(a, b) <= 0.85
    assert pen.title_signal(a, b).points == 15


def test_title_miss():
    s = pen.title_signal(nt("Song Title Here"), nt("Different Song X"))
    assert s.points == 0
    assert s.penalty == 1.0


def test_title_empty_no_signal():
    assert pen.title_signal("", "anything").points == 0
    assert pen.title_signal("anything", "").points == 0


# --- artist signal ---

def test_artist_exact():
    assert pen.artist_signal(na("Queen"), na("Queen")).points == 30


def test_artist_high_tier():
    a, b = na("Robert Plant"), na("Robert Plante")
    assert sim.ratio(a, b) > 0.85
    assert pen.artist_signal(a, b).points == 25


def test_artist_mid_tier():
    a, b = na("Yesterday"), na("Yesteryear")
    assert 0.70 < sim.ratio(a, b) <= 0.85
    assert pen.artist_signal(a, b).points == 15


def test_artist_low_tier():
    a, b = na("Adele"), na("Angel")
    assert 0.50 < sim.ratio(a, b) <= 0.70
    assert pen.artist_signal(a, b).points == -15


def test_artist_heavy_tier():
    # ratio 0.20 -> -int(30 * (1 - 0.40)) = -18
    a, b = na("Alpha Band"), na("Beta Group")
    assert sim.ratio(a, b) == pytest.approx(0.20)
    assert pen.artist_signal(a, b).points == -18


def test_artist_heavy_boundary_half():
    # ratio exactly 0.50 -> else branch -> -int(30 * 0) = 0
    a, b = na("ABCDEF"), na("ABCXYZ")
    assert sim.ratio(a, b) == 0.50
    assert pen.artist_signal(a, b).points == 0


def test_artist_heavy_penalty_beyond_budget_clamps():
    s = pen.artist_signal(na("Alpha Band"), na("Beta Group"))
    # negative points -> distance penalty saturates at 1.0
    assert s.penalty == 1.0


# --- album signal ---

def test_album_exact():
    assert pen.album_signal(nt("A Night at the Opera"), nt("A Night at the Opera")).points == 20


def test_album_high_tier():
    a, b = nt("The Album Name"), nt("The Album Nam")
    assert sim.ratio(a, b) >= 0.75
    assert pen.album_signal(a, b).points == 10


def test_album_miss():
    assert pen.album_signal(nt("Completely Different"), nt("Nothing Alike Here")).points == 0


def test_album_no_source_no_signal():
    s = pen.album_signal("", "whatever", source_present=False)
    assert s.points == 0
    assert s.penalty == 0.0  # absent source is neutral, not maximally bad


def test_album_empty_source_present_matches_empty_result():
    # Legacy quirk: raw source truthy but both normalize to "" -> exact bonus.
    assert pen.album_signal("", "", source_present=True).points == 20


def test_album_empty_source_present_nonempty_result():
    assert pen.album_signal("", "some album", source_present=True).points == 0


# --- isrc signal ---

def test_isrc_match():
    s = pen.isrc_signal("usrc17607839", "USRC17607839")
    assert s.points == 15
    assert s.penalty == 0.0


def test_isrc_mismatch():
    assert pen.isrc_signal("AAA", "BBB").points == 0


def test_isrc_missing():
    assert pen.isrc_signal(None, "USRC17607839").points == 0
    assert pen.isrc_signal("USRC17607839", None).points == 0


# --- version signals ---

VERSION_CASES = [
    ("Song (Karaoke Version)", "", -50),
    ("Song - Instrumental", "", -50),
    ("Song (Live)", "", -20),
    ("Song (Remix)", "", -20),
    ("Song (Tribute)", "", -20),
    ("Song (Radio Edit)", "", -20),
    ("Song", "Greatest Hits", -15),
    ("Song (Acoustic)", "", -10),
    ("Song", "Album (Remastered)", -10),
    ("Song", "Album (Deluxe)", -5),
    ("Song (Live)", "Album (Remastered)", -30),
    ("Plain Song", "Plain Album", 0),
    ("Song (Karaoke) (Live)", "Deluxe", -75),
]


@pytest.mark.parametrize("title, album, expected_points", VERSION_CASES)
def test_version_signals_sum_matches_legacy(title, album, expected_points):
    signals = pen.version_signals(title, album)
    assert sum(s.points for s in signals) == expected_points


def test_version_signal_is_full_penalty():
    signals = pen.version_signals("Song (Karaoke Version)", "")
    assert len(signals) == 1
    assert signals[0].penalty == 1.0
    assert signals[0].weight == 50
    assert signals[0].name == "version:karaoke"


# --- duration signal ---

DURATION_CASES = [
    ((None, 200, None), 0),
    ((200, None, None), 0),
    ((200, 200, None), 0),
    ((500, 200, None), -20),
    ((340, 200, None), -15),
    ((300, 200, None), -10),
    ((280, 200, None), 0),
    ((90, 200, None), -20),
    ((125, 200, None), -15),
    ((145, 200, None), -10),
    ((160, 200, None), 0),
    ((250, None, [300, 200, 210]), 0),
    ((200, 30, None), 0),
]


@pytest.mark.parametrize("args, expected_points", DURATION_CASES)
def test_duration_signal_matches_legacy(args, expected_points):
    cand, ref, alld = args
    assert pen.duration_signal(cand, ref, alld).points == expected_points


def test_duration_full_band_penalty_normalized():
    s = pen.duration_signal(500, 200)
    assert s.points == -20
    assert s.penalty == 1.0
    assert s.weight == 20


# --- configurability ---

def test_weights_override_changes_points():
    w = pen.DEFAULT_WEIGHTS.with_overrides(title_exact=80)
    s = pen.title_signal(nt("Song"), nt("Song"), w)
    assert s.points == 80
    assert s.weight == 80


def test_version_weight_override():
    vw = pen.VersionWeights(live=40)
    w = pen.DEFAULT_WEIGHTS.with_overrides(version=vw)
    signals = pen.version_signals("Song (Live)", "", w)
    assert sum(s.points for s in signals) == -40


def test_default_weights_frozen():
    with pytest.raises(Exception):
        pen.DEFAULT_WEIGHTS.title_exact = 1  # type: ignore[misc]
