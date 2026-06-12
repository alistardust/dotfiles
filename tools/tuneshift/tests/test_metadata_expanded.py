"""Tests for expanded TrackMetadata narrative fields."""
import pytest
from tuneshift.models import Track
from tuneshift.sequencer.metadata import track_to_metadata, TrackMetadata


def test_track_to_metadata_reads_narrative_fields():
    """New narrative fields are populated from track.metadata JSON."""
    track = Track(
        id=1, title="Protest", artist="Kim Petras",
        metadata={
            "emotional_intensity": 0.9,
            "lyrical_subject": "refusing to be silenced",
            "narrator_stance": "defiant",
            "sonic_texture": "polished",
            "space": "vast",
            "groove_feel": "driving",
            "opens_with": "synth pad swell",
            "closes_with": "hard cut",
            "energy_arc_within": "builds to peak",
            "classification_confidence": 0.85,
        },
    )
    meta = track_to_metadata(track)
    assert meta.emotional_intensity == 0.9
    assert meta.lyrical_subject == "refusing to be silenced"
    assert meta.narrator_stance == "defiant"
    assert meta.sonic_texture == "polished"
    assert meta.space == "vast"
    assert meta.groove_feel == "driving"
    assert meta.opens_with == "synth pad swell"
    assert meta.closes_with == "hard cut"
    assert meta.energy_arc_within == "builds to peak"
    assert meta.classification_confidence == 0.85


def test_track_to_metadata_missing_narrative_fields():
    """Missing narrative fields default to None."""
    track = Track(id=2, title="Old Track", artist="Artist", metadata={})
    meta = track_to_metadata(track)
    assert meta.emotional_intensity is None
    assert meta.narrator_stance is None
    assert meta.opens_with is None
    assert meta.classification_confidence is None
