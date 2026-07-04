"""Chunk 4 Task 4.7: migration of stale mappings is a plan (AC-P5).

E2E: a fixture of stale mappings (including a user_approved row) is migrated via
the plan/apply engine. user_approved rows are bypassed, the plan lists every
proposed change with a classification, only confident improvements apply, and
rollback restores the original state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tuneshift.db import Database
from tuneshift.models import PlatformMapping, Track
from tuneshift.planapply import migrate as migrate_mod
from tuneshift.planapply.apply import apply_plan, rollback_plan
from tuneshift.planapply.migrate import build_migration_plan, migration_summary
from tuneshift.reconcile import ReconcileResult


def _seed(tmp_db: Path) -> tuple[Database, dict[str, int]]:
    db = Database(tmp_db)
    ids = {}
    for name in ("improve", "same", "lowconf", "approved"):
        tid = db.add_track(Track(title=name, artist="Artist", album="Album"))
        ids[name] = tid
        db.upsert_platform_mapping(
            PlatformMapping(
                track_id=tid,
                platform="tidal",
                platform_track_id=f"OLD_{name}",
                match_score=55,
                status="matched",
                user_approved=(name == "approved"),
            )
        )
    return db, ids


def _stub_reconcile(monkeypatch: pytest.MonkeyPatch, ids: dict[str, int]) -> None:
    def fake(db, track_id, client, **kwargs):  # noqa: ANN001, ANN003
        if track_id == ids["improve"]:
            return ReconcileResult(platform_track_id="NEW_improve", confidence="high", score=98)
        if track_id == ids["same"]:
            return ReconcileResult(platform_track_id="OLD_same", confidence="high", score=90)
        if track_id == ids["lowconf"]:
            return ReconcileResult(platform_track_id="MAYBE", confidence="ambiguous", score=40)
        raise AssertionError("reconcile called for a bypassed approved row")

    monkeypatch.setattr(migrate_mod, "reconcile_track", fake)


def _current_id(db: Database, track_id: int) -> str:
    return db.get_platform_mapping(track_id, "tidal").platform_track_id


class TestMigrationPlan:
    def test_classifies_every_mapping_and_bypasses_approved(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, ids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, ids)

        plan = build_migration_plan(db, client=object(), platform="tidal")

        # Every existing mapping is represented in the plan.
        assert len(plan.changes) == 4
        assert migration_summary(plan) == {
            "improved": 1,
            "unchanged": 2,  # same-id + approved-bypass
            "needs-human-judgment": 1,
        }
        # Only the confident improvement is actionable.
        actionable = plan.actionable_changes()
        assert len(actionable) == 1
        assert actionable[0].proposed["platform_track_id"] == "NEW_improve"

    def test_apply_then_rollback_restores_and_never_touches_approved(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, ids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, ids)
        plan = build_migration_plan(db, client=object(), platform="tidal")

        report = apply_plan(db, plan)
        assert report.applied == 1

        # Improved mapping updated; everything else untouched.
        assert _current_id(db, ids["improve"]) == "NEW_improve"
        assert _current_id(db, ids["same"]) == "OLD_same"
        assert _current_id(db, ids["lowconf"]) == "OLD_lowconf"
        assert _current_id(db, ids["approved"]) == "OLD_approved"
        assert db.get_platform_mapping(ids["approved"], "tidal").user_approved is True

        # Rollback restores the original state in one step (AC-P4).
        rb = rollback_plan(db, plan.plan_id)
        assert rb.reverted == 1
        assert _current_id(db, ids["improve"]) == "OLD_improve"

    def test_track_ids_scope_limits_candidates(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, ids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, ids)
        plan = build_migration_plan(
            db, client=object(), platform="tidal", track_ids=[ids["improve"]]
        )
        assert len(plan.changes) == 1
        assert plan.changes[0].classification == "improved"
