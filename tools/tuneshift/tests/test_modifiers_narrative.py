"""Tests for narrative sequencer modifiers."""
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.modifiers import (
    SequenceContext, intensity_arc_modifier, chapter_break_modifier,
    duration_pacing_modifier,
)
from tuneshift.sequencer.intent import PlaylistIntent


def _make_track(emotional_intensity=0.5, duration_ms=240000, **kwargs):
    return TrackMetadata(
        track_id=1, title="Test", artist="A",
        emotional_intensity=emotional_intensity,
        duration_ms=duration_ms, **kwargs,
    )


def test_intensity_modifier_climax_rewards_intense():
    ctx = SequenceContext(position=13, total=20)
    track = _make_track(emotional_intensity=0.95)
    result = intensity_arc_modifier(track, ctx)
    assert result > 1.0


def test_intensity_modifier_climax_penalizes_lightweight():
    ctx = SequenceContext(position=13, total=20)
    track = _make_track(emotional_intensity=0.2)
    result = intensity_arc_modifier(track, ctx)
    assert result < 1.0


def test_intensity_modifier_opening_rewards_moderate():
    ctx = SequenceContext(position=1, total=20)
    track = _make_track(emotional_intensity=0.4)
    result = intensity_arc_modifier(track, ctx)
    assert result >= 1.0


def test_duration_pacing_penalizes_monotony():
    ctx = SequenceContext(position=5, total=20)
    for _ in range(3):
        ctx.advance(_make_track(duration_ms=240000))
    track = _make_track(duration_ms=242000)
    result = duration_pacing_modifier(track, ctx)
    assert result < 1.0


def test_duration_pacing_no_penalty_for_variety():
    ctx = SequenceContext(position=5, total=20)
    for _ in range(3):
        ctx.advance(_make_track(duration_ms=240000))
    track = _make_track(duration_ms=360000)
    result = duration_pacing_modifier(track, ctx)
    assert result >= 1.0


def test_chapter_break_rewards_contrast():
    intent = PlaylistIntent(
        dominant_themes=[], emotional_range=(0.3, 0.9),
        tonal_center="defiant", sonic_palette=["warm"],
        climax_candidates=[], suggested_arc="narrative",
        chapter_boundaries=[5],
    )
    ctx = SequenceContext(position=2, total=20)
    for _ in range(3):
        ctx.advance(_make_track(sonic_texture="warm", narrator_stance="vulnerable"))
    track = _make_track(sonic_texture="gritty", narrator_stance="defiant")
    result = chapter_break_modifier(track, ctx, intent)
    assert result > 1.0
