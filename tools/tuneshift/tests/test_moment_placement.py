"""Tests for moment pin placement in the climax region."""
import pytest
from tuneshift.sequencer.optimizer import _place_moments, optimize_sequence
from tuneshift.sequencer.metadata import TrackMetadata


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


def test_optimizer_no_duplicate_tracks():
    """Tracks selected as opener/closer must not also appear as position pins."""
    tracks = [
        TrackMetadata(track_id=i, title=f"Track {i}", artist=f"Artist {i}",
                      energy=0.1 * i, valence=0.5, emotional_intensity=0.1 * i)
        for i in range(1, 11)
    ]
    weights = {"energy": 0.5, "bpm": 0.2, "key": 0.1, "mode": 0.1, "themes": 0.1}
    result = optimize_sequence(tracks, weights, arc="narrative")
    track_ids = [t.track_id for t in result]
    assert len(track_ids) == len(set(track_ids)), (
        f"Duplicate track_ids in sequence: {[tid for tid in track_ids if track_ids.count(tid) > 1]}"
    )
