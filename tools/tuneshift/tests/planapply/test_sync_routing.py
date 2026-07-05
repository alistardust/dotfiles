"""Chunk 4 Task 4.6: sync remote push is ROUTED, forward-only, compensable.

A sync push goes through the plan/apply engine as a ``remote_push`` change: it
is executed by a remote executor, journaled under a ``remote:`` table, and never
un-pushed by rollback — rollback surfaces a compensating plan instead (AC-P4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tuneshift.db import Database
from tuneshift.models import PlaylistInfo, Track, TrackResult
from tuneshift.planapply import sync as sync_mod
from tuneshift.planapply.apply import apply_plan, rollback_plan
from tuneshift.planapply.sync import (
    build_compensating_plan,
    build_sync_plan,
    make_sync_executor,
)
from tuneshift.reconcile import ReconcileResult


class FakeClient:
    """In-memory stand-in for a platform client (protocol subset used by sync)."""

    platform_name = "tidal"

    def __init__(self) -> None:
        self.playlists: dict[str, list[str]] = {}
        self._next = 1

    def find_playlist_by_name(self, name: str) -> PlaylistInfo | None:
        for pid in self.playlists:
            if pid == f"pl:{name}":
                return PlaylistInfo(platform_id=pid, name=name, num_tracks=0)
        return None

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        pid = f"pl:{name}"
        self.playlists.setdefault(pid, [])
        return PlaylistInfo(platform_id=pid, name=name, num_tracks=0)

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackResult]:
        return [
            TrackResult(platform_id=tid, title="", artist="", album="")
            for tid in self.playlists.get(playlist_id, [])
        ]

    def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self.playlists[playlist_id] = list(track_ids)


def _seed(tmp_db: Path) -> tuple[Database, int, list[int]]:
    db = Database(tmp_db)
    pid = db.create_playlist("Roadtrip")
    tids = [
        db.add_track(Track(title=f"Song {i}", artist="Artist", album="Album"))
        for i in range(3)
    ]
    for pos, tid in enumerate(tids):
        db.add_track_to_playlist(pid, tid, pos)
    return db, pid, tids


def _stub_reconcile(monkeypatch, mapping: dict[int, str]) -> None:
    """Make reconcile_track return a confident id per track id (read-only)."""

    def fake(db, track_id, client, **kwargs):  # noqa: ANN001, ANN003
        tid = mapping.get(track_id)
        if tid is None:
            return ReconcileResult(confidence="not_found")
        return ReconcileResult(platform_track_id=tid, confidence="high", score=95)

    monkeypatch.setattr(sync_mod, "reconcile_track", fake)


class TestSyncRouting:
    def test_build_emits_single_remote_push_and_mutates_nothing(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A", tids[1]: "B", tids[2]: "C"})
        client = FakeClient()

        plan = build_sync_plan(db, pid, client, platform="tidal")

        assert len(plan.changes) == 1
        change = plan.changes[0]
        assert change.op == "remote_push"
        assert change.remote is True
        assert change.table == "remote:tidal"
        assert change.proposed["track_ids"] == ["A", "B", "C"]
        # Nothing pushed until apply.
        assert client.playlists == {}

    def test_apply_pushes_then_rollback_is_forward_only_with_compensation(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A", tids[1]: "B", tids[2]: "C"})
        client = FakeClient()
        # Remote already exists with an OLD order, linked locally.
        client.playlists["pl:Roadtrip"] = ["OLD1", "OLD2"]
        db.link_platform_playlist(pid, "tidal", "pl:Roadtrip")

        plan = build_sync_plan(db, pid, client, platform="tidal")
        executor = make_sync_executor(db, client, platform="tidal")
        report = apply_plan(db, plan, remote_executor=executor)

        assert report.applied == 1
        assert client.playlists["pl:Roadtrip"] == ["A", "B", "C"]

        # Rollback does NOT un-push inline; it surfaces a compensating plan.
        rb = rollback_plan(db, plan.plan_id)
        assert rb.reverted == 0
        assert rb.remote_skipped == 1
        assert len(rb.compensating) == 1
        assert client.playlists["pl:Roadtrip"] == ["A", "B", "C"]  # untouched

        comp = build_compensating_plan(rb)
        apply_plan(db, comp, remote_executor=executor)
        # The compensating push restores the prior remote order.
        assert client.playlists["pl:Roadtrip"] == ["OLD1", "OLD2"]

    def test_apply_creates_and_links_remote_playlist_when_absent(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A", tids[1]: "B", tids[2]: "C"})
        client = FakeClient()

        plan = build_sync_plan(db, pid, client, platform="tidal")
        executor = make_sync_executor(db, client, platform="tidal")
        apply_plan(db, plan, remote_executor=executor)

        assert client.playlists["pl:Roadtrip"] == ["A", "B", "C"]
        assert db.get_platform_playlist_id(pid, "tidal") == "pl:Roadtrip"

    def test_sync_is_idempotent_when_remote_matches(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A", tids[1]: "B", tids[2]: "C"})
        client = FakeClient()
        client.playlists["pl:Roadtrip"] = ["A", "B", "C"]
        db.link_platform_playlist(pid, "tidal", "pl:Roadtrip")

        plan = build_sync_plan(db, pid, client, platform="tidal")
        assert plan.is_empty()

    def test_remote_push_without_executor_fails_loudly(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A"})
        client = FakeClient()

        plan = build_sync_plan(db, pid, client, platform="tidal")
        report = apply_plan(db, plan)  # no remote_executor supplied
        assert report.failed == 1
        assert report.applied == 0
        assert "remote_executor" in report.errors[0]

    def test_new_link_is_journaled_and_removed_on_rollback(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A find-or-create link is a LOCAL write; it must be journaled so a
        # rollback reverses it, not orphaned pointing at a remote we've "forgotten"
        # how we created (AC-P4 local reversibility).
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A", tids[1]: "B", tids[2]: "C"})
        client = FakeClient()

        plan = build_sync_plan(db, pid, client, platform="tidal")
        executor = make_sync_executor(db, client, platform="tidal")
        apply_plan(db, plan, remote_executor=executor)
        assert db.get_platform_playlist_id(pid, "tidal") == "pl:Roadtrip"

        rollback_plan(db, plan.plan_id)
        # The link the sync created is gone; the remote push is left for the
        # compensating plan (forward-only).
        assert db.get_platform_playlist_id(pid, "tidal") is None

    def test_failed_push_does_not_orphan_a_link(
        self, tmp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If the remote push fails, the just-created link must roll back with the
        # rest of the apply transaction (no self-committing write escaping it).
        db, pid, tids = _seed(tmp_db)
        _stub_reconcile(monkeypatch, {tids[0]: "A", tids[1]: "B", tids[2]: "C"})

        class FailingClient(FakeClient):
            def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
                raise RuntimeError("remote push failed")

        client = FailingClient()
        plan = build_sync_plan(db, pid, client, platform="tidal")
        executor = make_sync_executor(db, client, platform="tidal")
        report = apply_plan(db, plan, remote_executor=executor)

        assert report.failed == 1
        assert report.applied == 0
        # No orphaned link left behind by the failed apply.
        assert db.get_platform_playlist_id(pid, "tidal") is None
