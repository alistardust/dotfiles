"""Tests for the rm command handler (platform client mocked)."""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.ingest_cmd as ingest_cmd
from tuneshift.commands.rm_cmd import handle_rm
from tuneshift.db import Database
from tuneshift.models import Track


class _FakeClient:
    def __init__(self, *, logged_in=True, tracks=None, raise_on_get=False):
        self._logged_in = logged_in
        self._tracks = tracks or []
        self._raise_on_get = raise_on_get
        self.removed = None

    def load_session(self):
        return self._logged_in

    def get_playlist_tracks(self, platform_playlist_id):
        if self._raise_on_get:
            raise RuntimeError("platform API down")
        return self._tracks

    def remove_tracks_by_positions(self, platform_playlist_id, positions):
        self.removed = positions


def _seed(db: Database, *, titles=("Alpha", "Beta"), platform=None) -> int:
    playlist_id = db.create_playlist("Mix")
    ids = [db.insert_track(Track(title=t, artist="A")) for t in titles]
    db.set_playlist_tracks(playlist_id, ids)
    if platform:
        db.link_platform_playlist(playlist_id, platform, "pl-1")
    return playlist_id


def test_rm_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(playlist="Nope", target="1")
    assert handle_rm(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_rm_position_out_of_range_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    args = SimpleNamespace(playlist="Mix", target="99")
    assert handle_rm(args, db) == 1
    assert "out of range" in capsys.readouterr().err


def test_rm_no_match_non_numeric_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    args = SimpleNamespace(playlist="Mix", target="zzz")
    assert handle_rm(args, db) == 1
    assert 'No track matching "zzz"' in capsys.readouterr().err


def test_rm_title_match_removes_track(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    playlist_id = _seed(db)
    args = SimpleNamespace(playlist="Mix", target="Alpha")
    assert handle_rm(args, db) == 0
    remaining = [t.title for t in db.get_playlist_tracks(playlist_id)]
    assert remaining == ["Beta"]


def test_rm_by_position_removes_track(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    playlist_id = _seed(db)
    args = SimpleNamespace(playlist="Mix", target="2")
    assert handle_rm(args, db) == 0
    remaining = [t.title for t in db.get_playlist_tracks(playlist_id)]
    assert remaining == ["Alpha"]


def test_rm_syncs_removal_to_platform(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    _seed(db, platform="tidal")
    client = _FakeClient(tracks=[SimpleNamespace(title="Alpha"), SimpleNamespace(title="Beta")])
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
    args = SimpleNamespace(playlist="Mix", target="Alpha")
    assert handle_rm(args, db) == 0
    assert client.removed == [0]
    assert "tidal: removed" in capsys.readouterr().out


def test_rm_platform_sync_failure_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    _seed(db, platform="tidal")
    client = _FakeClient(raise_on_get=True)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
    args = SimpleNamespace(playlist="Mix", target="Alpha")
    assert handle_rm(args, db) == 1
    assert "sync failed" in capsys.readouterr().err
