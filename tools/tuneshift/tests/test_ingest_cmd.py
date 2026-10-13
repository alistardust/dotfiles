"""Tests for the ingest command handler (client + core import mocked)."""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.ingest_cmd as ingest_cmd
from tuneshift.commands.ingest_cmd import handle_ingest
from tuneshift.db import Database
from tuneshift.ingest import IngestResult


def _result(**overrides) -> IngestResult:
    """An ingest outcome with every count at zero unless named."""
    fields = {
        "name": "My Mix",
        "total_remote": 10,
        "new_tracks": 4,
        "skipped": 0,
        "added_to_playlist": 0,
        "kept_local_only": 0,
        "removed_from_playlist": 0,
    }
    fields.update(overrides)
    return IngestResult(**fields)


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

    def _boom(db, client, playlist_id, replace=False):
        raise ValueError("bad playlist id")

    monkeypatch.setattr(ingest_cmd, "ingest_from_platform", _boom)
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 1
    assert "Error: bad playlist id" in capsys.readouterr().err


def test_ingest_success_reports_counts(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    monkeypatch.setattr(
        ingest_cmd,
        "ingest_from_platform",
        lambda db, client, pid, replace=False: _result(added_to_playlist=10),
    )
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 0
    out = capsys.readouterr().out
    assert 'Ingested "My Mix" from tidal: 10 remote tracks, 10 added' in out
    assert "4 new to library" in out
    assert "unavailable" not in out


def test_ingest_success_reports_skipped(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    monkeypatch.setattr(
        ingest_cmd,
        "ingest_from_platform",
        lambda db, client, pid, replace=False: _result(added_to_playlist=8, skipped=2),
    )
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 0
    assert "2 unavailable and skipped" in capsys.readouterr().out


def test_ingest_reports_local_only_tracks_that_were_kept(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """The merge is the point of the fix, so the report has to show it."""
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    monkeypatch.setattr(
        ingest_cmd,
        "ingest_from_platform",
        lambda db, client, pid, replace=False: _result(
            added_to_playlist=10, kept_local_only=3
        ),
    )
    args = SimpleNamespace(platform="tidal", playlist_id="x")
    assert handle_ingest(args, db) == 0
    assert "3 local-only kept" in capsys.readouterr().out


def test_ingest_reports_removals_on_stderr_under_replace(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """Destroying local-only tracks is loud, and only --replace can do it."""
    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: _FakeClient())
    monkeypatch.setattr(
        ingest_cmd,
        "ingest_from_platform",
        lambda db, client, pid, replace=False: _result(
            added_to_playlist=10, removed_from_playlist=3
        ),
    )
    args = SimpleNamespace(platform="tidal", playlist_id="x", replace=True)
    assert handle_ingest(args, db) == 0
    captured = capsys.readouterr()
    assert "Removed 3 local-only track(s)" in captured.err
    assert "--replace" in captured.err
