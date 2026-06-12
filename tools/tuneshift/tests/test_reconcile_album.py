"""Tests for album tracklist reconciliation strategy."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult, AlbumResult
from tuneshift.reconcile import reconcile_track


@pytest.fixture
def db_with_album_track(tmp_path: Path) -> tuple[Database, int]:
    """Create a database with a track that has album info."""
    db = Database(tmp_path / "test.db")
    track = Track(
        title="Revolution!",
        artist="Left at London",
        album="Transgender Street Legend, Vol. 2",
        duration_seconds=195
    )
    track_id = db.add_track(track)
    return db, track_id


@pytest.fixture
def mock_album_client():
    """Create a mock platform client that supports album search."""
    client = MagicMock()
    client.platform_name = "test_platform"
    return client


class TestAlbumGraphReconciliation:
    """Tests for album tracklist search strategy."""

    def test_finds_track_via_album_tracklist(
        self, db_with_album_track: tuple[Database, int], mock_album_client: MagicMock
    ) -> None:
        """When direct search fails, album tracklist search succeeds."""
        db, track_id = db_with_album_track

        # Direct search returns nothing
        mock_album_client.search_isrc.return_value = None
        mock_album_client.search_track.return_value = []

        # Album search finds the album
        mock_album_client.search_album.return_value = [
            AlbumResult(
                platform_id="alb1",
                title="Transgender Street Legend, Vol. 2",
                artist="Left at London"
            )
        ]

        # Album tracklist contains our track
        mock_album_client.get_album_tracks.return_value = [
            TrackResult(
                platform_id="trk99",
                title="Revolution!",
                artist="Left at London",
                album="Transgender Street Legend, Vol. 2",
                duration_seconds=195
            ),
        ]

        result = reconcile_track(db, track_id, mock_album_client)
        assert result.platform_track_id == "trk99"
        assert result.match_type == "album_tracklist"

    def test_album_tracklist_fuzzy_matches_title(
        self, db_with_album_track: tuple[Database, int], mock_album_client: MagicMock
    ) -> None:
        """Album tracklist strategy fuzzy-matches track titles."""
        db, track_id = db_with_album_track

        # Direct search returns nothing
        mock_album_client.search_isrc.return_value = None
        mock_album_client.search_track.return_value = []

        # Album search finds the album
        mock_album_client.search_album.return_value = [
            AlbumResult(
                platform_id="alb1",
                title="Transgender Street Legend, Vol. 2",
                artist="Left at London"
            )
        ]

        # Album tracklist has slightly different title formatting
        mock_album_client.get_album_tracks.return_value = [
            TrackResult(
                platform_id="trk99",
                title="Revolution! (Album Version)",
                artist="Left at London",
                album="Transgender Street Legend, Vol. 2",
                duration_seconds=195
            ),
        ]

        result = reconcile_track(db, track_id, mock_album_client)
        assert result.platform_track_id == "trk99"
        assert result.match_type == "album_tracklist"

    def test_album_tracklist_returns_empty_without_album(
        self, tmp_path: Path, mock_album_client: MagicMock
    ) -> None:
        """Album tracklist strategy returns nothing if track has no album."""
        db = Database(tmp_path / "test.db")
        track = Track(
            title="No Album Track",
            artist="Some Artist",
            # No album set
        )
        track_id = db.add_track(track)

        # Direct searches return nothing
        mock_album_client.search_isrc.return_value = None
        mock_album_client.search_track.return_value = []

        result = reconcile_track(db, track_id, mock_album_client)
        assert result.confidence == "not_found"
        mock_album_client.search_album.assert_not_called()

    def test_album_tracklist_handles_search_failure(
        self, db_with_album_track: tuple[Database, int], mock_album_client: MagicMock
    ) -> None:
        """Album tracklist strategy gracefully handles search failures."""
        db, track_id = db_with_album_track

        # Direct search returns nothing
        mock_album_client.search_isrc.return_value = None
        mock_album_client.search_track.return_value = []

        # Album search returns empty (album not found)
        mock_album_client.search_album.return_value = []

        result = reconcile_track(db, track_id, mock_album_client)
        assert result.confidence == "not_found"

    def test_album_tracklist_prefers_standard_edition(
        self, db_with_album_track: tuple[Database, int], mock_album_client: MagicMock
    ) -> None:
        """Album tracklist strategy prefers standard editions."""
        db, track_id = db_with_album_track

        # Direct search returns nothing
        mock_album_client.search_isrc.return_value = None
        mock_album_client.search_track.return_value = []

        # Album search returns multiple editions
        mock_album_client.search_album.return_value = [
            AlbumResult(
                platform_id="alb_deluxe",
                title="Transgender Street Legend, Vol. 2 (Deluxe)",
                artist="Left at London"
            ),
            AlbumResult(
                platform_id="alb_std",
                title="Transgender Street Legend, Vol. 2",
                artist="Left at London"
            ),
        ]

        # Track found in standard edition
        mock_album_client.get_album_tracks.return_value = [
            TrackResult(
                platform_id="trk99",
                title="Revolution!",
                artist="Left at London",
                album="Transgender Street Legend, Vol. 2",
                duration_seconds=195
            ),
        ]

        result = reconcile_track(db, track_id, mock_album_client)
        # Verify that get_album_tracks was called, indicating album search succeeded
        assert mock_album_client.get_album_tracks.called
        # Verify the track was found via album search
        assert result.platform_track_id == "trk99"
        # Verify one of the calls was with the standard edition (first album after sorting)
        call_args_list = [call[0][0] for call in mock_album_client.get_album_tracks.call_args_list]
        assert "alb_std" in call_args_list
