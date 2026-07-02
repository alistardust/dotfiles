"""Tests for the status and list command handlers (no network)."""

from pathlib import Path
from types import SimpleNamespace

from tuneshift.cli import main
from tuneshift.commands.status_cmd import handle_list, handle_status
from tuneshift.db import Database
from tuneshift.models import Track


def _seed(db: Database, name: str, *, with_platform: bool = False) -> int:
    playlist_id = db.create_playlist(name)
    track_id = db.insert_track(Track(title="Song", artist="Artist"))
    db.set_playlist_tracks(playlist_id, [track_id])
    if with_platform:
        db.link_platform_playlist(playlist_id, "tidal", "tidal-123")
    return playlist_id


def test_status_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(playlist="Nope")
    assert handle_status(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_status_named_playlist_shows_tracks_and_platform(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "Mix", with_platform=True)
    db.close()

    assert main(["--db", str(tmp_db), "status", "Mix"]) == 0
    out = capsys.readouterr().out
    assert "Mix" in out
    assert "Tracks: 1" in out
    assert "Platforms: tidal" in out


def test_status_named_playlist_without_platform(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "Solo")
    db.close()

    assert main(["--db", str(tmp_db), "status", "Solo"]) == 0
    assert "Platforms: (none linked)" in capsys.readouterr().out


def test_status_no_playlists_returns_0(tmp_db: Path, capsys) -> None:
    Database(tmp_db).close()
    assert main(["--db", str(tmp_db), "status"]) == 0
    assert "No playlists" in capsys.readouterr().out


def test_status_all_playlists(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "One")
    _seed(db, "Two")
    db.close()

    assert main(["--db", str(tmp_db), "status"]) == 0
    out = capsys.readouterr().out
    assert "One" in out
    assert "Two" in out


def test_list_no_playlists_returns_0(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_list(SimpleNamespace(), db) == 0
    assert "No playlists." in capsys.readouterr().out


def test_list_shows_track_count_and_platform_bracket(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "Mix", with_platform=True)
    db.close()

    assert main(["--db", str(tmp_db), "list"]) == 0
    out = capsys.readouterr().out
    assert "Mix (1 tracks)" in out
    assert "[tidal]" in out
