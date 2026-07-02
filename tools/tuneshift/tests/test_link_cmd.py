"""Tests for the link command handler (platform client mocked)."""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.link_cmd as link_cmd
from tuneshift.commands.link_cmd import handle_link
from tuneshift.db import Database


class _FakeClient:
    def __init__(self, logged_in=True, found=None):
        self._logged_in = logged_in
        self._found = found or {}

    def load_session(self):
        return self._logged_in

    def find_playlist_by_name(self, name):
        platform_id = self._found.get(name)
        if platform_id is None:
            return None
        return SimpleNamespace(platform_id=platform_id)


def test_manual_link_extracts_id_from_url(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    db.create_playlist("Mix")
    args = SimpleNamespace(
        platform="spotify",
        name="Mix",
        url="https://open.spotify.com/playlist/ABC123xyz",
        quiet=False,
    )
    assert handle_link(args, db) == 0
    assert "ABC123xyz" in capsys.readouterr().out
    playlist = db.find_playlist_by_name("Mix")
    assert db.get_platform_playlist_id(playlist.id, "spotify") == "ABC123xyz"


def test_manual_link_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(platform="spotify", name="Nope", url="ABC", quiet=False)
    assert handle_link(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_auto_unknown_platform_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(link_cmd, "_load_client", lambda platform: None)
    args = SimpleNamespace(platform="bogus", name=None, url=None, quiet=False)
    assert handle_link(args, db) == 1
    assert "Unknown platform: bogus" in capsys.readouterr().err


def test_auto_not_logged_in_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(link_cmd, "_load_client", lambda platform: _FakeClient(logged_in=False))
    args = SimpleNamespace(platform="tidal", name=None, url=None, quiet=False)
    assert handle_link(args, db) == 1
    assert "Not logged in" in capsys.readouterr().err


def test_auto_no_playlists_returns_0(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(link_cmd, "_load_client", lambda platform: _FakeClient())
    args = SimpleNamespace(platform="tidal", name=None, url=None, quiet=False)
    assert handle_link(args, db) == 0
    assert "No playlists in database." in capsys.readouterr().out


def test_auto_discovery_links_matches_and_reports(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    db.create_playlist("Found")
    db.create_playlist("Missing")
    client = _FakeClient(found={"Found": "tidal-999"})
    monkeypatch.setattr(link_cmd, "_load_client", lambda platform: client)
    args = SimpleNamespace(platform="tidal", name=None, url=None, quiet=False)

    assert handle_link(args, db) == 0
    out = capsys.readouterr().out
    assert "Linked: Found -> tidal-999" in out
    assert "1 linked" in out
    found = db.find_playlist_by_name("Found")
    assert db.get_platform_playlist_id(found.id, "tidal") == "tidal-999"
    missing = db.find_playlist_by_name("Missing")
    assert db.get_platform_playlist_id(missing.id, "tidal") is None
