"""FL1b proof: selection reads persisted candidates, not a live search (AC-X3).

Spec §4.1a retires ``reconcile_track``'s live candidate collection for
STEADY-STATE selection in favour of reading the persisted ``track_candidates``
set. The only live fetches allowed are (a) lock self-heal and (b) an explicit
refresh (``force=True``) / a cold cache. This proves:

  1. AC-X3: when candidates are already persisted, interactive matching does NOT
     hit the platform client — it scores over the persisted set.
  2. Cold cache: the first reconcile does one live refresh, persists the
     candidate set (in discovery order), and picks a winner.
  3. AC-P4: a subsequent reconcile is reproducible from the cache with NO further
     live search and the SAME winner.
"""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


class _ExplodingClient:
    """A client that fails loudly if any search method is called.

    Used to prove the steady-state path performs NO live search (AC-X3).
    """

    platform_name = "tidal"

    def _boom(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("live search performed during steady-state matching")

    search_track = _boom
    search_isrc = _boom
    search_album = _boom
    get_album_tracks = _boom
    search_artist = _boom
    get_artist_albums = _boom


class _CountingClient:
    """A client returning two realistic candidates, counting search calls."""

    platform_name = "tidal"

    def __init__(self) -> None:
        self.search_calls = 0

    def search_track(self, query, limit=10):  # noqa: ANN001
        del query, limit
        self.search_calls += 1
        return [
            TrackResult(
                platform_id="tidal-a", title="Ordinary World", artist="Duran Duran",
                album="Duran Duran (The Wedding Album)", duration_seconds=300,
                isrc="GBL;A", available=True,
            ),
            TrackResult(
                platform_id="tidal-b", title="Ordinary World", artist="Duran Duran",
                album="Greatest", duration_seconds=300, isrc="GBL;A", available=True,
            ),
        ]

    def search_isrc(self, isrc):  # noqa: ANN001
        del isrc
        return None

    def search_album(self, query, limit=5):  # noqa: ANN001
        del query, limit
        return []

    def get_album_tracks(self, album_id):  # noqa: ANN001
        del album_id
        return []

    def search_artist(self, query, limit=3):  # noqa: ANN001
        del query, limit
        return []

    def get_artist_albums(self, artist_id, limit=20):  # noqa: ANN001
        del artist_id, limit
        return []


def _seed_track(db: Database) -> int:
    track_id = db.add_track(
        Track(title="Ordinary World", artist="Duran Duran",
              album="Duran Duran (The Wedding Album)", duration_seconds=300)
    )
    playlist_id = db.create_playlist("90s")
    db.add_track_to_playlist(playlist_id, track_id, 0)
    return track_id


def test_steady_state_reads_persisted_candidates_no_live_search(tmp_path: Path) -> None:
    db = Database(tmp_path / "x3.db")
    track_id = _seed_track(db)

    # Persist a candidate set exactly as the resolver would (discovery order).
    db.upsert_track_candidate(
        track_id, "tidal", "tidal-a",
        {"title": "Ordinary World", "artist": "Duran Duran",
         "album": "Duran Duran (The Wedding Album)", "duration_seconds": 300,
         "isrc": "GBL;A", "available": True},
        discovery_rank=0,
    )
    db.upsert_track_candidate(
        track_id, "tidal", "tidal-b",
        {"title": "Ordinary World", "artist": "Duran Duran", "album": "Greatest",
         "duration_seconds": 300, "isrc": "GBL;A", "available": True},
        discovery_rank=1,
    )

    # Interactive matching must NOT hit the client — reads the persisted set.
    result = reconcile_track(db, track_id, _ExplodingClient(), force=False)
    assert result.platform_track_id in {"tidal-a", "tidal-b"}


def test_cold_cache_refreshes_then_reproducible(tmp_path: Path) -> None:
    db = Database(tmp_path / "x3b.db")
    track_id = _seed_track(db)
    client = _CountingClient()

    # Cold cache: exactly one live refresh, candidates persisted.
    first = reconcile_track(db, track_id, client, force=False)
    assert client.search_calls >= 1
    calls_after_first = client.search_calls
    persisted = db.get_track_candidates(track_id, platform="tidal")
    assert {c["platform_track_id"] for c in persisted} == {"tidal-a", "tidal-b"}

    # AC-P4: a second reconcile is reproducible from cache with NO new search.
    second = reconcile_track(db, track_id, client, force=False)
    assert client.search_calls == calls_after_first  # no additional live search
    assert second.platform_track_id == first.platform_track_id
