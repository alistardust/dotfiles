"""Tests for the ingest command handler (client + core import mocked)."""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.ingest_cmd as ingest_cmd
from tuneshift.commands.ingest_cmd import handle_ingest
from tuneshift.db import Database


class _FakeClient:
    def __init__(self, logged_in=True):
        self._logged_in = logged_in

    def load_session(self):
        return self._logged_in


def test_ingest_unknown_platform_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: None)
    args = SimpleNamespace(platform="bogus", playlist_id="x")
    assert handle_ingest(args, db) == 1
    assert "Unknown platform: bogus" in capsys.readouterr().err


def test_ingest_not_logged_in_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient(logged_in=False))
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 1
    assert "Not logged in to tidal" in capsys.readouterr().err


def test_ingest_value_error_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())

    def _boom(db, client, playlist_id):
        raise ValueError("bad playlist id")

    monkeypatch.setattr(ingest_cmd, "ingest_from_platform", _boom)
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 1
    assert "Error: bad playlist id" in capsys.readouterr().err


def test_ingest_success_reports_counts(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    monkeypatch.setattr(
        ingest_cmd, "ingest_from_platform", lambda db, client, pid: ("My Mix", 10, 4, 0)
    )
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 0
    out = capsys.readouterr().out
    assert 'Ingested "My Mix" from tidal: 10 tracks (4 new)' in out
    assert "unavailable" not in out


def test_ingest_success_reports_skipped(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    monkeypatch.setattr(
        ingest_cmd, "ingest_from_platform", lambda db, client, pid: ("My Mix", 10, 4, 2)
    )
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 0
    assert "(2 unavailable, skipped)" in capsys.readouterr().out
