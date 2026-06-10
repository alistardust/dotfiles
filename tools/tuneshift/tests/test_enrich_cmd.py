"""Tests for the enrich command."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from tuneshift.commands.enrich_cmd import handle_enrich
from tuneshift.db import Database
from tuneshift.models import PlatformMapping, Track


def _setup_playlist_with_mapping(db: Database) -> tuple[int, int]:
    """Create a playlist with one track that has a platform mapping."""
    playlist_id = db.create_playlist("Test Playlist")
    track = Track(title="Suffragette City", artist="David Bowie", album="Ziggy Stardust")
    track_id = db.add_track(track)
    db.add_track_to_playlist(playlist_id, track_id, 1)
    db.upsert_platform_mapping(
        PlatformMapping(
            track_id=track_id,
            platform="tidal",
            platform_track_id="12345",
        )
    )
    return playlist_id, track_id


class TestHandleEnrich:
    def test_enriches_track_metadata(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        playlist_id, track_id = _setup_playlist_with_mapping(db)

        mock_client = MagicMock()
        mock_client.load_session.return_value = True
        mock_client.get_track_metadata.return_value = {"tempo": 143.0, "key": "A"}

        args = SimpleNamespace(playlist="Test Playlist", platform="tidal")
        with patch("tuneshift.commands.ingest_cmd._load_client", return_value=mock_client):
            result = handle_enrich(args, db)

        assert result == 0
        track = db.get_playlist_tracks(playlist_id)[0]
        assert track.tempo == 143.0
        assert track.key == "A"

    def test_skips_already_enriched(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        playlist_id, track_id = _setup_playlist_with_mapping(db)
        db.update_track_metadata(track_id, {"tempo": 120.0, "key": "C"})

        mock_client = MagicMock()
        mock_client.load_session.return_value = True

        args = SimpleNamespace(playlist="Test Playlist", platform="tidal")
        with patch("tuneshift.commands.ingest_cmd._load_client", return_value=mock_client):
            result = handle_enrich(args, db)

        assert result == 0
        # get_track_metadata should not have been called
        mock_client.get_track_metadata.assert_not_called()

    def test_playlist_not_found(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(playlist="Nonexistent", platform="tidal")
        assert handle_enrich(args, db) == 1

    def test_not_logged_in(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        db.create_playlist("Test")
        # need at least a playlist to get past the not-found check
        # hack: rename via direct SQL
        mock_client = MagicMock()
        mock_client.load_session.return_value = False

        args = SimpleNamespace(playlist="Test", platform="tidal")
        with patch("tuneshift.commands.ingest_cmd._load_client", return_value=mock_client):
            result = handle_enrich(args, db)
        assert result == 1
