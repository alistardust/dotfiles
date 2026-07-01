"""Unit tests for doctor plan file I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from tuneshift.doctor.plan import (
    DoctorPlan,
    PlanError,
    PlanItem,
    plan_path,
    read_plan,
    write_plan,
)


def _item(**kw) -> PlanItem:
    base = dict(
        id=1, track_id=10, playlist="Test", title="Song", artist="Artist",
        issue="unavailable",
    )
    base.update(kw)
    return PlanItem(**base)


def test_plan_path_beside_db():
    db = Path("/tmp/music/tuneshift.db")
    assert plan_path(db) == Path("/tmp/music/.tuneshift/doctor-plan.json")


def test_roundtrip_write_read(tmp_path: Path):
    db = tmp_path / "tuneshift.db"
    plan = DoctorPlan(scope="My Playlist", items=[
        _item(id=1, proposed_platform_id="123", confidence=95),
        _item(id=2, issue="stale_album", proposed_album="Down on the Upside"),
    ])
    written = write_plan(db, plan)
    assert written.exists()

    loaded = read_plan(db)
    assert loaded.scope == "My Playlist"
    assert len(loaded.items) == 2
    assert loaded.items[0].proposed_platform_id == "123"
    assert loaded.items[0].confidence == 95
    assert loaded.items[1].issue == "stale_album"


def test_read_missing_raises(tmp_path: Path):
    with pytest.raises(PlanError, match="No plan found"):
        read_plan(tmp_path / "tuneshift.db")


def test_read_malformed_json_raises(tmp_path: Path):
    db = tmp_path / "tuneshift.db"
    path = plan_path(db)
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json")
    with pytest.raises(PlanError, match="Malformed"):
        read_plan(db)


def test_read_missing_items_key_raises(tmp_path: Path):
    db = tmp_path / "tuneshift.db"
    path = plan_path(db)
    path.parent.mkdir(parents=True)
    path.write_text('{"version": 1}')
    with pytest.raises(PlanError, match="missing 'items'"):
        read_plan(db)


def test_invalid_issue_type_rejected():
    with pytest.raises(ValueError, match="Unknown issue type"):
        _item(issue="bogus")


def test_invalid_status_rejected():
    with pytest.raises(ValueError, match="Unknown status"):
        _item(status="bogus")


def test_actionable_items_filters_applied():
    plan = DoctorPlan(scope="x", items=[
        _item(id=1, status="pending"),
        _item(id=2, status="applied"),
        _item(id=3, status="failed"),
        _item(id=4, status="applied_no_sync"),
        _item(id=5, status="skipped"),
    ])
    ids = [i.id for i in plan.actionable_items()]
    assert ids == [1, 3, 5]


def test_from_dict_ignores_unknown_keys():
    item = PlanItem.from_dict({
        "id": 1, "track_id": 5, "playlist": "P", "title": "T", "artist": "A",
        "issue": "duplicate", "some_future_field": "ignored",
    })
    assert item.id == 1
    assert item.issue == "duplicate"


def test_write_is_atomic_no_tmp_left(tmp_path: Path):
    db = tmp_path / "tuneshift.db"
    write_plan(db, DoctorPlan(scope="x", items=[_item()]))
    leftovers = list((tmp_path / ".tuneshift").glob("*.tmp"))
    assert leftovers == []


def test_get_by_id():
    plan = DoctorPlan(scope="x", items=[_item(id=7)])
    assert plan.get(7).id == 7
    assert plan.get(99) is None
