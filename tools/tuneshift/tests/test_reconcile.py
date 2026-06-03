"""Tests for the reconciliation engine."""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, PlatformMapping, TrackResult
from tuneshift.reconcile import reconcile_track, ReconcileResult


def test_reconcile_uses_cache(tmp_db: Path) -> None:
    """Cached approved mapping returns immediately."""
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=track_id, platform="spotify",
        platform_track_id="sp123", match_score=95,
        status="matched", user_approved=True,
    ))

    client = MagicMock()
    client.platform_name = "spotify"

    result = reconcile_track(db, track_id, client)
    assert result.from_cache is True
    assert result.platform_track_id == "sp123"
    assert result.confidence == "high"
    client.search_track.assert_not_called()


def test_reconcile_searches_when_no_cache(tmp_db: Path) -> None:
    """Without cache, searches platform and scores results."""
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))

    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.return_value = [
        TrackResult(platform_id="sp1", title="Heroes", artist="David Bowie", album="Heroes"),
        TrackResult(platform_id="sp2", title="Heroes", artist="Wallflowers", album="Other"),
    ]

    result = reconcile_track(db, track_id, client)
    assert result.confidence == "high"
    assert result.platform_track_id == "sp1"
    assert result.score == 100
    assert result.from_cache is False


def test_reconcile_isrc_match(tmp_db: Path) -> None:
    """ISRC match takes priority over text search."""
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes", isrc="GBAYE7700012"))

    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = TrackResult(
        platform_id="tid99", title="Heroes", artist="David Bowie",
        album="Heroes", isrc="GBAYE7700012",
    )

    result = reconcile_track(db, track_id, client)
    assert result.platform_track_id == "tid99"
    assert result.score == 100
    client.search_track.assert_not_called()


def test_reconcile_not_found(tmp_db: Path) -> None:
    """No results returns not_found."""
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Obscure Song", artist="Nobody", album="Nothing"))

    client = MagicMock()
    client.platform_name = "ytmusic"
    client.search_isrc.return_value = None
    client.search_track.return_value = []

    result = reconcile_track(db, track_id, client)
    assert result.confidence == "not_found"


def test_reconcile_force_bypasses_cache(tmp_db: Path) -> None:
    """force=True ignores cached mapping."""
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=track_id, platform="spotify",
        platform_track_id="old_id", match_score=80,
        status="matched", user_approved=True,
    ))

    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.return_value = [
        TrackResult(platform_id="new_id", title="Heroes", artist="David Bowie", album="Heroes"),
    ]

    result = reconcile_track(db, track_id, client, force=True)
    assert result.from_cache is False
    assert result.platform_track_id == "new_id"
