"""Tests for the doctor applier."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tuneshift.db import Database
from tuneshift.doctor.applier import apply_plan, preview_apply
from tuneshift.doctor.plan import DoctorPlan, PlanItem
from tuneshift.models import AlbumResult, PlatformMapping, Track


@pytest.fixture
def db():
    path = Path(tempfile.mkdtemp()) / "t.db"
    return Database(path)


@pytest.fixture(autouse=True)
def _no_rate_limit_or_network(monkeypatch):
    """Neutralize the rate limiter and re-enrichment fetch in the applier."""
    from tuneshift.enrichment import platform_metadata

    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)
    monkeypatch.setattr(
        platform_metadata, "fetch_track_report",
        lambda client, pid: {"metadata": {}}, raising=True,
    )


class FakeClient:
    def __init__(self, albums=None):
        self._albums = albums or []
        self.searched = []

    def load_session(self):
        return True

    def search_album(self, query, limit=5):
        self.searched.append(query)
        return self._albums


def _mapped_track(db, title, artist, album, tidal_id):
    tid = db.add_track(Track(title=title, artist=artist, album=album))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=tid, platform="tidal", platform_track_id=tidal_id,
        platform_title=title, platform_artist=artist, platform_album=album,
        status="matched", user_approved=True,
    ))
    return tid


def test_remap_updates_platform_mapping(db):
    tid = _mapped_track(db, "Song", "Artist", "Album", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="version_mismatch", current_platform_id="OLD",
        proposed_platform_id="NEW", proposed_title="Song", proposed_album="Album",
        confidence=95, resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], client=FakeClient(), do_sync=False)

    assert result.applied == 1
    assert item.status == "applied"
    m = db.get_platform_mappings_for_tracks([tid], "tidal")[tid]
    assert m.platform_track_id == "NEW"


def test_manual_item_without_override_is_skipped(db):
    tid = _mapped_track(db, "Song", "Artist", "Album", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="unavailable", current_platform_id="OLD",
        proposed_platform_id="", resolution="manual",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], client=FakeClient(), do_sync=False)

    assert result.skipped == 1
    assert item.status == "skipped"


def test_manual_item_with_low_confidence_proposal_is_skipped(db):
    """A low-confidence proposal must NOT be applied in bulk without override."""
    tid = _mapped_track(db, "Song", "Artist", "Album", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="unmapped", current_platform_id="",
        proposed_platform_id="GUESS", confidence=60, resolution="manual",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], client=FakeClient(), do_sync=False)

    assert result.skipped == 1
    assert result.applied == 0
    assert item.status == "skipped"
    # The low-confidence guess must not have been written.
    assert db.get_platform_mappings_for_tracks([tid], "tidal")[tid].platform_track_id != "GUESS"


def test_override_forces_remap_for_manual_item(db):
    tid = _mapped_track(db, "Song", "Artist", "Album", "OLD")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="unavailable", current_platform_id="OLD",
        proposed_platform_id="", resolution="manual",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], overrides={1: "FORCED"},
                        client=FakeClient(), do_sync=False)

    assert result.applied == 1
    m = db.get_platform_mappings_for_tracks([tid], "tidal")[tid]
    assert m.platform_track_id == "FORCED"


def test_duplicate_merges_tracks(db):
    pid = db.create_playlist("P")
    keep = _mapped_track(db, "Song", "Artist", "Album", "K")
    dup = _mapped_track(db, "Song", "The Artist", "Album", "D")
    db.add_track_to_playlist(pid, keep, 0)
    db.add_track_to_playlist(pid, dup, 1)
    item = PlanItem(
        id=1, track_id=keep, playlist="P", title="Song", artist="Artist",
        issue="duplicate", keep_track_id=keep, merge_track_ids=[dup],
        resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], client=FakeClient(), do_sync=False)

    assert result.applied == 1
    assert db.get_track(dup) is None
    assert db.get_playlist_track_ids(pid) == [keep]


def test_duplicate_override_changes_keep(db):
    pid = db.create_playlist("P")
    a = _mapped_track(db, "Song", "Artist", "Album", "A")
    b = _mapped_track(db, "Song", "Artist B", "Album", "B")
    db.add_track_to_playlist(pid, a, 0)
    db.add_track_to_playlist(pid, b, 1)
    item = PlanItem(
        id=1, track_id=a, playlist="P", title="Song", artist="Artist",
        issue="duplicate", keep_track_id=a, merge_track_ids=[b],
        resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])

    apply_plan(db, plan, [item], overrides={1: str(b)},
               client=FakeClient(), do_sync=False)

    assert db.get_track(a) is None
    assert db.get_track(b) is not None


def test_stale_album_recovers_release_year(db):
    tid = _mapped_track(db, "Song", "Artist", "Greatest Hits", "T1")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="stale_album", current_platform_id="T1", resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])
    client = FakeClient(albums=[
        AlbumResult(platform_id="AL1", title="Greatest Hits",
                    artist="Artist", release_year=1999),
    ])

    result = apply_plan(db, plan, [item], client=client, do_sync=False)

    assert result.applied == 1
    meta = db.get_track_platform_metadata(tid, "tidal")
    assert meta["release_year"] == 1999


def test_stale_album_fails_when_unrecoverable(db):
    tid = _mapped_track(db, "Song", "Artist", "Lost Album", "T1")
    item = PlanItem(
        id=1, track_id=tid, playlist="P", title="Song", artist="Artist",
        issue="stale_album", current_platform_id="T1", resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], client=FakeClient(albums=[]),
                        do_sync=False)

    assert result.failed == 1
    assert item.status == "failed"


def test_partial_success_one_fails_others_apply(db):
    good = _mapped_track(db, "Good", "Artist", "Album", "OLD")
    bad = _mapped_track(db, "Bad", "Artist", "Album", "OLD2")
    good_item = PlanItem(
        id=1, track_id=good, playlist="P", title="Good", artist="Artist",
        issue="version_mismatch", current_platform_id="OLD",
        proposed_platform_id="NEW", resolution="auto",
    )
    # Missing proposed id + not manual → remap raises ApplyError → failed.
    bad_item = PlanItem(
        id=2, track_id=bad, playlist="P", title="Bad", artist="Artist",
        issue="version_mismatch", current_platform_id="OLD2",
        proposed_platform_id="", resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[good_item, bad_item])

    result = apply_plan(db, plan, [good_item, bad_item],
                        client=FakeClient(), do_sync=False)

    assert result.applied == 1
    assert result.failed == 1
    assert good_item.status == "applied"
    assert bad_item.status == "failed"


def test_duplicate_override_rejects_id_outside_group(db):
    pid = db.create_playlist("P")
    a = _mapped_track(db, "Song", "Artist", "Album", "A")
    b = _mapped_track(db, "Song", "Artist B", "Album", "B")
    db.add_track_to_playlist(pid, a, 0)
    db.add_track_to_playlist(pid, b, 1)
    item = PlanItem(
        id=1, track_id=a, playlist="P", title="Song", artist="Artist",
        issue="duplicate", keep_track_id=a, merge_track_ids=[b],
        resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])

    result = apply_plan(db, plan, [item], overrides={1: "9999"},
                        client=FakeClient(), do_sync=False)

    assert result.failed == 1
    assert "not part of" in item.note


def test_preview_apply_classifies_actions():
    auto = PlanItem(id=1, track_id=1, playlist="P", title="A", artist="X",
                    issue="version_mismatch", proposed_platform_id="N1",
                    confidence=90, resolution="auto")
    manual = PlanItem(id=2, track_id=2, playlist="P", title="B", artist="X",
                      issue="unmapped", proposed_platform_id="N2",
                      confidence=55, resolution="manual")
    dup = PlanItem(id=3, track_id=3, playlist="P", title="C", artist="X",
                   issue="duplicate", keep_track_id=3, merge_track_ids=[4],
                   resolution="auto")

    preview = preview_apply([auto, manual, dup], overrides={2: "FORCED"})
    actions = {item.id: action for item, action, _ in preview}

    assert actions == {1: "auto", 2: "override", 3: "auto"}


def test_preview_apply_skips_manual_without_override():
    manual = PlanItem(id=1, track_id=1, playlist="P", title="B", artist="X",
                      issue="unmapped", proposed_platform_id="N2",
                      confidence=55, resolution="manual")
    preview = preview_apply([manual], overrides={})
    assert preview[0][1] == "skip"
