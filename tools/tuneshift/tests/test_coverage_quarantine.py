"""Task 1.8: coverage report + quarantine surface (spec §4.4, AC-D1/AC-D6).

Coverage uses the AC-D1 denominator ``resolved / (resolved + quarantined)`` so
quarantine cannot game the floor. Quarantined tracks are excluded from playlist
selection (AC-D6) and surfaced with machine-readable reasons on triage.
"""

from pathlib import Path

import pytest

from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


def _resolved(db: Database, title: str, *, isrc: str | None = None, **fields) -> int:
    tid = db.insert_track(Track(title=title, artist="A", isrc=isrc))
    db.enqueue_resolution(tid)
    db.set_resolution_state(tid, "resolved")
    if fields:
        db.set_track_fields(tid, fields, source="test")
    return tid


def _quarantined(db: Database, title: str, reason: str) -> int:
    tid = db.insert_track(Track(title=title, artist="A"))
    db.enqueue_resolution(tid)
    db.set_resolution_state(tid, "quarantined", last_error=reason)
    db.set_track_fields(
        tid, {"quarantine_state": "unresolved", "quarantine_reason": reason},
        source="test",
    )
    return tid


def test_coverage_denominator_excludes_pending_uses_quarantined(db: Database) -> None:
    _resolved(db, "R1")
    _resolved(db, "R2")
    _resolved(db, "R3")
    _quarantined(db, "Q1", "no_candidate")
    # a pending track must NOT count in the denominator
    p = db.insert_track(Track(title="P1", artist="A"))
    db.enqueue_resolution(p)

    report = db.coverage_report()
    assert report["resolved"] == 3
    assert report["quarantined"] == 1
    assert report["pending"] == 1
    # 3 / (3 + 1) = 0.75  — quarantine is in the denominator, pending is not
    assert report["coverage"] == pytest.approx(0.75)


def test_coverage_zero_when_nothing_resolved(db: Database) -> None:
    report = db.coverage_report()
    assert report["coverage"] == 0.0
    assert report["resolved"] == 0


def test_field_fill_rates(db: Database) -> None:
    _resolved(db, "R1", isrc="US1234500001", album_artist="A")
    _resolved(db, "R2", isrc="US1234500002")
    _resolved(db, "R3")
    _resolved(db, "R4")

    report = db.coverage_report()
    rates = report["field_fill_rates"]
    # 2 of 4 tracks have isrc
    assert rates["isrc"] == pytest.approx(0.5)
    # 1 of 4 has album_artist
    assert rates["album_artist"] == pytest.approx(0.25)


def test_quarantined_excluded_from_playlist_selection(db: Database) -> None:
    pid = db.create_playlist("P")
    good = _resolved(db, "Good")
    bad = _quarantined(db, "Bad", "no_candidate")
    db.add_track_to_playlist(pid, good, 1)
    db.add_track_to_playlist(pid, bad, 2)

    selectable = db.get_selectable_track_ids(pid)
    assert good in selectable
    assert bad not in selectable


def test_quarantined_tracks_listed_with_reasons(db: Database) -> None:
    _resolved(db, "Good")
    bad = _quarantined(db, "Bad", "no_candidate: nothing on tidal")

    listed = db.get_quarantined_tracks()
    assert len(listed) == 1
    entry = listed[0]
    assert entry["track_id"] == bad
    assert entry["title"] == "Bad"
    assert "no_candidate" in entry["reason"]


def test_triage_surfaces_quarantined(db: Database, capsys) -> None:
    from types import SimpleNamespace

    from tuneshift.commands.triage_cmd import handle_triage

    bad = _quarantined(db, "Bad Track", "no_candidate: nothing found")
    rc = handle_triage(SimpleNamespace(playlist=None, platform=None), db)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bad Track" in out
    assert "no_candidate" in out
    assert str(bad) in out
