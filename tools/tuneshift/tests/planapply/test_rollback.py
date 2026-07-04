"""Chunk 4 Task 4.3: one-step rollback of an applied plan (AC-P4).

``rollback_plan`` replays the journal in reverse. The uniform reverse rule is:
if a write had no prior state, delete the row; otherwise restore the prior state.
This handles insert/update/delete symmetrically. Remote pushes are forward-only:
rollback never un-pushes them inline, it reports them for a compensating plan.
"""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.planapply.apply import apply_plan, rollback_plan
from tuneshift.planapply.models import Plan, PlanChange, row_key_for
from tuneshift.planapply.plan import new_plan_id


def _seed(tmp_db: Path) -> tuple[Database, int, int]:
    db = Database(tmp_db)
    pid = db.create_playlist("Pride")
    tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
    return db, pid, tid


def _insert_change(pid: int, tid: int, proposed_id: str) -> PlanChange:
    return PlanChange(
        op="insert",
        table="playlist_track_mappings",
        row_key=row_key_for(playlist_id=pid, track_id=tid, platform="tidal"),
        current=None,
        proposed={
            "playlist_id": pid,
            "track_id": tid,
            "platform": "tidal",
            "platform_track_id": proposed_id,
            "source": "matched",
            "user_approved": 0,
        },
    )


def test_rollback_of_insert_deletes_the_row(tmp_db: Path) -> None:
    db, pid, tid = _seed(tmp_db)
    plan = Plan(
        plan_id=new_plan_id(), kind="rematch", changes=[_insert_change(pid, tid, "AAA")]
    )
    apply_plan(db, plan)
    assert db.get_playlist_track_mapping(pid, tid, "tidal") is not None

    report = rollback_plan(db, plan.plan_id)

    assert report.reverted == 1
    # Original state restored: the row that did not exist before is gone.
    assert db.get_playlist_track_mapping(pid, tid, "tidal") is None
    # Journal cleared so the plan cannot be double-rolled-back.
    assert db.has_journal(plan.plan_id) is False


def test_rollback_of_update_restores_prior_value(tmp_db: Path) -> None:
    db, pid, tid = _seed(tmp_db)
    # Pre-existing mapping.
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "ORIGINAL", source="matched", user_approved=False
    )
    change = PlanChange(
        op="update",
        table="playlist_track_mappings",
        row_key=row_key_for(playlist_id=pid, track_id=tid, platform="tidal"),
        current={"platform_track_id": "ORIGINAL"},
        proposed={
            "playlist_id": pid,
            "track_id": tid,
            "platform": "tidal",
            "platform_track_id": "NEW",
            "source": "matched",
            "user_approved": 0,
        },
    )
    plan = Plan(plan_id=new_plan_id(), kind="rematch", changes=[change])
    apply_plan(db, plan)
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "NEW"

    rollback_plan(db, plan.plan_id)

    restored = db.get_playlist_track_mapping(pid, tid, "tidal")
    assert restored["platform_track_id"] == "ORIGINAL"


def test_reapply_after_apply_is_noop(tmp_db: Path) -> None:
    # AC-P4 idempotency at the apply level: applying an already-applied plan
    # object does nothing (all changes marked applied).
    db, pid, tid = _seed(tmp_db)
    plan = Plan(
        plan_id=new_plan_id(), kind="rematch", changes=[_insert_change(pid, tid, "AAA")]
    )
    apply_plan(db, plan)
    report2 = apply_plan(db, plan)
    assert report2.applied == 0
    assert report2.skipped == 1
