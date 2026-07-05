"""Chunk 4 gate: end-to-end plan/apply flow across routes (§7, ACs P1-P5).

Proves the routes compose in one database: local (migrate, lock) and remote
(sync) plans coexist, each plan's journal is scoped by plan id, and rolling one
back does not disturb another. This is the integration guarantee the per-route
unit tests don't cover on their own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tuneshift.db import Database
from tuneshift.models import PlatformMapping, PlaylistInfo, Track, TrackResult
from tuneshift.planapply import migrate as migrate_mod
from tuneshift.planapply import sync as sync_mod
from tuneshift.planapply.apply import apply_plan, rollback_plan
from tuneshift.planapply.builders import build_lock_plan
from tuneshift.planapply.migrate import build_migration_plan
from tuneshift.planapply.sync import (
    build_compensating_plan,
    build_sync_plan,
    make_sync_executor,
)
from tuneshift.reconcile import ReconcileResult


class FakeClient:
    platform_name = "tidal"

    def __init__(self) -> None:
        self.playlists: dict[str, list[str]] = {}

    def find_playlist_by_name(self, name: str) -> PlaylistInfo | None:
        pid = f"pl:{name}"
        return PlaylistInfo(platform_id=pid, name=name, num_tracks=0) if pid in self.playlists else None

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        self.playlists.setdefault(f"pl:{name}", [])
        return PlaylistInfo(platform_id=f"pl:{name}", name=name, num_tracks=0)

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackResult]:
        return [TrackResult(platform_id=t, title="", artist="", album="")
                for t in self.playlists.get(playlist_id, [])]

    def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self.playlists[playlist_id] = list(track_ids)


def test_planapply_multiroute_flow(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = Database(tmp_db)
    pid = db.create_playlist("Roadtrip")
    tids = [db.add_track(Track(title=f"S{i}", artist="A", album="Al")) for i in range(2)]
    for pos, t in enumerate(tids):
        db.add_track_to_playlist(pid, t, pos)
    # A stale global mapping for the first track.
    db.upsert_platform_mapping(
        PlatformMapping(track_id=tids[0], platform="tidal",
                        platform_track_id="OLD", status="matched", user_approved=False)
    )

    client = FakeClient()
    client.playlists["pl:Roadtrip"] = ["REMOTE_OLD"]
    db.link_platform_playlist(pid, "tidal", "pl:Roadtrip")

    # Confident re-resolution for both routes.
    def fake_reconcile(db, track_id, client, **kw):  # noqa: ANN001, ANN003
        return ReconcileResult(platform_track_id=f"NEW{track_id}",
                               confidence="high", score=97)

    monkeypatch.setattr(migrate_mod, "reconcile_track", fake_reconcile)
    monkeypatch.setattr(sync_mod, "reconcile_track", fake_reconcile)

    # 1) Migration plan (local): improves the stale global mapping.
    migration = build_migration_plan(db, client, platform="tidal", track_ids=[tids[0]])
    assert apply_plan(db, migration).applied == 1
    assert db.get_platform_mapping(tids[0], "tidal").platform_track_id == f"NEW{tids[0]}"

    # 2) Lock plan (local): per-playlist identity lock on the second track.
    lock = build_lock_plan(db, pid, tids[1], "tidal", "LOCKED_ID")
    assert apply_plan(db, lock).applied == 1
    assert db.get_playlist_track_mapping(pid, tids[1], "tidal")["platform_track_id"] == "LOCKED_ID"

    # 3) Sync plan (remote): push reconciled ids forward.
    sync_plan = build_sync_plan(db, pid, client, platform="tidal")
    executor = make_sync_executor(db, client, platform="tidal")
    assert apply_plan(db, sync_plan, remote_executor=executor).applied == 1
    assert client.playlists["pl:Roadtrip"] == [f"NEW{tids[0]}", f"NEW{tids[1]}"]

    # Roll back ONLY the migration — lock and remote state must be untouched
    # (journals are scoped by plan id).
    rb_migration = rollback_plan(db, migration.plan_id)
    assert rb_migration.reverted == 1
    assert db.get_platform_mapping(tids[0], "tidal").platform_track_id == "OLD"
    assert db.get_playlist_track_mapping(pid, tids[1], "tidal")["platform_track_id"] == "LOCKED_ID"
    assert client.playlists["pl:Roadtrip"] == [f"NEW{tids[0]}", f"NEW{tids[1]}"]

    # Roll back the sync (remote, forward-only) -> compensating plan restores remote.
    rb_sync = rollback_plan(db, sync_plan.plan_id)
    assert rb_sync.remote_skipped == 1
    comp = build_compensating_plan(rb_sync)
    apply_plan(db, comp, remote_executor=executor)
    assert client.playlists["pl:Roadtrip"] == ["REMOTE_OLD"]

    # Roll back the lock (local) independently.
    rb_lock = rollback_plan(db, lock.plan_id)
    assert rb_lock.reverted == 1
    assert db.get_playlist_track_mapping(pid, tids[1], "tidal") is None
