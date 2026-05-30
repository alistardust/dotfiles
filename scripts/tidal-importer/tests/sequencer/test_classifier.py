"""Tests for LLM-based track classification."""
import json
from unittest.mock import MagicMock

from tidal_importer.sequencer.classifier import (
    TrackClassifier,
    build_classification_prompt,
    parse_classification_response,
)


class TestBuildPrompt:
    def test_builds_prompt_with_track_list(self):
        tracks = [
            {"title": "Hotel California", "artist": "Eagles"},
            {"title": "Stairway to Heaven", "artist": "Led Zeppelin"},
        ]
        prompt = build_classification_prompt(tracks)
        assert "Hotel California" in prompt
        assert "Stairway to Heaven" in prompt
        assert "themes" in prompt
        assert "vibes" in prompt
        assert "JSON" in prompt


class TestParseResponse:
    def test_parses_valid_json_array(self):
        response = json.dumps(
            [
                {
                    "title": "Hotel California",
                    "artist": "Eagles",
                    "themes": ["excess", "disillusionment", "california"],
                    "vibes": ["haunting", "dark", "hypnotic"],
                    "instruments": ["electric guitar", "drums", "bass"],
                    "density": "mid",
                    "era_mood": ["mid 70s rock", "west coast"],
                }
            ]
        )
        results = parse_classification_response(response)
        assert len(results) == 1
        assert results[0]["themes"] == ["excess", "disillusionment", "california"]
        assert results[0]["density"] == "mid"

    def test_handles_malformed_json(self):
        results = parse_classification_response("not json at all")
        assert results == []

    def test_handles_json_wrapped_in_markdown(self):
        response = (
            '```json\n[{"title": "X", "artist": "Y", "themes": ["a"], '
            '"vibes": ["b"], "instruments": ["c"], "density": "mid", '
            '"era_mood": ["d"]}]\n```'
        )
        results = parse_classification_response(response)
        assert len(results) == 1


class TestTrackClassifier:
    def test_classifies_batch(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "title": "Blowin' in the Wind",
                            "artist": "Bob Dylan",
                            "themes": ["justice", "freedom", "questioning"],
                            "vibes": ["contemplative", "gentle", "earnest"],
                            "instruments": ["acoustic guitar", "harmonica", "vocals"],
                            "density": "sparse",
                            "era_mood": ["early 60s folk", "protest era"],
                        }
                    ]
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        classifier = TrackClassifier(client=mock_client)
        results = classifier.classify(
            [{"title": "Blowin' in the Wind", "artist": "Bob Dylan"}]
        )
        assert len(results) == 1
        assert "justice" in results[0]["themes"]

    def test_handles_api_failure_gracefully(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        classifier = TrackClassifier(client=mock_client)
        results = classifier.classify([{"title": "Test", "artist": "Test"}])
        assert results == []
