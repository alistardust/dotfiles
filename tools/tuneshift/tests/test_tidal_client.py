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


def test_search_album() -> None:
    """search_album returns AlbumResult list."""
    from tuneshift.models import AlbumResult
    
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True
    
    mock_album = MagicMock()
    mock_album.id = 12345
    mock_album.name = "Youthquake"
    mock_album.artist.name = "Dead or Alive"
    mock_album.num_tracks = 10
    mock_album.year = 1985
    client._session.search.return_value = {"albums": [mock_album]}

    results = client.search_album("Youthquake Dead or Alive", limit=5)
    assert len(results) == 1
    assert results[0].platform_id == "12345"
    assert results[0].title == "Youthquake"
    assert results[0].artist == "Dead or Alive"


def test_get_album_tracks() -> None:
    """get_album_tracks returns TrackResult list for all tracks on album."""
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True
    
    mock_track = MagicMock()
    mock_track.id = 999
    mock_track.name = "You Spin Me Round"
    mock_track.artist.name = "Dead or Alive"
    mock_track.album.name = "Youthquake"
    mock_track.duration = 200
    mock_track.isrc = "GBAYE8500123"
    mock_album = MagicMock()
    mock_album.tracks.return_value = [mock_track]
    client._session.album.return_value = mock_album

    results = client.get_album_tracks("12345")
    assert len(results) == 1
    assert results[0].title == "You Spin Me Round"


def test_search_artist() -> None:
    """search_artist returns ArtistResult list."""
    from tuneshift.models import ArtistResult
    
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True
    
    mock_artist = MagicMock()
    mock_artist.id = 777
    mock_artist.name = "Big Freedia"
    client._session.search.return_value = {"artists": [mock_artist]}

    results = client.search_artist("Big Freedia", limit=3)
    assert len(results) == 1
    assert results[0].platform_id == "777"
    assert results[0].name == "Big Freedia"


def test_get_artist_albums() -> None:
    """get_artist_albums returns AlbumResult list."""
    from tuneshift.models import AlbumResult
    
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True
    
    mock_album = MagicMock()
    mock_album.id = 456
    mock_album.name = "3rd Ward Bounce"
    mock_album.artist.name = "Big Freedia"
    mock_album.num_tracks = 12
    mock_album.year = 2018
    mock_artist = MagicMock()
    mock_artist.get_albums.return_value = [mock_album]
    client._session.artist.return_value = mock_artist

    results = client.get_artist_albums("777", limit=20)
    assert len(results) == 1
    assert results[0].title == "3rd Ward Bounce"


def test_get_track() -> None:
    """get_track returns a single TrackResult by ID."""
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._session.check_login.return_value = True
    
    mock_track = MagicMock()
    mock_track.id = 122361821
    mock_track.name = "Louder"
    mock_track.artist.name = "Big Freedia"
    mock_track.album.name = "3rd Ward Bounce"
    mock_track.duration = 195
    mock_track.isrc = "USRC12345678"
    client._session.track.return_value = mock_track

    result = client.get_track("122361821")
    assert result is not None
    assert result.title == "Louder"
    assert result.platform_id == "122361821"
