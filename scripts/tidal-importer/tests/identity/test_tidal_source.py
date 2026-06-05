"""Tests for Tidal discography source."""

from __future__ import annotations

from unittest.mock import MagicMock

from tidal_importer.identity.sources.tidal import TidalSource


class TestTidalSearch:
    def test_no_client_returns_empty(self):
        source = TidalSource(client=None)
        result = source.search("Artist", "Title", artist_id=123)
        assert len(result.recordings) == 0

    def test_no_artist_id_returns_empty(self):
        source = TidalSource(client=MagicMock())
        result = source.search("Artist", "Title", artist_id=None)
        assert len(result.recordings) == 0

    def test_finds_track_in_discography(self):
        mock_track = MagicMock()
        mock_track.name = "Karma Police"
        mock_track.duration = 263
        mock_track.isrc = "GBAYE9700103"

        mock_album = MagicMock()
        mock_album.id = 1001
        mock_album.name = "OK Computer"
        mock_album.year = 1997

        mock_client = MagicMock()
        mock_client.get_artist_albums.return_value = [mock_album]
        mock_client.get_album_tracks.return_value = [mock_track]

        source = TidalSource(client=mock_client)
        result = source.search("Radiohead", "Karma Police", artist_id=123)

        assert len(result.recordings) == 1
        assert result.recordings[0].score == 0.65
        assert result.recordings[0].duration_ms == 263000
        assert result.evidence.source == "tidal_discography"
        assert result.evidence.confidence == 0.65

    def test_no_match_returns_empty(self):
        mock_track = MagicMock()
        mock_track.name = "Completely Different Song"
        mock_track.duration = 200

        mock_album = MagicMock()
        mock_album.id = 1001
        mock_album.name = "Some Album"
        mock_album.year = 2020

        mock_client = MagicMock()
        mock_client.get_artist_albums.return_value = [mock_album]
        mock_client.get_album_tracks.return_value = [mock_track]

        source = TidalSource(client=mock_client)
        result = source.search("Artist", "My Song", artist_id=123)

        assert len(result.recordings) == 0

    def test_api_error_returns_empty(self):
        mock_client = MagicMock()
        mock_client.get_artist_albums.side_effect = Exception("API error")

        source = TidalSource(client=mock_client)
        result = source.search("Artist", "Title", artist_id=123)
        assert len(result.recordings) == 0
