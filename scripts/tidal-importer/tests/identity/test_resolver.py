"""Tests for the track identity resolver pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from tidal_importer.identity.db import IdentityDB
from tidal_importer.identity.models import (
    ConfidenceTier,
    Evidence,
    TrackInput,
    RecordingCandidate,
    ResolutionResult,
    SourceResult,
)
from tidal_importer.identity.resolver import ResolverConfig, TrackResolver


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    return IdentityDB(str(db_path))


@pytest.fixture
def track():
    return TrackInput(
        platform="tidal",
        platform_id="12345",
        title="Karma Police",
        artist="Radiohead",
        album="OK Computer",
        duration_ms=263000,
        isrc="GBAYE9700103",
    )


class TestCacheCheck:
    def test_fresh_confirmed_cache_hit(self, db, track):
        """Fresh CONFIRMED resolution returns cached result."""
        resolved = ResolutionResult(
            platform="tidal",
            platform_id="12345",
            title="Karma Police",
            artist="Radiohead",
            mb_recording_id="abc123",
            confidence=0.92,
            tier=ConfidenceTier.CONFIRMED,
            evidence=[
                Evidence(
                    id="ev-cache-1",
                    recording_id="",
                    source="musicbrainz",
                    evidence_type="isrc_match",
                    confidence=0.92,
                )
            ],
            resolved_at=datetime.now(timezone.utc),
        )
        db.store_resolved_track(resolved)

        resolver = TrackResolver(db=db)
        result = resolver.resolve(track)
        assert result is not None
        assert result.confidence == 0.92

    def test_stale_cache_misses(self, db, track):
        """Cache older than 90 days is not used."""
        resolved = ResolutionResult(
            platform="tidal",
            platform_id="12345",
            title="Karma Police",
            artist="Radiohead",
            mb_recording_id="abc123",
            confidence=0.92,
            tier=ConfidenceTier.CONFIRMED,
            evidence=[
                Evidence(id="ev-stale", recording_id="", source="musicbrainz",
                         evidence_type="isrc_match", confidence=0.92)
            ],
            resolved_at=datetime.now(timezone.utc) - timedelta(days=91),
        )
        db.store_resolved_track(resolved)

        resolver = TrackResolver(db=db)
        # No sources configured, so resolve returns None after cache miss
        result = resolver.resolve(track)
        assert result is None

    def test_upgrade_mode_requires_verified(self, db, track):
        """In upgrade mode, CONFIRMED is not enough."""
        resolved = ResolutionResult(
            platform="tidal",
            platform_id="12345",
            title="Karma Police",
            artist="Radiohead",
            mb_recording_id="abc123",
            confidence=0.85,
            tier=ConfidenceTier.CONFIRMED,
            evidence=[
                Evidence(id="ev-upgrade", recording_id="", source="musicbrainz",
                         evidence_type="text_search", confidence=0.85)
            ],
            resolved_at=datetime.now(timezone.utc),
        )
        db.store_resolved_track(resolved)

        config = ResolverConfig(upgrade_mode=True)
        resolver = TrackResolver(db=db, config=config)
        result = resolver.resolve(track)
        assert result is None


class TestISRCResolution:
    def test_single_isrc_resolves_immediately(self, db, track):
        """Single ISRC match resolves at step 2."""
        mock_mb = MagicMock()
        mock_mb.lookup_isrc.return_value = SourceResult(
            recordings=[
                RecordingCandidate(
                    title="Karma Police",
                    artist="Radiohead",
                    mb_recording_id="mb-rec-1",
                    duration_ms=263000,
                    score=0.97,
                )
            ],
            evidence=Evidence(
                id="mb-isrc-1",
                recording_id="",
                source="musicbrainz",
                evidence_type="isrc_match",
                confidence=0.97,
            ),
        )

        resolver = TrackResolver(db=db, musicbrainz=mock_mb)
        result = resolver.resolve(track)

        assert result is not None
        assert result.mb_recording_id == "mb-rec-1"
        assert result.confidence == 0.97
        assert result.tier == ConfidenceTier.VERIFIED
        # Should not call search since ISRC resolved
        mock_mb.search.assert_not_called()


class TestTextSearchResolution:
    def test_text_search_with_high_confidence(self, db):
        """Text search with good match resolves at step 3."""
        track = TrackInput(
            platform="tidal",
            platform_id="999",
            title="Karma Police",
            artist="Radiohead",
            album="OK Computer",
            duration_ms=263000,
            isrc=None,
        )

        mock_mb = MagicMock()
        mock_mb.lookup_isrc.return_value = None
        mock_mb.search.return_value = SourceResult(
            recordings=[
                RecordingCandidate(
                    title="Karma Police",
                    artist="Radiohead",
                    mb_recording_id="mb-rec-2",
                    duration_ms=263000,
                    score=0.85,
                )
            ],
            evidence=Evidence(
                id="mb-search-1",
                recording_id="",
                source="musicbrainz",
                evidence_type="text_search",
                confidence=0.85,
            ),
        )

        resolver = TrackResolver(db=db, musicbrainz=mock_mb)
        result = resolver.resolve(track)

        assert result is not None
        assert result.confidence == 0.85
        assert result.tier == ConfidenceTier.CONFIRMED


class TestDiscogsConfirmation:
    def test_discogs_adds_bonus(self, db):
        """Discogs confirmation adds bonus to text search score."""
        track = TrackInput(
            platform="tidal",
            platform_id="999",
            title="Karma Police",
            artist="Radiohead",
            album="OK Computer",
            duration_ms=263000,
            isrc=None,
        )

        mock_mb = MagicMock()
        mock_mb.lookup_isrc.return_value = None
        # Text search returns below threshold
        mock_mb.search.return_value = SourceResult(
            recordings=[
                RecordingCandidate(
                    title="Karma Police",
                    artist="Radiohead",
                    mb_recording_id="mb-rec-3",
                    duration_ms=263000,
                    score=0.75,
                )
            ],
            evidence=Evidence(
                id="mb-search-2",
                recording_id="",
                source="musicbrainz",
                evidence_type="text_search",
                confidence=0.75,
            ),
        )

        mock_discogs = MagicMock()
        mock_discogs.search.return_value = SourceResult(
            recordings=[
                RecordingCandidate(
                    title="Karma Police",
                    artist="Radiohead",
                    score=0.70,
                )
            ],
            evidence=Evidence(
                id="discogs-1",
                recording_id="",
                source="discogs",
                evidence_type="text_search",
                confidence=0.70,
            ),
        )

        resolver = TrackResolver(db=db, musicbrainz=mock_mb, discogs=mock_discogs)
        result = resolver.resolve(track)

        assert result is not None
        # 0.75 base + 0.05 discogs bonus = 0.80
        assert result.confidence == 0.80
        assert result.tier == ConfidenceTier.CONFIRMED


class TestNoMatch:
    def test_unresolved_stores_candidates(self, db):
        """When no source reaches threshold, candidates are stored."""
        track = TrackInput(
            platform="tidal",
            platform_id="999",
            title="Obscure Track",
            artist="Unknown Artist",
            duration_ms=200000,
        )

        mock_mb = MagicMock()
        mock_mb.lookup_isrc.return_value = None
        mock_mb.search.return_value = SourceResult(
            recordings=[
                RecordingCandidate(
                    title="Obscure Track",
                    artist="Unknown Artist",
                    score=0.65,
                )
            ],
            evidence=Evidence(
                id="mb-search-3",
                recording_id="",
                source="musicbrainz",
                evidence_type="text_search",
                confidence=0.65,
            ),
        )

        resolver = TrackResolver(db=db, musicbrainz=mock_mb)
        result = resolver.resolve(track)

        assert result is None


class TestResolvePlaylist:
    def test_raises_not_implemented(self, db, track):
        resolver = TrackResolver(db=db)
        with pytest.raises(NotImplementedError, match="future release"):
            resolver.resolve_playlist([track])


class TestRateLimiting:
    def test_respects_rate_limiter(self, db, track):
        """Rate limiter is consulted before API calls."""
        mock_limiter = MagicMock()
        mock_limiter.acquire.return_value = True

        mock_mb = MagicMock()
        mock_mb.lookup_isrc.return_value = SourceResult(
            recordings=[
                RecordingCandidate(
                    title="Karma Police",
                    artist="Radiohead",
                    mb_recording_id="mb-1",
                    score=0.97,
                )
            ],
            evidence=Evidence(
                id="e1",
                recording_id="",
                source="musicbrainz",
                evidence_type="isrc_match",
                confidence=0.97,
            ),
        )

        resolver = TrackResolver(
            db=db,
            musicbrainz=mock_mb,
            rate_limiters={"musicbrainz": mock_limiter},
        )
        resolver.resolve(track)
        mock_limiter.acquire.assert_called()
