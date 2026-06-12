"""Tests for transition and narrative connection scoring."""
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.scoring import transition_score, narrative_connection_score, emotional_arc_score


@pytest.fixture
def track_a():
    return TrackMetadata(
        track_id=1, title="Song A", artist="Artist",
        closes_with="fade to silence", sonic_texture="warm", space="intimate",
        narrator_stance="vulnerable", lyrical_subject="heartbreak",
    )


@pytest.fixture
def track_b_bridge():
    return TrackMetadata(
        track_id=2, title="Song B", artist="Artist 2",
        opens_with="silence to vocal", sonic_texture="warm", space="intimate",
        narrator_stance="defiant", lyrical_subject="self-acceptance",
    )


@pytest.fixture
def track_c_contrast():
    return TrackMetadata(
        track_id=3, title="Song C", artist="Artist 3",
        opens_with="drum fill explosion", sonic_texture="gritty", space="vast",
        narrator_stance="triumphant", lyrical_subject="victory",
    )


def test_transition_score_sonic_bridge(track_a, track_b_bridge):
    score = transition_score(track_a, track_b_bridge)
    assert score > 0.7


def test_transition_score_no_data():
    a = TrackMetadata(track_id=1, title="A", artist="X")
    b = TrackMetadata(track_id=2, title="B", artist="Y")
    score = transition_score(a, b)
    assert score == 0.5


def test_narrative_connection_empowerment_arc(track_a, track_b_bridge):
    score = narrative_connection_score(track_a, track_b_bridge)
    assert score > 0.6


def test_narrative_connection_progressive(track_b_bridge, track_c_contrast):
    score = narrative_connection_score(track_b_bridge, track_c_contrast)
    assert score >= 0.5


def test_emotional_arc_smooth():
    a = TrackMetadata(track_id=1, title="A", artist="X", emotional_intensity=0.5)
    b = TrackMetadata(track_id=2, title="B", artist="Y", emotional_intensity=0.6)
    assert emotional_arc_score(a, b) > 0.7


def test_emotional_arc_jarring():
    a = TrackMetadata(track_id=1, title="A", artist="X", emotional_intensity=0.1)
    b = TrackMetadata(track_id=2, title="B", artist="Y", emotional_intensity=0.9)
    assert emotional_arc_score(a, b) < 0.5
