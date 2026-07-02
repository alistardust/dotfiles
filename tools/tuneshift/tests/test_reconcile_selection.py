"""Selection snapshots for album/artist strategies (Chunk 3).

These freeze the *behavior change* from Chunk 3: candidate albums and artists
are now ranked by the shared scorers (``score_album_match`` /
``score_artist_match``) and gated by their classifiers, rather than blindly
taking ``albums[0]`` / ``artists[0]``. The tests deliberately place the
correct candidate away from index 0 so a regression back to blind picking
would fail here.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.models import AlbumResult, ArtistResult, Track, TrackResult
from tuneshift.reconcile import reconcile_track


@pytest.fixture
def db_with_track(tmp_path: Path) -> tuple[Database, int]:
    db = Database(tmp_path / "test.db")
    track_id = db.add_track(Track(
        title="Can I Kick It?",
        artist="A Tribe Called Quest",
        album="People's Instinctive Travels and the Paths of Rhythm",
        duration_seconds=252,
    ))
    return db, track_id


def _found_track() -> TrackResult:
    return TrackResult(
        platform_id="trk_right",
        title="Can I Kick It?",
        artist="A Tribe Called Quest",
        album="People's Instinctive Travels and the Paths of Rhythm",
        duration_seconds=252,
    )


def test_album_tracklist_ranks_best_album_not_index_zero(
    db_with_track: tuple[Database, int],
) -> None:
    """The correct album is chosen even when a wrong album is returned first."""
    db, track_id = db_with_track
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_track.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

    # Wrong album first, correct album second — blind [0] would pick wrong.
    client.search_album.return_value = [
        AlbumResult(platform_id="alb_wrong", title="Midnight Marauders",
                    artist="A Tribe Called Quest"),
        AlbumResult(platform_id="alb_right",
                    title="People's Instinctive Travels and the Paths of Rhythm",
                    artist="A Tribe Called Quest"),
    ]

    def _tracks(album_id: str) -> list[TrackResult]:
        return [_found_track()] if album_id == "alb_right" else [
            TrackResult(platform_id="x", title="Award Tour",
                        artist="A Tribe Called Quest", album="Midnight Marauders",
                        duration_seconds=200),
        ]

    client.get_album_tracks.side_effect = _tracks

    result = reconcile_track(db, track_id, client)
    assert result.platform_track_id == "trk_right"
    # The best-ranked album's tracklist was fetched.
    assert "alb_right" in [c[0][0] for c in client.get_album_tracks.call_args_list]


def test_artist_browse_picks_best_artist_not_index_zero(
    db_with_track: tuple[Database, int],
) -> None:
    """Artist browse selects the best-matching artist, not artists[0]."""
    db, track_id = db_with_track
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_track.return_value = []
    # Album search yields nothing so we fall through to artist browse.
    client.search_album.return_value = []

    # A confusable wrong artist first, the real one second.
    client.search_artist.return_value = [
        ArtistResult(platform_id="art_wrong", name="A Tribe Called Quest Tribute"),
        ArtistResult(platform_id="art_right", name="A Tribe Called Quest"),
    ]

    def _albums(artist_id: str, limit: int = 20) -> list[AlbumResult]:
        if artist_id == "art_right":
            return [AlbumResult(
                platform_id="alb_right",
                title="People's Instinctive Travels and the Paths of Rhythm",
                artist="A Tribe Called Quest",
            )]
        return []

    client.get_artist_albums.side_effect = _albums
    client.get_album_tracks.return_value = [_found_track()]

    result = reconcile_track(db, track_id, client)
    assert result.platform_track_id == "trk_right"
    # We browsed the correct artist's discography.
    assert "art_right" in [c[0][0] for c in client.get_artist_albums.call_args_list]
