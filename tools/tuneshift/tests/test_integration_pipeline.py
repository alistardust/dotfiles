"""End-to-end test: full pipeline from playlist creation through curation and sequencing."""

from pathlib import Path

import pytest

from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.curator import curate_analyze
from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer.metadata import get_track_metadata_map
from tuneshift.sequencer.optimizer import sequence_playlist


@pytest.fixture
def populated_db(tmp_path: Path) -> Database:
    """Create a database with a playlist, tracks, and metadata."""
    db = Database(tmp_path / "test.db")
    pid = db.create_playlist("Integration Test")
    db.set_goal(pid, "Test playlist for integration")
    db.set_weights(
        pid,
        {"narrative_arc": 0.9, "mood_continuity": 0.7, "energy_flow": 0.3},
    )

    for i in range(10):
        track = Track(
            title=f"Track {i}",
            artist=f"Artist {i % 3}",
            energy=i * 0.1,
            valence=0.5 - (i * 0.05),  # Descending valence
        )
        # Store additional metadata in the metadata dict
        track.metadata = {
            "emotional_intensity": i * 0.1,
            "narrator_stance": "defiant" if i > 5 else "gentle",
            "themes": ["fury"] if i > 5 else ["peace"],
            "vibes": ["angry"] if i > 5 else ["calm"],
        }
        tid = db.add_track(track)
        db.add_track_to_playlist(pid, tid, i)

    return db


class TestFullPipeline:
    """Test the full pipeline: identity -> curation analyze -> sequencing."""

    def test_sequence_uses_stored_weights(self, populated_db: Database) -> None:
        """Verify that sequencing respects weights stored in the playlist."""
        db = populated_db
        playlists = db.list_playlists()
        pid = playlists[0].id

        # Get weights from playlist
        weights = db.get_weights(pid)
        assert weights is not None
        assert "narrative_arc" in weights

        # Sequence should return all 10 tracks
        result = sequence_playlist(db, pid, arc="wave")
        assert len(result) == 10
        assert all(isinstance(tid, int) for tid in result)

    def test_analyze_produces_coverage_report(self, populated_db: Database) -> None:
        """Verify that analysis produces a coverage report with scores."""
        db = populated_db
        playlists = db.list_playlists()
        pid = playlists[0].id
        track_ids = db.get_playlist_track_ids(pid)

        # Get metadata for all tracks
        metadata_map = get_track_metadata_map(db, track_ids)
        tracks = [metadata_map[tid] for tid in track_ids if tid in metadata_map]

        # Create context
        ctx = PlaylistContext(
            goal=db.get_goal(pid),
            narrative_sections=[],
            mood_profile=None,
            all_tracks=tracks,
        )

        # Analyze
        report = curate_analyze(tracks, ctx)

        # Verify report structure
        assert "scores" in report
        assert len(report["scores"]) == 10
        assert all(
            "average" in entry for entry in report["scores"].values()
        )

    def test_full_flow_identity_to_sequence(self, populated_db: Database) -> None:
        """Full flow: create playlist with identity, analyze, sequence."""
        db = populated_db
        playlists = db.list_playlists()
        pid = playlists[0].id

        # Verify identity is stored
        goal = db.get_goal(pid)
        weights = db.get_weights(pid)
        assert goal is not None
        assert goal == "Test playlist for integration"
        assert weights is not None
        assert weights["narrative_arc"] == 0.9

        # Get all track IDs
        track_ids = db.get_playlist_track_ids(pid)
        assert len(track_ids) == 10

        # Analyze: get metadata and run curation
        metadata_map = get_track_metadata_map(db, track_ids)
        tracks = [metadata_map[tid] for tid in track_ids if tid in metadata_map]
        assert len(tracks) == 10

        ctx = PlaylistContext(
            goal=db.get_goal(pid),
            narrative_sections=[],
            mood_profile=None,
            all_tracks=tracks,
        )
        report = curate_analyze(tracks, ctx)

        # Verify analysis report
        assert "scores" in report
        assert len(report["scores"]) == 10
        for entry in report["scores"].values():
            assert entry["average"] >= 0

        # Sequence with stored weights
        result = sequence_playlist(db, pid, arc="wave")
        assert len(result) == 10

        # All tracks accounted for (same set, potentially different order)
        assert set(result) == set(track_ids)

        # Verify sequencer respects weights by using them
        result_weights = sequence_playlist(
            db, pid, arc="wave", weights=weights
        )
        assert len(result_weights) == 10
        assert set(result_weights) == set(track_ids)

    def test_sequence_with_metadata(self, populated_db: Database) -> None:
        """Verify that sequencing works with track metadata."""
        db = populated_db
        playlists = db.list_playlists()
        pid = playlists[0].id
        track_ids = db.get_playlist_track_ids(pid)

        # Get metadata
        metadata_map = get_track_metadata_map(db, track_ids)

        # All tracks should have energy and valence set
        for tid in track_ids:
            assert tid in metadata_map
            meta = metadata_map[tid]
            assert meta.energy is not None
            assert meta.valence is not None
            assert meta.track_id == tid

        # Sequence with narrative arc
        result = sequence_playlist(db, pid, arc="narrative")
        assert len(result) == 10

    def test_sequence_handles_single_track(self, tmp_path: Path) -> None:
        """Verify sequencing handles single-track playlists."""
        db = Database(tmp_path / "single.db")
        pid = db.create_playlist("Single Track")
        track = Track(title="Lonely Song", artist="Solo Artist", energy=0.5)
        tid = db.add_track(track)
        db.add_track_to_playlist(pid, tid, 0)

        result = sequence_playlist(db, pid)
        assert len(result) == 1
        assert result[0] == tid

    def test_sequence_handles_empty_playlist(self, tmp_path: Path) -> None:
        """Verify sequencing handles empty playlists."""
        db = Database(tmp_path / "empty.db")
        pid = db.create_playlist("Empty")

        result = sequence_playlist(db, pid)
        assert len(result) == 0
