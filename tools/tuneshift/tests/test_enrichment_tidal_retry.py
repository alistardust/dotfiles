"""Integration tests for Tidal catalog metadata enrichment with retry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


from tuneshift.db import Database
from tuneshift.enrichment import platform_metadata
from tuneshift.enrichment.retry import TransientAPIError
from tuneshift.models import PlatformMapping, Track


def _setup(db: Database) -> int:
    playlist_id = db.create_playlist("Test")
    track = Track(title="Blue Monday", artist="New Order", album="Power, Corruption & Lies")
    track_id = db.add_track(track)
    db.add_track_to_playlist(playlist_id, track_id, 0)
    db.upsert_platform_mapping(PlatformMapping(
        track_id=track_id, platform="tidal", platform_track_id="999",
    ))
    return playlist_id


def test_catalog_enrichment_retries_then_succeeds(tmp_path: Path, monkeypatch):
    """A transient 429 on the first attempt should be retried, not skipped."""
    db = Database(tmp_path / "test.db")
    pid = _setup(db)

    # Avoid real sleeps and rate limiter waits
    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)
    import tuneshift.enrichment.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda s: None)

    calls = {"n": 0}

    def fake_fetch(client, track_id):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TransientAPIError("rate limited", status_code=429)
        return {
            "release_year": 1983, "release_date": "1983-03-07", "genres": ["new wave"],
            "audio_qualities": ["LOSSLESS"], "album_name": "Power, Corruption & Lies",
            "album_type": None, "explicit": False, "duration_ms": 450000,
            "popularity": 80, "raw_metadata": "{}",
        }

    monkeypatch.setattr(platform_metadata, "_fetch_tidal_track_metadata", fake_fetch)

    client = MagicMock()
    enriched, skipped, failed = platform_metadata.enrich_playlist_from_tidal(
        db, pid, max_retries=3, client=client, quiet=True,
    )
    # The retried track should succeed, not be skipped
    assert calls["n"] == 2
    assert enriched == 1
    assert failed == 0


def _setup_pid(db: Database) -> int:
    """Return the existing test playlist id."""
    pl = db.find_playlist_by_name("Test")
    return pl.id


def test_catalog_enrichment_permanent_skips(tmp_path: Path, monkeypatch):
    """ObjectNotFound (permanent) should be skipped immediately, not retried."""
    db = Database(tmp_path / "test.db")
    pid = _setup(db)

    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)

    class ObjectNotFound(Exception):
        pass

    calls = {"n": 0}

    def fake_fetch(client, track_id):
        calls["n"] += 1
        raise ObjectNotFound("track 999 not found")

    monkeypatch.setattr(platform_metadata, "_fetch_tidal_track_metadata", fake_fetch)

    client = MagicMock()
    enriched, skipped, failed = platform_metadata.enrich_playlist_from_tidal(
        db, pid, max_retries=3, client=client, quiet=True,
    )
    assert enriched == 0
    assert skipped == 1
    assert failed == 0
    assert calls["n"] == 1  # no retries on permanent error


def test_catalog_enrichment_exhausted_marks_failed(tmp_path: Path, monkeypatch):
    """Persistent transient errors exhaust retries and mark the track failed."""
    db = Database(tmp_path / "test.db")
    pid = _setup(db)

    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)
    import tuneshift.enrichment.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda s: None)

    def fake_fetch(client, track_id):
        raise TransientAPIError("rate limited", status_code=503)

    monkeypatch.setattr(platform_metadata, "_fetch_tidal_track_metadata", fake_fetch)

    client = MagicMock()
    enriched, skipped, failed = platform_metadata.enrich_playlist_from_tidal(
        db, pid, max_retries=2, client=client, quiet=True,
    )
    assert enriched == 0
    assert failed == 1
