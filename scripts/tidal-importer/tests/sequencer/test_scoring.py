"""Tests for pairwise transition scoring."""
from tidal_importer.sequencer.cache import TrackMetadata
from tidal_importer.sequencer.scoring import (
    theme_score,
    energy_score,
    instrumentation_score,
    bpm_score,
    mode_score,
    key_score,
    score_pair,
    jaccard,
)


class TestJaccard:
    def test_identical_sets(self):
        assert jaccard(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_disjoint_sets(self):
        assert jaccard(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        result = jaccard(["a", "b", "c"], ["b", "c", "d"])
        assert abs(result - 0.5) < 0.001  # 2 shared / 4 total

    def test_empty_sets(self):
        assert jaccard([], []) == 0.0


class TestThemeScore:
    def test_identical_themes(self):
        a = TrackMetadata(isrc="A", tidal_id=1, title="A", artist="A",
                          themes=["love", "loss"], vibes=["sad", "slow"],
                          era_mood=["60s folk"])
        b = TrackMetadata(isrc="B", tidal_id=2, title="B", artist="B",
                          themes=["love", "loss"], vibes=["sad", "slow"],
                          era_mood=["60s folk"])
        assert theme_score(a, b) == 1.0

    def test_completely_different(self):
        a = TrackMetadata(isrc="A", tidal_id=1, title="A", artist="A",
                          themes=["war", "anger"], vibes=["aggressive", "loud"],
                          era_mood=["punk"])
        b = TrackMetadata(isrc="B", tidal_id=2, title="B", artist="B",
                          themes=["love", "peace"], vibes=["gentle", "soft"],
                          era_mood=["folk"])
        assert theme_score(a, b) == 0.0


class TestBpmScore:
    def test_identical_bpm(self):
        assert bpm_score(120.0, 120.0) == 1.0

    def test_within_tolerance(self):
        score = bpm_score(120.0, 130.0)
        assert 0.4 < score < 0.7  # ~8% difference

    def test_halftime_compatible(self):
        score = bpm_score(70.0, 140.0)
        assert score == 0.9

    def test_large_difference_zero(self):
        score = bpm_score(60.0, 180.0)
        assert score == 0.0


class TestModeScore:
    def test_same_mode(self):
        assert mode_score(1, 1, 0.5, 0.5) == 1.0

    def test_different_mode(self):
        assert mode_score(1, 0, 0.5, 0.5) == 0.5

    def test_resolution_bonus(self):
        # minor -> major with both low valence = resolution
        score = mode_score(0, 1, 0.3, 0.3)
        assert score == 0.7


class TestKeyScore:
    def test_same_key(self):
        assert key_score("8A", "8A") == 1.0

    def test_adjacent_key(self):
        assert key_score("8A", "9A") == 1.0

    def test_relative_major_minor(self):
        assert key_score("8A", "8B") == 1.0

    def test_distant_key(self):
        score = key_score("1A", "7A")
        assert score < 0.5


class TestScorePair:
    def test_full_data_returns_weighted_score(self):
        a = TrackMetadata(
            isrc="A", tidal_id=1, title="A", artist="ArtistA",
            bpm=120.0, key_note=0, mode=1, energy=0.5, valence=0.5,
            acousticness=0.3, themes=["love"], vibes=["warm"],
            instruments=["guitar"], density="mid", era_mood=["70s"],
            camelot_code="8B",
        )
        b = TrackMetadata(
            isrc="B", tidal_id=2, title="B", artist="ArtistB",
            bpm=125.0, key_note=0, mode=1, energy=0.55, valence=0.45,
            acousticness=0.35, themes=["love"], vibes=["warm"],
            instruments=["guitar"], density="mid", era_mood=["70s"],
            camelot_code="8B",
        )
        weights = {"themes": 0.35, "energy": 0.22, "instrumentation": 0.18,
                   "bpm": 0.12, "mode": 0.08, "key": 0.05}
        score = score_pair(a, b, weights)
        assert 0.8 < score <= 1.0  # very similar tracks

    def test_missing_bpm_renormalizes(self):
        a = TrackMetadata(
            isrc="A", tidal_id=1, title="A", artist="A",
            bpm=None, energy=0.5, valence=0.5,
            themes=["love"], vibes=["warm"], instruments=["guitar"],
            density="mid", era_mood=["70s"], camelot_code="8B",
            mode=1, acousticness=0.3,
        )
        b = TrackMetadata(
            isrc="B", tidal_id=2, title="B", artist="B",
            bpm=None, energy=0.5, valence=0.5,
            themes=["love"], vibes=["warm"], instruments=["guitar"],
            density="mid", era_mood=["70s"], camelot_code="8B",
            mode=1, acousticness=0.3,
        )
        weights = {"themes": 0.35, "energy": 0.22, "instrumentation": 0.18,
                   "bpm": 0.12, "mode": 0.08, "key": 0.05}
        score = score_pair(a, b, weights)
        assert 0.8 < score <= 1.0
