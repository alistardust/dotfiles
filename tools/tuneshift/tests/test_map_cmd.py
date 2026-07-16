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


def test_map_clears_quarantine_and_sets_verified_tier(db_with_playlist_and_track):
    """FEAT-5: a user-approved map self-heals a quarantined/tier-less track."""
    db, _playlist_id, track_id = db_with_playlist_and_track
    # Simulate the resolver having quarantined this track.
    db.enqueue_resolution(track_id)
    db.set_resolution_state(track_id, "quarantined", last_error="no_confident_match")
    db.set_track_fields(
        track_id,
        {"quarantine_state": "unresolved", "quarantine_reason": "no_confident_match"},
        source="test",
    )

    args = argparse.Namespace(
        playlist="Trans Wrath", title="Louder",
        tidal="48931", ytmusic=None, verify=False,
    )
    assert handle_map(args, db) == 0

    # Quarantine cleared on both sources of truth.
    assert db.get_track(track_id).quarantine_state is None
    assert db.get_resolution_queue_state(track_id) == "resolved"
    # A user-approved exact map is authoritative identity -> VERIFIED.
    tier, score, _ = db.get_resolution_state(track_id)
    assert tier == "VERIFIED"
    assert score == 1.0


def test_map_verify_hydrates_identity_fields(db_with_playlist_and_track):
    """FEAT-5: --verify map also fills NULL identity fields from the result."""
    db, playlist_id, _track_id = db_with_playlist_and_track
    # A track with NULL album/isrc/duration so the fill-NULL hydration is visible.
    bare_id = db.add_track(Track(title="Fighter", artist="Christina Aguilera"))
    db.add_track_to_playlist(playlist_id, bare_id, position=1)

    client = MagicMock()
    client.load_session.return_value = True
    client.get_track.return_value = TrackResult(
        platform_id="48931", title="Fighter", artist="Christina Aguilera",
        album="Stripped", duration_seconds=246, isrc="USRC10300123",
    )
    args = argparse.Namespace(
        playlist="Trans Wrath", title="Fighter",
        tidal="48931", ytmusic=None, verify=True,
    )
    with patch("tuneshift.commands.map_cmd._load_client", return_value=client):
        assert handle_map(args, db) == 0

    refreshed = db.get_track(bare_id)
    assert refreshed.album == "Stripped"
    assert refreshed.isrc == "USRC10300123"
    assert refreshed.duration_seconds == 246
    tier, _score, _ = db.get_resolution_state(bare_id)
    assert tier == "VERIFIED"


def test_map_refetches_catalog_with_refresh(db_with_playlist_and_track, monkeypatch):
    """A map writes a (possibly changed) Tidal mapping, so catalog capture must
    refetch (refresh=True) instead of reusing metadata cached for a prior id."""
    db, playlist_id, track_id = db_with_playlist_and_track
    seen = {}

    def fake_capture(db_, tid, platform, pid, *, client=None, refresh=False):
        seen["refresh"] = refresh
        return []

    monkeypatch.setattr(
        "tuneshift.library.enrichment.capture_tidal_catalog", fake_capture
    )
    mock_client = MagicMock()
    mock_client.load_session.return_value = True

    args = argparse.Namespace(
        playlist="Trans Wrath", title="Louder", tidal="48931",
        ytmusic=None, verify=False,
    )
    with patch("tuneshift.commands.map_cmd._load_client", return_value=mock_client):
        rc = handle_map(args, db)

    assert rc == 0
    assert seen.get("refresh") is True
