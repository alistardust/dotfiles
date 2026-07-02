"""Ordering/behavior snapshot for ``reconcile_track`` taken BEFORE the refactor.

Captured while the signature is ``reconcile_track(db, track_id, client, ...)``
(no ``playlist_id``). This freezes the current candidate scoring, tiebreak,
classification, and alternative ordering so the package split (Chunk 2) and the
``playlist_id`` addition are provably behavior-preserving by default. The values
here intentionally include current weaknesses (e.g. an unrelated same-album track
ranking above the live version); those are re-baselined in the scoring chunks with
a human-reviewed diff.
"""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


def _pool() -> list[TrackResult]:
    return [
        TrackResult(
            platform_id="std", title="Can I Kick It?", artist="A Tribe Called Quest",
            album="People's Instinctive Travels and the Paths of Rhythm",
            duration_seconds=252,
        ),
        TrackResult(
            platform_id="remaster", title="Can I Kick It?", artist="A Tribe Called Quest",
            album="People's Instinctive Travels (25th Anniversary Remaster)",
            duration_seconds=252,
        ),
        TrackResult(
            platform_id="live", title="Can I Kick It? (Live)", artist="A Tribe Called Quest",
            album="Live at the Apollo", duration_seconds=300,
        ),
        TrackResult(
            platform_id="wrong", title="Buggin' Out", artist="A Tribe Called Quest",
            album="People's Instinctive Travels and the Paths of Rhythm",
            duration_seconds=230,
        ),
    ]


def test_reconcile_track_ordering_snapshot(tmp_db: Path) -> None:
    db = Database(tmp_db)
    track_id = db.add_track(Track(
        title="Can I Kick It?", artist="A Tribe Called Quest",
        album="People's Instinctive Travels and the Paths of Rhythm",
        duration_seconds=252,
    ))
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    client.search_track.return_value = _pool()

    result = reconcile_track(db, track_id, client)

    assert result.platform_track_id == "std"
    assert result.platform_title == "Can I Kick It?"
    assert result.platform_album == "People's Instinctive Travels and the Paths of Rhythm"
    assert result.score == 100
    assert result.confidence == "ambiguous"
    assert result.match_type == "title_artist"
    assert result.is_divergent is False
    assert result.divergence_note is None
    assert [a.platform_id for a in result.alternatives] == ["remaster", "wrong", "live"]
