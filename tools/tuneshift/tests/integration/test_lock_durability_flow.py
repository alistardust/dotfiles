"""Chunk 5 gate: end-to-end identity-lock lifecycle on one playlist+track (§8).

The per-task unit tests each exercise a single lock behaviour against a fresh
fixture. This test proves the behaviours *compose* — one durable lock carried
through its whole life in a single database, each transition routed through
plan/apply and never mutating anything the user did not approve:

1. CREATE   - map a per-playlist identity lock (AC-L1).
2. UNCHANGED - re-doctor with the lock still live and still satisfying the
   playlist preference -> plan classifies it ``locked`` and skips (AC-L2/L4).
3. DOWNGRADE - the locked id is still live but Tidal drops its Atmos mode, so it
   no longer satisfies ``prefer spatial=atmos`` -> plan FLAGS it, never swaps
   (AC-L5).
4. DISAPPEARANCE - the locked id genuinely dies; a same-recording (ISRC)
   equivalent exists -> a ROUTED heal plan proposes the re-bind, surfaced (not
   silent) and applied only on the reviewed ``include_locked`` pass (AC-L3).

Throughout, the lock is authoritative: default applies never touch it, and after
the reviewed heal it stays ``user_approved`` (AC-L4 durability).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.planapply.apply import apply_plan
from tuneshift.planapply.builders import build_lock_plan
from tuneshift.planapply.heal import build_heal_plan
from tuneshift.planapply.rematch import build_rematch_plan

ATMOS_ID = "atmos-100"
HEALED_ID = "atmos-200"
ISRC = "USUM71900001"


def _client() -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_track.return_value = []
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def _atmos_track(platform_id: str, modes: list[str]) -> TrackResult:
    return TrackResult(
        platform_id=platform_id, title="Flowers", artist="Miley Cyrus",
        album="Endless Summer Vacation", duration_seconds=200,
        isrc=ISRC, available=True, audio_modes=modes,
    )


def test_identity_lock_lifecycle(tmp_db: Path) -> None:
    db = Database(tmp_db)
    pid = db.create_playlist("Atmos Favourites")
    tid = db.add_track(Track(
        title="Flowers", artist="Miley Cyrus",
        album="Endless Summer Vacation", duration_seconds=200, isrc=ISRC,
    ))
    db.add_track_to_playlist(pid, tid, 0)
    db.set_preferences(pid, {"prefer": ["atmos"]})

    # 1) CREATE — map the per-playlist identity lock to the Atmos release.
    lock = build_lock_plan(db, pid, tid, "tidal", ATMOS_ID)
    assert apply_plan(db, lock).applied == 1
    mapping = db.get_playlist_track_mapping(pid, tid, "tidal")
    assert mapping["platform_track_id"] == ATMOS_ID
    assert mapping["source"] == "locked"
    assert mapping["user_approved"] == 1

    # 2) UNCHANGED — locked id still live and still Atmos: a plain locked skip.
    client = _client()
    client.get_track.return_value = _atmos_track(ATMOS_ID, ["DOLBY_ATMOS", "STEREO"])
    plan = build_rematch_plan(db, pid, client, platform="tidal")
    locked = [c for c in plan.changes if c.locked]
    assert len(locked) == 1
    assert locked[0].classification == "locked"
    assert not [c for c in plan.changes if c.classification == "downgrade-flag"]
    assert apply_plan(db, plan).applied == 0
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == ATMOS_ID

    # 3) DOWNGRADE — Tidal drops Atmos on the SAME id: flag it, never swap (AC-L5).
    client = _client()
    client.get_track.return_value = _atmos_track(ATMOS_ID, ["STEREO"])
    plan = build_rematch_plan(db, pid, client, platform="tidal")
    flagged = [c for c in plan.changes if c.classification == "downgrade-flag"]
    assert len(flagged) == 1
    assert flagged[0].locked is True
    assert flagged[0].status == "skipped"
    assert flagged[0].proposed["platform_track_id"] == ATMOS_ID  # lock re-affirmed
    assert "spatial" in flagged[0].reason and "atmos" in flagged[0].reason
    assert apply_plan(db, plan).applied == 0
    # Lock is untouched and still approved after the flag.
    held = db.get_playlist_track_mapping(pid, tid, "tidal")
    assert held["platform_track_id"] == ATMOS_ID
    assert held["user_approved"] == 1

    # 4) DISAPPEARANCE — the locked id dies; a same-recording (ISRC) equivalent
    #    exists. The heal is ROUTED: proposed, surfaced, applied only on review.
    client = _client()
    client.get_track.return_value = None  # locked id is gone
    client.search_track.return_value = [_atmos_track(HEALED_ID, ["DOLBY_ATMOS", "STEREO"])]
    heal = build_heal_plan(db, client, platform="tidal", playlist_id=pid)
    assert len(heal.changes) == 1
    change = heal.changes[0]
    assert change.table == "playlist_track_mappings"
    assert change.reason == "lock_healed"
    assert change.proposed["platform_track_id"] == HEALED_ID
    assert change.locked is True  # touches the locked row

    # Default apply protects the lock — the heal is surfaced, not silent (AC-L3).
    assert apply_plan(db, heal).applied == 0
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == ATMOS_ID

    # The reviewed "yes, heal it" re-binds to the equivalent, still locked (AC-L4).
    report = apply_plan(db, heal, include_locked=True)
    assert report.applied == 1
    healed = db.get_playlist_track_mapping(pid, tid, "tidal")
    assert healed["platform_track_id"] == HEALED_ID
    assert healed["user_approved"] == 1
