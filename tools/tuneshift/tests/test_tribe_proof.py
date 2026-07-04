"""Real-world proof: People's Instinctive Travels resolves correctly.

Alice's canonical adversarial case (A Tribe Called Quest, *People's Instinctive
Travels and the Paths of Rhythm*). This is a full integration test through the
real ``reconcile_track`` cascade + shared scorers, using realistic adversarial
Tidal candidate sets. It proves the two failure modes the engine exists to beat:

  1. "Can I Kick It?" must NEVER resolve to "Buggin' Out" — a *different* song on
     the same album by the same artist, which a naive top-hit matcher grabs.
  2. When several versions are returned, the studio/anniversary edition is
     preferred over a live cut.

The candidate list deliberately returns the trap FIRST so a regression back to
blind top-hit selection fails here loudly.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


@pytest.fixture
def tribe_db(tmp_path: Path) -> tuple[Database, int]:
    db = Database(tmp_path / "tribe.db")
    track_id = db.add_track(Track(
        title="Can I Kick It?",
        artist="A Tribe Called Quest",
        album="People's Instinctive Travels and the Paths of Rhythm "
        "(25th Anniversary Edition)",
        duration_seconds=252,
    ))
    return db, track_id


def _adversarial_tidal_client() -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    client.get_album_tracks.return_value = []
    client.search_track.return_value = [
        # TRAP first: different song, same artist/album, plausible duration.
        TrackResult(
            platform_id="trk_buggin_out",
            title="Buggin' Out",
            artist="A Tribe Called Quest",
            album="People's Instinctive Travels and the Paths of Rhythm",
            duration_seconds=223,
            available=True,
        ),
        # Live cut: correct title, wrong version.
        TrackResult(
            platform_id="trk_live",
            title="Can I Kick It? (Live)",
            artist="A Tribe Called Quest",
            album="Live at the Apollo",
            duration_seconds=270,
            available=True,
        ),
        # CORRECT: anniversary reissue of the studio recording.
        TrackResult(
            platform_id="trk_anniversary",
            title="Can I Kick It?",
            artist="A Tribe Called Quest",
            album="People's Instinctive Travels and the Paths of Rhythm "
            "(25th Anniversary Edition)",
            duration_seconds=252,
            available=True,
        ),
    ]
    return client


def test_can_i_kick_it_never_resolves_to_buggin_out(
    tribe_db: tuple[Database, int],
) -> None:
    db, track_id = tribe_db
    result = reconcile_track(db, track_id, _adversarial_tidal_client(), force=True)
    assert result.platform_track_id != "trk_buggin_out", (
        "resolved to a different song — the exact Soundiiz-class failure the "
        "engine exists to beat"
    )


def test_can_i_kick_it_prefers_studio_over_live(
    tribe_db: tuple[Database, int],
) -> None:
    db, track_id = tribe_db
    result = reconcile_track(db, track_id, _adversarial_tidal_client(), force=True)
    assert result.platform_track_id == "trk_anniversary"
    assert result.availability == "exact_available"
    assert result.confidence == "high"


def test_can_i_kick_it_trap_returned_first_is_still_rejected(
    tribe_db: tuple[Database, int],
) -> None:
    """Even though 'Buggin' Out' is the first search hit, it is rejected."""
    db, track_id = tribe_db
    client = _adversarial_tidal_client()
    assert client.search_track.return_value[0].platform_id == "trk_buggin_out"
    result = reconcile_track(db, track_id, client, force=True)
    assert result.platform_track_id == "trk_anniversary"
