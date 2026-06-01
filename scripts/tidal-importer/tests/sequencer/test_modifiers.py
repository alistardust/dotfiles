"""Tests for context-aware scoring modifiers."""
import pytest

from tidal_importer.sequencer.cache import TrackMetadata
from tidal_importer.sequencer.modifiers import (
    SCORE_FLOOR,
    SequenceContext,
    artist_recency_penalty,
    artist_variety_bonus,
    energy_monotony_penalty,
    era_diversity_bonus,
    narrative_arc_modifier,
    score_candidate,
    subgenre_staleness_penalty,
)


def _make_track(
    idx: int,
    artist: str = "Artist",
    energy: float = 0.5,
    themes: list[str] | None = None,
    vibes: list[str] | None = None,
    era_mood: list[str] | None = None,
) -> TrackMetadata:
    return TrackMetadata(
        isrc=f"ISRC{idx:010d}",
        tidal_id=idx,
        title=f"Track {idx}",
        artist=artist,
        energy=energy,
        valence=0.5,
        acousticness=0.5,
        mode=1,
        key_note=0,
        camelot_code="8B",
        bpm=120.0,
        themes=themes or ["love"],
        vibes=vibes or ["warm"],
        instruments=["guitar"],
        density="mid",
        era_mood=era_mood or ["70s rock"],
    )


class TestSequenceContext:
    def test_advance_tracks_position(self):
        ctx = SequenceContext(total=10, context_window=3)
        t = _make_track(0, "Beatles")
        ctx.advance(t)
        assert ctx.position == 1
        assert ctx.seen_artists["Beatles"] == 0

    def test_context_window_limits_recent(self):
        ctx = SequenceContext(total=10, context_window=3)
        for i in range(5):
            ctx.advance(_make_track(i, f"Artist{i}"))
        assert len(ctx.recent_tracks) == 3
        assert len(ctx.recent_energies) == 3


class TestArtistRecencyPenalty:
    def test_unknown_artist_no_penalty(self):
        ctx = SequenceContext(total=10)
        candidate = _make_track(1, "NewArtist")
        assert artist_recency_penalty(candidate, ctx) == 1.0

    def test_just_heard_heavy_penalty(self):
        ctx = SequenceContext(total=10)
        ctx.advance(_make_track(0, "Beatles"))
        candidate = _make_track(1, "Beatles")
        result = artist_recency_penalty(candidate, ctx)
        assert result == pytest.approx(0.10)

    def test_decay_with_distance(self):
        ctx = SequenceContext(total=10)
        ctx.advance(_make_track(0, "Beatles"))
        ctx.advance(_make_track(1, "Stones"))
        ctx.advance(_make_track(2, "Doors"))
        candidate = _make_track(3, "Beatles")
        # Beatles was 3 positions ago
        result = artist_recency_penalty(candidate, ctx)
        assert result == pytest.approx(0.25)

    def test_far_back_no_penalty(self):
        ctx = SequenceContext(total=20)
        ctx.advance(_make_track(0, "Beatles"))
        for i in range(1, 10):
            ctx.advance(_make_track(i, f"Other{i}"))
        candidate = _make_track(10, "Beatles")
        result = artist_recency_penalty(candidate, ctx)
        assert result == pytest.approx(1.0)

    def test_strength_zero_disables(self):
        ctx = SequenceContext(total=10)
        ctx.advance(_make_track(0, "Beatles"))
        candidate = _make_track(1, "Beatles")
        result = artist_recency_penalty(candidate, ctx, strength=0.0)
        assert result == pytest.approx(1.0)


class TestArtistVarietyBonus:
    def test_new_artist_gets_bonus(self):
        ctx = SequenceContext(total=10)
        ctx.advance(_make_track(0, "Beatles"))
        candidate = _make_track(1, "NewArtist")
        result = artist_variety_bonus(candidate, ctx)
        assert result > 1.0

    def test_heard_artist_no_bonus(self):
        ctx = SequenceContext(total=10)
        ctx.advance(_make_track(0, "Beatles"))
        candidate = _make_track(1, "Beatles")
        result = artist_variety_bonus(candidate, ctx)
        assert result == 1.0


class TestSubgenreStaleness:
    def test_fresh_themes_no_penalty(self):
        ctx = SequenceContext(total=10, context_window=3)
        ctx.advance(_make_track(0, themes=["love"], vibes=["warm"]))
        candidate = _make_track(1, themes=["protest"], vibes=["angry"])
        result = subgenre_staleness_penalty(candidate, ctx)
        assert result == 1.0

    def test_saturated_themes_penalty(self):
        ctx = SequenceContext(total=10, context_window=5)
        for i in range(5):
            ctx.advance(_make_track(i, f"A{i}", themes=["love", "peace"], vibes=["warm", "mellow"]))
        candidate = _make_track(5, "B", themes=["love", "peace"], vibes=["warm", "mellow"])
        result = subgenre_staleness_penalty(candidate, ctx)
        assert result < 1.0


class TestEraDiversityBonus:
    def test_different_era_gets_bonus(self):
        ctx = SequenceContext(total=10, context_window=3)
        for i in range(3):
            ctx.advance(_make_track(i, f"A{i}", era_mood=["70s rock"]))
        candidate = _make_track(3, era_mood=["60s folk"])
        result = era_diversity_bonus(candidate, ctx)
        assert result > 1.0

    def test_same_era_no_bonus(self):
        ctx = SequenceContext(total=10, context_window=3)
        for i in range(3):
            ctx.advance(_make_track(i, f"A{i}", era_mood=["70s rock"]))
        candidate = _make_track(3, era_mood=["70s rock"])
        result = era_diversity_bonus(candidate, ctx)
        assert result == 1.0


class TestEnergyMonotony:
    def test_no_penalty_with_varied_energy(self):
        ctx = SequenceContext(total=10, context_window=5)
        energies = [0.2, 0.7, 0.3, 0.8, 0.4]
        for i, e in enumerate(energies):
            ctx.advance(_make_track(i, f"A{i}", energy=e))
        candidate = _make_track(5, energy=0.5)
        result = energy_monotony_penalty(candidate, ctx)
        assert result == 1.0

    def test_penalty_for_continuing_flatline(self):
        ctx = SequenceContext(total=10, context_window=5)
        for i in range(5):
            ctx.advance(_make_track(i, f"A{i}", energy=0.5))
        candidate = _make_track(5, energy=0.5)
        result = energy_monotony_penalty(candidate, ctx)
        assert result < 1.0

    def test_bonus_for_breaking_flatline(self):
        ctx = SequenceContext(total=10, context_window=5)
        for i in range(5):
            ctx.advance(_make_track(i, f"A{i}", energy=0.5))
        candidate = _make_track(5, energy=0.8)
        result = energy_monotony_penalty(candidate, ctx)
        assert result > 1.0


class TestNarrativeArc:
    def test_river_rewards_gradual_drift(self):
        ctx = SequenceContext(total=20, context_window=5, narrative_mode="river")
        ctx.advance(_make_track(0, themes=["love", "peace"], vibes=["warm", "mellow"]))
        # Candidate has some overlap, some novelty (gradual drift)
        candidate = _make_track(1, themes=["love", "journey"], vibes=["warm", "adventurous"])
        result = narrative_arc_modifier(candidate, ctx)
        assert result >= 1.0

    def test_chapter_boosts_contrast_after_run(self):
        ctx = SequenceContext(total=20, context_window=5, narrative_mode="chapter")
        # 3 very similar tracks
        for i in range(3):
            ctx.advance(_make_track(i, f"A{i}", themes=["love", "peace"], vibes=["warm", "mellow"]))
        # Contrasting candidate
        candidate = _make_track(3, themes=["rebellion", "freedom"], vibes=["angry", "raw"])
        result = narrative_arc_modifier(candidate, ctx)
        assert result > 1.0


class TestScoreCandidate:
    def test_respects_score_floor(self):
        ctx = SequenceContext(total=10)
        ctx.advance(_make_track(0, "Beatles"))
        candidate = _make_track(1, "Beatles")
        # Even with penalties, should not go below floor
        result = score_candidate(candidate, _make_track(0, "Beatles"), ctx, 0.01)
        assert result >= SCORE_FLOOR

    def test_integration_penalizes_same_artist(self):
        ctx = SequenceContext(total=20, context_window=5)
        ctx.advance(_make_track(0, "Beatles", themes=["love"], vibes=["warm"]))
        current = _make_track(0, "Beatles")

        same_artist = _make_track(1, "Beatles", themes=["love"], vibes=["warm"])
        diff_artist = _make_track(2, "Stones", themes=["love"], vibes=["warm"])

        score_same = score_candidate(same_artist, current, ctx, 0.8)
        score_diff = score_candidate(diff_artist, current, ctx, 0.8)

        # Different artist should score higher even with same base score
        assert score_diff > score_same
