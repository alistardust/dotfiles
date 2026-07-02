"""Tests for the diff command handler (platform client mocked)."""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.ingest_cmd as ingest_cmd
from tuneshift.commands.diff_cmd import handle_diff
from tuneshift.db import Database
from tuneshift.models import Track


class _FakeClient:
    def __init__(self, logged_in=True):
        self._logged_in = logged_in

    def load_session(self):
        return self._logged_in


def _seed(db: Database, name="Mix", *, tracks=1, platform=None) -> int:
    playlist_id = db.create_playlist(name)
    ids = [db.insert_track(Track(title=f"T{i}", artist="A")) for i in range(tracks)]
    if ids:
        db.set_playlist_tracks(playlist_id, ids)
    if platform:
        db.link_platform_playlist(playlist_id, platform, "pl-1")
    return playlist_id


def test_diff_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(playlist="Nope", platform=None)
    assert handle_diff(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_diff_no_linked_platforms_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, tracks=1)
    args = SimpleNamespace(playlist="Mix", platform=None)
    assert handle_diff(args, db) == 1
    assert "No platforms linked." in capsys.readouterr().err


def test_diff_empty_playlist_returns_0(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, tracks=0)
    args = SimpleNamespace(playlist="Mix", platform="tidal")
    assert handle_diff(args, db) == 0
    assert "is empty" in capsys.readouterr().out


def test_diff_unknown_platform_arg_skips(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, tracks=1)
    args = SimpleNamespace(playlist="Mix", platform="bogus")
    assert handle_diff(args, db) == 0
    assert "Unknown platform: bogus" in capsys.readouterr().err


def test_diff_not_logged_in_skips(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    _seed(db, tracks=1)
    monkeypatch.setattr(
        ingest_cmd, "_load_client", lambda platform: _FakeClient(logged_in=False)
    )
    args = SimpleNamespace(playlist="Mix", platform="tidal")
    assert handle_diff(args, db) == 0
    assert "Not logged in to tidal." in capsys.readouterr().err


def test_diff_unmapped_track_needs_reconciliation(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    _seed(db, tracks=1, platform="tidal")
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    args = SimpleNamespace(playlist="Mix", platform=None)
    assert handle_diff(args, db) == 0
    out = capsys.readouterr().out
    assert "Would push" in out
    assert "needs reconciliation" in out
