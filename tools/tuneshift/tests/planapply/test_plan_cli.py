"""Chunk 4 Task 4.8: the ``plan`` CLI — generate, show, reject, apply, rollback.

Exercises the migrate + sync routes through the command handler, proving a
generated plan writes a durable file, applies nothing on its own, applies
exactly the resolved plan, and rolls back (local) / yields a compensating plan
(remote).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.commands import plan_cmd
from tuneshift.db import Database
from tuneshift.models import PlatformMapping, PlaylistInfo, Track, TrackResult
from tuneshift.planapply import migrate as migrate_mod
from tuneshift.planapply import sync as sync_mod
from tuneshift.planapply.plan import list_plans, read_plan
from tuneshift.reconcile import ReconcileResult


class FakeClient:
    platform_name = "tidal"

    def __init__(self) -> None:
        self.playlists: dict[str, list[str]] = {}

    def load_session(self) -> bool:
        return True

    def find_playlist_by_name(self, name: str) -> PlaylistInfo | None:
        pid = f"pl:{name}"
        if pid in self.playlists:
            return PlaylistInfo(platform_id=pid, name=name, num_tracks=0)
        return None

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        pid = f"pl:{name}"
        self.playlists.setdefault(pid, [])
        return PlaylistInfo(platform_id=pid, name=name, num_tracks=0)

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackResult]:
        return [
            TrackResult(platform_id=t, title="", artist="", album="")
            for t in self.playlists.get(playlist_id, [])
        ]

    def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self.playlists[playlist_id] = list(track_ids)


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(
        "tuneshift.commands.ingest_cmd._load_client", lambda platform: client
    )
    return client


class TestMigrateCli:
    def test_generate_show_apply_rollback(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
    ) -> None:
        db = Database(tmp_db)
        tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
        db.upsert_platform_mapping(
            PlatformMapping(track_id=tid, platform="tidal", platform_track_id="OLD",
                            status="matched", user_approved=False)
        )
        monkeypatch.setattr(
            migrate_mod, "reconcile_track",
            lambda db, track_id, client, **kw: ReconcileResult(
                platform_track_id="NEW", confidence="high", score=99
            ),
        )

        rc = plan_cmd.handle_plan(
            SimpleNamespace(action="migrate", platform="tidal"), db
        )
        assert rc == 0
        plan_ids = list_plans(db.path)
        assert len(plan_ids) == 1
        plan_id = plan_ids[0]

        # Generation applied nothing (AC-P1).
        assert db.get_platform_mapping(tid, "tidal").platform_track_id == "OLD"

        assert plan_cmd.handle_plan(
            SimpleNamespace(action="show", plan_id=plan_id), db
        ) == 0

        rc = plan_cmd.handle_plan(
            SimpleNamespace(action="apply", plan_id=plan_id,
                            include_locked=False, interactive=False),
            db,
        )
        assert rc == 0
        assert db.get_platform_mapping(tid, "tidal").platform_track_id == "NEW"

        rc = plan_cmd.handle_plan(
            SimpleNamespace(action="rollback", plan_id=plan_id), db
        )
        assert rc == 0
        assert db.get_platform_mapping(tid, "tidal").platform_track_id == "OLD"

    def test_reject_prunes_change_before_apply(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
    ) -> None:
        db = Database(tmp_db)
        tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
        db.upsert_platform_mapping(
            PlatformMapping(track_id=tid, platform="tidal", platform_track_id="OLD",
                            status="matched", user_approved=False)
        )
        monkeypatch.setattr(
            migrate_mod, "reconcile_track",
            lambda db, track_id, client, **kw: ReconcileResult(
                platform_track_id="NEW", confidence="high", score=99
            ),
        )
        plan_cmd.handle_plan(SimpleNamespace(action="migrate", platform="tidal"), db)
        plan_id = list_plans(db.path)[0]

        # Reject the only actionable change, then apply -> nothing changes.
        change_id = read_plan(db.path, plan_id).actionable_changes()[0].change_id
        plan_cmd.handle_plan(
            SimpleNamespace(action="reject", plan_id=plan_id, change_id=change_id), db
        )
        plan_cmd.handle_plan(
            SimpleNamespace(action="apply", plan_id=plan_id,
                            include_locked=False, interactive=False),
            db,
        )
        assert db.get_platform_mapping(tid, "tidal").platform_track_id == "OLD"


class TestSyncCli:
    def test_generate_apply_pushes_then_rollback_compensates(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
    ) -> None:
        db = Database(tmp_db)
        pid = db.create_playlist("Roadtrip")
        tids = [
            db.add_track(Track(title=f"S{i}", artist="A", album="Al")) for i in range(2)
        ]
        for pos, t in enumerate(tids):
            db.add_track_to_playlist(pid, t, pos)
        fake_client.playlists["pl:Roadtrip"] = ["OLD1"]
        db.link_platform_playlist(pid, "tidal", "pl:Roadtrip")

        monkeypatch.setattr(
            sync_mod, "reconcile_track",
            lambda db, track_id, client, **kw: ReconcileResult(
                platform_track_id=f"NEW{track_id}", confidence="high", score=95
            ),
        )

        rc = plan_cmd.handle_plan(
            SimpleNamespace(action="sync", playlist="Roadtrip",
                            platform="tidal", reconcile=False),
            db,
        )
        assert rc == 0
        plan_id = list_plans(db.path)[0]
        # Nothing pushed on generation (AC-P1).
        assert fake_client.playlists["pl:Roadtrip"] == ["OLD1"]

        rc = plan_cmd.handle_plan(
            SimpleNamespace(action="apply", plan_id=plan_id,
                            include_locked=False, interactive=False),
            db,
        )
        assert rc == 0
        assert fake_client.playlists["pl:Roadtrip"] == [f"NEW{tids[0]}", f"NEW{tids[1]}"]

        # Rollback of a remote push writes a compensating plan (a 2nd saved plan).
        rc = plan_cmd.handle_plan(
            SimpleNamespace(action="rollback", plan_id=plan_id), db
        )
        assert rc == 0
        assert len(list_plans(db.path)) == 2
