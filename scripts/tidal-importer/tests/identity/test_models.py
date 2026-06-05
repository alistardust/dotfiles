"""Tests for identity resolution data models."""

import pytest

from tidal_importer.identity.models import (
    Album,
    Artist,
    ConfidenceTier,
    Evidence,
    Recording,
    RecordingCandidate,
    Release,
    ResolvedTrack,
    SourceResult,
)


class TestConfidenceTier:
    def test_from_score_verified(self):
        assert ConfidenceTier.from_score(0.97) == ConfidenceTier.VERIFIED

    def test_from_score_confirmed(self):
        assert ConfidenceTier.from_score(0.85) == ConfidenceTier.CONFIRMED

    def test_from_score_probable(self):
        assert ConfidenceTier.from_score(0.65) == ConfidenceTier.PROBABLE

    def test_from_score_uncertain(self):
        assert ConfidenceTier.from_score(0.40) == ConfidenceTier.UNCERTAIN

    def test_from_score_boundary_verified(self):
        assert ConfidenceTier.from_score(0.95) == ConfidenceTier.VERIFIED

    def test_from_score_boundary_confirmed(self):
        assert ConfidenceTier.from_score(0.80) == ConfidenceTier.CONFIRMED

    def test_from_score_boundary_probable(self):
        assert ConfidenceTier.from_score(0.60) == ConfidenceTier.PROBABLE

    def test_from_score_zero(self):
        assert ConfidenceTier.from_score(0.0) == ConfidenceTier.UNCERTAIN


class TestAlbum:
    def test_is_compilation_true(self):
        album = Album(id="1", title="Gold", primary_type="Album", secondary_types=["Compilation"])
        assert album.is_compilation is True

    def test_is_compilation_false(self):
        album = Album(id="2", title="Arrival", primary_type="Album", secondary_types=[])
        assert album.is_compilation is False

    def test_is_live(self):
        album = Album(id="3", title="Live", primary_type="Album", secondary_types=["Live"])
        assert album.is_live is True


class TestRelease:
    def test_is_original(self):
        release = Release(id="1", album_id="a1", title="Arrival", release_year=1976)
        assert release.is_original is True

    def test_remaster_not_original(self):
        release = Release(id="2", album_id="a1", title="Arrival (Remastered)", is_remaster=True)
        assert release.is_original is False


class TestEvidence:
    def test_defaults(self):
        ev = Evidence(id="1", recording_id="r1", source="musicbrainz",
                      evidence_type="isrc_match", confidence=0.97)
        assert ev.is_current is True
        assert ev.superseded_by is None


class TestSourceResult:
    def test_empty(self):
        result = SourceResult(recordings=[])
        assert result.evidence is None

    def test_with_candidate(self):
        cand = RecordingCandidate(title="DQ", artist="ABBA", score=0.97)
        result = SourceResult(recordings=[cand])
        assert result.recordings[0].score == 0.97
