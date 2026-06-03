"""Unit tests for the Tidal platform client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from tuneshift.models import TrackResult
from tuneshift.platforms.tidal import TidalClient


def test_tidal_platform_name() -> None:
    client = TidalClient.__new__(TidalClient)
    client._session = None
    client._rate_limiter = MagicMock()
    assert client.platform_name == "tidal"


def test_search_track_wraps_platform_ids_as_strings() -> None:
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True

    track = MagicMock()
    track.id = 123456
    track.name = "Life on Mars?"
    track.artist = MagicMock(name="artist")
    track.artist.name = "David Bowie"
    track.album = MagicMock(name="album")
    track.album.name = "Hunky Dory"
    track.duration = 221
    track.isrc = "GBAYE7100001"
    client._session.search.return_value = {"tracks": [track]}

    results = client.search_track("Life on Mars?")

    assert results == [
        TrackResult(
            platform_id="123456",
            title="Life on Mars?",
            artist="David Bowie",
            album="Hunky Dory",
            duration_seconds=221,
            isrc="GBAYE7100001",
        )
    ]
    client._rate_limiter.wait.assert_called_once()


def test_load_session_reads_saved_token(tmp_path: Path) -> None:
    token_path = tmp_path / "tidal.json"
    token_path.write_text(
        """{"token_type": "Bearer", "access_token": "abc", "refresh_token": "def", "expiry_time": null}""",
        encoding="utf-8",
    )

    with patch("tuneshift.platforms.tidal.validate_no_symlink") as validate, patch(
        "tuneshift.platforms.tidal.tidalapi.Session"
    ) as session_cls:
        session = session_cls.return_value
        session.load_oauth_session.return_value = True
        client = TidalClient(token_path=token_path)

        assert client.load_session() is True

        validate.assert_called_once_with(token_path)
        session.load_oauth_session.assert_called_once()


def test_replace_playlist_tracks_clears_and_readds_tracks() -> None:
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True

    playlist = MagicMock()
    existing_track = MagicMock()
    playlist.tracks.return_value = [existing_track, existing_track]
    client._session.playlist.return_value = playlist

    client.replace_playlist_tracks("42", ["100", "200"])

    playlist.remove_by_indices.assert_called_once_with([0, 1])
    playlist.add.assert_called_once_with([100, 200])
    client._rate_limiter.wait.assert_called_once()
