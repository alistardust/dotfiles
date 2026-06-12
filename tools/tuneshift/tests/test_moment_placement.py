"""Tests for moment pin placement in the climax region."""
import pytest
from tuneshift.sequencer.optimizer import _place_moments


def test_place_moments_targets_climax_region():
    """Moments are placed in the 55-75% region."""
    positions = _place_moments(
        tracks=[],
        moments=[42],
        total=20,
    )
    assert len(positions) == 1
    target_pos = list(positions.keys())[0]
    assert 11 <= target_pos <= 15


def test_place_moments_multiple_spaced():
    """Multiple moments are evenly spaced in climax region."""
    positions = _place_moments(
        tracks=[], moments=[42, 99], total=20,
    )
    assert len(positions) == 2
    pos_list = sorted(positions.keys())
    assert pos_list[0] < pos_list[1]
    assert all(11 <= p <= 15 for p in pos_list)


def test_place_moments_empty():
    """No moments returns empty dict."""
    assert _place_moments([], [], 20) == {}
