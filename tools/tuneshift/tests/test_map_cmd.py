"""Tests for tuneshift map/unmap commands."""
import argparse
import pytest
from unittest.mock import MagicMock, patch

from tuneshift.commands.map_cmd import handle_map, handle_unmap
from tuneshift.db import Database
from tuneshift.models import Track, TrackResult


@pytest.fixture
def db_with_playlist_and_track(tmp_path):
    db = Database(tmp_path / "test.db")
    track = Track(title="Louder", artist="Big Freedia", album="3rd Ward Bounce")
    track_id = db.add_track(track)
    playlist_id = db.create_playlist("Trans Wrath")
    db.add_track_to_playlist(playlist_id, track_id, position=0)
    return db, playlist_id, track_id


def test_handle_map_stores_approved_mapping(db_with_playlist_and_track):
    """map command stores user-approved platform mapping."""
    db, playlist_id, track_id = db_with_playlist_and_track
    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal="122361821",
        ytmusic=None,
        verify=False,
    )
    result = handle_map(args, db)
    assert result == 0

    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping is not None
    assert mapping.platform_track_id == "122361821"
    assert mapping.user_approved is True


def test_handle_map_with_verify_checks_platform(db_with_playlist_and_track):
    """map --verify fetches track from platform before storing."""
    db, playlist_id, track_id = db_with_playlist_and_track
    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal="122361821",
        ytmusic=None,
        verify=True,
    )
    mock_client = MagicMock()
    mock_client.get_track.return_value = TrackResult(
        platform_id="122361821",
        title="Louder (feat. Icona Pop)",
        artist="Big Freedia",
        album="3rd Ward Bounce",
        duration_seconds=195,
    )
    mock_client.load_session.return_value = True

    with patch("tuneshift.commands.map_cmd._load_client", return_value=mock_client):
        result = handle_map(args, db)

    assert result == 0
    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping.platform_title == "Louder (feat. Icona Pop)"


def test_handle_map_verify_fails_on_invalid_id(db_with_playlist_and_track):
    """map --verify returns 1 if track not found on platform."""
    db, playlist_id, track_id = db_with_playlist_and_track
    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal="999999999",
        ytmusic=None,
        verify=True,
    )
    mock_client = MagicMock()
    mock_client.get_track.return_value = None
    mock_client.load_session.return_value = True

    with patch("tuneshift.commands.map_cmd._load_client", return_value=mock_client):
        result = handle_map(args, db)

    assert result == 1


def test_handle_unmap_clears_mapping(db_with_playlist_and_track):
    """unmap command removes platform mapping."""
    db, playlist_id, track_id = db_with_playlist_and_track
    db.set_platform_mapping(track_id, "tidal", "122361821", user_approved=True)

    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal=True,
        ytmusic=False,
    )
    result = handle_unmap(args, db)
    assert result == 0

    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping is None


def _map_args(**overrides):
    """Namespace with all map flags defaulted; override per test."""
    base = dict(
        playlist=None, title=None, track_id=None,
        tidal=None, ytmusic=None, verify=False, dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_handle_map_by_track_id_without_playlist(db_with_playlist_and_track):
    """map --track-id maps by canonical id with no playlist/title needed."""
    db, _playlist_id, track_id = db_with_playlist_and_track
    args = _map_args(track_id=track_id, tidal="122361821")

    result = handle_map(args, db)

    assert result == 0
    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping is not None
    assert mapping.platform_track_id == "122361821"
    assert mapping.user_approved is True


def test_handle_map_unknown_track_id_errors(db_with_playlist_and_track):
    """map --track-id with a nonexistent id fails cleanly, writes nothing."""
    db, _playlist_id, _track_id = db_with_playlist_and_track
    args = _map_args(track_id=999999, tidal="122361821")

    result = handle_map(args, db)

    assert result == 1


def test_handle_map_dry_run_does_not_write(db_with_playlist_and_track):
    """--dry-run reports the intended mapping but persists nothing."""
    db, _playlist_id, track_id = db_with_playlist_and_track
    args = _map_args(track_id=track_id, tidal="122361821", dry_run=True)

    result = handle_map(args, db)

    assert result == 0
    assert db.get_platform_mapping(track_id, "tidal") is None


def test_handle_map_verify_dry_run_checks_but_does_not_write(db_with_playlist_and_track):
    """--verify --dry-run performs the platform lookup but writes nothing."""
    db, _playlist_id, track_id = db_with_playlist_and_track
    args = _map_args(track_id=track_id, tidal="122361821", verify=True, dry_run=True)

    mock_client = MagicMock()
    mock_client.load_session.return_value = True
    mock_client.get_track.return_value = TrackResult(
        platform_id="122361821", title="Louder", artist="Big Freedia",
        album="3rd Ward Bounce", duration_seconds=195,
    )

    with patch("tuneshift.commands.map_cmd._load_client", return_value=mock_client):
        result = handle_map(args, db)

    assert result == 0
    mock_client.get_track.assert_called_once_with("122361821")
    assert db.get_platform_mapping(track_id, "tidal") is None


def test_handle_map_requires_track_selector(db_with_playlist_and_track):
    """Neither --track-id nor playlist+title supplied is an error."""
    db, _playlist_id, _track_id = db_with_playlist_and_track
    args = _map_args(tidal="122361821")

    result = handle_map(args, db)

    assert result == 1
