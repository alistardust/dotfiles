"""Tests for Database.get_release_years_for_playlist (Task 3)."""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track


def _add(db: Database, pid: int, title: str, position: int) -> int:
    tid = db.add_track(Track(title=title, artist="Artist", album="Album"))
    db.add_track_to_playlist(pid, tid, position)
    return tid


def test_returns_year_per_track(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    t1 = _add(db, pid, "Has Year", 0)
    t2 = _add(db, pid, "No Year", 1)
    db.upsert_track_platform_metadata(t1, "tidal", "100", release_year=1998)

    years = db.get_release_years_for_playlist(pid)
    assert years == {t1: 1998, t2: None}


def test_earliest_year_across_platforms(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    tid = _add(db, pid, "Reissued", 0)
    db.upsert_track_platform_metadata(tid, "tidal", "1", release_year=2010)
    db.upsert_track_platform_metadata(tid, "spotify", "2", release_year=1994)

    years = db.get_release_years_for_playlist(pid)
    assert years == {tid: 1994}


def test_every_playlist_track_present(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    ids = [_add(db, pid, f"T{i}", i) for i in range(3)]
    years = db.get_release_years_for_playlist(pid)
    assert set(years) == set(ids)
    assert all(v is None for v in years.values())
