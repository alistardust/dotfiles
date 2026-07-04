"""Chunk 4 Task 4.5: map/unmap (lock) and enrichment overwrites are ROUTED.

Per the §7.1 mutation-routing table, a manual ``map``/``unmap`` is a lock
create/release and an enrichment overwrite of a matcher-read field are both
ROUTED: they produce a reviewable plan and journal their writes, rather than
mutating inline. This module's builders produce those plans; the CLI wiring is
Task 4.8.
"""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.planapply.apply import apply_plan, rollback_plan
from tuneshift.planapply.builders import (
    build_enrich_plan,
    build_lock_plan,
    build_unlock_plan,
)


def _seed(tmp_db: Path) -> tuple[Database, int, int]:
    db = Database(tmp_db)
    pid = db.create_playlist("Pride")
    tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
    db.add_track_to_playlist(pid, tid, 0)
    return db, pid, tid


class TestLockRouting:
    def test_map_creates_locked_mapping_via_plan(self, tmp_db: Path) -> None:
        db, pid, tid = _seed(tmp_db)
        plan = build_lock_plan(db, pid, tid, "tidal", "PINNED")
        # Nothing written until apply.
        assert db.get_playlist_track_mapping(pid, tid, "tidal") is None
        apply_plan(db, plan)
        mapping = db.get_playlist_track_mapping(pid, tid, "tidal")
        assert mapping["platform_track_id"] == "PINNED"
        assert mapping["source"] == "locked"
        assert mapping["user_approved"] is True

    def test_unmap_releases_lock_via_plan_and_is_reversible(self, tmp_db: Path) -> None:
        db, pid, tid = _seed(tmp_db)
        db.set_playlist_track_mapping(
            pid, tid, "tidal", "PINNED", source="locked", user_approved=True
        )
        plan = build_unlock_plan(db, pid, tid, "tidal")
        # Releasing an approved lock touches an approved row -> opt-in required.
        report = apply_plan(db, plan)
        assert report.applied == 0
        assert report.skipped_locked == 1
        report2 = apply_plan(db, plan, include_locked=True)
        assert report2.applied == 1
        assert db.get_playlist_track_mapping(pid, tid, "tidal") is None
        # Rollback restores the released lock.
        rollback_plan(db, plan.plan_id)
        restored = db.get_playlist_track_mapping(pid, tid, "tidal")
        assert restored["platform_track_id"] == "PINNED"
        assert restored["user_approved"] is True

    def test_unmap_of_absent_mapping_is_empty_plan(self, tmp_db: Path) -> None:
        db, pid, tid = _seed(tmp_db)
        plan = build_unlock_plan(db, pid, tid, "tidal")
        assert plan.is_empty()


class TestEnrichRouting:
    def test_enrich_overwrite_is_planned_journaled_and_reversible(
        self, tmp_db: Path
    ) -> None:
        db, pid, tid = _seed(tmp_db)
        db.conn.execute(
            "UPDATE tracks SET album_type = 'album', label = 'OldLabel' WHERE id = ?",
            (tid,),
        )
        db.conn.commit()
        plan = build_enrich_plan(
            db, tid, {"album_type": "compilation", "label": "NewLabel"}
        )
        assert not plan.is_empty()
        apply_plan(db, plan)
        row = db.conn.execute(
            "SELECT album_type, label FROM tracks WHERE id = ?", (tid,)
        ).fetchone()
        assert row["album_type"] == "compilation"
        assert row["label"] == "NewLabel"
        # Reversible in one step (AC-P4).
        rollback_plan(db, plan.plan_id)
        row2 = db.conn.execute(
            "SELECT album_type, label FROM tracks WHERE id = ?", (tid,)
        ).fetchone()
        assert row2["album_type"] == "album"
        assert row2["label"] == "OldLabel"

    def test_enrich_with_no_change_is_empty_plan(self, tmp_db: Path) -> None:
        db, pid, tid = _seed(tmp_db)
        db.conn.execute(
            "UPDATE tracks SET album_type = 'album' WHERE id = ?", (tid,)
        )
        db.conn.commit()
        plan = build_enrich_plan(db, tid, {"album_type": "album"})
        assert plan.is_empty()

    def test_enrich_rejects_non_matcher_field(self, tmp_db: Path) -> None:
        db, pid, tid = _seed(tmp_db)
        import pytest

        with pytest.raises(ValueError):
            build_enrich_plan(db, tid, {"title": "Hacked"})
