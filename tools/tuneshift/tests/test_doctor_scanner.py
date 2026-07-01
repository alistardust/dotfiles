"""Unit tests for the doctor scanner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.doctor import scanner
from tuneshift.enrichment import platform_metadata
from tuneshift.enrichment.retry import PermanentAPIError, TransientAPIError
from tuneshift.models import PlatformMapping, Track


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)
    import tuneshift.enrichment.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda s: None)


def _add(db: Database, playlist_id: int, title: str, artist: str,
         tidal_id: str | None, position: int, duration: int | None = None) -> int:
    track = Track(title=title, artist=artist, album="Album",
                  duration_seconds=duration)
    tid = db.add_track(track)
    db.add_track_to_playlist(playlist_id, tid, position)
    if tidal_id is not None:
        db.upsert_platform_mapping(PlatformMapping(
            track_id=tid, platform="tidal", platform_track_id=tidal_id,
            platform_title=title,
        ))
    return tid


def _report(**kw) -> dict:
    base = dict(available=True, duration_seconds=None, title="",
                album_id="1", album_stale=False, metadata=None)
    base.update(kw)
    return base


def test_healthy_track_produces_no_issue(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", "100", 0, duration=200)

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song", duration_seconds=200),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert items == []


def test_unavailable_via_permanent_error(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Gone", "Artist", "404", 0)

    def boom(c, i):
        raise PermanentAPIError("not found")

    monkeypatch.setattr(platform_metadata, "fetch_track_report", boom)
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert len(items) == 1
    assert items[0].issue == "unavailable"


def test_unavailable_via_available_false(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", "100", 0)

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(available=False),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert items[0].issue == "unavailable"


def test_stale_album_detected(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", "100", 0, duration=200)

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song", duration_seconds=200, album_stale=True),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert items[0].issue == "stale_album"


def test_version_mismatch_by_duration(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Can I Kick It", "ATCQ", "100", 0, duration=250)

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Can I Kick It", duration_seconds=400),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert items[0].issue == "version_mismatch"
    assert "400" in items[0].note


def test_version_mismatch_by_keyword(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", "100", 0, duration=200)

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song (Live)", duration_seconds=205),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert items[0].issue == "version_mismatch"


def test_small_duration_delta_not_flagged(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", "100", 0, duration=200)

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song", duration_seconds=210),  # 10s < 15s
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert items == []


def test_unmapped_detected_without_api(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", None, 0)  # no mapping

    called = {"n": 0}

    def counted(c, i):
        called["n"] += 1
        return _report()

    monkeypatch.setattr(platform_metadata, "fetch_track_report", counted)
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    assert len(items) == 1
    assert items[0].issue == "unmapped"
    assert called["n"] == 0  # unmapped costs no API call


def test_merged_duplicate_track_gets_no_separate_item(tmp_path: Path, monkeypatch):
    """A non-keep duplicate row must not also produce an unmapped/remap item.

    The merge deletes that row, so a later per-track fix would be stranded.
    """
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "The Artist", "100", 0, duration=200)  # keep (mapped)
    _add(db, pid, "song", "Artist", None, 1, duration=200)       # merge, unmapped

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song", duration_seconds=200),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )

    # Exactly one duplicate item; the unmapped merge row is NOT separately flagged.
    assert [i.issue for i in items] == ["duplicate"]
    assert len(items[0].merge_track_ids) == 1


def test_duplicate_detected(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "The Artist", "100", 0, duration=200)
    _add(db, pid, "song", "Artist", "101", 1, duration=200)  # same identity

    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song", duration_seconds=200),
    )
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True,
    )
    dupes = [i for i in items if i.issue == "duplicate"]
    assert len(dupes) == 1
    assert dupes[0].keep_track_id is not None
    assert len(dupes[0].merge_track_ids) == 1


def test_transient_exhausted_marks_manual(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    _add(db, pid, "Song", "Artist", "100", 0)

    def flaky(c, i):
        raise TransientAPIError("rate limited", status_code=429)

    monkeypatch.setattr(platform_metadata, "fetch_track_report", flaky)
    items, _ = scanner.scan_tracks(
        db, MagicMock(), db.get_playlist_tracks(pid), "P",
        quiet=True, max_retries=1,
    )
    assert items[0].issue == "unavailable"
    assert items[0].resolution == "manual"


def test_scan_is_read_only_no_metadata_written(tmp_path: Path, monkeypatch):
    """The doctor scan must never write to the database (read-only diagnostic)."""
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    tid = _add(db, pid, "Song", "Artist", "100", 0, duration=200)

    meta = {"release_year": 1990, "album_name": "Album", "genres": ["rock"],
            "audio_qualities": ["LOSSLESS"]}
    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda c, i: _report(title="Song", duration_seconds=200, metadata=meta),
    )
    scanner.scan_tracks(db, MagicMock(), db.get_playlist_tracks(pid), "P", quiet=True)

    # No metadata rows written as a side effect of scanning.
    assert db.get_track_platform_metadata(tid, "tidal") is None
