"""Tests for the audit command handler (orchestration + banned-artist check)."""

from pathlib import Path
from types import SimpleNamespace

from tuneshift.commands.audit_cmd import handle_audit
from tuneshift.db import Database
from tuneshift.models import Track


def _args(playlist=None, **kwargs):
    base = dict(
        playlist=playlist,
        matching_only=False,
        vibes_only=False,
        concept_only=False,
        fix=False,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _seed(db: Database, name: str, artist: str = "Clean Artist") -> int:
    playlist_id = db.create_playlist(name)
    track_id = db.insert_track(Track(title="Song", artist=artist))
    db.set_playlist_tracks(playlist_id, [track_id])
    return playlist_id


def test_audit_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_audit(_args(playlist="Nope"), db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_audit_clean_playlist_reports_clean(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "Mix")
    assert handle_audit(_args(playlist="Mix"), db) == 0
    assert "All playlists clean." in capsys.readouterr().out


def test_audit_flags_banned_artist(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "Mix", artist="Bad Guy")
    db.ban_artist("Bad Guy", reason="test")
    assert handle_audit(_args(playlist="Mix"), db) == 0
    out = capsys.readouterr().out
    assert "[BANNED]" in out
    assert "Bad Guy" in out
    assert "1 total finding(s)" in out


def test_audit_all_playlists_when_no_name(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, "One")
    _seed(db, "Two")
    assert handle_audit(_args(playlist=None), db) == 0
    assert "All playlists clean." in capsys.readouterr().out
