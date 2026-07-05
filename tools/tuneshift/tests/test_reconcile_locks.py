"""Chunk 6: durable self-healing lock behavior in reconcile."""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import PlatformMapping, Track, TrackResult
from tuneshift.reconcile import reconcile_track


def _seed_locked(db: Database, *, platform="tidal", pid="old123", isrc=None,
                 duration=195, fingerprint=None) -> int:
    track_id = db.add_track(Track(
        title="Heroes", artist="David Bowie", album="Heroes",
        duration_seconds=duration, isrc=isrc,
    ))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=track_id, platform=platform, platform_track_id=pid,
        match_score=97, status="matched", user_approved=True,
        fingerprint=fingerprint,
    ))
    return track_id


def _client(platform="tidal"):
    client = MagicMock()
    client.platform_name = platform
    client.search_track.return_value = []
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def test_lock_not_verified_by_default(tmp_db: Path) -> None:
    """Default (verify_locked=False) trusts the lock and never probes liveness."""
    db = Database(tmp_db)
    track_id = _seed_locked(db)
    client = _client()

    result = reconcile_track(db, track_id, client)

    assert result.platform_track_id == "old123"
    assert result.reason_code == "locked"
    client.get_track.assert_not_called()


def test_lock_alive_kept_verify_is_pure(tmp_db: Path) -> None:
    """A live locked id is kept, and verify writes nothing (self-heal is routed)."""
    db = Database(tmp_db)
    track_id = _seed_locked(db, fingerprint=None)
    client = _client()
    client.get_track.return_value = TrackResult(
        platform_id="old123", title="Heroes", artist="David Bowie",
        album="Heroes", duration_seconds=195, available=True,
    )

    result = reconcile_track(db, track_id, client, verify_locked=True)

    assert result.platform_track_id == "old123"
    assert result.reason_code == "locked"
    assert result.availability == "exact_available"
    # Verify is a pure query: no inline fingerprint backfill (that's routed now).
    stored = db.get_platform_mapping(track_id, "tidal")
    assert stored.fingerprint is None


def test_lock_dead_reported_held_no_inline_swap(tmp_db: Path) -> None:
    """A dead locked id is reported HELD; verify never swaps or writes inline.

    The actual re-bind to an equivalent recording is a routed plan
    (planapply.heal.build_heal_plan), covered in tests/planapply/test_heal.py.
    """
    db = Database(tmp_db)
    track_id = _seed_locked(db, pid="dead999", duration=195)
    client = _client()
    client.get_track.return_value = None  # locked id is gone
    client.search_track.return_value = [TrackResult(
        platform_id="new456", title="Heroes", artist="David Bowie",
        album="Heroes", duration_seconds=195, available=True,
    )]

    result = reconcile_track(db, track_id, client, verify_locked=True)

    assert result.availability == "exact_unavailable"
    assert result.reason_code == "lock_held"
    # DB is untouched — no silent swap, no status flip.
    stored = db.get_platform_mapping(track_id, "tidal")
    assert stored.platform_track_id == "dead999"
    assert stored.status == "matched"
    assert stored.user_approved is True


def test_lock_dead_no_equivalent_reported_held(tmp_db: Path) -> None:
    """A dead lock is reported held; verify still writes nothing."""
    db = Database(tmp_db)
    track_id = _seed_locked(db, pid="dead999", duration=195)
    client = _client()
    client.get_track.return_value = None
    client.search_track.return_value = [TrackResult(
        platform_id="live777", title="Heroes (Live)", artist="David Bowie",
        album="Stage", duration_seconds=360, available=True,
    )]

    result = reconcile_track(db, track_id, client, verify_locked=True)

    assert result.availability == "exact_unavailable"
    assert result.reason_code == "lock_held"
    stored = db.get_platform_mapping(track_id, "tidal")
    # Never swapped, never mutated inline.
    assert stored.platform_track_id == "dead999"
    assert stored.status == "matched"
    assert stored.user_approved is True


def test_lock_liveness_undeterminable_trusts_lock(tmp_db: Path) -> None:
    """A client with no get_track (e.g. Spotify) cannot verify -> trust the lock."""
    db = Database(tmp_db)
    track_id = _seed_locked(db, platform="spotify", pid="sp123")

    class NoLivenessClient:
        platform_name = "spotify"

        def search_track(self, *a, **k):
            return []

        def search_isrc(self, *a, **k):
            return None

    result = reconcile_track(db, track_id, NoLivenessClient(), verify_locked=True)

    assert result.platform_track_id == "sp123"
    assert result.reason_code == "locked"
    assert result.availability == "exact_available"


def test_lock_verify_is_idempotent(tmp_db: Path) -> None:
    """Repeated verify runs on a live lock do not drift the mapping."""
    db = Database(tmp_db)
    track_id = _seed_locked(db)
    client = _client()
    client.get_track.return_value = TrackResult(
        platform_id="old123", title="Heroes", artist="David Bowie",
        album="Heroes", duration_seconds=195, available=True,
    )

    first = reconcile_track(db, track_id, client, verify_locked=True)
    second = reconcile_track(db, track_id, client, verify_locked=True)

    assert first.platform_track_id == second.platform_track_id == "old123"
    assert first.reason_code == second.reason_code == "locked"
