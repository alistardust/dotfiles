"""FL3 gate: the unified preference model bites end-to-end (not just storage).

These are integration tests over the full ``reconcile_track`` selection path
(no stubbed engine). They prove the three FL3 fixes actually change which
release a playlist gets:

* multiple targets coexist on one axis and BOTH fire in selection (the
  historical overwrite bug where the second ``content avoid`` clobbered the
  first);
* a playlist-agnostic per-track (track-global) preference fires on any playlist
  even when that playlist has no pref of its own;
* the three-layer precedence resolved for a match agrees with what ``prefs
  show`` renders (most-specific wins).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tuneshift.commands.prefs_cmd import handle_prefs
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


def _args(action, key=None, value=None, target=None, *, playlist=None, track=None):
    return SimpleNamespace(
        action=action, key=key, value=value, target=target,
        playlist=playlist, track=track,
    )


@pytest.fixture()
def db(tmp_path) -> Database:
    database = Database(tmp_path / "fl3.db")
    yield database
    database.close()


def _seed(db: Database) -> tuple[int, int]:
    track_id = db.add_track(Track(title="Song", artist="Artist", album="Album"))
    playlist_id = db.create_playlist("Playlist")
    db.add_track_to_playlist(playlist_id, track_id, 0)
    return track_id, playlist_id


class TestMultiTargetBothFire:
    """Two ``content avoid`` targets on one axis both survive storage and both
    reach the matching engine — the overwrite bug (second ``avoid`` clobbering
    the first) is gone.

    ``content`` targets are also down-ranked by the intent-fidelity default, so
    an explicit avoid rarely changes the *winner* on its own; the rigorous proof
    is therefore at the exact seam ``reconcile_track`` consults — the resolved
    active preferences handed to the two-phase engine — plus a corroborating
    end-to-end selection.
    """

    def _candidates(self) -> list[TrackResult]:
        return [
            TrackResult(platform_id="karaoke", title="Song",
                        artist="Artist", album="Album",
                        tidal_version="Karaoke Version"),
            TrackResult(platform_id="instrumental", title="Song",
                        artist="Artist", album="Album",
                        tidal_version="Instrumental"),
            TrackResult(platform_id="clean", title="Song",
                        artist="Artist", album="Album"),
        ]

    def test_both_targets_active_at_reconcile_seam(self, db):
        from tuneshift.matching.criteria import Strength
        from tuneshift.matching.preferences import Preferences
        from tuneshift.reconcile import _scoped_active_prefs

        track_id, playlist_id = _seed(db)
        # Set BOTH targets via the CLI (the layer where the overwrite happened).
        assert handle_prefs(
            _args("set", "content", "avoid", "karaoke", playlist="Playlist"), db
        ) == 0
        assert handle_prefs(
            _args("set", "content", "avoid", "instrumental", playlist="Playlist"), db
        ) == 0
        # Both persist — the second did not overwrite the first.
        targets = {c["target"] for c in db.get_preferences(playlist_id)["criteria"]}
        assert targets == {"karaoke", "instrumental"}

        # Both are resolved as active AVOID preferences at the exact seam the
        # engine reads — proving both are wired through, not just stored.
        active = _scoped_active_prefs(db, track_id, playlist_id, Preferences())
        content = {
            ap.ref.target: ap.ref.strength
            for ap in active if ap.ref.criterion == "content"
        }
        assert content == {"karaoke": Strength.AVOID, "instrumental": Strength.AVOID}

    def test_both_avoids_select_a_clean_take(self, db):
        track_id, playlist_id = _seed(db)
        assert handle_prefs(
            _args("set", "content", "avoid", "karaoke", playlist="Playlist"), db
        ) == 0
        assert handle_prefs(
            _args("set", "content", "avoid", "instrumental", playlist="Playlist"), db
        ) == 0
        result = reconcile_track(
            db, track_id, _client(self._candidates()), playlist_id=playlist_id
        )
        # Neither avoided version is chosen.
        assert result.platform_track_id == "clean"


class TestTrackGlobalFiresOnAnyPlaylist:
    """A playlist-agnostic per-track preference (NULL playlist_id) fires when the
    track is reconciled on a playlist that has no preference of its own."""

    def _stereo_and_atmos(self) -> list[TrackResult]:
        return [
            TrackResult(platform_id="stereo", title="Song", artist="Artist",
                        album="Album", audio_modes=["STEREO"]),
            TrackResult(platform_id="atmos", title="Song", artist="Artist",
                        album="Album", audio_modes=["DOLBY_ATMOS"]),
        ]

    def test_track_global_pref_selects_atmos_on_playlist(self, db):
        track_id, playlist_id = _seed(db)
        # Track-global (--track only): applies on every playlist.
        assert handle_prefs(
            _args("set", "spatial", "prefer", "atmos", track=track_id), db
        ) == 0
        result = reconcile_track(
            db, track_id, _client(self._stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos"

    def test_no_track_global_pref_keeps_default_stereo(self, db):
        track_id, playlist_id = _seed(db)
        result = reconcile_track(
            db, track_id, _client(self._stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "stereo"


class TestPrecedenceSelectionMatchesShow:
    """The most-specific scope wins both in the resolved match and in the
    ``prefs show`` rendering (AC-CLI1)."""

    def _stereo_and_atmos(self) -> list[TrackResult]:
        return [
            TrackResult(platform_id="stereo", title="Song", artist="Artist",
                        album="Album", audio_modes=["STEREO"]),
            TrackResult(platform_id="atmos", title="Song", artist="Artist",
                        album="Album", audio_modes=["DOLBY_ATMOS"]),
        ]

    def test_playlist_track_override_wins_and_show_agrees(self, db, capsys):
        track_id, playlist_id = _seed(db)
        # Global avoids Atmos; the playlist-track override prefers it.
        assert handle_prefs(_args("set", "spatial", "avoid", "atmos"), db) == 0
        assert handle_prefs(
            _args("set", "spatial", "prefer", "atmos",
                  playlist="Playlist", track=track_id), db
        ) == 0

        # Selection: the most-specific playlist-track PREFER wins -> Atmos.
        result = reconcile_track(
            db, track_id, _client(self._stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos"

        # show agrees: playlist-track is the effective winner, global overridden.
        capsys.readouterr()
        assert handle_prefs(
            _args("list", playlist="Playlist", track=track_id), db
        ) == 0
        out = capsys.readouterr().out
        assert "* spatial prefer atmos" in out
        assert "(overridden)" in out


class TestShowTrackDisplaysOverride:
    """`prefs show --playlist --track` renders the playlist-track override (the
    historical display gap, issue #3)."""

    def test_show_playlist_track_lists_the_override(self, db, capsys):
        track_id, playlist_id = _seed(db)
        assert handle_prefs(
            _args("set", "spatial", "prefer", "atmos",
                  playlist="Playlist", track=track_id), db
        ) == 0
        capsys.readouterr()
        assert handle_prefs(
            _args("show", playlist="Playlist", track=track_id), db
        ) == 0
        out = capsys.readouterr().out
        assert "[playlist-track]" in out
        assert "spatial prefer atmos" in out
