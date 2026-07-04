"""Tests for the add command with platform sync."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from tuneshift.commands.add_cmd import handle_add
from tuneshift.db import Database
from tuneshift.models import Track


class TestHandleAdd:
    def test_adds_track_to_new_playlist(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(
            playlist="New Playlist",
            title="Killer Queen",
            artist="Queen",
            album="Sheer Heart Attack",
        )

        result = handle_add(args, db)

        assert result == 0
        pl = db.find_playlist_by_name("New Playlist")
        assert pl is not None
        tracks = db.get_playlist_tracks(pl.id)
        assert len(tracks) == 1
        assert tracks[0].title == "Killer Queen"
        assert tracks[0].artist == "Queen"

    def test_adds_to_existing_playlist(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        # Create playlist with one track
        pid = db.create_playlist("Existing")
        t = Track(title="Song 1", artist="Artist 1")
        tid = db.add_track(t)
        db.add_track_to_playlist(pid, tid, 1)

        args = SimpleNamespace(
            playlist="Existing",
            title="Song 2",
            artist="Artist 2",
            album=None,
        )
        handle_add(args, db)

        tracks = db.get_playlist_tracks(pid)
        assert len(tracks) == 2
        assert tracks[1].title == "Song 2"

    def test_deduplicates_existing_track(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        t = Track(title="Existing Song", artist="Some Artist", album="Album")
        existing_id = db.add_track(t)

        args = SimpleNamespace(
            playlist="New",
            title="Existing Song",
            artist="Some Artist",
            album="Album",
        )
        handle_add(args, db)

        pl = db.find_playlist_by_name("New")
        tracks = db.get_playlist_tracks(pl.id)
        assert tracks[0].id == existing_id

    def test_appends_at_correct_position(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        pid = db.create_playlist("Ordered")
        for i in range(3):
            t = Track(title=f"Song {i}", artist="A")
            tid = db.add_track(t)
            db.add_track_to_playlist(pid, tid, i + 1)

        args = SimpleNamespace(
            playlist="Ordered",
            title="Song 3",
            artist="A",
            album=None,
        )
        handle_add(args, db)

        tracks = db.get_playlist_tracks(pid)
        assert len(tracks) == 4
        assert tracks[3].title == "Song 3"

    def test_syncs_to_linked_platform(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        pid = db.create_playlist("Synced")
        db.link_platform_playlist(pid, "tidal", "tidal-pl-123")

        mock_client = MagicMock()
        mock_client.load_session.return_value = True
        mock_client.search_track.return_value = [{"id": "t-999", "title": "KQ", "artist": "Queen"}]

        mock_reconcile = MagicMock()
        mock_reconcile.return_value = MagicMock(platform_track_id="t-999", audit=None)

        with patch("tuneshift.commands.ingest_cmd._load_client", return_value=mock_client), \
             patch("tuneshift.reconcile.reconcile_track", mock_reconcile):
            args = SimpleNamespace(
                playlist="Synced",
                title="Killer Queen",
                artist="Queen",
                album=None,
            )
            handle_add(args, db)

        mock_client.add_tracks.assert_called_once_with("tidal-pl-123", ["t-999"])


def test_add_with_replace_swaps_track(tmp_path: Path) -> None:
    """--replace removes old track and puts new one at same position."""
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Test")
    old_track = Track(title="American Dream", artist="Shea Diamond", album="Seen")
    old_id = db.add_track(old_track)
    db.add_track_to_playlist(playlist_id, old_id, position=0)
    other = Track(title="Other", artist="Other")
    other_id = db.add_track(other)
    db.add_track_to_playlist(playlist_id, other_id, position=1)
    db.set_pin(playlist_id, old_id, pin_type="opener")

    args = SimpleNamespace(
        playlist="Test",
        title="I Am America",
        artist="Shea Diamond",
        album="Seen",
        replace="American Dream",
    )
    result = handle_add(args, db)
    assert result == 0

    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 2
    assert tracks[0].title == "I Am America"
    assert tracks[1].title == "Other"

    pins = db.get_pins(playlist_id)
    assert len(pins) == 1
    assert pins[0].track_id == tracks[0].id
    assert pins[0].pin_type == "opener"
