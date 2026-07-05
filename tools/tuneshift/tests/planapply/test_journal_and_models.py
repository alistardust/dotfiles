"""Chunk 4 Task 4.1: apply_journal storage + plan model (AC-P4 storage).

The journal records every applied write (prior -> new) so an applied plan can be
reversed in one step by replaying the entries in reverse. The plan model
(`PlanChange`/`Plan`) is the in-memory representation every mutating command
produces before anything is written.
"""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.planapply.models import Plan, PlanChange


class TestPlanChangeModel:
    def test_defaults_are_pending_local_and_improved(self) -> None:
        change = PlanChange(
            op="update",
            table="playlist_track_mappings",
            row_key='{"playlist_id": 1, "track_id": 2, "platform": "tidal"}',
            current={"platform_track_id": "OLD"},
            proposed={"platform_track_id": "NEW"},
            reason="better version",
        )
        assert change.status == "pending"
        assert change.locked is False
        assert change.remote is False
        assert change.classification == "improved"

    def test_round_trips_through_dict(self) -> None:
        change = PlanChange(
            op="insert",
            table="playlist_track_mappings",
            row_key='{"playlist_id": 1, "track_id": 2, "platform": "tidal"}',
            current=None,
            proposed={"platform_track_id": "NEW", "source": "matched"},
            reason="first placement",
            provenance="select_version",
        )
        plan = Plan(plan_id="p-123", kind="rematch", scope="Pride", changes=[change])
        restored = Plan.from_dict(plan.to_dict())
        assert restored.plan_id == "p-123"
        assert restored.kind == "rematch"
        assert restored.scope == "Pride"
        assert len(restored.changes) == 1
        assert restored.changes[0].proposed == {
            "platform_track_id": "NEW",
            "source": "matched",
        }


class TestApplyJournal:
    def test_journal_round_trips_and_reads_newest_first(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.record_journal_entry(
            plan_id="p-1",
            table_name="playlist_track_mappings",
            row_key='{"playlist_id": 1, "track_id": 2, "platform": "tidal"}',
            op="update",
            prior_value={"platform_track_id": "OLD"},
            new_value={"platform_track_id": "NEW"},
        )
        db.record_journal_entry(
            plan_id="p-1",
            table_name="playlist_track_mappings",
            row_key='{"playlist_id": 1, "track_id": 3, "platform": "tidal"}',
            op="insert",
            prior_value=None,
            new_value={"platform_track_id": "X"},
        )

        entries = db.get_journal_entries("p-1")
        # Reverse-chronological for reverse replay: the second write comes first.
        assert len(entries) == 2
        assert entries[0].op == "insert"
        assert entries[0].prior_value is None
        assert entries[0].new_value == {"platform_track_id": "X"}
        assert entries[1].op == "update"
        assert entries[1].prior_value == {"platform_track_id": "OLD"}

    def test_journal_is_scoped_by_plan_id(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.record_journal_entry(
            plan_id="p-1", table_name="t", row_key="k1", op="insert",
            prior_value=None, new_value={"a": 1},
        )
        db.record_journal_entry(
            plan_id="p-2", table_name="t", row_key="k2", op="insert",
            prior_value=None, new_value={"a": 2},
        )
        assert len(db.get_journal_entries("p-1")) == 1
        assert len(db.get_journal_entries("p-2")) == 1
        assert db.has_journal("p-1") is True
        assert db.has_journal("p-3") is False
