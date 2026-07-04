"""Integration tests: per-playlist preferences bias reconciliation ordering."""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


def _client(results: list[TrackResult]) -> MagicMock:
    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.return_value = results
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


class TestGlobalPreferencesRoundTrip:
    def test_set_get_global_preferences(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert db.get_global_preferences() is None
        db.set_global_preferences({"avoid": ["remix"]})
        assert db.get_global_preferences() == {"avoid": ["remix"]}

    def test_overwrite_global_preferences(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.set_global_preferences({"avoid": ["remix"]})
        db.set_global_preferences({"avoid": ["live"]})
        assert db.get_global_preferences() == {"avoid": ["live"]}

    def test_clear_global_preferences(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.set_global_preferences({"avoid": ["remix"]})
        db.set_global_preferences(None)
        assert db.get_global_preferences() is None


class TestPlaylistPreferenceReRank:
    """Preferences bias candidate *ordering* within a scoring band.

    In Chunk 2 this is a bounded tie-break: among candidates that score equally
    under default scoring, a preferred keyword decides the pick. Overriding a
    version penalty (e.g. forcing a live take to beat the studio master on a
    live-recordings playlist) is version-intent semantics owned by Chunk 4; the
    default-preferences path here stays byte-parity with the pre-preferences
    engine.
    """

    def _setup(self, tmp_db: Path) -> tuple[Database, int, int]:
        db = Database(tmp_db)
        track_id = db.add_track(
            Track(title="Song", artist="Artist", album="Neutral Album")
        )
        playlist_id = db.create_playlist("A Playlist")
        db.add_track_to_playlist(playlist_id, track_id, 0)
        return db, track_id, playlist_id

    def _tied_candidates(self) -> list[TrackResult]:
        # Identical title/artist; albums both fully mismatch the source album
        # and carry no version/edition keywords -> identical default score.
        return [
            TrackResult(platform_id="alpha", title="Song", artist="Artist",
                        album="Alpha"),
            TrackResult(platform_id="bravo", title="Song", artist="Artist",
                        album="Bravo"),
        ]

    def test_default_preferences_preserve_insertion_order_on_a_tie(
        self, tmp_db: Path
    ) -> None:
        db, track_id, playlist_id = self._setup(tmp_db)
        # No preferences set -> default cascade -> byte-parity ordering: the
        # first-inserted candidate wins the tie.
        result = reconcile_track(
            db, track_id, _client(self._tied_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "alpha"

    def test_preferred_keyword_breaks_the_tie(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = self._setup(tmp_db)
        db.set_preferences(playlist_id, {"prefer": ["bravo"]})
        result = reconcile_track(
            db, track_id, _client(self._tied_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "bravo"

    def test_playlist_id_none_ignores_configured_preferences(
        self, tmp_db: Path
    ) -> None:
        db, track_id, playlist_id = self._setup(tmp_db)
        # Preferences exist but no playlist_id is passed -> not consulted ->
        # default (insertion-order) tie-break stands.
        db.set_preferences(playlist_id, {"prefer": ["bravo"]})
        result = reconcile_track(
            db, track_id, _client(self._tied_candidates()), playlist_id=None
        )
        assert result.platform_track_id == "alpha"

    def test_track_preferences_override_playlist(self, tmp_db: Path) -> None:
        # Track-level prefs are the highest-precedence layer: they must win over
        # a conflicting playlist-level preference. Proves the track layer is
        # actually consulted in reconcile (previously wired as track=None).
        db, track_id, playlist_id = self._setup(tmp_db)
        db.set_preferences(playlist_id, {"prefer": ["alpha"]})
        db.set_track_preferences(track_id, {"prefer": ["bravo"]})
        result = reconcile_track(
            db, track_id, _client(self._tied_candidates()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "bravo"


class TestAudioFormatPreferenceEndToEnd:
    """A per-playlist audio-format preference selects the Atmos release through
    the full reconcile path (AC-S5), not just the engine unit.

    This is the wiring that the earlier per-axis attempts dropped: a stored
    ``prefer atmos`` is bridged onto the engine's typed ``spatial`` criterion, so
    reconcile actually returns the Atmos platform id when both a stereo and an
    Atmos release exist for the same recording (Tidal ships them as separate
    ids).
    """

    def _setup(self, tmp_db: Path) -> tuple[Database, int, int]:
        db = Database(tmp_db)
        track_id = db.add_track(
            Track(title="Flowerz", artist="Armand", album="Flowerz")
        )
        playlist_id = db.create_playlist("Atmos Playlist")
        db.add_track_to_playlist(playlist_id, track_id, 0)
        return db, track_id, playlist_id

    def _stereo_and_atmos(self) -> list[TrackResult]:
        # Same recording, two releases differing only by spatial audio mode.
        return [
            TrackResult(
                platform_id="stereo", title="Flowerz", artist="Armand",
                album="Flowerz", audio_modes=["STEREO"],
            ),
            TrackResult(
                platform_id="atmos", title="Flowerz", artist="Armand",
                album="Flowerz", audio_modes=["DOLBY_ATMOS"],
            ),
        ]

    def test_prefer_atmos_selects_atmos_release(self, tmp_db: Path) -> None:
        db, track_id, playlist_id = self._setup(tmp_db)
        db.set_preferences(playlist_id, {"prefer": ["atmos"]})
        result = reconcile_track(
            db, track_id, _client(self._stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos"

    def test_default_prefs_do_not_force_atmos(self, tmp_db: Path) -> None:
        # No audio-format preference -> the stereo release (first-inserted, tied)
        # is not displaced: byte-parity with the pre-preferences behaviour.
        db, track_id, playlist_id = self._setup(tmp_db)
        result = reconcile_track(
            db, track_id, _client(self._stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "stereo"

    def test_prefer_atmos_on_playlist_without_id_is_ignored(
        self, tmp_db: Path
    ) -> None:
        # Preference exists but no playlist context is passed -> not consulted.
        db, track_id, playlist_id = self._setup(tmp_db)
        db.set_preferences(playlist_id, {"prefer": ["atmos"]})
        result = reconcile_track(
            db, track_id, _client(self._stereo_and_atmos()), playlist_id=None
        )
        assert result.platform_track_id == "stereo"

    def test_typed_pref_winner_not_overridden_by_keyword_bias(
        self, tmp_db: Path
    ) -> None:
        # Review finding (Chunk 3 gate): the free-text keyword/edition tiebreak
        # must only fire when the engine left the top band unresolved
        # (decided_by is None). Here "prefer atmos" resolves the winner via the
        # typed spatial criterion, so a co-listed free-text keyword ("bravo")
        # that happens to match the STEREO release's album must NOT re-sort the
        # band and steal the pick back to stereo.
        db, track_id, playlist_id = self._setup(tmp_db)
        db.set_preferences(playlist_id, {"prefer": ["atmos", "bravo"]})
        candidates = [
            TrackResult(
                platform_id="stereo", title="Flowerz", artist="Armand",
                album="Flowerz (Bravo Edition)", audio_modes=["STEREO"],
            ),
            TrackResult(
                platform_id="atmos", title="Flowerz", artist="Armand",
                album="Flowerz", audio_modes=["DOLBY_ATMOS"],
            ),
        ]
        result = reconcile_track(
            db, track_id, _client(candidates), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos"

