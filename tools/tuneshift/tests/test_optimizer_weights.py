"""Tests for weight vector integration in optimizer."""

import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.optimizer import optimize_sequence
from tuneshift.sequencer.weights import PRESETS


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A", "energy": 0.5}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestOptimizerWeights:
    def test_accepts_new_weight_dimensions(self) -> None:
        tracks = [_track(i, energy=i * 0.1) for i in range(5)]
        result = optimize_sequence(
            tracks, weights=PRESETS["energy-wave"], arc="wave"
        )
        assert len(result) == 5
        assert {t.track_id for t in result} == {0, 1, 2, 3, 4}

    def test_narrative_queen_preset(self) -> None:
        tracks = [_track(i, emotional_intensity=i * 0.2) for i in range(5)]
        result = optimize_sequence(
            tracks, weights=PRESETS["narrative-queen"], arc="narrative"
        )
        assert len(result) == 5
