"""Tests for reconcile module (TDD)."""
import json
from pathlib import Path

import pytest

from tidal_importer.client import TrackResult
from tidal_importer.reconcile import (
    SourceTrack,
    ReconciledTrack,
    parse_csv,
    reconcile_track,
    reconcile_playlist,
    save_reconciled,
    load_reconciled,
)
from tests.conftest import FakeTidalClient


class TestParseCsv:
    """Test CSV parsing."""

    def test_parses_valid_csv(self, tmp_path):
        """Parse standard Soundiiz CSV with all fields."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            "title,artist,album\n"
            "Mr. Tambourine Man,The Byrds,Mr. Tambourine Man\n"
            "Eight Miles High,The Byrds,Fifth Dimension\n"
        )
        tracks = parse_csv(csv_path)
        assert len(tracks) == 2
        assert tracks[0].title == "Mr. Tambourine Man"
        assert tracks[0].artist == "The Byrds"
        assert tracks[0].album == "Mr. Tambourine Man"
        assert tracks[0].row_number == 1
        assert tracks[1].title == "Eight Miles High"
        assert tracks[1].row_number == 2

    def test_handles_missing_album(self, tmp_path):
        """Handle empty album field gracefully."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            "title,artist,album\n"
            "Track A,Artist A,\n"
            "Track B,Artist B,Album B\n"
        )
        tracks = parse_csv(csv_path)
        assert len(tracks) == 2
        assert tracks[0].album is None
        assert tracks[1].album == "Album B"

    def test_preserves_row_order(self, tmp_path):
        """Row numbers must match input order."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            "title,artist,album\n"
            "Track 1,Artist 1,Album 1\n"
            "Track 2,Artist 2,Album 2\n"
            "Track 3,Artist 3,Album 3\n"
        )
        tracks = parse_csv(csv_path)
        assert [t.row_number for t in tracks] == [1, 2, 3]

    def test_empty_csv_returns_empty(self, tmp_path):
        """Empty CSV (header only) returns empty list."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text("title,artist,album\n")
        tracks = parse_csv(csv_path)
        assert tracks == []

    def test_handles_quoted_fields(self, tmp_path):
        """Handle quoted CSV fields with commas."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            'title,artist,album\n'
            '"Track, with comma","Artist, name",Album\n'
        )
        tracks = parse_csv(csv_path)
        assert len(tracks) == 1
        assert tracks[0].title == "Track, with comma"
        assert tracks[0].artist == "Artist, name"


class TestReconcileTrack:
    """Test single track reconciliation."""

    def test_high_confidence_match(self):
        """Exact match returns high confidence."""
        client = FakeTidalClient(search_results={
            '"Mr. Tambourine Man" The Byrds': [
                TrackResult(
                    tidal_id=123,
                    title="Mr. Tambourine Man",
                    artist="The Byrds",
                    album="Mr. Tambourine Man"
                ),
            ]
        })
        source = SourceTrack(
            title="Mr. Tambourine Man",
            artist="The Byrds",
            album="Mr. Tambourine Man",
            row_number=1,
        )
        result = reconcile_track(source, client)
        assert result.status == "matched"
        assert result.confidence == "high"
        assert result.tidal_id == 123
        assert result.score >= 80

    def test_ambiguous_match(self):
        """Multiple similar results return ambiguous with alternatives."""
        client = FakeTidalClient(search_results={
            '"Mr. Tambourine Man" The Byrds': [
                TrackResult(
                    tidal_id=123,
                    title="Mr. Tambourine Man",
                    artist="The Byrds",
                    album="Mr. Tambourine Man"
                ),
                TrackResult(
                    tidal_id=456,
                    title="Mr. Tambourine Man",
                    artist="The Byrds",
                    album="Mr. Tambourine Man (Remastered)"
                ),
            ]
        })
        source = SourceTrack(
            title="Mr. Tambourine Man",
            artist="The Byrds",
            album=None,
            row_number=1,
        )
        result = reconcile_track(source, client)
        assert result.status == "ambiguous"
        assert result.confidence == "ambiguous"
        assert len(result.alternatives) <= 3
        assert len(result.alternatives) >= 1

    def test_not_found(self):
        """No results or low scores return not_found."""
        client = FakeTidalClient(search_results={
            '"Mr. Tambourine Man" The Byrds': []
        })
        source = SourceTrack(
            title="Mr. Tambourine Man",
            artist="The Byrds",
            album=None,
            row_number=1,
        )
        result = reconcile_track(source, client)
        assert result.status == "not_found"
        assert result.confidence == "not_found"
        assert result.tidal_id is None

    def test_already_in_playlist(self):
        """Match found in existing_track_ids returns already_in_playlist."""
        client = FakeTidalClient(search_results={
            '"Mr. Tambourine Man" The Byrds': [
                TrackResult(
                    tidal_id=123,
                    title="Mr. Tambourine Man",
                    artist="The Byrds",
                    album="Mr. Tambourine Man"
                ),
            ]
        })
        source = SourceTrack(
            title="Mr. Tambourine Man",
            artist="The Byrds",
            album="Mr. Tambourine Man",
            row_number=1,
        )
        result = reconcile_track(source, client, existing_track_ids={123, 456})
        assert result.status == "already_in_playlist"
        assert result.tidal_id == 123

    def test_prefers_remaster_on_tie(self):
        """When scores tie, prefer remastered version."""
        client = FakeTidalClient(search_results={
            '"Track" Artist': [
                TrackResult(
                    tidal_id=100,
                    title="Track",
                    artist="Artist",
                    album="Album"
                ),
                TrackResult(
                    tidal_id=200,
                    title="Track",
                    artist="Artist",
                    album="Album (Remastered)"
                ),
            ]
        })
        source = SourceTrack(
            title="Track",
            artist="Artist",
            album=None,
            row_number=1,
        )
        result = reconcile_track(source, client)
        # Both should score identically on title+artist
        # but remaster should be selected
        assert result.tidal_id == 200
        assert "Remastered" in result.tidal_album

    def test_search_error_handled(self):
        """Search errors are caught and return not_found."""
        client = FakeTidalClient(error_on_search=RuntimeError("API error"))
        source = SourceTrack(
            title="Track",
            artist="Artist",
            album=None,
            row_number=1,
        )
        result = reconcile_track(source, client)
        assert result.status == "not_found"
        assert result.confidence == "not_found"


class TestReconcilePlaylist:
    """Test full playlist reconciliation."""

    def test_reconciles_all_tracks(self, tmp_path):
        """Reconcile all tracks from CSV."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            "title,artist,album\n"
            "Track A,Artist A,Album A\n"
            "Track B,Artist B,Album B\n"
        )
        client = FakeTidalClient(search_results={
            '"Track A" Artist A': [
                TrackResult(tidal_id=1, title="Track A", artist="Artist A", album="Album A")
            ],
            '"Track B" Artist B': [
                TrackResult(tidal_id=2, title="Track B", artist="Artist B", album="Album B")
            ],
        })
        results = reconcile_playlist(csv_path, client)
        assert len(results) == 2
        assert results[0].source.title == "Track A"
        assert results[1].source.title == "Track B"

    def test_with_existing_playlist(self, tmp_path):
        """Skip tracks already in existing playlist."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            "title,artist,album\n"
            "Track A,Artist A,Album A\n"
            "Track B,Artist B,Album B\n"
        )
        # Create a fake playlist with Track A already in it
        client = FakeTidalClient(search_results={
            '"Track A" Artist A': [
                TrackResult(tidal_id=1, title="Track A", artist="Artist A", album="Album A")
            ],
            '"Track B" Artist B': [
                TrackResult(tidal_id=2, title="Track B", artist="Artist B", album="Album B")
            ],
        })
        playlist_info = client.create_playlist("Existing Playlist")
        client.add_tracks(playlist_info.playlist_id, [1])  # Track A already added
        
        results = reconcile_playlist(csv_path, client, existing_playlist_id=playlist_info.playlist_id)
        assert len(results) == 2
        # Track A should be marked as already_in_playlist
        assert results[0].status == "already_in_playlist"
        assert results[0].tidal_id == 1
        # Track B should be newly matched
        assert results[1].status == "matched"
        assert results[1].tidal_id == 2

    def test_progress_callback_called(self, tmp_path):
        """Progress callback invoked after each track."""
        csv_path = tmp_path / "tracks.csv"
        csv_path.write_text(
            "title,artist,album\n"
            "Track A,Artist A,Album A\n"
            "Track B,Artist B,Album B\n"
        )
        client = FakeTidalClient(search_results={
            '"Track A" Artist A': [
                TrackResult(tidal_id=1, title="Track A", artist="Artist A", album="Album A")
            ],
            '"Track B" Artist B': [
                TrackResult(tidal_id=2, title="Track B", artist="Artist B", album="Album B")
            ],
        })
        
        progress_calls = []
        
        def callback(current: int, total: int):
            progress_calls.append((current, total))
        
        reconcile_playlist(csv_path, client, progress_callback=callback)
        assert progress_calls == [(1, 2), (2, 2)]


class TestSaveAndLoad:
    """Test JSON persistence."""

    def test_roundtrip(self, tmp_path):
        """Save and load should preserve data."""
        tracks = [
            ReconciledTrack(
                source=SourceTrack(
                    title="Track A",
                    artist="Artist A",
                    album="Album A",
                    row_number=1,
                ),
                status="matched",
                confidence="high",
                tidal_id=123,
                tidal_title="Track A",
                tidal_artist="Artist A",
                tidal_album="Album A",
                score=95,
                alternatives=[],
            ),
            ReconciledTrack(
                source=SourceTrack(
                    title="Track B",
                    artist="Artist B",
                    album=None,
                    row_number=2,
                ),
                status="not_found",
                confidence="not_found",
                tidal_id=None,
                tidal_title=None,
                tidal_artist=None,
                tidal_album=None,
                score=0,
                alternatives=[],
            ),
        ]
        
        output_path = tmp_path / "reconciled.json"
        save_reconciled(tracks, output_path)
        
        loaded = load_reconciled(output_path)
        assert len(loaded) == 2
        assert loaded[0].tidal_id == 123
        assert loaded[0].status == "matched"
        assert loaded[1].status == "not_found"

    def test_invalid_json_raises(self, tmp_path):
        """Invalid JSON raises ValueError."""
        json_path = tmp_path / "bad.json"
        json_path.write_text("{not valid json")
        
        with pytest.raises((ValueError, json.JSONDecodeError)):
            load_reconciled(json_path)

    def test_invalid_status_raises(self, tmp_path):
        """Invalid status enum raises ValueError."""
        json_path = tmp_path / "bad.json"
        json_path.write_text(json.dumps({
            "generated_at": "2024-01-01T00:00:00",
            "total": 1,
            "matched": 0,
            "ambiguous": 0,
            "not_found": 0,
            "already_in_playlist": 0,
            "tracks": [{
                "source": {
                    "title": "Track",
                    "artist": "Artist",
                    "album": None,
                    "row_number": 1,
                },
                "status": "invalid_status",
                "confidence": "high",
                "tidal_id": None,
                "tidal_title": None,
                "tidal_artist": None,
                "tidal_album": None,
                "score": 0,
                "alternatives": [],
            }]
        }))
        
        with pytest.raises(ValueError, match="status"):
            load_reconciled(json_path)
