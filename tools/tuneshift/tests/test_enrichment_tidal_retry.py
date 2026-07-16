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


def test_album_too_many_requests_does_not_break_track_metadata():
    """Fix 1: a TooManyRequests on the best-effort album lookup must be
    swallowed so track-level metadata is still returned."""
    from tidalapi.exceptions import TooManyRequests

    track = MagicMock()
    track.audio_quality = "LOSSLESS"
    track.audio_modes = ["DOLBY_ATMOS"]
    album = MagicMock()
    album.name = "Lateralus"
    album.id = 12345
    track.album = album
    track.artist = None  # skip artist branch for this test

    session = MagicMock()
    session.track.return_value = track
    # tidalapi relabels the 429 message to "Album unavailable"
    session.album.side_effect = TooManyRequests("Album unavailable")

    client = MagicMock()
    client._session = session

    meta = platform_metadata._fetch_tidal_track_metadata(client, "999")

    assert meta is not None
    assert meta["album_name"] == "Lateralus"
    assert "DOLBY_ATMOS" in meta["audio_qualities"]
    # release info could not be fetched, but that's non-fatal
    assert meta["release_year"] is None


def test_asset_not_available_album_flagged_stale():
    """Fix 3: AssetNotAvailable (delisted album) must set album_stale, not be
    swallowed as a generic best-effort error."""
    from tidalapi.exceptions import AssetNotAvailable

    track = MagicMock()
    track.audio_quality = "LOSSLESS"
    track.audio_modes = []
    album = MagicMock()
    album.name = "Delisted Album"
    album.id = 777
    track.album = album
    track.artist = None
    track.duration = 200
    track.name = "Song"
    track.available = True

    session = MagicMock()
    session.track.return_value = track
    session.album.side_effect = AssetNotAvailable("asset not available")

    client = MagicMock()
    client._session = session

    report = platform_metadata.fetch_track_report(client, "999")

    assert report["album_stale"] is True
    assert report["available"] is True
    assert report["metadata"]["album_name"] == "Delisted Album"


def _track_with_album(album_type_value):
    import datetime

    track = MagicMock()
    track.audio_quality = "LOSSLESS"
    track.audio_modes = []
    track.artist = None
    track.duration = 200
    track.name = "Song"
    track.available = True
    track.explicit = False
    album = MagicMock()
    album.name = "Some Release"
    album.id = 5
    track.album = album

    full_album = MagicMock()
    full_album.release_date = datetime.datetime(1998, 5, 1)
    full_album.type = album_type_value

    session = MagicMock()
    session.track.return_value = track
    session.album.return_value = full_album
    client = MagicMock()
    client._session = session
    return client


def test_fetch_track_report_captures_album_type_lowercased():
    report = platform_metadata.fetch_track_report(_track_with_album("EP"), "5")
    assert report["metadata"]["album_type"] == "ep"


def test_album_type_regular_album_not_tagged():
    from tuneshift.db import Database as _DB

    import tempfile
    from pathlib import Path as _P
    db = _DB(_P(tempfile.mkdtemp()) / "t.db")
    tid = db.add_track(Track(title="S", artist="A", album="Some Release"))
    # A plain album: derive_tags must NOT emit an album-type tag for "album".
    db.upsert_track_platform_metadata(tid, "tidal", "5", album_type="album",
                                      release_year=1998)
    tags = platform_metadata.derive_tags(db, tid)
    assert "album" not in tags
    assert "1990s" in tags  # decade still derived


def test_album_type_ep_is_tagged():
    from tuneshift.db import Database as _DB

    import tempfile
    from pathlib import Path as _P
    db = _DB(_P(tempfile.mkdtemp()) / "t.db")
    tid = db.add_track(Track(title="S", artist="A", album="Some EP"))
    db.upsert_track_platform_metadata(tid, "tidal", "5", album_type="ep")
    tags = platform_metadata.derive_tags(db, tid)
    assert "ep" in tags
