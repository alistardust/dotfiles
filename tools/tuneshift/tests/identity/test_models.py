"""Tests for identity resolution models."""

from tuneshift.identity.models import (
    ConfidenceTier,
    Evidence,
    ResolutionResult,
    ResolutionStatus,
    TrackInput,
)


class TestConfidenceTier:
    def test_verified_threshold(self):
        assert ConfidenceTier.from_score(0.95) == ConfidenceTier.VERIFIED
        assert ConfidenceTier.from_score(1.0) == ConfidenceTier.VERIFIED

    def test_confirmed_threshold(self):
        assert ConfidenceTier.from_score(0.80) == ConfidenceTier.CONFIRMED
        assert ConfidenceTier.from_score(0.94) == ConfidenceTier.CONFIRMED

    def test_probable_threshold(self):
        assert ConfidenceTier.from_score(0.60) == ConfidenceTier.PROBABLE
        assert ConfidenceTier.from_score(0.79) == ConfidenceTier.PROBABLE

    def test_uncertain_threshold(self):
        assert ConfidenceTier.from_score(0.59) == ConfidenceTier.UNCERTAIN
        assert ConfidenceTier.from_score(0.0) == ConfidenceTier.UNCERTAIN


class TestTrackInput:
    def test_minimal_construction(self):
        t = TrackInput(title="Heroes", artist="David Bowie")
        assert t.title == "Heroes"
        assert t.artist == "David Bowie"
        assert t.album is None
        assert t.isrc is None
        assert t.duration_ms is None

    def test_full_construction(self):
        t = TrackInput(
            title="Heroes",
            artist="David Bowie",
            album="Heroes",
            isrc="GBUM71029604",
            duration_ms=372000,
        )
        assert t.duration_ms == 372000
        assert t.isrc == "GBUM71029604"


class TestResolutionResult:
    def test_resolved_status(self):
        r = ResolutionResult(
            track_id=1,
            status=ResolutionStatus.RESOLVED,
            mb_recording_id="abc-123",
            confidence_score=0.92,
            confidence_tier=ConfidenceTier.CONFIRMED,
        )
        assert r.status == ResolutionStatus.RESOLVED
        assert r.error is None

    def test_failed_status_has_error(self):
        r = ResolutionResult(
            track_id=1,
            status=ResolutionStatus.FAILED,
            error="All sources exhausted",
        )
        assert r.status == ResolutionStatus.FAILED
        assert r.error == "All sources exhausted"
        assert r.mb_recording_id is None


class TestEvidence:
    def test_construction(self):
        e = Evidence(
            source="musicbrainz",
            evidence_type="isrc_lookup",
            confidence=0.90,
        )
        assert e.source == "musicbrainz"
        assert e.raw_data is None
