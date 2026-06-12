"""Tests for playlist ingestion."""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import TrackResult, PlaylistInfo
from tuneshift.ingest import ingest_from_platform


def test_ingest_creates_playlist_and_tracks(tmp_db: Path) -> None:
    """Ingest creates canonical playlist with tracks."""
    db = Database(tmp_db)

    client = MagicMock()
    client.platform_name = "tidal"
    client.get_playlist.return_value = PlaylistInfo(
        platform_id="pl_123", name="Diamond Dogs", num_tracks=2,
    )
    client.get_playlist_tracks.return_value = [
        TrackResult(platform_id="t1", title="Diamond Dogs", artist="David Bowie", album="Diamond Dogs"),
        TrackResult(platform_id="t2", title="Rebel Rebel", artist="David Bowie", album="Diamond Dogs"),
    ]

    name, total, new, _skipped = ingest_from_platform(db, client, "pl_123")
    assert name == "Diamond Dogs"
    assert total == 2
    assert new == 2

    # Verify playlist created
    pl = db.find_playlist_by_name("Diamond Dogs")
    assert pl is not None

    # Verify tracks in order
    tracks = db.get_playlist_tracks(pl.id)
    assert len(tracks) == 2
    assert tracks[0].title == "Diamond Dogs"
    assert tracks[1].title == "Rebel Rebel"


def test_ingest_deduplicates_existing_tracks(tmp_db: Path) -> None:
    """Ingest reuses existing canonical tracks."""
    db = Database(tmp_db)
    from tuneshift.models import Track
    db.add_track(Track(title="Diamond Dogs", artist="David Bowie", album="Diamond Dogs"))

    client = MagicMock()
    client.platform_name = "spotify"
    client.get_playlist.return_value = PlaylistInfo(
        platform_id="sp_pl1", name="Test Playlist", num_tracks=1,
    )
    client.get_playlist_tracks.return_value = [
        TrackResult(platform_id="sp_t1", title="Diamond Dogs", artist="David Bowie", album="Diamond Dogs"),
    ]

    name, total, new, _skipped = ingest_from_platform(db, client, "sp_pl1")
    assert total == 1
    assert new == 0


def test_ingest_stores_platform_mapping(tmp_db: Path) -> None:
    """Ingest stores platform track mapping."""
    db = Database(tmp_db)

    client = MagicMock()
    client.platform_name = "tidal"
    client.get_playlist.return_value = PlaylistInfo(
        platform_id="pl_1", name="Test", num_tracks=1,
    )
    client.get_playlist_tracks.return_value = [
        TrackResult(platform_id="tid_99", title="Heroes", artist="David Bowie", album="Heroes"),
    ]

    ingest_from_platform(db, client, "pl_1")

    # Check mapping was stored
    track = db.find_track("Heroes", "David Bowie", "Heroes")
    mapping = db.get_platform_mapping(track.id, "tidal")
    assert mapping is not None
    assert mapping.platform_track_id == "tid_99"
    assert mapping.user_approved is True
