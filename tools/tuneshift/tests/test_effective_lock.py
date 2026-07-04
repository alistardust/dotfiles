"""Chunk 5 Task 5.1: two-level composite identity-lock resolution (ACs L1/L4).

A lock is two-level (global default + per-playlist override, override wins) and
composite (platform-id OR ISRC OR fingerprint). ``db.get_effective_lock``
resolves the effective lock for a (track, platform, playlist) and ``reconcile_track``
honours it on every path — including a forced re-doctor, which must never re-pick
away from a lock.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.matching.selection import IdentityLock
from tuneshift.models import PlatformMapping, Track, TrackResult
from tuneshift.reconcile import reconcile_track


def _client(platform: str = "tidal") -> MagicMock:
    client = MagicMock()
    client.platform_name = platform
    client.search_track.return_value = []
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def _seed(db: Database) -> tuple[int, int, int]:
    track_id = db.add_track(
        Track(title="Buddy", artist="De La Soul", album="3 Feet High", isrc="USxx1")
    )
    pl_native = db.create_playlist("Native Tongues")
    pl_other = db.create_playlist("Other")
    db.add_track_to_playlist(pl_native, track_id, 0)
    db.add_track_to_playlist(pl_other, track_id, 0)
    return track_id, pl_native, pl_other


class TestEffectiveLock:
    def test_playlist_override_wins_over_global(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id, pl_native, pl_other = _seed(db)
        db.upsert_platform_mapping(
            PlatformMapping(
                track_id=track_id, platform="tidal", platform_track_id="GLOBAL",
                match_score=97, status="matched", user_approved=True,
            )
        )
        db.set_playlist_track_mapping(
            pl_native, track_id, "tidal", "PLAYLIST", source="locked", user_approved=True
        )

        eff_native = db.get_effective_lock(track_id, "tidal", pl_native)
        eff_other = db.get_effective_lock(track_id, "tidal", pl_other)
        eff_global = db.get_effective_lock(track_id, "tidal", None)

        assert eff_native.platform_track_id == "PLAYLIST"
        assert eff_native.scope == "playlist"
        # No override on the other playlist -> global default lock applies.
        assert eff_other.platform_track_id == "GLOBAL"
        assert eff_other.scope == "global"
        assert eff_global.platform_track_id == "GLOBAL"

    def test_no_lock_returns_none(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id, pl_native, _ = _seed(db)
        # A non-approved mapping is not a lock.
        db.upsert_platform_mapping(
            PlatformMapping(
                track_id=track_id, platform="tidal", platform_track_id="AUTO",
                match_score=90, status="matched", user_approved=False,
            )
        )
        assert db.get_effective_lock(track_id, "tidal", pl_native) is None

    def test_unapproved_playlist_mapping_is_not_a_lock(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id, pl_native, _ = _seed(db)
        db.upsert_platform_mapping(
            PlatformMapping(
                track_id=track_id, platform="tidal", platform_track_id="GLOBAL",
                match_score=97, status="matched", user_approved=True,
            )
        )
        # A per-playlist mapping that is NOT user_approved must not shadow the
        # global lock.
        db.set_playlist_track_mapping(
            pl_native, track_id, "tidal", "AUTO_PL", source="matched", user_approved=False
        )
        eff = db.get_effective_lock(track_id, "tidal", pl_native)
        assert eff.platform_track_id == "GLOBAL"
        assert eff.scope == "global"


class TestIdentityLockComposite:
    def test_matches_on_fingerprint(self) -> None:
        from tuneshift.matching.fingerprint import build_fingerprint

        fp = build_fingerprint(title="Heroes", artist="Bowie", duration_seconds=195)
        lock = IdentityLock(platform_id="DEAD", fingerprint=fp)
        candidate = TrackResult(
            platform_id="NEW", title="Heroes", artist="Bowie", album="Heroes",
            duration_seconds=196,
        )
        other = TrackResult(
            platform_id="OTHER", title="Ashes", artist="Bowie", album="Scary Monsters",
            duration_seconds=100,
        )
        # A candidate that is the SAME recording (title/artist/class + duration
        # bucket) matches even though the platform id changed; a different
        # recording does not.
        assert lock.matches(candidate, candidate_fingerprint=build_fingerprint(
            title="Heroes", artist="Bowie", duration_seconds=196))
        assert not lock.matches(other, candidate_fingerprint=build_fingerprint(
            title="Ashes", artist="Bowie", duration_seconds=100))

    def test_matches_on_platform_id_or_isrc_without_fingerprint(self) -> None:
        lock = IdentityLock(platform_id="X", isrc="USxx1")
        same_id = TrackResult(platform_id="X", title="t", artist="a", album="al")
        same_isrc = TrackResult(
            platform_id="Y", title="t", artist="a", album="al", isrc="usxx1"
        )
        other = TrackResult(platform_id="Z", title="t", artist="a", album="al")
        assert lock.matches(same_id)
        assert lock.matches(same_isrc)
        assert not lock.matches(other)


class TestReconcileHonoursTwoLevelLock:
    def test_reconcile_returns_playlist_override(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id, pl_native, pl_other = _seed(db)
        db.upsert_platform_mapping(
            PlatformMapping(
                track_id=track_id, platform="tidal", platform_track_id="GLOBAL",
                match_score=97, status="matched", user_approved=True,
            )
        )
        db.set_playlist_track_mapping(
            pl_native, track_id, "tidal", "PLAYLIST", source="locked", user_approved=True
        )
        client = _client()

        # On the Native Tongues playlist the per-playlist lock wins.
        res_native = reconcile_track(db, track_id, client, playlist_id=pl_native)
        assert res_native.platform_track_id == "PLAYLIST"
        assert res_native.reason_code == "locked"
        # On another playlist the global default lock applies.
        res_other = reconcile_track(db, track_id, client, playlist_id=pl_other)
        assert res_other.platform_track_id == "GLOBAL"

    def test_forced_redoctor_still_honours_lock(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        track_id, pl_native, _ = _seed(db)
        db.set_playlist_track_mapping(
            pl_native, track_id, "tidal", "PLAYLIST", source="locked", user_approved=True
        )
        client = _client()
        # A forced re-doctor bypasses the cache; candidates include the locked id
        # plus a "better" scoring alternative. The lock must still win.
        client.search_track.return_value = [
            TrackResult(platform_id="PLAYLIST", title="Buddy", artist="De La Soul",
                        album="3 Feet High", available=True),
            TrackResult(platform_id="ALT", title="Buddy", artist="De La Soul",
                        album="3 Feet High and Rising (Deluxe)", available=True),
        ]

        res = reconcile_track(db, track_id, client, playlist_id=pl_native, force=True)
        assert res.platform_track_id == "PLAYLIST"


class TestReconcileHonoursFingerprintAxis:
    def test_forced_redoctor_resolves_lock_via_fingerprint(self, tmp_db: Path) -> None:
        """AC-L1 composite: a platform re-ID with no shared ISRC still resolves
        to the SAME recording via the fingerprint axis (not just platform-id/ISRC).

        Regression guard: ``_resolve_lock`` previously never passed a candidate
        fingerprint, so the fingerprint branch of ``IdentityLock.matches`` was
        dead and this lock would have surfaced as ``locked_missing`` instead of
        resolving to the equivalent id.
        """
        import json

        from tuneshift.matching.fingerprint import build_fingerprint

        db = Database(tmp_db)
        # A track with NO ISRC (common for user-entered / YouTube tracks), so the
        # fingerprint is the only surviving identity axis after a platform re-ID.
        track_id = db.add_track(Track(title="Heroes", artist="Bowie", album="Heroes"))
        pid = db.create_playlist("Bowie")
        db.add_track_to_playlist(pid, track_id, 0)
        fp = build_fingerprint(title="Heroes", artist="Bowie", duration_seconds=195)
        db.upsert_platform_mapping(PlatformMapping(
            track_id=track_id, platform="tidal", platform_track_id="DEAD",
            match_score=97, status="matched", user_approved=True,
            fingerprint=json.dumps(fp.as_dict()),
        ))

        client = _client()
        # The locked id is gone; the same recording exists under a NEW id with no
        # ISRC — only the fingerprint links them.
        client.search_track.return_value = [
            TrackResult(platform_id="NEW", title="Heroes", artist="Bowie",
                        album="Heroes", duration_seconds=196, available=True),
        ]

        res = reconcile_track(db, track_id, client, playlist_id=pid, force=True)
        assert res.platform_track_id == "NEW"
