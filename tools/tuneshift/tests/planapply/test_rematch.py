"""Chunk 4 Task 4.4: re-match produces a plan, mutates nothing until apply.

A per-playlist re-match runs the selection engine (via ``reconcile_track``) and
emits ``playlist_track_mappings`` ``current -> proposed`` changes into a
:class:`Plan`. The DB is untouched until :func:`apply_plan` runs the plan
(AC-P1). Confident improvements are actionable; ambiguous / not-found results are
classified ``needs-human-judgment`` and left for triage, never silently written.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.planapply.apply import apply_plan
from tuneshift.planapply.rematch import build_rematch_plan


def _client(results: list[TrackResult]) -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_track.return_value = results
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def _seed_playlist(tmp_db: Path) -> tuple[Database, int, int]:
    db = Database(tmp_db)
    pid = db.create_playlist("Pride")
    tid = db.add_track(Track(title="Wonderwall", artist="Oasis", album="Morning Glory"))
    db.add_track_to_playlist(pid, tid, 0)
    return db, pid, tid


def test_rematch_builds_plan_without_mutating(tmp_db: Path) -> None:
    db, pid, tid = _seed_playlist(tmp_db)
    candidates = [
        TrackResult(
            platform_id="TIDAL_MATCH", title="Wonderwall", artist="Oasis",
            album="Morning Glory", available=True,
        )
    ]
    plan = build_rematch_plan(db, pid, _client(candidates), platform="tidal")

    # A confident match proposes a mapping change...
    actionable = [c for c in plan.changes if c.is_actionable]
    assert len(actionable) == 1
    assert actionable[0].table == "playlist_track_mappings"
    assert actionable[0].proposed["platform_track_id"] == "TIDAL_MATCH"
    # ...but nothing is written yet.
    assert db.get_playlist_track_mapping(pid, tid, "tidal") is None


def test_apply_of_rematch_plan_writes_mapping(tmp_db: Path) -> None:
    db, pid, tid = _seed_playlist(tmp_db)
    candidates = [
        TrackResult(
            platform_id="TIDAL_MATCH", title="Wonderwall", artist="Oasis",
            album="Morning Glory", available=True,
        )
    ]
    plan = build_rematch_plan(db, pid, _client(candidates), platform="tidal")
    report = apply_plan(db, plan)

    assert report.applied == 1
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "TIDAL_MATCH"


def test_rematch_of_unchanged_mapping_is_noop(tmp_db: Path) -> None:
    db, pid, tid = _seed_playlist(tmp_db)
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "TIDAL_MATCH", source="matched", user_approved=False
    )
    candidates = [
        TrackResult(
            platform_id="TIDAL_MATCH", title="Wonderwall", artist="Oasis",
            album="Morning Glory", available=True,
        )
    ]
    plan = build_rematch_plan(db, pid, _client(candidates), platform="tidal")
    # Proposed == current -> unchanged, not actionable (idempotency).
    assert plan.actionable_changes() == []
    report = apply_plan(db, plan)
    assert report.applied == 0


def test_rematch_marks_user_approved_mapping_locked(tmp_db: Path) -> None:
    db, pid, tid = _seed_playlist(tmp_db)
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "PINNED", source="locked", user_approved=True
    )
    candidates = [
        TrackResult(
            platform_id="DIFFERENT", title="Wonderwall", artist="Oasis",
            album="Morning Glory", available=True,
        )
    ]
    plan = build_rematch_plan(db, pid, _client(candidates), platform="tidal")
    # The change touching the approved row is present but marked locked ->
    # excluded from apply by default (AC-P3).
    locked = [c for c in plan.changes if c.locked]
    assert len(locked) == 1
    report = apply_plan(db, plan)
    assert report.applied == 0
    assert report.skipped_locked == 1
    # The pin is untouched.
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "PINNED"
