"""Tests for confidence scoring algorithm."""

import pytest

from tidal_importer.identity.confidence import compute_confidence
from tidal_importer.identity.models import ConfidenceTier, Evidence


def _ev(source: str, evidence_type: str, confidence: float) -> Evidence:
    return Evidence(id=f"ev-{source}-{confidence}", recording_id="r1",
                    source=source, evidence_type=evidence_type, confidence=confidence)


class TestComputeConfidence:
    def test_single_isrc(self):
        score, tier = compute_confidence([_ev("musicbrainz", "isrc_match", 0.97)])
        assert score == 0.97
        assert tier == ConfidenceTier.VERIFIED

    def test_text_search_with_discogs(self):
        evidence = [
            _ev("musicbrainz", "text_search", 0.85),
            _ev("discogs", "compilation_flag", 0.85),
        ]
        score, tier = compute_confidence(evidence)
        assert score == 0.90
        assert tier == ConfidenceTier.CONFIRMED

    def test_discogs_capped_at_099(self):
        evidence = [
            _ev("musicbrainz", "isrc_match", 0.97),
            _ev("discogs", "compilation_flag", 0.97),
        ]
        score, tier = compute_confidence(evidence)
        assert score == 0.99

    def test_non_isrc_capped_at_094(self):
        evidence = [
            _ev("musicbrainz", "text_search", 0.85),
            _ev("discogs", "compilation_flag", 0.85),
            _ev("itunes", "text_search", 0.70),
            _ev("lastfm", "text_search", 0.70),
        ]
        score, tier = compute_confidence(evidence)
        assert score == 0.94
        assert tier == ConfidenceTier.CONFIRMED

    def test_contradiction(self):
        evidence = [
            _ev("musicbrainz", "text_search", 0.85),
            _ev("discogs", "contradiction", 0.75),
        ]
        score, tier = compute_confidence(evidence)
        assert score == 0.75
        assert tier == ConfidenceTier.PROBABLE

    def test_empty(self):
        score, tier = compute_confidence([])
        assert score == 0.0
        assert tier == ConfidenceTier.UNCERTAIN

    def test_discogs_standalone(self):
        score, tier = compute_confidence([_ev("discogs", "text_search", 0.70)])
        assert score == 0.70
        assert tier == ConfidenceTier.PROBABLE

    def test_tidal_browse(self):
        score, tier = compute_confidence([_ev("tidal_discography", "discography_browse", 0.65)])
        assert score == 0.65
        assert tier == ConfidenceTier.PROBABLE

    def test_isrc_not_capped_at_094(self):
        evidence = [
            _ev("musicbrainz", "isrc_match", 0.97),
            _ev("discogs", "compilation_flag", 0.85),
        ]
        score, tier = compute_confidence(evidence)
        assert score == 0.99
        assert tier == ConfidenceTier.VERIFIED
