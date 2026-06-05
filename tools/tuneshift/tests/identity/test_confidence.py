"""Tests for confidence scoring."""

from tuneshift.identity.confidence import compute_confidence
from tuneshift.identity.models import ConfidenceTier, Evidence


class TestComputeConfidence:
    def test_empty_evidence(self):
        score, tier = compute_confidence([])
        assert score == 0.0
        assert tier == ConfidenceTier.UNCERTAIN

    def test_single_high_confidence(self):
        evidence = [Evidence(source="musicbrainz", evidence_type="isrc_lookup", confidence=0.95)]
        score, tier = compute_confidence(evidence)
        assert score >= 0.95
        assert tier == ConfidenceTier.VERIFIED

    def test_multiple_sources_combine(self):
        evidence = [
            Evidence(source="musicbrainz", evidence_type="text_search", confidence=0.75),
            Evidence(source="discogs", evidence_type="release_confirmation", confidence=0.05),
        ]
        score, tier = compute_confidence(evidence)
        assert score == 0.80
        assert tier == ConfidenceTier.CONFIRMED

    def test_single_low_confidence(self):
        evidence = [Evidence(source="musicbrainz", evidence_type="text_search", confidence=0.55)]
        score, tier = compute_confidence(evidence)
        assert score == 0.55
        assert tier == ConfidenceTier.UNCERTAIN

    def test_confidence_capped_at_one(self):
        evidence = [
            Evidence(source="musicbrainz", evidence_type="isrc_lookup", confidence=0.95),
            Evidence(source="discogs", evidence_type="release_confirmation", confidence=0.10),
        ]
        score, tier = compute_confidence(evidence)
        assert score <= 1.0
        assert tier == ConfidenceTier.VERIFIED
