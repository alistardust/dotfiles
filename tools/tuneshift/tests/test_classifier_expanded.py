"""Tests for expanded classifier prompt and response parsing."""
import json
import pytest
from tuneshift.sequencer.classifier import parse_classification_response, build_classification_prompt


def test_parse_expanded_response():
    """Parser handles new narrative fields in JSON response."""
    response = json.dumps([{
        "title": "Protest",
        "artist": "Kim Petras",
        "themes": ["empowerment", "identity"],
        "vibes": ["anthemic", "dark"],
        "instruments": ["synth", "drums"],
        "density": "dense",
        "era_mood": ["2020s pop"],
        "lyrical_subject": "trans defiance",
        "emotional_intensity": 0.9,
        "narrator_stance": "defiant",
        "sonic_texture": "polished",
        "space": "vast",
        "groove_feel": "driving",
        "opens_with": "synth pad",
        "closes_with": "hard cut",
        "energy_arc_within": "builds to peak",
        "confidence": 0.85,
    }])
    results = parse_classification_response(response)
    assert len(results) == 1
    assert results[0]["emotional_intensity"] == 0.9
    assert results[0]["narrator_stance"] == "defiant"
    assert results[0]["confidence"] == 0.85


def test_parse_legacy_response_still_works():
    """Old-format responses (without new fields) still parse correctly."""
    response = json.dumps([{
        "title": "Old Song",
        "artist": "Artist",
        "themes": ["rock"],
        "vibes": ["energetic"],
        "instruments": ["guitar"],
        "density": "mid",
        "era_mood": ["1970s rock"],
    }])
    results = parse_classification_response(response)
    assert len(results) == 1
    assert "emotional_intensity" not in results[0]


def test_build_prompt_includes_narrative_fields():
    """Expanded prompt mentions all new classification fields."""
    tracks = [{"title": "Test", "artist": "Artist"}]
    prompt = build_classification_prompt(tracks)
    assert "emotional_intensity" in prompt
    assert "narrator_stance" in prompt
    assert "sonic_texture" in prompt
    assert "opens_with" in prompt
    assert "confidence" in prompt
