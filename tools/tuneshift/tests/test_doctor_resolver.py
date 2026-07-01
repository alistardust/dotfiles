"""Unit tests for the doctor resolver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.doctor import resolver
from tuneshift.doctor.plan import PlanItem
from tuneshift.models import Track
from tuneshift.reconcile import ReconcileResult


def _track(db: Database, title="Song", artist="Artist") -> int:
    return db.add_track(Track(title=title, artist=artist, album="Album"))


def _item(track_id: int, issue: str, **kw) -> PlanItem:
    base = dict(id=1, track_id=track_id, playlist="P", title="Song",
                artist="Artist", issue=issue)
    base.update(kw)
    return PlanItem(**base)


def test_unavailable_high_confidence_auto(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "unavailable", current_platform_id="111")

    monkeypatch.setattr(resolver, "reconcile_track", lambda *a, **k: ReconcileResult(
        platform_track_id="222", platform_title="Song", platform_album="Album",
        score=95, confidence="high",
    ))
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "auto"
    assert item.proposed_platform_id == "222"
    assert item.confidence == 95


def test_low_confidence_marks_manual(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "unavailable", current_platform_id="111")

    monkeypatch.setattr(resolver, "reconcile_track", lambda *a, **k: ReconcileResult(
        platform_track_id="222", score=50, confidence="ambiguous",
    ))
    resolver.resolve_item(db, MagicMock(), item, threshold=70)
    assert item.resolution == "manual"


def test_not_found_marks_manual(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "unavailable")

    monkeypatch.setattr(resolver, "reconcile_track", lambda *a, **k: ReconcileResult(
        confidence="not_found",
    ))
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "manual"
    assert "no candidate" in item.note


def test_proposal_equal_to_current_is_manual(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "version_mismatch", current_platform_id="111")

    monkeypatch.setattr(resolver, "reconcile_track", lambda *a, **k: ReconcileResult(
        platform_track_id="111", score=99, confidence="high",
    ))
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "manual"
    assert "current mapping" in item.note


def test_version_mismatch_proposes_standard(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "version_mismatch", current_platform_id="extended-1")

    monkeypatch.setattr(resolver, "reconcile_track", lambda *a, **k: ReconcileResult(
        platform_track_id="standard-1", platform_album="People's Instinctive Travels",
        score=88, confidence="high",
    ))
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "auto"
    assert item.proposed_platform_id == "standard-1"


def test_stale_album_is_metadata_only(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "stale_album")
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "auto"
    assert item.confidence == 100
    assert item.proposed_platform_id == ""  # no remap


def test_duplicate_untouched(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "duplicate", keep_track_id=tid, merge_track_ids=[99])
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "auto"
    assert item.keep_track_id == tid


def test_unmapped_uses_reconcile(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "t.db")
    tid = _track(db)
    item = _item(tid, "unmapped")

    monkeypatch.setattr(resolver, "reconcile_track", lambda *a, **k: ReconcileResult(
        platform_track_id="333", score=90, confidence="high",
    ))
    resolver.resolve_item(db, MagicMock(), item)
    assert item.resolution == "auto"
    assert item.proposed_platform_id == "333"
