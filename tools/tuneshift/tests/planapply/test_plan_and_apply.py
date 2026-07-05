"""Chunk 4 Task 4.2: plan engine core (ACs P1/P2/P3).

- Plans are durable JSON files (AC-P1): write, read back, and prune/reject
  individual changes before apply (AC-P2).
- Apply writes exactly the resolved (non-rejected) LOCAL changes and journals
  each write so it is reversible (AC-P4 mechanism, exercised fully in 4.3).
- Changes touching a ``user_approved``/locked row are marked ``locked`` and are
  EXCLUDED by default; ``include_locked=True`` is the explicit opt-in (AC-P3).
"""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.planapply.apply import apply_plan
from tuneshift.planapply.models import Plan, PlanChange, row_key_for
from tuneshift.planapply.plan import new_plan_id, read_plan, reject_change, write_plan


def _mapping_change(
    playlist_id: int, track_id: int, *, proposed_id: str, locked: bool = False
) -> PlanChange:
    return PlanChange(
        op="insert",
        table="playlist_track_mappings",
        row_key=row_key_for(
            playlist_id=playlist_id, track_id=track_id, platform="tidal"
        ),
        current=None,
        proposed={
            "playlist_id": playlist_id,
            "track_id": track_id,
            "platform": "tidal",
            "platform_track_id": proposed_id,
            "source": "matched",
            "user_approved": 0,
        },
        reason="first placement",
        locked=locked,
    )


class TestPlanFileRoundTrip:
    def test_write_then_read_restores_plan(self, tmp_db: Path) -> None:
        plan = Plan(
            plan_id=new_plan_id(),
            kind="rematch",
            scope="Pride",
            changes=[_mapping_change(1, 2, proposed_id="AAA")],
        )
        write_plan(tmp_db, plan)
        restored = read_plan(tmp_db, plan.plan_id)
        assert restored.plan_id == plan.plan_id
        assert restored.changes[0].proposed["platform_track_id"] == "AAA"

    def test_reject_change_marks_it_rejected(self, tmp_db: Path) -> None:
        c = _mapping_change(1, 2, proposed_id="AAA")
        c.change_id = 1
        plan = Plan(plan_id=new_plan_id(), kind="rematch", changes=[c])
        reject_change(plan, 1)
        assert plan.get(1).status == "rejected"
        assert plan.actionable_changes() == []


class TestApplyWritesAndJournals:
    def _seed(self, tmp_db: Path) -> tuple[Database, int, int]:
        db = Database(tmp_db)
        pid = db.create_playlist("Pride")
        from tuneshift.models import Track

        tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
        return db, pid, tid

    def test_apply_inserts_row_and_journals(self, tmp_db: Path) -> None:
        db, pid, tid = self._seed(tmp_db)
        plan = Plan(
            plan_id=new_plan_id(),
            kind="rematch",
            changes=[_mapping_change(pid, tid, proposed_id="AAA")],
        )
        report = apply_plan(db, plan)

        assert report.applied == 1
        mapping = db.get_playlist_track_mapping(pid, tid, "tidal")
        assert mapping is not None
        assert mapping["platform_track_id"] == "AAA"
        # Journaled for reversibility.
        entries = db.get_journal_entries(plan.plan_id)
        assert len(entries) == 1
        assert entries[0].op == "insert"
        assert entries[0].prior_value is None

    def test_replan_after_apply_is_empty_noop(self, tmp_db: Path) -> None:
        # AC-P4 idempotency: a change whose proposed state already matches the DB
        # is not re-applied (the builder marks it unchanged, so apply skips it).
        db, pid, tid = self._seed(tmp_db)
        db.set_playlist_track_mapping(
            pid, tid, "tidal", "AAA", source="matched", user_approved=False
        )
        change = _mapping_change(pid, tid, proposed_id="AAA")
        change.op = "update"
        change.current = {"platform_track_id": "AAA"}
        # Same current == proposed -> classification unchanged, not actionable.
        change.classification = "unchanged"
        change.status = "skipped"
        plan = Plan(plan_id=new_plan_id(), kind="rematch", changes=[change])
        report = apply_plan(db, plan)
        assert report.applied == 0
        assert report.skipped == 1

    def test_locked_change_excluded_by_default_then_opt_in(self, tmp_db: Path) -> None:
        db, pid, tid = self._seed(tmp_db)
        plan = Plan(
            plan_id=new_plan_id(),
            kind="rematch",
            changes=[_mapping_change(pid, tid, proposed_id="LOCK", locked=True)],
        )
        # Default: the locked change is not applied.
        report = apply_plan(db, plan)
        assert report.applied == 0
        assert report.skipped_locked == 1
        assert db.get_playlist_track_mapping(pid, tid, "tidal") is None

        # Explicit opt-in applies it.
        plan2 = Plan(
            plan_id=new_plan_id(),
            kind="rematch",
            changes=[_mapping_change(pid, tid, proposed_id="LOCK", locked=True)],
        )
        report2 = apply_plan(db, plan2, include_locked=True)
        assert report2.applied == 1
        assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "LOCK"

    def test_rejected_change_is_not_applied(self, tmp_db: Path) -> None:
        db, pid, tid = self._seed(tmp_db)
        c = _mapping_change(pid, tid, proposed_id="AAA")
        c.change_id = 1
        plan = Plan(plan_id=new_plan_id(), kind="rematch", changes=[c])
        reject_change(plan, 1)
        report = apply_plan(db, plan)
        assert report.applied == 0
        assert db.get_playlist_track_mapping(pid, tid, "tidal") is None
