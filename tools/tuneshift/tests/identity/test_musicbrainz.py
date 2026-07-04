"""Tests for MusicBrainz identity source."""

from unittest.mock import patch

import pytest

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
        from musicbrainzngs import ResponseError
        mock_mb.get_recordings_by_isrc.side_effect = ResponseError(cause=Exception("Not found"))
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

    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_search_api_error_returns_empty_results(self, mock_mb):
        mock_mb.search_recordings.side_effect = RuntimeError("timeout")
        source = MusicBrainzSource()

        result = source.search("Artist", "Title")

        assert result.recordings == []
        assert result.evidence is None


class TestMusicBrainzAdditionalLookupISRC:
    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_multiple_matches_are_filtered_by_duration(self, mock_mb):
        mock_mb.get_recordings_by_isrc.return_value = {
            "isrc": {
                "recording-list": [
                    {
                        "id": "abc-short",
                        "title": "Heroes",
                        "artist-credit": [{"artist": {"name": "David Bowie"}}],
                        "length": "372000",
                    },
                    {
                        "id": "abc-live",
                        "title": "Heroes (Live)",
                        "artist-credit": [{"artist": {"name": "David Bowie"}}],
                        "length": "420000",
                    },
                ]
            }
        }
        source = MusicBrainzSource()

        result = source.lookup_isrc("GBAYE7700012", duration_ms=372000)

        assert result is not None
        assert [candidate.mb_recording_id for candidate in result.recordings] == ["abc-short"]
        assert result.evidence is not None
        assert result.evidence.evidence_type == "isrc_lookup"
        assert result.evidence.confidence == pytest.approx(0.90)

    @patch("tuneshift.identity.sources.musicbrainz.musicbrainzngs")
    def test_lookup_isrc_no_results_returns_none(self, mock_mb):
        mock_mb.get_recordings_by_isrc.return_value = {"isrc": {"recording-list": []}}
        source = MusicBrainzSource()

        assert source.lookup_isrc("GBAYE0000000") is None


class TestMusicBrainzLanguageComposer:
    """M6: capture language + composer from the MB recording/work data."""

    def test_recording_to_candidate_extracts_language_and_composer(self):
        source = MusicBrainzSource()
        recording = {
            "id": "rec-99",
            "title": "99 Luftballons",
            "artist-credit": [{"artist": {"name": "Nena"}}],
            "length": "232000",
            "language": "deu",
            "work-relation-list": [
                {
                    "work": {
                        "id": "work-1",
                        "title": "99 Luftballons",
                        "artist-relation-list": [
                            {"type": "composer",
                             "artist": {"name": "Carlo Karges"}},
                            {"type": "lyricist",
                             "artist": {"name": "Someone Else"}},
                        ],
                    }
                }
            ],
        }
        candidate = source._recording_to_candidate(recording)
        assert candidate.language == "deu"
        assert candidate.composer == "Carlo Karges"
        assert candidate.mb_work_id == "work-1"

    def test_recording_to_candidate_missing_language_composer_is_none(self):
        source = MusicBrainzSource()
        recording = {
            "id": "rec-1",
            "title": "Heroes",
            "artist-credit": [{"artist": {"name": "David Bowie"}}],
            "length": "372000",
        }
        candidate = source._recording_to_candidate(recording)
        assert candidate.language is None
        assert candidate.composer is None
        assert candidate.mb_work_id is None
