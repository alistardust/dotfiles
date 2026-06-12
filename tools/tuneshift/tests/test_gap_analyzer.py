import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.gap_analyzer import analyze_gaps, GapReport


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestGapAnalysis:
    def test_detects_thin_section(self) -> None:
        tracks = [_track(i, emotional_intensity=0.8) for i in range(3)]
        sections = [
            {"name": "OPENING", "start": 1, "end": 2, "description": "Setup"},
            {"name": "WRATH", "start": 3, "end": 10, "description": "Fury"},  # needs 8 tracks, has ~1
        ]
        gaps = analyze_gaps(tracks, sections, goal="Fury playlist")
        assert any(g.section_name == "WRATH" for g in gaps)

    def test_detects_missing_transition(self) -> None:
        tracks = [
            _track(1, emotional_intensity=0.9, vibes=["explosive"]),
            _track(2, emotional_intensity=0.1, vibes=["peaceful"]),
        ]
        sections = [
            {"name": "WRATH", "start": 1, "end": 1, "description": "Fury"},
            {"name": "EXHALE", "start": 2, "end": 2, "description": "Recovery"},
        ]
        gaps = analyze_gaps(tracks, sections, goal="Arc playlist")
        assert any("transition" in g.gap_type for g in gaps)

    def test_no_gaps_when_sections_filled(self) -> None:
        tracks = [_track(i, emotional_intensity=0.5) for i in range(5)]
        sections = [
            {"name": "OPENING", "start": 1, "end": 3, "description": "Setup"},
            {"name": "CLOSE", "start": 4, "end": 5, "description": "End"},
        ]
        gaps = analyze_gaps(tracks, sections, goal="Balanced")
        # Sections are adequately filled (5 tracks for 5 positions)
        thin_gaps = [g for g in gaps if g.gap_type == "thin_section"]
        assert len(thin_gaps) == 0
