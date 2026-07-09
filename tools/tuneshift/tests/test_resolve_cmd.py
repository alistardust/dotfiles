"""Tests for the resolve CLI command (library-first platform resolution).

The command was rewritten from MusicBrainz/Discogs identity resolution to
platform candidate resolution (spec §4.1a). These tests cover the command
wiring — selector routing, the client boundary, and error paths — while the
deep hydrate/persist/quarantine behavior is proven end-to-end in
``tests/integration/test_resolve_end_to_end.py``.
"""

from argparse import Namespace
from unittest.mock import patch

import os

import pytest

from tuneshift.commands.resolve import run_resolve
from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.platforms.rate_limiter import RateLimiter


class _FakeClient:
    """Minimal platform client returning one realistic candidate."""

    platform_name = "tidal"

    def search_track(self, query, limit=10):
        del query, limit
        return [
            TrackResult(
                platform_id="tidal-1",
                title="Diamond Dogs",
                artist="David Bowie",
                album="Diamond Dogs",
                duration_seconds=384,
                isrc="GBAYE7400001",
                available=True,
            )
        ]

    def search_isrc(self, isrc):
        del isrc
        return None

    def search_album(self, query, limit=5):
        del query, limit
        return []

    def get_album_tracks(self, album_id):
        del album_id
        return []

    def search_artist(self, query, limit=3):
        del query, limit
        return []

    def get_artist_albums(self, artist_id, limit=20):
        del artist_id, limit
        return []


def _args(**overrides) -> Namespace:
    base = dict(
        playlist=None,
        track=None,
        all=False,
        platform="tidal",
        upgrade=False,
        force=False,
        status=False,
        verbose=False,
        throttle=None,
    )
    base.update(overrides)
    return Namespace(**base)


class TestResolveCommand:
    def test_resolve_playlist_by_name(self, tmp_path):
        db = Database(tmp_path / "test.db")
        playlist_id = db.create_playlist("Diamond Dogs")
        track = Track(title="Diamond Dogs", artist="David Bowie", album=None)
        track_id = db.add_track(track)
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        with patch(
            "tuneshift.commands.resolve._load_client", return_value=_FakeClient()
        ):
            run_resolve(_args(playlist="Diamond Dogs"), db)

        # The playlist's track was driven through the real resolver: queued,
        # resolved, and hydrated from the candidate.
        assert db.get_resolution_queue_state(track_id) == "resolved"
        hydrated = db.get_track(track_id)
        assert hydrated.isrc == "GBAYE7400001"
        assert hydrated.duration_seconds == 384
        assert hydrated.album == "Diamond Dogs"

    def test_no_selector_errors(self, tmp_path):
        db = Database(tmp_path / "test.db")
        with pytest.raises(SystemExit):
            run_resolve(_args(), db)

    def test_unknown_platform_errors(self, tmp_path):
        db = Database(tmp_path / "test.db")
        playlist_id = db.create_playlist("P")
        track_id = db.add_track(Track(title="T", artist="A", album=None))
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        with patch("tuneshift.commands.resolve._load_client", return_value=None):
            with pytest.raises(SystemExit):
                run_resolve(_args(playlist="P"), db)

    def test_force_reresolves_already_resolved(self, tmp_path):
        db = Database(tmp_path / "test.db")
        playlist_id = db.create_playlist("Diamond Dogs")
        track = Track(title="Diamond Dogs", artist="David Bowie", album=None)
        track_id = db.add_track(track)
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        calls = {"n": 0}

        class _CountingClient(_FakeClient):
            def search_track(self, query, limit=10):
                calls["n"] += 1
                return super().search_track(query, limit)

        client = _CountingClient()
        with patch("tuneshift.commands.resolve._load_client", return_value=client):
            run_resolve(_args(playlist="Diamond Dogs"), db)
            first = calls["n"]
            assert first > 0
            # Without --force a re-run skips already-resolved tracks (no search).
            run_resolve(_args(playlist="Diamond Dogs"), db)
            assert calls["n"] == first
            # With --force the track is re-resolved (search runs again).
            run_resolve(_args(playlist="Diamond Dogs", force=True), db)
            assert calls["n"] > first

    def test_status_needs_no_client(self, tmp_path):
        db = Database(tmp_path / "test.db")
        playlist_id = db.create_playlist("Diamond Dogs")
        track_id = db.add_track(Track(title="Diamond Dogs", artist="David Bowie", album=None))
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        # status must not touch the network/client boundary at all.
        with patch(
            "tuneshift.commands.resolve._load_client",
            side_effect=AssertionError("client must not load for --status"),
        ):
            run_resolve(_args(playlist="Diamond Dogs", status=True), db)


def test_run_resolve_refuses_when_lock_held(tmp_path):
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Diamond Dogs")
    track = Track(title="Diamond Dogs", artist="David Bowie", album=None)
    tid = db.add_track(track)
    db.add_track_to_playlist(playlist_id, tid, position=0)

    # A live resolve "holds" the lock: the parent PID is alive and distinct.
    lock = tmp_path / ".tuneshift" / "resolve.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getppid()), encoding="utf-8")

    with patch(
        "tuneshift.commands.resolve._load_client", return_value=_FakeClient()
    ):
        with pytest.raises(SystemExit):
            run_resolve(_args(playlist="Diamond Dogs"), db)

    # The run refused, so the track was not resolved.
    assert db.get_resolution_queue_state(tid) != "resolved"


def test_resolve_throttle_sets_rate_limiter(tmp_path):
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Diamond Dogs")
    track = Track(title="Diamond Dogs", artist="David Bowie", album=None)
    tid = db.add_track(track)
    db.add_track_to_playlist(playlist_id, tid, position=0)

    seen = {}
    real_rl = RateLimiter

    def spy_rl(*args, **kwargs):
        rl = real_rl(*args, **kwargs)
        seen["rl"] = rl
        return rl

    # Disable enrichment so the test does not hit the local LLM (Ollama).
    with patch(
        "tuneshift.commands.resolve._load_client", return_value=_FakeClient()
    ), patch(
        "tuneshift.library.enrichment.make_enricher", return_value=None
    ), patch("tuneshift.platforms.rate_limiter.RateLimiter", side_effect=spy_rl):
        run_resolve(_args(playlist="Diamond Dogs", throttle=1.0), db)

    # 1 op/sec -> 1.0s minimum interval (RateLimiter._min_interval == 1/mps).
    assert seen["rl"]._min_interval == pytest.approx(1.0)


def test_resolve_throttle_rejects_nonpositive(tmp_path):
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Diamond Dogs")
    track = Track(title="Diamond Dogs", artist="David Bowie", album=None)
    tid = db.add_track(track)
    db.add_track_to_playlist(playlist_id, tid, position=0)

    with patch(
        "tuneshift.commands.resolve._load_client", return_value=_FakeClient()
    ):
        with pytest.raises(SystemExit):
            run_resolve(_args(playlist="Diamond Dogs", throttle=0.0), db)
