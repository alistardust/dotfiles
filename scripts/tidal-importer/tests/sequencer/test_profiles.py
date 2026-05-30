"""Tests for weight profiles and configuration."""
import pytest
from tidal_importer.sequencer.profiles import (
    WeightProfile,
    get_profile,
    DEFAULT_WEIGHTS,
    normalize_weights,
    merge_cli_overrides,
)


def test_default_weights_sum_to_one():
    total = sum(DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001


def test_get_profile_default():
    profile = get_profile("default")
    assert profile.name == "default"
    assert profile.weights["themes"] == 0.35
    assert profile.arc == "wave"
    assert profile.bold_jump_chance == 0.10
    assert profile.artist_min_separation == 4


def test_get_profile_psych_journey():
    profile = get_profile("psych-journey")
    assert profile.weights["instrumentation"] == 0.25
    assert profile.arc == "narrative"
    assert profile.bold_jump_chance == 0.15


def test_get_profile_unknown_raises():
    with pytest.raises(KeyError, match="Unknown profile"):
        get_profile("nonexistent")


def test_normalize_weights():
    weights = {"themes": 0.5, "energy": 0.3, "bpm": 0.2}
    normalized = normalize_weights(weights)
    assert abs(sum(normalized.values()) - 1.0) < 0.001
    assert abs(normalized["themes"] - 0.5) < 0.001


def test_normalize_weights_unbalanced():
    weights = {"themes": 1.0, "energy": 1.0}
    normalized = normalize_weights(weights)
    assert abs(normalized["themes"] - 0.5) < 0.001
    assert abs(normalized["energy"] - 0.5) < 0.001


def test_merge_cli_overrides():
    base = {"themes": 0.35, "energy": 0.22, "instrumentation": 0.18,
            "bpm": 0.12, "mode": 0.08, "key": 0.05}
    overrides = {"themes": 0.5, "energy": 0.3}
    merged = merge_cli_overrides(base, overrides)
    assert abs(sum(merged.values()) - 1.0) < 0.001
    assert merged["themes"] > merged["instrumentation"]
    assert merged["energy"] > merged["bpm"]
