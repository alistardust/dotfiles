"""Tests for playlist intent inference."""
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.intent import infer_intent


def _make_tracks(specs):
    tracks = []
    for i, (title, intensity, stance, themes, texture) in enumerate(specs):
        tracks.append(TrackMetadata(
            track_id=i, title=title, artist=f"Artist {i}",
            emotional_intensity=intensity, narrator_stance=stance,
            themes=themes, vibes=[], sonic_texture=texture,
        ))
    return tracks


def test_infer_intent_identifies_climax_candidates():
    tracks = _make_tracks([
        ("A", 0.3, "joyful", ["pop"], "warm"),
        ("B", 0.5, "introspective", ["folk"], "warm"),
        ("C", 0.95, "defiant", ["rock"], "gritty"),
        ("D", 0.4, "celebratory", ["pop"], "polished"),
        ("E", 0.9, "vulnerable", ["ballad"], "warm"),
    ])
    intent = infer_intent(tracks)
    assert 2 in intent.climax_candidates
    assert 4 in intent.climax_candidates


def test_infer_intent_finds_dominant_themes():
    tracks = _make_tracks([
        ("A", 0.5, "joyful", ["pop", "dance"], "polished"),
        ("B", 0.5, "joyful", ["pop", "synth"], "polished"),
        ("C", 0.5, "defiant", ["rock", "pop"], "gritty"),
    ])
    intent = infer_intent(tracks)
    assert "pop" in intent.dominant_themes


def test_infer_intent_detects_chapter_boundaries():
    tracks = _make_tracks([
        ("A", 0.5, "vulnerable", ["folk", "acoustic"], "warm"),
        ("B", 0.5, "vulnerable", ["folk", "acoustic"], "warm"),
        ("C", 0.5, "vulnerable", ["folk", "acoustic"], "warm"),
        ("D", 0.8, "defiant", ["rock", "electric"], "gritty"),
        ("E", 0.8, "defiant", ["rock", "electric"], "gritty"),
    ])
    intent = infer_intent(tracks)
    assert any(2 <= b <= 3 for b in intent.chapter_boundaries)
