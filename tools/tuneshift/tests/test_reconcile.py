"""Tests for the reconciliation engine."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.models import Track, PlatformMapping, TrackResult
from tuneshift.reconcile import reconcile_track


@pytest.fixture
def mock_client():
    """Create a mock platform client with all required methods."""
    client = MagicMock()
    client.platform_name = "test_platform"
    client.search_track.return_value = []
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


@pytest.fixture
def db_with_track(tmp_path):
    """Create a database with a test track for reconciliation."""
    db = Database(tmp_path / "test.db")
    track = Track(
        title="Louder",
        artist="Big Freedia",
        album="3rd Ward Bounce",
        duration_seconds=195
    )
    track_id = db.add_track(track)
    return db, track_id


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
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

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
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

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
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

    result = reconcile_track(db, track_id, client, force=True)
    assert result.from_cache is False
    assert result.platform_track_id == "new_id"


class TestReconcileWithIdentity:
    def test_isrc_match_gets_score_bonus(self, tmp_path):
        """score_match gives +15 bonus when ISRCs match."""
        from tuneshift.matching import score_match
        from tuneshift.models import Track, TrackResult

        canonical = Track(id=1, title="Heroes", artist="David Bowie", album=None, isrc="GBAYE7700012")
        candidate = TrackResult(
            platform_id="123", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=372, isrc="GBAYE7700012",
        )
        score_with_isrc = score_match(canonical, candidate)

        candidate_no_isrc = TrackResult(
            platform_id="456", title="Heroes", artist="David Bowie",
            album="Heroes", duration_seconds=372, isrc=None,
        )
        score_without_isrc = score_match(canonical, candidate_no_isrc)
        assert score_with_isrc >= score_without_isrc + 15

    def test_resolved_track_with_mapping_skips_reconcile(self, tmp_path):
        """Track with mb_recording_id + existing platform mapping skips reconcile."""
        from unittest.mock import MagicMock

        from tuneshift.db import Database
        from tuneshift.models import PlatformMapping, Track
        from tuneshift.reconcile import reconcile_track

        db = Database(tmp_path / "test.db")
        track = Track(title="Heroes", artist="David Bowie", album="Heroes", isrc="GBAYE7700012")
        track_id = db.add_track(track)

        db.store_resolution(
            track_id=track_id, mb_recording_id="mb-123", mb_release_group_id=None,
            confidence_tier="CONFIRMED", confidence_score=0.85,
            evidence=[{"source": "musicbrainz", "evidence_type": "isrc_lookup", "confidence": 0.85}],
        )
        db.upsert_platform_mapping(PlatformMapping(
            track_id=track_id, platform="tidal", platform_track_id="999",
        ))

        mock_client = MagicMock()
        mock_client.platform_name = "tidal"
        result = reconcile_track(db, track_id, mock_client)
        mock_client.search_isrc.assert_not_called()
        mock_client.search_track.assert_not_called()
        assert result.platform_track_id == "999"
        assert result.from_cache is True


def test_reconcile_finds_track_via_album_lookup(mock_client, db_with_track):
    """When title+artist search fails, album lookup finds the track."""
    db, track_id = db_with_track
    mock_client.search_track.return_value = []
    from tuneshift.models import AlbumResult, TrackResult
    mock_album = AlbumResult(platform_id="alb1", title="3rd Ward Bounce", artist="Big Freedia", track_count=12)
    mock_client.search_album.return_value = [mock_album]
    mock_client.get_album_tracks.return_value = [
        TrackResult(platform_id="t1", title="Louder", artist="Big Freedia", album="3rd Ward Bounce", duration_seconds=195),
    ]

    result = reconcile_track(db, track_id, mock_client, force=True)
    assert result.confidence == "high"
    assert result.platform_track_id == "t1"


def test_reconcile_deduplicates_across_strategies(mock_client, db_with_track):
    """Same platform_id from multiple strategies is only scored once."""
    db, track_id = db_with_track
    from tuneshift.models import TrackResult
    same_track = TrackResult(platform_id="t1", title="Louder", artist="Big Freedia", album="3rd Ward Bounce", duration_seconds=195)
    mock_client.search_track.return_value = [same_track]
    mock_client.search_album.return_value = []
    mock_client.search_artist.return_value = []

    result = reconcile_track(db, track_id, mock_client, force=True)
    assert result.platform_track_id == "t1"


def test_reconcile_high_score_album_candidate_wins(mock_client, db_with_track):
    """A high-scoring album-lookup candidate is selected as the best match.

    Text/album strategies never short-circuit the cascade (only an ISRC match
    at score 100 does), so later strategies still run; the winning candidate is
    simply the highest-scoring one. The mock_client fixture returns empty lists
    for the other search methods, so album lookup supplies the only candidate.
    """
    db, track_id = db_with_track
    from tuneshift.models import AlbumResult, TrackResult
    mock_album = AlbumResult(platform_id="alb1", title="3rd Ward Bounce", artist="Big Freedia", track_count=12)
    mock_client.search_album.return_value = [mock_album]
    mock_client.get_album_tracks.return_value = [
        TrackResult(platform_id="t1", title="Louder", artist="Big Freedia", album="3rd Ward Bounce", duration_seconds=195),
    ]

    result = reconcile_track(db, track_id, mock_client, force=True)
    assert result.platform_track_id == "t1"


def test_reconcile_tries_all_strategies_when_low_scores(mock_client, db_with_track):
    """Low-scoring results exhaust all strategies."""
    db, track_id = db_with_track
    from tuneshift.models import ArtistResult, AlbumResult, TrackResult

    # Album lookup returns wrong track (low score)
    mock_album = AlbumResult(platform_id="alb1", title="Other Album", artist="Other Artist", track_count=5)
    mock_client.search_album.return_value = [mock_album]
    mock_client.get_album_tracks.return_value = [
        TrackResult(platform_id="t_wrong", title="Wrong Song", artist="Other Artist", album="Other Album"),
    ]
    # ISRC returns nothing
    mock_client.search_isrc.return_value = None
    # Title+artist returns weak match
    mock_client.search_track.return_value = [
        TrackResult(platform_id="t_weak", title="Louder (Live)", artist="Big Freedia", album="Live Album"),
    ]
    # Artist browse returns the real match
    mock_artist = ArtistResult(platform_id="art1", name="Big Freedia")
    mock_client.search_artist.return_value = [mock_artist]
    mock_client.get_artist_albums.return_value = [mock_album]

    reconcile_track(db, track_id, mock_client, force=True)
    # All strategies were called
    mock_client.search_album.assert_called()
    mock_client.search_track.assert_called()
    mock_client.search_artist.assert_called()


def test_reconcile_availability_exact_available(tmp_db: Path) -> None:
    """A clean playable match reports EXACT_AVAILABLE with an audit."""
    from tuneshift.matching import Availability

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))
    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.return_value = [
        TrackResult(platform_id="sp1", title="Heroes", artist="David Bowie",
                    album="Heroes", available=True),
    ]
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

    result = reconcile_track(db, track_id, client)
    assert result.availability == Availability.EXACT_AVAILABLE
    assert result.audit is not None
    assert result.audit.chosen_platform_id == "sp1"


def test_reconcile_availability_blocked_is_exact_unavailable(tmp_db: Path) -> None:
    """The exact recording found but not playable -> EXACT_UNAVAILABLE, not a miss."""
    from tuneshift.matching import Availability

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))
    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.return_value = [
        TrackResult(platform_id="sp1", title="Heroes", artist="David Bowie",
                    album="Heroes", available=False),
    ]
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

    result = reconcile_track(db, track_id, client)
    assert result.availability == Availability.EXACT_UNAVAILABLE


def test_reconcile_ytmusic_miss_is_ambiguous(tmp_db: Path) -> None:
    """YouTube Music can't distinguish absence -> AMBIGUOUS, never NOT_FOUND."""
    from tuneshift.matching import Availability

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Obscure", artist="Nobody", album="None"))
    client = MagicMock()
    client.platform_name = "ytmusic"
    client.search_isrc.return_value = None
    client.search_track.return_value = []
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

    result = reconcile_track(db, track_id, client)
    assert result.availability == Availability.AMBIGUOUS
