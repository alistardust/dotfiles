"""Tests for MusicBrainz identity source."""

from unittest.mock import patch

from tuneshift.identity.sources.musicbrainz import MusicBrainzSource


class TestMusicBrainzLookupISRC:
    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_found_single_recording(self, mock_mb):
        mock_mb.get_recordings_by_isrc.return_value = {
            "isrc": {
                "recording-list": [
                    {
                        "id": "abc-123",
                        "title": "Heroes",
                        "artist-credit": [{"artist": {"name": "David Bowie"}}],
                        "length": "372000",
                        "release-group-list": [
                            {"id": "rg-1", "title": "Heroes", "type": "Album"}
                        ],
                    }
                ]
            }
        }
        source = MusicBrainzSource()
        result = source.lookup_isrc("GBAYE7700012", duration_ms=372000)
        assert result is not None
        assert len(result.recordings) == 1
        assert result.recordings[0].mb_recording_id == "abc-123"
        assert result.evidence is not None
        assert result.evidence.source == "musicbrainz"

    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_isrc_not_found(self, mock_mb):
        mock_mb.get_recordings_by_isrc.side_effect = Exception("Not found")
        source = MusicBrainzSource()
        result = source.lookup_isrc("INVALID000000")
        assert result is None


class TestMusicBrainzSearch:
    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_search_returns_candidates(self, mock_mb):
        mock_mb.search_recordings.return_value = {
            "recording-list": [
                {
                    "id": "abc-123",
                    "title": "Heroes",
                    "artist-credit": [{"artist": {"name": "David Bowie"}}],
                    "length": "372000",
                    "ext:score": "100",
                    "release-list": [
                        {
                            "release-group": {
                                "id": "rg-1",
                                "title": "Heroes",
                                "type": "Album",
                            }
                        }
                    ],
                }
            ]
        }
        source = MusicBrainzSource()
        result = source.search("David Bowie", "Heroes", duration_ms=372000)
        assert len(result.recordings) >= 1
        assert result.recordings[0].title == "Heroes"

    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_search_no_results(self, mock_mb):
        mock_mb.search_recordings.return_value = {"recording-list": []}
        source = MusicBrainzSource()
        result = source.search("Unknown", "Nonexistent")
        assert result.recordings == []
