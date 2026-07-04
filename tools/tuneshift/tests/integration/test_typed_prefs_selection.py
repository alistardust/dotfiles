"""Integration: typed (criterion, strength, target) prefs drive real selection.

These exercise the AC-CLI1 general preference model end-to-end through
``reconcile_track`` — a preference stored at global / playlist / playlist-track
scope must actually change which platform release the matcher picks, using the
"Beg For You" Atmos-vs-stereo shape (same recording, separate Tidal IDs
distinguished only by ``audio_modes``). This is the wiring that closes the
CONTROL-pillar gap where an "Atmos" playlist matched all-stereo IDs.
"""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


def _client(results: list[TrackResult]) -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_track.return_value = results
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def _candidates() -> list[TrackResult]:
    # Same identity (title/artist/album/isrc) -> identical base distance -> the
    # two releases fall in one ambiguity cluster, so a spatial preference (not the
    # base score) decides which wins. Stereo is listed FIRST so a default run
    # picks stereo; the preference must flip that.
    stereo = TrackResult(
        platform_id="stereo_id", title="Beg For You", artist="Charli XCX",
        album="Crash", isrc="GBARL2100123", duration_seconds=173,
        available=True, audio_modes=["STEREO"],
    )
    atmos = TrackResult(
        platform_id="atmos_id", title="Beg For You", artist="Charli XCX",
        album="Crash", isrc="GBARL2100123", duration_seconds=173,
        available=True, audio_modes=["DOLBY_ATMOS"],
    )
    return [stereo, atmos]


def _setup(tmp_db: Path) -> tuple[Database, int, int]:
    db = Database(tmp_db)
    track_id = db.add_track(
        Track(title="Beg For You", artist="Charli XCX", album="Crash",
              isrc="GBARL2100123", duration_seconds=173)
    )
    playlist_id = db.create_playlist("Spatial Sessions")
    db.add_track_to_playlist(playlist_id, track_id, 0)
    return db, track_id, playlist_id


class TestNoPrefParity:
    def test_default_picks_first_listed_stereo(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = _setup(tmp_db)
        result = reconcile_track(
            db, track_id, _client(_candidates()), playlist_id=playlist_id
        )
        # No preference configured -> the tie resolves to insertion order (stereo).
        assert result.platform_track_id == "stereo_id"


class TestGlobalScope:
    def test_global_prefer_atmos_selects_atmos(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_global_preferences(
            {"criteria": [{"criterion": "spatial", "strength": "prefer",
                           "target": "atmos"}]}
        )
        result = reconcile_track(
            db, track_id, _client(_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos_id"


class TestPlaylistScope:
    def test_playlist_prefer_atmos_selects_atmos(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_preferences(
            playlist_id,
            {"criteria": [{"criterion": "spatial", "strength": "prefer",
                           "target": "atmos"}]},
        )
        result = reconcile_track(
            db, track_id, _client(_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos_id"

    def test_playlist_require_atmos_hard_filters_stereo(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_preferences(
            playlist_id,
            {"criteria": [{"criterion": "spatial", "strength": "require",
                           "target": "atmos"}]},
        )
        result = reconcile_track(
            db, track_id, _client(_candidates()), playlist_id=playlist_id
        )
        # require eliminates the stereo release entirely (phase-1 hard filter).
        assert result.platform_track_id == "atmos_id"


class TestPlaylistTrackScope:
    def test_playlist_track_prefer_atmos_selects_atmos(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_playlist_track_pref(playlist_id, track_id, "spatial", "prefer", "atmos")
        result = reconcile_track(
            db, track_id, _client(_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos_id"


class TestPrecedence:
    def test_playlist_track_require_overrides_global_avoid(self, tmp_db: Path) -> None:
        # Most-specific scope wins: a global "avoid atmos" is overridden by a
        # playlist-track "require atmos", and the two do NOT fight as contradictory
        # hard filters (the collapse in resolve_scoped_specs keeps only the
        # specific one).
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_global_preferences(
            {"criteria": [{"criterion": "spatial", "strength": "avoid",
                           "target": "atmos"}]}
        )
        db.set_playlist_track_pref(playlist_id, track_id, "spatial", "require", "atmos")
        result = reconcile_track(
            db, track_id, _client(_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos_id"
