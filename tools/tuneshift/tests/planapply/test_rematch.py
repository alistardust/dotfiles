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
from tuneshift.models import PlatformMapping, Track, TrackResult
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
    # The change touching the approved row is present, marked locked, and
    # classified "locked" — never proposed for a change to a DIFFERENT release
    # (AC-L2). It is excluded from apply by default (AC-P3).
    locked = [c for c in plan.changes if c.locked]
    assert len(locked) == 1
    assert locked[0].classification == "locked"
    assert locked[0].proposed["platform_track_id"] == "PINNED"
    report = apply_plan(db, plan)
    assert report.applied == 0
    assert report.skipped_locked == 1
    # The pin is untouched.
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "PINNED"


def test_rematch_locked_reaffirms_effective_lock_not_stale_playlist_row(tmp_db: Path) -> None:
    """AC-L1/L2/L4: when a stale UNAPPROVED playlist row coexists with an approved
    GLOBAL lock, the plan must re-affirm the effective (global) lock id — never
    cement the unapproved playlist id as though it were the lock.

    Regression guard: the locked branch previously took ``current_id`` from any
    playlist row and only checked approval at either scope, so it proposed the
    unapproved playlist id as the locked release.
    """
    db, pid, tid = _seed_playlist(tmp_db)
    # Approved GLOBAL lock — the authoritative identity.
    db.upsert_platform_mapping(PlatformMapping(
        track_id=tid, platform="tidal", platform_track_id="GLOBAL",
        match_score=97, status="matched", user_approved=True,
    ))
    # Stale UNAPPROVED playlist auto-row pointing elsewhere.
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "AUTO_PL", source="matched", user_approved=False
    )
    plan = build_rematch_plan(db, pid, _client([]), platform="tidal")

    locked = [c for c in plan.changes if c.locked]
    assert len(locked) == 1
    assert locked[0].classification == "locked"
    # Re-affirms the GLOBAL lock, never the stale unapproved playlist id.
    assert locked[0].proposed["platform_track_id"] == "GLOBAL"


def test_rematch_flags_locked_version_downgrade(tmp_db: Path) -> None:
    """AC-L5: a still-live locked id whose metadata degraded is FLAGGED, not swapped.

    The playlist prefers ``spatial=atmos`` and the locked release used to carry
    Atmos. The id still exists, but Tidal has dropped the Atmos mode (now stereo
    only), so it no longer satisfies the preference. The re-doctor plan surfaces
    a ``downgrade-flag`` for Alice to decide; the lock is never broken and never
    silently accepted-as-degraded. Distinct from AC-L3 (disappearance).
    """
    db, pid, tid = _seed_playlist(tmp_db)
    db.set_preferences(pid, {"prefer": ["atmos"]})
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "ATMOS_ID", source="locked", user_approved=True
    )
    client = _client([])
    # The locked id is alive but no longer Atmos — the degradation AC-L5 covers.
    client.get_track.return_value = TrackResult(
        platform_id="ATMOS_ID", title="Wonderwall", artist="Oasis",
        album="Morning Glory", available=True, audio_modes=["STEREO"],
    )

    plan = build_rematch_plan(db, pid, client, platform="tidal")

    flagged = [c for c in plan.changes if c.classification == "downgrade-flag"]
    assert len(flagged) == 1
    change = flagged[0]
    assert change.locked is True
    assert change.status == "skipped"
    assert change.proposed["platform_track_id"] == "ATMOS_ID"  # lock re-affirmed
    assert "spatial" in change.reason and "atmos" in change.reason

    # Applying the plan never touches the lock (surfaced, not acted on).
    report = apply_plan(db, plan)
    assert report.applied == 0
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "ATMOS_ID"
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["user_approved"] == 1


def test_rematch_locked_no_flag_when_pref_still_satisfied(tmp_db: Path) -> None:
    """A locked id that STILL satisfies the preference is a plain locked skip."""
    db, pid, tid = _seed_playlist(tmp_db)
    db.set_preferences(pid, {"prefer": ["atmos"]})
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "ATMOS_ID", source="locked", user_approved=True
    )
    client = _client([])
    client.get_track.return_value = TrackResult(
        platform_id="ATMOS_ID", title="Wonderwall", artist="Oasis",
        album="Morning Glory", available=True, audio_modes=["DOLBY_ATMOS", "STEREO"],
    )

    plan = build_rematch_plan(db, pid, client, platform="tidal")

    assert not [c for c in plan.changes if c.classification == "downgrade-flag"]
    locked = [c for c in plan.changes if c.locked]
    assert len(locked) == 1
    assert locked[0].classification == "locked"
