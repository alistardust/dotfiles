"""Database schema and CRUD tests for tuneshift."""

import sqlite3
from pathlib import Path

import pytest

from tuneshift.db import Database, get_default_db_path
from tuneshift.models import PlatformMapping, Track


def test_create_schema(tmp_db: Path) -> None:
    """Schema creates all expected tables."""
    Database(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "tracks" in tables
    assert "platform_tracks" in tables
    assert "playlists" in tables
    assert "playlist_tracks" in tables
    assert "platform_playlists" in tables
    assert "sync_log" in tables


def test_schema_idempotent(tmp_db: Path) -> None:
    """Creating DB twice does not error."""
    Database(tmp_db)
    Database(tmp_db)


def test_env_var_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TUNESHIFT_DB env var overrides default path."""
    custom_path = tmp_path / "custom.db"
    monkeypatch.setenv("TUNESHIFT_DB", str(custom_path))
    assert get_default_db_path() == custom_path


def test_insert_and_get_track(tmp_db: Path) -> None:
    db = Database(tmp_db)
    track = Track(title="Five Years", artist="David Bowie", album="Ziggy Stardust")
    track_id = db.insert_track(track)
    assert track_id > 0
    fetched = db.get_track(track_id)
    assert fetched is not None
    assert fetched.title == "Five Years"
    assert fetched.artist == "David Bowie"


def test_insert_playlist_and_tracks(tmp_db: Path) -> None:
    db = Database(tmp_db)
    first_track_id = db.insert_track(
        Track(title="Future Legend", artist="David Bowie", album="Diamond Dogs")
    )
    second_track_id = db.insert_track(
        Track(title="Diamond Dogs", artist="David Bowie", album="Diamond Dogs")
    )
    playlist_id = db.create_playlist("Diamond Dogs", "Bowie 1974")
    db.set_playlist_tracks(playlist_id, [first_track_id, second_track_id])
    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 2
    assert tracks[0].title == "Future Legend"
    assert tracks[1].title == "Diamond Dogs"


def test_upsert_platform_mapping(tmp_db: Path) -> None:
    db = Database(tmp_db)
    track_id = db.insert_track(Track(title="Heroes", artist="David Bowie"))
    mapping = PlatformMapping(
        track_id=track_id,
        platform="spotify",
        platform_track_id="spotify:track:abc",
        match_score=95,
    )
    db.upsert_platform_mapping(mapping)
    fetched = db.get_platform_mapping(track_id, "spotify")
    assert fetched is not None
    assert fetched.platform_track_id == "spotify:track:abc"


def test_find_track_by_identity(tmp_db: Path) -> None:
    db = Database(tmp_db)
    db.insert_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))
    found = db.find_track("Heroes", "David Bowie", "Heroes")
    assert found is not None
    assert found.title == "Heroes"


def test_find_track_not_found(tmp_db: Path) -> None:
    db = Database(tmp_db)
    found = db.find_track("Nonexistent", "Nobody", None)
    assert found is None


def test_list_playlists(tmp_db: Path) -> None:
    db = Database(tmp_db)
    db.create_playlist("Playlist A")
    db.create_playlist("Playlist B")
    playlists = db.list_playlists()
    assert len(playlists) == 2
    names = [playlist.name for playlist in playlists]
    assert "Playlist A" in names
    assert "Playlist B" in names


def test_remove_playlist_track_by_position(tmp_db: Path) -> None:
    db = Database(tmp_db)
    first_track_id = db.insert_track(Track(title="A", artist="X"))
    second_track_id = db.insert_track(Track(title="B", artist="X"))
    third_track_id = db.insert_track(Track(title="C", artist="X"))
    playlist_id = db.create_playlist("Test")
    db.set_playlist_tracks(playlist_id, [first_track_id, second_track_id, third_track_id])
    db.remove_playlist_track_by_position(playlist_id, 1)
    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 2
    assert tracks[0].title == "A"
    assert tracks[1].title == "C"
