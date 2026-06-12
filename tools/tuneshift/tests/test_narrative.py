"""Tests for narrative system: parsing, CLI command, and intent integration."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer.intent import (
    _parse_narrative_climax,
    _parse_narrative_sections,
)
from tuneshift.sequencer.metadata import TrackMetadata


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


def _make_track_metadata(track_id: int, title: str = "Track") -> TrackMetadata:
    """Create a minimal TrackMetadata for testing."""
    return TrackMetadata(
        track_id=track_id,
        title=f"{title} {track_id}",
        artist="Artist",
    )


class TestParseNarrativeSections:
    def test_basic_section_parsing(self) -> None:
        narrative = """OPENING (1-2): The setup.
BUILD (3-8): Rising tension.
WRATH (11-18): Peak fury.
ANTHEM (26): Final track."""
        result = _parse_narrative_sections(narrative, track_count=30)
        # Position 1 is index 0, excluded by 0 < start check
        # Position 3 is index 2, 11 is index 10, 26 is index 25
        assert 2 in result
        assert 10 in result
        assert 25 in result

    def test_excludes_out_of_range(self) -> None:
        narrative = "LATE (50-60): Beyond playlist length."
        result = _parse_narrative_sections(narrative, track_count=30)
        assert result == []

    def test_empty_narrative(self) -> None:
        result = _parse_narrative_sections("", track_count=10)
        assert result == []

    def test_no_matching_patterns(self) -> None:
        result = _parse_narrative_sections("Just some text about the playlist.", track_count=10)
        assert result == []


class TestParseNarrativeClimax:
    def test_identifies_wrath_section(self) -> None:
        narrative = "WRATH (3-5): Fury section."
        tracks = [_make_track_metadata(i) for i in range(10)]
        result = _parse_narrative_climax(narrative, tracks)
        # Positions 3-5 -> indices 2, 3, 4
        assert tracks[2].track_id in result
        assert tracks[3].track_id in result
        assert tracks[4].track_id in result

    def test_identifies_anthem_section(self) -> None:
        narrative = "ANTHEM (8-9): Closing anthem."
        tracks = [_make_track_metadata(i) for i in range(10)]
        result = _parse_narrative_climax(narrative, tracks)
        # Positions 8-9 -> indices 7, 8
        assert tracks[7].track_id in result
        assert tracks[8].track_id in result

    def test_bounds_check_negative_position(self) -> None:
        """Position 0 (user error) should not produce negative index access."""
        narrative = "WRATH (0-3): Bad range."
        tracks = [_make_track_metadata(i) for i in range(5)]
        result = _parse_narrative_climax(narrative, tracks)
        # Index -1 should be excluded by 0 <= i check
        assert tracks[-1].track_id not in result
        # Valid indices 0, 1, 2 should be included
        assert tracks[0].track_id in result
        assert tracks[1].track_id in result
        assert tracks[2].track_id in result

    def test_bounds_check_beyond_track_count(self) -> None:
        narrative = "FURY (4-20): Big section."
        tracks = [_make_track_metadata(i) for i in range(6)]
        result = _parse_narrative_climax(narrative, tracks)
        # Should not crash, capped at len(tracks)
        assert len(result) <= len(tracks)

    def test_fallback_to_metadata_when_no_climax_keywords(self) -> None:
        narrative = "OPENING (1-3): Introduction.\nBUILD (4-6): Rising."
        tracks = [_make_track_metadata(i) for i in range(8)]
        # No climax keywords, should fall back to metadata-based
        result = _parse_narrative_climax(narrative, tracks)
        # Result comes from _infer_climax_from_metadata (returns list)
        assert isinstance(result, list)


class TestNarrativeDB:
    def test_set_and_get_narrative(self, db: Database) -> None:
        playlist_id = db.create_playlist("Test Playlist")
        db.set_narrative(playlist_id, "OPENING (1-3): The beginning.")
        result = db.get_narrative(playlist_id)
        assert result == "OPENING (1-3): The beginning."

    def test_get_narrative_returns_none_when_unset(self, db: Database) -> None:
        playlist_id = db.create_playlist("Empty")
        result = db.get_narrative(playlist_id)
        assert result is None

    def test_clear_narrative(self, db: Database) -> None:
        playlist_id = db.create_playlist("Clear Test")
        db.set_narrative(playlist_id, "Some narrative")
        db.set_narrative(playlist_id, None)
        result = db.get_narrative(playlist_id)
        assert result is None


class TestConfidenceFieldMapping:
    """Verify that 'confidence' from LLM is stored as 'classification_confidence'."""

    def test_confidence_remapped_on_store(self, db: Database) -> None:
        playlist_id = db.create_playlist("Confidence Test")
        track = Track(title="Song", artist="Artist")
        track_id = db.add_track(track)
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        # Simulate LLM response with "confidence" field
        db.update_track_metadata(track_id, {
            "confidence": 0.85,
            "emotional_intensity": 0.7,
            "narrator_stance": "defiant",
        })

        stored = db.get_track(track_id)
        assert stored.metadata["classification_confidence"] == 0.85
        assert "confidence" not in stored.metadata


class TestEnrichClassificationGuard:
    """Verify that 0.0 emotional_intensity is not treated as unclassified."""

    def test_zero_intensity_not_reclassified(self, db: Database) -> None:
        playlist_id = db.create_playlist("Zero Test")
        track = Track(title="Calm", artist="Artist")
        track_id = db.add_track(track)
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        db.update_track_metadata(track_id, {
            "emotional_intensity": 0.0,
            "narrator_stance": "peaceful",
        })

        stored = db.get_track(track_id)
        meta = stored.metadata or {}
        # Both fields are set (not None), so this track should NOT be reclassified
        assert meta.get("narrator_stance") is not None
        assert meta.get("emotional_intensity") is not None
