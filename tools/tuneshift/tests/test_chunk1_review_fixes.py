"""Regression tests for the Chunk 1 (data layer) code review findings.

Each test reproduces a concrete bug the reviewer found on a scratch DB:
  1. approve/re-enqueue: quarantined rows were permanently wedged and an
     approved track still counted as quarantined in coverage (two sources of
     truth). AC-D1/AC-D6.
  2. rate-limit retries consumed the hard-failure attempt budget, so transient
     429s could quarantine a track. AC-D7 worker semantics.
  3. playlist-scoped match_audits leaked across playlists on read.
  4. the Tidal SEARCH path (_track_to_result) discarded the native
     version/audio metadata BUILD-FIRST is meant to preserve. spec §4.2.
"""

from __future__ import annotations

import pytest

from tuneshift.db import Database
from tuneshift.library.worker import ResolutionRateLimited, ResolutionWorker
from tuneshift.models import Track, TrackResult
from tuneshift.platforms.tidal import TidalClient


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


# --- Finding 1: approve consistency + re-enqueue reopen ---------------------


def test_approve_makes_coverage_consistent(db: Database) -> None:
    """A quarantined track that is approved must count as resolved everywhere.

    Before the fix, approve cleared tracks.quarantine_state but left
    resolution_queue.state='quarantined', so coverage_report kept counting it.
    """
    tid = db.insert_track(Track(title="Buddy", artist="De La Soul"))
    db.enqueue_resolution(tid)
    db.set_resolution_state(tid, "quarantined", last_error="no_candidate")
    db.set_track_fields(
        tid, {"quarantine_state": "unresolved", "quarantine_reason": "no_candidate"},
        source="resolver",
    )
    assert db.coverage_report()["quarantined"] == 1

    db.approve_resolution(tid)

    # No longer quarantined in EITHER source of truth.
    assert db.get_quarantined_tracks() == []
    report = db.coverage_report()
    assert report["quarantined"] == 0
    assert report["resolved"] == 1


def test_re_enqueue_reopens_quarantined_but_not_resolved(db: Database) -> None:
    """Re-adding an unresolvable track reopens it; a resolved track is untouched."""
    q = db.insert_track(Track(title="Quarantined", artist="X"))
    db.enqueue_resolution(q)
    db.set_resolution_state(q, "quarantined", last_error="no_candidate",
                            increment_attempts=True)

    # Re-enqueue (as add/import does) must reopen a quarantined row for retry.
    db.enqueue_resolution(q)
    row = db.conn.execute(
        "SELECT state, attempts, last_error FROM resolution_queue WHERE track_id=?",
        (q,),
    ).fetchone()
    assert row["state"] == "pending"
    assert row["attempts"] == 0
    assert row["last_error"] is None

    # A resolved row is NOT reset (no wasteful re-resolution).
    r = db.insert_track(Track(title="Resolved", artist="Y"))
    db.enqueue_resolution(r)
    db.set_resolution_state(r, "resolved")
    db.enqueue_resolution(r)
    assert db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (r,)
    ).fetchone()["state"] == "resolved"


# --- Finding 2: rate-limits must not consume the quarantine budget ----------


def test_rate_limit_does_not_consume_quarantine_budget(db: Database) -> None:
    """Transient 429s must never count toward the hard-failure quarantine ceiling."""
    tid = db.insert_track(Track(title="RL", artist="Z"))

    calls = {"n": 0}

    def resolver(_track):
        calls["n"] += 1
        # Two rate limits, then one hard error.
        if calls["n"] <= 2:
            raise ResolutionRateLimited("429")
        raise RuntimeError("500")

    worker = ResolutionWorker(db, resolver=resolver, max_attempts=2)
    worker.enqueue(tid)

    # Rate-limited twice -> still pending, hard-failure budget untouched.
    worker._resolve_one(tid)
    worker._resolve_one(tid)
    row = db.conn.execute(
        "SELECT state, attempts FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()
    assert row["state"] == "pending"
    assert row["attempts"] == 0

    # First hard error consumes budget slot 1 of 2 -> still pending, not quarantined.
    worker._resolve_one(tid)
    row = db.conn.execute(
        "SELECT state, attempts FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()
    assert row["state"] == "pending", "one hard failure < max_attempts must not quarantine"
    assert row["attempts"] == 1


# --- Finding 3: playlist-scoped audits must not leak across playlists -------


def test_playlist_scoped_audit_does_not_leak(db: Database) -> None:
    from tuneshift.matching.audit import MatchAudit

    tid = db.insert_track(Track(title="Shared", artist="Both"))
    p1 = db.create_playlist("P1")
    p2 = db.create_playlist("P2")
    db.add_track_to_playlist(p1, tid, 0)
    db.add_track_to_playlist(p2, tid, 0)

    audit = MatchAudit(availability="not_found", reason_code="no_match")
    db.save_match_audit(tid, "tidal", audit, playlist_id=p1)

    # The audit belongs to P1 only.
    p1_ids = db.get_unavailable_track_ids(p1, "tidal")
    p2_ids = db.get_unavailable_track_ids(p2, "tidal")
    assert tid in p1_ids
    assert tid not in p2_ids, "P1's audit must not mark the track unavailable in P2"

    items = db.get_review_items()
    surfaced = {(it.playlist_id, it.track_id) for it in items}
    assert (p1, tid) in surfaced
    assert (p2, tid) not in surfaced, "P1's audit must not surface as a P2 review item"


def test_global_audit_applies_to_all_playlists(db: Database) -> None:
    """A legacy/global audit (playlist_id=0) still applies as a fallback."""
    from tuneshift.matching.audit import MatchAudit

    tid = db.insert_track(Track(title="Legacy", artist="Old"))
    p1 = db.create_playlist("P1")
    db.add_track_to_playlist(p1, tid, 0)
    audit = MatchAudit(availability="not_found", reason_code="no_match")
    db.save_match_audit(tid, "tidal", audit)  # playlist_id defaults to 0

    assert tid in db.get_unavailable_track_ids(p1, "tidal")


# --- Finding 4: the search path must preserve native Tidal metadata ---------


class _FakeArtist:
    def __init__(self, name):
        self.name = name


class _FakeAlbum:
    def __init__(self, name, artist, album_type):
        self.name = name
        self.artist = _FakeArtist(artist)
        self.type = album_type


class _FakeTrack:
    id = 400368598
    name = "Flowers"
    duration = 200
    isrc = "USUM71900000"
    available = True
    premium_streaming_only = False
    pay_to_stream = False
    audio_modes = ["DOLBY_ATMOS"]
    audio_quality = "HI_RES_LOSSLESS"
    version = "Dolby Atmos"
    media_metadata_tags = ["HIRES_LOSSLESS", "DOLBY_ATMOS"]

    def __init__(self):
        self.artist = _FakeArtist("Miley Cyrus")
        self.album = _FakeAlbum("Endless Summer Vacation", "Miley Cyrus", "ALBUM")


def test_track_to_result_populates_native_metadata() -> None:
    result = TidalClient._track_to_result(_FakeTrack())
    assert isinstance(result, TrackResult)
    assert result.audio_modes == ["DOLBY_ATMOS"]
    assert result.audio_quality == "HI_RES_LOSSLESS"
    assert result.tidal_version == "Dolby Atmos"
    assert result.media_metadata_tags == ["HIRES_LOSSLESS", "DOLBY_ATMOS"]
    assert result.album_artist == "Miley Cyrus"
    assert result.album_type == "ALBUM"


def test_track_to_result_defensive_when_attrs_absent() -> None:
    class _Bare:
        id = 1
        name = "Bare"
        duration = 100
        isrc = None
        available = None

    result = TidalClient._track_to_result(_Bare())
    assert result.audio_modes is None
    assert result.audio_quality is None
    assert result.tidal_version is None
    assert result.media_metadata_tags is None
    assert result.album_artist is None
    assert result.album_type is None
