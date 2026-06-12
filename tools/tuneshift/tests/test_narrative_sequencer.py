"""Test that narrative mode places tracks into declared sections."""
import pytest
from tuneshift.sequencer.optimizer import optimize_sequence, assign_tracks_to_sections
from tuneshift.sequencer.narrative_parser import parse_narrative
from tuneshift.sequencer.metadata import TrackMetadata


def _make_track(track_id: int, title: str, intensity: float = 0.5, stance: str | None = None) -> TrackMetadata:
    return TrackMetadata(
        track_id=track_id,
        title=title,
        artist="Test",
        duration_ms=200_000,
        energy=intensity,
        emotional_intensity=intensity,
        narrator_stance=stance,
    )


NARRATIVE = """
OPENING (1-2): Gentle intro, setting the scene.
WRATH (3-4): Fury and defiance.
CLOSER (5): Triumphant anthem.
"""


def test_narrative_mode_respects_section_positions():
    """Tracks should end up in their declared section positions."""
    tracks = [
        _make_track(1, "Gentle Intro", intensity=0.2, stance="vulnerable"),
        _make_track(2, "Setup Song", intensity=0.3, stance="vulnerable"),
        _make_track(3, "Rage Track", intensity=0.9, stance="defiant"),
        _make_track(4, "Fury Song", intensity=0.85, stance="defiant"),
        _make_track(5, "Anthem", intensity=0.7, stance="triumphant"),
    ]
    result = optimize_sequence(
        tracks,
        weights=None,
        arc="narrative",
        narrative=NARRATIVE,
    )
    ids = [t.track_id for t in result]
    # Gentle/vulnerable tracks in positions 0-1 (OPENING)
    assert set(ids[0:2]) == {1, 2}, f"OPENING section wrong: {ids[0:2]}"
    # Defiant/high-intensity tracks in positions 2-3 (WRATH)
    assert set(ids[2:4]) == {3, 4}, f"WRATH section wrong: {ids[2:4]}"
    # Triumphant track in position 4 (CLOSER)
    assert ids[4] == 5, f"CLOSER section wrong: {ids[4]}"


def test_section_assignment_uses_fitness():
    """assign_tracks_to_sections should assign by fitness scoring."""
    sections = parse_narrative(NARRATIVE)
    tracks = [
        _make_track(1, "Gentle Intro", intensity=0.2, stance="vulnerable"),
        _make_track(2, "Rage Track", intensity=0.9, stance="defiant"),
        _make_track(3, "Anthem", intensity=0.7, stance="triumphant"),
        _make_track(4, "Setup", intensity=0.3, stance="vulnerable"),
        _make_track(5, "Fury", intensity=0.85, stance="defiant"),
    ]
    assignments = assign_tracks_to_sections(tracks, sections, goal="narrative")
    # Vulnerable tracks in OPENING
    opening_ids = {t.track_id for t in assignments["OPENING"]}
    assert 1 in opening_ids or 4 in opening_ids
    # Defiant tracks in WRATH
    wrath_ids = {t.track_id for t in assignments["WRATH"]}
    assert 2 in wrath_ids or 5 in wrath_ids


def test_narrative_mode_with_no_narrative_falls_back():
    """Without narrative text, narrative mode should still produce a result."""
    tracks = [
        _make_track(1, "A", intensity=0.5),
        _make_track(2, "B", intensity=0.6),
        _make_track(3, "C", intensity=0.7),
    ]
    result = optimize_sequence(tracks, weights=None, arc="narrative", narrative=None)
    assert len(result) == 3
    assert set(t.track_id for t in result) == {1, 2, 3}
