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


def test_lock_alive_kept_and_fingerprint_backfilled(tmp_db: Path) -> None:
    """A live locked id is kept; a missing fingerprint is backfilled for future heals."""
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
    stored = db.get_platform_mapping(track_id, "tidal")
    assert stored.fingerprint is not None  # backfilled


def test_lock_dead_heals_to_equivalent(tmp_db: Path) -> None:
    """A dead locked id re-binds to an equivalent live id for the SAME recording."""
    db = Database(tmp_db)
    track_id = _seed_locked(db, pid="dead999", duration=195)
    client = _client()
    client.get_track.return_value = None  # locked id is gone
    # Search surfaces the same recording under a new id.
    client.search_track.return_value = [TrackResult(
        platform_id="new456", title="Heroes", artist="David Bowie",
        album="Heroes", duration_seconds=195, available=True,
    )]

    result = reconcile_track(db, track_id, client, verify_locked=True)

    assert result.platform_track_id == "new456"
    assert result.reason_code == "lock_healed"
    assert result.availability == "exact_available"
    stored = db.get_platform_mapping(track_id, "tidal")
    assert stored.platform_track_id == "new456"
    assert stored.user_approved is True  # still locked
    assert stored.fingerprint is not None


def test_lock_dead_no_equivalent_is_held(tmp_db: Path) -> None:
    """When only a DIFFERENT recording is available, the lock is held, not swapped."""
    db = Database(tmp_db)
    track_id = _seed_locked(db, pid="dead999", duration=195)
    client = _client()
    client.get_track.return_value = None
    # Only a live version exists — a different recording class.
    client.search_track.return_value = [TrackResult(
        platform_id="live777", title="Heroes (Live)", artist="David Bowie",
        album="Stage", duration_seconds=360, available=True,
    )]

    result = reconcile_track(db, track_id, client, verify_locked=True)

    assert result.availability == "exact_unavailable"
    assert result.reason_code == "lock_held"
    stored = db.get_platform_mapping(track_id, "tidal")
    # Never swapped to the different recording.
    assert stored.platform_track_id == "dead999"
    assert stored.status == "unavailable"
    assert stored.user_approved is True


def test_lock_dead_heals_via_isrc(tmp_db: Path) -> None:
    """ISRC equivalence heals even when title/duration differ cosmetically."""
    db = Database(tmp_db)
    track_id = _seed_locked(db, pid="dead999", isrc="GBAYE7700012", duration=195)
    client = _client()
    client.get_track.return_value = None
    client.search_track.return_value = [TrackResult(
        platform_id="new456", title="Heroes (2017 Remaster)", artist="David Bowie",
        album="Heroes (2017 Remaster)", duration_seconds=372,
        isrc="GBAYE7700012", available=True,
    )]

    result = reconcile_track(db, track_id, client, verify_locked=True)

    assert result.platform_track_id == "new456"
    assert result.reason_code == "lock_healed"


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
