"""Chunk 5 Task 5.3: lock self-heal is ROUTED, never mutated inline (AC-L3, §7.1).

When a locked release genuinely disappears, the engine does NOT silently swap it.
``build_heal_plan`` verifies the locked id's liveness and PROPOSES the outcome
into a reviewable :class:`Plan`:

- locked id alive / undeterminable -> no change,
- locked id dead + same-recording equivalent found -> propose re-bind (surfaced
  for review; applied only with ``include_locked``),
- locked id dead + no equivalent -> propose hold-as-unavailable.

``reconcile_track(verify_locked=True)`` is a pure query: it reports a dead lock as
held/needs-review but never writes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import PlatformMapping, Track, TrackResult
from tuneshift.planapply.apply import apply_plan
from tuneshift.planapply.heal import build_heal_plan
from tuneshift.reconcile import reconcile_track


def _client() -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_track.return_value = []
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def _seed_global_lock(db: Database, *, pid="dead999", isrc=None, duration=195) -> int:
    track_id = db.add_track(Track(
        title="Heroes", artist="David Bowie", album="Heroes",
        duration_seconds=duration, isrc=isrc,
    ))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=track_id, platform="tidal", platform_track_id=pid,
        match_score=97, status="matched", user_approved=True,
    ))
    return track_id


class TestReconcileVerifyIsPure:
    def test_dead_lock_reported_held_without_writing(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db, pid="dead999")
        client = _client()
        client.get_track.return_value = None  # locked id is gone
        client.search_track.return_value = [TrackResult(
            platform_id="new456", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=195, available=True,
        )]

        result = reconcile_track(db, track_id, client, verify_locked=True)

        # Held, surfaced — never silently swapped.
        assert result.availability == "exact_unavailable"
        assert result.reason_code == "lock_held"
        # DB is untouched: the lock still points at the dead id, still matched.
        stored = db.get_platform_mapping(track_id, "tidal")
        assert stored.platform_track_id == "dead999"
        assert stored.status == "matched"
        assert stored.user_approved is True

    def test_alive_lock_kept_without_writing(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db)
        client = _client()
        client.get_track.return_value = TrackResult(
            platform_id="dead999", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=195, available=True,
        )
        result = reconcile_track(db, track_id, client, verify_locked=True)
        assert result.platform_track_id == "dead999"
        assert result.reason_code == "locked"
        assert result.availability == "exact_available"


class TestBuildHealPlan:
    def test_dead_lock_proposes_rebind(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db, pid="dead999", duration=195)
        client = _client()
        client.get_track.return_value = None
        client.search_track.return_value = [TrackResult(
            platform_id="new456", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=195, available=True,
        )]

        plan = build_heal_plan(db, client, platform="tidal", track_ids=[track_id])

        assert len(plan.changes) == 1
        change = plan.changes[0]
        assert change.table == "platform_tracks"
        assert change.classification == "improved"
        assert change.reason == "lock_healed"
        assert change.proposed["platform_track_id"] == "new456"
        assert change.proposed["user_approved"] == 1
        assert change.locked is True  # touches the locked row; needs include_locked

    def test_dead_lock_no_equivalent_proposes_hold(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db, pid="dead999", duration=195)
        client = _client()
        client.get_track.return_value = None
        client.search_track.return_value = [TrackResult(
            platform_id="live777", title="Heroes (Live)", artist="David Bowie",
            album="Stage", duration_seconds=360, available=True,
        )]

        plan = build_heal_plan(db, client, platform="tidal", track_ids=[track_id])

        assert len(plan.changes) == 1
        change = plan.changes[0]
        assert change.reason == "lock_held"
        assert change.proposed["status"] == "unavailable"
        assert change.proposed["platform_track_id"] == "dead999"  # never swapped

    def test_alive_lock_proposes_no_change(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db)
        client = _client()
        client.get_track.return_value = TrackResult(
            platform_id="dead999", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=195, available=True,
        )
        plan = build_heal_plan(db, client, platform="tidal", track_ids=[track_id])
        assert plan.changes == []

    def test_heal_surfaced_but_not_applied_by_default(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db, pid="dead999", duration=195)
        client = _client()
        client.get_track.return_value = None
        client.search_track.return_value = [TrackResult(
            platform_id="new456", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=195, available=True,
        )]
        plan = build_heal_plan(db, client, platform="tidal", track_ids=[track_id])

        # Default apply protects the locked row — the heal is surfaced, not silent.
        report = apply_plan(db, plan)
        assert report.applied == 0
        assert report.skipped_locked == 1
        assert db.get_platform_mapping(track_id, "tidal").platform_track_id == "dead999"

        # An explicit include_locked apply (the reviewed "yes, heal it") re-binds.
        report2 = apply_plan(db, plan, include_locked=True)
        assert report2.applied == 1
        stored = db.get_platform_mapping(track_id, "tidal")
        assert stored.platform_track_id == "new456"
        assert stored.user_approved is True  # still locked after heal

    def test_dead_lock_heals_via_isrc_equivalence(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = _seed_global_lock(db, pid="dead999", isrc="GBAYE7700012", duration=195)
        client = _client()
        client.get_track.return_value = None
        client.search_track.return_value = [TrackResult(
            platform_id="new456", title="Heroes (2017 Remaster)", artist="David Bowie",
            album="Heroes (2017 Remaster)", duration_seconds=372,
            isrc="GBAYE7700012", available=True,
        )]

        plan = build_heal_plan(db, client, platform="tidal", track_ids=[track_id])

        assert len(plan.changes) == 1
        assert plan.changes[0].reason == "lock_healed"
        assert plan.changes[0].proposed["platform_track_id"] == "new456"

    def test_playlist_scope_heal_targets_playlist_mapping(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id = db.add_track(Track(
            title="Buddy", artist="De La Soul", album="3 Feet High",
            duration_seconds=200,
        ))
        pid = db.create_playlist("Native Tongues")
        db.add_track_to_playlist(pid, track_id, 0)
        db.set_playlist_track_mapping(
            pid, track_id, "tidal", "pldead", source="locked", user_approved=True
        )
        client = _client()
        client.get_track.return_value = None
        client.search_track.return_value = [TrackResult(
            platform_id="plnew", title="Buddy", artist="De La Soul",
            album="3 Feet High", duration_seconds=200, available=True,
        )]

        plan = build_heal_plan(db, client, platform="tidal", playlist_id=pid)

        assert len(plan.changes) == 1
        change = plan.changes[0]
        assert change.table == "playlist_track_mappings"
        assert change.proposed["platform_track_id"] == "plnew"
