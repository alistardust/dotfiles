"""concept_rule_acceptances table + DB methods (Task 6)."""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import _SCHEMA_VERSION, Database
from tuneshift.models import Track


def _setup(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("P")
    tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
    db.add_track_to_playlist(pid, tid, 0)
    return db, pid, tid


def test_add_then_get_returns_pair(tmp_path: Path):
    db, pid, tid = _setup(tmp_path)
    db.add_concept_acceptance(pid, tid, "released 1993-2003")
    assert db.get_concept_acceptances(pid) == {(tid, "released 1993-2003")}


def test_acceptance_key_is_normalized(tmp_path: Path):
    db, pid, tid = _setup(tmp_path)
    db.add_concept_acceptance(pid, tid, "  Released   1993-2003 ")
    # Stored key is whitespace-collapsed and casefolded.
    assert db.get_concept_acceptances(pid) == {(tid, "released 1993-2003")}


def test_add_is_idempotent(tmp_path: Path):
    db, pid, tid = _setup(tmp_path)
    db.add_concept_acceptance(pid, tid, "rule x")
    db.add_concept_acceptance(pid, tid, "rule x")
    assert len(db.get_concept_acceptances(pid)) == 1


def test_clear_removes_pair(tmp_path: Path):
    db, pid, tid = _setup(tmp_path)
    db.add_concept_acceptance(pid, tid, "rule x")
    db.clear_concept_acceptance(pid, tid, "rule x")
    assert db.get_concept_acceptances(pid) == set()


def test_list_returns_raw_rule_text(tmp_path: Path):
    db, pid, tid = _setup(tmp_path)
    db.add_concept_acceptance(pid, tid, "Released 1993-2003")
    assert db.list_concept_acceptances(pid) == [(tid, "Released 1993-2003")]


def test_schema_version_bumped_and_table_present(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    version = db.conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'version'"
    ).fetchone()[0]
    assert int(version) == _SCHEMA_VERSION
    row = db.conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='concept_rule_acceptances'"
    ).fetchone()
    assert row is not None
