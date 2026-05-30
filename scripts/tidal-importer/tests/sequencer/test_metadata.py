"""Tests for multi-source metadata fetcher."""
from unittest.mock import MagicMock, patch

import pytest

from tidal_importer.sequencer.cache import MetadataCache, TrackMetadata
from tidal_importer.sequencer.metadata import (
    LastFmSource,
    MetadataFetcher,
    MusicBrainzSource,
    SpotifySource,
    isrc_to_camelot,
)


class TestIsrcToCamelot:
    def test_c_major(self):
        assert isrc_to_camelot(0, 1) == "8B"

    def test_a_minor(self):
        assert isrc_to_camelot(9, 0) == "8A"

    def test_none_key(self):
        assert isrc_to_camelot(None, 1) is None

    def test_none_mode(self):
        assert isrc_to_camelot(0, None) is None


class TestSpotifySource:
    def test_fetch_by_isrc_returns_features(self):
        mock_sp = MagicMock()
        mock_sp.search.return_value = {
            "tracks": {"items": [{"id": "spotify123", "name": "Test"}]}
        }
        mock_sp.audio_features.return_value = [{
            "tempo": 120.0,
            "key": 0,
            "mode": 1,
            "energy": 0.7,
            "valence": 0.5,
            "acousticness": 0.3,
            "loudness": -5.0,
            "danceability": 0.6,
            "duration_ms": 240000,
        }]

        source = SpotifySource(client=mock_sp)
        result = source.fetch_features(["USRC17607839"])

        assert "USRC17607839" in result
        features = result["USRC17607839"]
        assert features["bpm"] == 120.0
        assert features["energy"] == 0.7
        assert features["camelot_code"] == "8B"

    def test_fetch_handles_missing_track(self):
        mock_sp = MagicMock()
        mock_sp.search.return_value = {"tracks": {"items": []}}

        source = SpotifySource(client=mock_sp)
        result = source.fetch_features(["NONEXISTENT"])
        assert result == {}


class TestMetadataFetcher:
    def test_uses_cache_for_known_tracks(self, tmp_path):
        cache = MetadataCache(tmp_path / "test.db")
        cached_meta = TrackMetadata(
            isrc="CACHED001",
            tidal_id=1,
            title="Cached",
            artist="Artist",
            bpm=120.0,
            energy=0.7,
            themes=["love"],
            vibes=["warm"],
            instruments=["guitar"],
            density="mid",
            era_mood=["70s"],
        )
        cache.save(cached_meta)

        fetcher = MetadataFetcher(cache=cache)
        results = fetcher.get_metadata([
            {"isrc": "CACHED001", "tidal_id": 1, "title": "Cached", "artist": "Artist"}
        ])
        assert results["CACHED001"].bpm == 120.0

    def test_fetches_uncached_from_sources(self, tmp_path):
        cache = MetadataCache(tmp_path / "test.db")
        mock_spotify = MagicMock()
        mock_spotify.fetch_features.return_value = {
            "NEW001": {
                "bpm": 140.0,
                "key_note": 5,
                "mode": 0,
                "energy": 0.8,
                "valence": 0.6,
                "acousticness": 0.1,
                "loudness": -4.0,
                "danceability": 0.7,
                "duration_ms": 300000,
                "camelot_code": "12A",
            }
        }

        fetcher = MetadataFetcher(cache=cache, spotify_source=mock_spotify)
        results = fetcher.get_metadata([
            {"isrc": "NEW001", "tidal_id": 2, "title": "New", "artist": "B"}
        ])
        assert results["NEW001"].bpm == 140.0
        assert cache.get("NEW001") is not None
