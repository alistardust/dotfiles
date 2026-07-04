"""Task 1.4: new version-selection tables + CRUD (spec §4.1a).

- resolution_queue: resumable enrich/resolve work queue (AC-D2/D7 async).
- track_candidates: hydrated top-N platform candidates per track (AC-C1 inputs).
- playlist_track_mappings: per-playlist release override of the global mapping
  (AC-S1 "same track, different version per playlist").
- playlist_track_prefs: most-specific (playlist+track+criterion) preference scope.
"""

import pytest

from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def seeded(db):
    tid = db.insert_track(Track(title="Buddy", artist="De La Soul", album="3 Feet High and Rising"))
    pid = db.create_playlist("Native Tongues")
    return db, tid, pid


def test_new_tables_exist(db):
    tables = {
        r[0]
        for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {
        "resolution_queue",
        "track_candidates",
        "playlist_track_mappings",
        "playlist_track_prefs",
    } <= tables


def test_resolution_queue_lifecycle(seeded):
    db, tid, _ = seeded
    assert db.next_pending_resolution() is None
    db.enqueue_resolution(tid)
    assert db.next_pending_resolution() == tid

    db.set_resolution_state(tid, "in_progress")
    assert db.next_pending_resolution() is None

    db.set_resolution_state(tid, "failed", last_error="rate limited", increment_attempts=True)
    row = db.conn.execute(
        "SELECT state, attempts, last_error FROM resolution_queue WHERE track_id=?",
        (tid,),
    ).fetchone()
    assert row["state"] == "failed"
    assert row["attempts"] == 1
    assert row["last_error"] == "rate limited"

    db.set_resolution_state(tid, "done")
    assert db.next_pending_resolution() is None


def test_enqueue_resolution_is_idempotent(seeded):
    db, tid, _ = seeded
    db.enqueue_resolution(tid)
    db.enqueue_resolution(tid)
    count = db.conn.execute(
        "SELECT COUNT(*) c FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()["c"]
    assert count == 1


def test_track_candidate_upsert_and_read(seeded):
    db, tid, _ = seeded
    db.upsert_track_candidate(tid, "tidal", "111", {"audio_modes": ["DOLBY_ATMOS"]})
    db.upsert_track_candidate(tid, "tidal", "222", {"audio_modes": ["STEREO"]})
    cands = db.get_track_candidates(tid, platform="tidal")
    ids = {c["platform_track_id"] for c in cands}
    assert ids == {"111", "222"}

    # upsert same key updates captured_metadata, no duplicate row
    db.upsert_track_candidate(tid, "tidal", "111", {"audio_modes": ["DOLBY_ATMOS", "STEREO"]})
    cands = db.get_track_candidates(tid, platform="tidal")
    assert len(cands) == 2
    c111 = next(c for c in cands if c["platform_track_id"] == "111")
    assert c111["captured_metadata"]["audio_modes"] == ["DOLBY_ATMOS", "STEREO"]


def test_playlist_track_mapping_override(seeded):
    db, tid, pid = seeded
    assert db.get_playlist_track_mapping(pid, tid, "tidal") is None
    db.set_playlist_track_mapping(pid, tid, "tidal", "2630", source="pin", user_approved=True)
    m = db.get_playlist_track_mapping(pid, tid, "tidal")
    assert m["platform_track_id"] == "2630"
    assert m["source"] == "pin"
    assert m["user_approved"] is True

    # upsert replaces the release for this playlist without duplicating
    db.set_playlist_track_mapping(pid, tid, "tidal", "9999", source="doctor")
    m = db.get_playlist_track_mapping(pid, tid, "tidal")
    assert m["platform_track_id"] == "9999"
    assert m["user_approved"] is False
    count = db.conn.execute(
        "SELECT COUNT(*) c FROM playlist_track_mappings WHERE playlist_id=? AND track_id=? AND platform=?",
        (pid, tid, "tidal"),
    ).fetchone()["c"]
    assert count == 1


def test_playlist_track_prefs(seeded):
    db, tid, pid = seeded
    assert db.get_playlist_track_prefs(pid, tid) == []
    db.set_playlist_track_pref(pid, tid, "spatial", "prefer", "atmos")
    db.set_playlist_track_pref(pid, tid, "recording", "avoid", "live")
    prefs = {p["criterion"]: p for p in db.get_playlist_track_prefs(pid, tid)}
    assert prefs["spatial"]["strength"] == "prefer"
    assert prefs["spatial"]["target"] == "atmos"
    assert prefs["recording"]["strength"] == "avoid"

    # upsert same criterion replaces
    db.set_playlist_track_pref(pid, tid, "spatial", "require", "atmos")
    prefs = {p["criterion"]: p for p in db.get_playlist_track_prefs(pid, tid)}
    assert prefs["spatial"]["strength"] == "require"
    assert len(prefs) == 2
