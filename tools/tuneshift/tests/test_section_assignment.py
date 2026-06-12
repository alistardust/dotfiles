import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.optimizer import assign_tracks_to_sections
from tuneshift.sequencer.narrative_parser import NarrativeSection


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestAssignTracksToSections:
    def test_assigns_intense_tracks_to_wrath(self) -> None:
        sections = [
            NarrativeSection(name="OPENING", start_position=1, end_position=2,
                           description="Gentle setup", implied_intensity=0.2,
                           implied_stance=None, capacity=2),
            NarrativeSection(name="WRATH", start_position=3, end_position=5,
                           description="Fury and defiance", implied_intensity=0.9,
                           implied_stance="defiant", capacity=3),
        ]
        tracks = [
            _track(1, emotional_intensity=0.1, narrator_stance="gentle"),
            _track(2, emotional_intensity=0.2, narrator_stance="peaceful"),
            _track(3, emotional_intensity=0.9, narrator_stance="defiant"),
            _track(4, emotional_intensity=0.8, narrator_stance="angry"),
            _track(5, emotional_intensity=0.7, narrator_stance="defiant"),
        ]
        assignments = assign_tracks_to_sections(tracks, sections, "Trans fury")
        # High-intensity tracks should be in WRATH
        wrath_ids = {t.track_id for t in assignments.get("WRATH", [])}
        assert 3 in wrath_ids
        assert 4 in wrath_ids

    def test_respects_section_capacity(self) -> None:
        sections = [
            NarrativeSection(name="OPENING", start_position=1, end_position=2,
                           description="Setup", implied_intensity=0.3,
                           implied_stance=None, capacity=2),
        ]
        tracks = [_track(i, emotional_intensity=0.3) for i in range(5)]
        assignments = assign_tracks_to_sections(tracks, sections, "Test")
        # OPENING can only hold 2 tracks
        assert len(assignments.get("OPENING", [])) <= 2
        # Rest go to flex pool
        assert "_flex" in assignments
        assert len(assignments["_flex"]) >= 3

    def test_empty_sections_all_go_to_flex(self) -> None:
        tracks = [_track(i) for i in range(5)]
        assignments = assign_tracks_to_sections(tracks, [], "Test")
        assert "_flex" in assignments
        assert len(assignments["_flex"]) == 5
