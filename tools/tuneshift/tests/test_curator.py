import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.curator import curate_trim, curate_analyze, CurationResult


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A", "duration_ms": 200000}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestCurateTrim:
    def test_trims_to_target_track_count(self) -> None:
        tracks = [_track(i, energy=0.5, themes=["rock"]) for i in range(20)]
        ctx = PlaylistContext(goal="Rock playlist", narrative_sections=[], mood_profile=None, all_tracks=tracks)
        constraints = {"track_count": {"target": 10, "tolerance": 2, "hard_limit": 12}}
        result = curate_trim(tracks, ctx, constraints)
        assert len(result.keep) <= 12
        assert len(result.keep) >= 8

    def test_respects_hard_limit(self) -> None:
        tracks = [_track(i, duration_ms=300000) for i in range(30)]  # 5 min each
        ctx = PlaylistContext(goal="Short playlist", narrative_sections=[], mood_profile=None, all_tracks=tracks)
        constraints = {"duration": {"target_minutes": 60, "tolerance_minutes": 5, "hard_limit_minutes": 65}}
        result = curate_trim(tracks, ctx, constraints)
        total_ms = sum(t.duration_ms or 0 for t in result.keep)
        assert total_ms <= 65 * 60 * 1000


class TestCurateAnalyze:
    def test_returns_coverage_report(self) -> None:
        tracks = [_track(i, themes=["trans", "fury"], emotional_intensity=0.8) for i in range(10)]
        ctx = PlaylistContext(goal="Trans fury", narrative_sections=[], mood_profile=None, all_tracks=tracks)
        report = curate_analyze(tracks, ctx)
        assert "scores" in report
        assert len(report["scores"]) == 10
