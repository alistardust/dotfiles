import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.scoring import (
    score_track_contribution,
    score_narrative_fit,
    score_mood_contribution,
    CURATION_SCORERS,
)


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestCurationScoring:
    def test_all_scorers_registered(self) -> None:
        expected = {"narrative_fit", "mood_contribution", "sonic_role", "energy_role", "uniqueness", "redundancy"}
        assert set(CURATION_SCORERS.keys()) == expected

    def test_narrative_fit_high_for_matching_track(self) -> None:
        ctx = PlaylistContext(
            goal="Trans fury and empowerment",
            narrative_sections=[{"name": "WRATH", "description": "Fury and defiance"}],
            mood_profile=None,
            all_tracks=[],
        )
        track = _track(1, lyrical_subject="identity", narrator_stance="defiant",
                      themes=["trans", "rage"], emotional_intensity=0.9)
        score = score_narrative_fit(track, ctx, [])
        assert score > 0.6

    def test_narrative_fit_low_for_unrelated_track(self) -> None:
        ctx = PlaylistContext(
            goal="Trans fury and empowerment",
            narrative_sections=[{"name": "WRATH", "description": "Fury and defiance"}],
            mood_profile=None,
            all_tracks=[],
        )
        track = _track(2, lyrical_subject="partying", narrator_stance="carefree",
                      themes=["summer", "beach"], emotional_intensity=0.3)
        score = score_narrative_fit(track, ctx, [])
        assert score < 0.4

    def test_missing_classification_returns_neutral(self) -> None:
        ctx = PlaylistContext(goal="Any", narrative_sections=[], mood_profile=None, all_tracks=[])
        track = _track(3)  # no classification data
        scores = score_track_contribution(track, ctx, [])
        # Must return all 6 scoring dimensions even without classification data
        expected_keys = {"narrative_fit", "mood_contribution", "sonic_role", "energy_role", "uniqueness", "redundancy"}
        assert set(scores.keys()) == expected_keys
        # Must not crash; neutral range acceptable for unclassified tracks
        assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scores.values())
