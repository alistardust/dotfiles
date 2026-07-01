"""Command-layer tests for `tuneshift doctor` (apply path + helpers)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.commands import doctor_cmd
from tuneshift.db import Database
from tuneshift.doctor.plan import DoctorPlan, PlanItem, read_plan, write_plan
from tuneshift.models import PlatformMapping, Track


@pytest.fixture
def db():
    return Database(Path(tempfile.mkdtemp()) / "t.db")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    from tuneshift.enrichment import platform_metadata

    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)
    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda client, pid: {"metadata": {}}, raising=True,
    )


class FakeClient:
    def load_session(self):
        return True

    def search_album(self, query, limit=5):
        return []


def _mapped_track(db, title, artist, tidal_id):
    tid = db.add_track(Track(title=title, artist=artist, album="Album"))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=tid, platform="tidal", platform_track_id=tidal_id,
        status="matched", user_approved=True,
    ))
    return tid


def test_parse_overrides_valid():
    overrides, err = doctor_cmd._parse_overrides(["1=ABC", "2=DEF"])
    assert err is None
    assert overrides == {1: "ABC", 2: "DEF"}


def test_parse_overrides_rejects_bad_format():
    _, err = doctor_cmd._parse_overrides(["nope"])
    assert err is not None


def test_apply_missing_plan_returns_2(db):
    args = SimpleNamespace(apply=True, only=None, override=None,
                           no_sync=True, yes=True, quiet=True)
    assert doctor_cmd.handle_doctor(args, db) == 2


def test_apply_applies_plan_and_persists_status(db, monkeypatch):
    tid = _mapped_track(db, "Song", "Artist", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="version_mismatch", current_platform_id="OLD",
        proposed_platform_id="NEW", resolution="auto", confidence=95,
    )
    write_plan(db.path, DoctorPlan(scope="P", items=[item]))

    monkeypatch.setattr(doctor_cmd, "_load_tidal_client",
                        lambda: (FakeClient(), None))

    args = SimpleNamespace(apply=True, only=None, override=None,
                           no_sync=True, yes=True, quiet=True)
    rc = doctor_cmd.handle_doctor(args, db)

    assert rc == 0
    m = db.get_platform_mappings_for_tracks([tid], "tidal")[tid]
    assert m.platform_track_id == "NEW"
    # Status persisted back to the plan file.
    reloaded = read_plan(db.path)
    assert reloaded.get(1).status == "applied"


def test_apply_partial_failure_returns_1(db, monkeypatch):
    good = _mapped_track(db, "Good", "Artist", "OLD")
    bad = _mapped_track(db, "Bad", "Artist", "OLD2")
    items = [
        PlanItem(id=1, track_id=good, playlist="P", title="Good", artist="Artist",
                 issue="version_mismatch", proposed_platform_id="NEW",
                 resolution="auto"),
        PlanItem(id=2, track_id=bad, playlist="P", title="Bad", artist="Artist",
                 issue="version_mismatch", proposed_platform_id="",
                 resolution="auto"),
    ]
    write_plan(db.path, DoctorPlan(scope="P", items=items))
    monkeypatch.setattr(doctor_cmd, "_load_tidal_client",
                        lambda: (FakeClient(), None))

    args = SimpleNamespace(apply=True, only=None, override=None,
                           no_sync=True, yes=True, quiet=True)
    rc = doctor_cmd.handle_doctor(args, db)

    assert rc == 1


def test_apply_only_filters_items(db, monkeypatch):
    a = _mapped_track(db, "A", "Artist", "OLDA")
    b = _mapped_track(db, "B", "Artist", "OLDB")
    items = [
        PlanItem(id=1, track_id=a, playlist="P", title="A", artist="Artist",
                 issue="version_mismatch", proposed_platform_id="NEWA",
                 resolution="auto"),
        PlanItem(id=2, track_id=b, playlist="P", title="B", artist="Artist",
                 issue="version_mismatch", proposed_platform_id="NEWB",
                 resolution="auto"),
    ]
    write_plan(db.path, DoctorPlan(scope="P", items=items))
    monkeypatch.setattr(doctor_cmd, "_load_tidal_client",
                        lambda: (FakeClient(), None))

    args = SimpleNamespace(apply=True, only=[1], override=None,
                           no_sync=True, yes=True, quiet=True)
    doctor_cmd.handle_doctor(args, db)

    # Only item 1 applied; item 2 untouched.
    assert db.get_platform_mappings_for_tracks([a], "tidal")[a].platform_track_id == "NEWA"
    assert db.get_platform_mappings_for_tracks([b], "tidal")[b].platform_track_id == "OLDB"


def test_scan_requires_playlist_or_all(db):
    args = SimpleNamespace(apply=False, all=False, playlist=None, quiet=True)
    assert doctor_cmd.handle_doctor(args, db) == 2


def test_apply_dry_run_makes_no_changes(db, monkeypatch, capsys):
    tid = _mapped_track(db, "Song", "Artist", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="version_mismatch", proposed_platform_id="NEW",
        confidence=95, resolution="auto",
    )
    write_plan(db.path, DoctorPlan(scope="P", items=[item]))
    monkeypatch.setattr(doctor_cmd, "_load_tidal_client",
                        lambda: (FakeClient(), None))

    args = SimpleNamespace(apply=True, only=None, override=None, no_sync=True,
                           dry_run=True, yes=True, quiet=True)
    rc = doctor_cmd.handle_doctor(args, db)

    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    # Mapping unchanged.
    assert db.get_platform_mappings_for_tracks([tid], "tidal")[tid].platform_track_id == "OLD"
    # Plan status not persisted as applied.
    assert read_plan(db.path).get(1).status == "pending"


def test_apply_only_manual_item_is_skipped_without_override(db, monkeypatch):
    tid = _mapped_track(db, "Song", "Artist", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="unmapped", proposed_platform_id="GUESS", confidence=60,
        resolution="manual",
    )
    write_plan(db.path, DoctorPlan(scope="P", items=[item]))
    monkeypatch.setattr(doctor_cmd, "_load_tidal_client",
                        lambda: (FakeClient(), None))

    args = SimpleNamespace(apply=True, only=[1], override=None, no_sync=True,
                           dry_run=False, yes=True, quiet=True)
    rc = doctor_cmd.handle_doctor(args, db)

    # Manual item selected but not overridden -> skipped, exit 1 (not fully applied).
    assert rc == 1
    assert db.get_platform_mappings_for_tracks([tid], "tidal")[tid].platform_track_id == "OLD"
    assert read_plan(db.path).get(1).status == "skipped"
