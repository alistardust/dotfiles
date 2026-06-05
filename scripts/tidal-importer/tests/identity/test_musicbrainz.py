"""Tests for MusicBrainz source."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tidal_importer.identity.sources.musicbrainz import MusicBrainzSource


class TestISRCLookup:
    def setup_method(self):
        self.source = MusicBrainzSource()

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.get_recordings_by_isrc")
    def test_single_isrc_match(self, mock_isrc):
        mock_isrc.return_value = {
            "recording-list": [
                {
                    "id": "abc123",
                    "title": "Test Song",
                    "length": "240000",
                    "artist-credit": [{"artist": {"name": "Test Artist"}}],
                }
            ]
        }
        result = self.source.lookup_isrc("USAB12345678")
        assert result is not None
        assert len(result.recordings) == 1
        assert result.recordings[0].title == "Test Song"
        assert result.recordings[0].score == 0.97
        assert result.evidence.confidence == 0.97
        assert result.evidence.evidence_type == "isrc_match"

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.get_recordings_by_isrc")
    def test_multiple_isrc_disambiguated_by_duration(self, mock_isrc):
        mock_isrc.return_value = {
            "recording-list": [
                {
                    "id": "abc1",
                    "title": "Test Song",
                    "length": "240000",
                    "artist-credit": [{"artist": {"name": "Artist"}}],
                },
                {
                    "id": "abc2",
                    "title": "Test Song (Live)",
                    "length": "360000",
                    "artist-credit": [{"artist": {"name": "Artist"}}],
                },
            ]
        }
        result = self.source.lookup_isrc("USAB12345678", duration_ms=241000)
        assert result is not None
        assert len(result.recordings) == 1
        assert result.recordings[0].mb_recording_id == "abc1"
        assert result.evidence.confidence == 0.92

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.get_recordings_by_isrc")
    def test_no_results_returns_none(self, mock_isrc):
        mock_isrc.return_value = {"recording-list": []}
        result = self.source.lookup_isrc("USAB00000000")
        assert result is None

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.get_recordings_by_isrc")
    def test_api_error_returns_none(self, mock_isrc):
        import musicbrainzngs
        mock_isrc.side_effect = musicbrainzngs.WebServiceError("timeout")
        result = self.source.lookup_isrc("USAB12345678")
        assert result is None


class TestTextSearch:
    def setup_method(self):
        self.source = MusicBrainzSource()

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.search_recordings")
    def test_good_match_high_confidence(self, mock_search):
        mock_search.return_value = {
            "recording-list": [
                {
                    "id": "rec1",
                    "title": "Karma Police",
                    "length": "263000",
                    "artist-credit": [{"artist": {"name": "Radiohead"}}],
                }
            ]
        }
        result = self.source.search("Radiohead", "Karma Police", duration_ms=264000)
        assert len(result.recordings) == 1
        assert result.recordings[0].score == 0.85
        assert result.evidence.source == "musicbrainz"

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.search_recordings")
    def test_poor_title_match_excluded(self, mock_search):
        mock_search.return_value = {
            "recording-list": [
                {
                    "id": "rec1",
                    "title": "Completely Different Song",
                    "length": "200000",
                    "artist-credit": [{"artist": {"name": "Radiohead"}}],
                }
            ]
        }
        result = self.source.search("Radiohead", "Karma Police", duration_ms=264000)
        assert len(result.recordings) == 0

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.search_recordings")
    def test_api_error_returns_empty(self, mock_search):
        import musicbrainzngs
        mock_search.side_effect = musicbrainzngs.WebServiceError("timeout")
        result = self.source.search("Artist", "Title")
        assert len(result.recordings) == 0


class TestReleaseGroupInfo:
    def setup_method(self):
        self.source = MusicBrainzSource()

    @patch("tidal_importer.identity.sources.musicbrainz.musicbrainzngs.get_release_group_by_id")
    def test_returns_type_info(self, mock_rg):
        mock_rg.return_value = {
            "release-group": {
                "id": "rg1",
                "title": "OK Computer",
                "primary-type": "Album",
                "secondary-type-list": [],
                "first-release-date": "1997-05-21",
            }
        }
        info = self.source.get_release_group_info("rg1")
        assert info["primary_type"] == "Album"
        assert info["first_release_date"] == "1997-05-21"
