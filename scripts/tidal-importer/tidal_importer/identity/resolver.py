"""Track identity resolver: the core resolution pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from tidal_importer.identity.confidence import compute_confidence
from tidal_importer.identity.db import IdentityDB
from tidal_importer.identity.models import (
    ConfidenceTier,
    Evidence,
    RecordingCandidate,
    ResolutionResult,
    SourceResult,
    TrackInput,
)
from tidal_importer.identity.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CACHE_FRESHNESS_DAYS = 90
CONFIRMED_THRESHOLD = 0.80
VERIFIED_THRESHOLD = 0.95


@dataclass
class ResolverConfig:
    """Configuration for the resolver pipeline."""
    upgrade_mode: bool = False
    max_candidates: int = 10


class TrackResolver:
    """5-step pipeline for resolving track identity."""

    def __init__(
        self,
        db: IdentityDB,
        musicbrainz=None,
        discogs=None,
        tidal=None,
        config: ResolverConfig | None = None,
        rate_limiters: dict[str, RateLimiter] | None = None,
    ) -> None:
        self._db = db
        self._mb = musicbrainz
        self._discogs = discogs
        self._tidal = tidal
        self._config = config or ResolverConfig()
        self._rate_limiters = rate_limiters or {}

    def resolve(self, track: TrackInput) -> ResolutionResult | None:
        """Resolve a single track through the 5-step pipeline.

        Steps:
        1. Cache check (exit if CONFIRMED+ with fresh evidence)
        2. ISRC lookup via MusicBrainz
        3. Text search via MusicBrainz
        4. Discogs search
        5. Tidal discography browse
        """
        # Step 1: Cache check
        cached = self._check_cache(track)
        if cached is not None:
            return cached

        # Collect evidence through pipeline steps
        all_evidence: list[Evidence] = []
        best_candidates: list[RecordingCandidate] = []

        # Step 2: ISRC lookup
        if track.isrc and self._mb:
            self._wait_for_rate_limit("musicbrainz")
            result = self._mb.lookup_isrc(track.isrc, duration_ms=track.duration_ms)
            if result:
                best_candidates.extend(result.recordings)
                if result.evidence:
                    all_evidence.append(result.evidence)
                # Check if we can exit early
                score, _ = compute_confidence(all_evidence)
                threshold = VERIFIED_THRESHOLD if self._config.upgrade_mode else CONFIRMED_THRESHOLD
                if score >= threshold and len(result.recordings) == 1:
                    return self._finalize(track, result.recordings[0], all_evidence)

        # Step 3: MB text search
        if self._mb:
            self._wait_for_rate_limit("musicbrainz")
            result = self._mb.search(track.artist, track.title, duration_ms=track.duration_ms)
            if result.recordings:
                best_candidates.extend(result.recordings)
                if result.evidence:
                    all_evidence.append(result.evidence)
                score, _ = compute_confidence(all_evidence)
                threshold = VERIFIED_THRESHOLD if self._config.upgrade_mode else CONFIRMED_THRESHOLD
                if score >= threshold:
                    top = sorted(result.recordings, key=lambda c: c.score, reverse=True)[0]
                    return self._finalize(track, top, all_evidence)

        # Step 4: Discogs
        if self._discogs:
            self._wait_for_rate_limit("discogs")
            result = self._discogs.search(track.artist, track.title)
            if result.recordings:
                best_candidates.extend(result.recordings)
                if result.evidence:
                    all_evidence.append(result.evidence)
                score, _ = compute_confidence(all_evidence)
                threshold = VERIFIED_THRESHOLD if self._config.upgrade_mode else CONFIRMED_THRESHOLD
                if score >= threshold:
                    top = sorted(best_candidates, key=lambda c: c.score, reverse=True)[0]
                    return self._finalize(track, top, all_evidence)

        # Step 5: Tidal discography browse
        if self._tidal and track.platform_artist_id:
            self._wait_for_rate_limit("tidal")
            result = self._tidal.search(
                track.artist, track.title, artist_id=int(track.platform_artist_id)
            )
            if result.recordings:
                best_candidates.extend(result.recordings)
                if result.evidence:
                    all_evidence.append(result.evidence)

        # Final evaluation
        if all_evidence:
            score, _ = compute_confidence(all_evidence)
            threshold = VERIFIED_THRESHOLD if self._config.upgrade_mode else CONFIRMED_THRESHOLD
            if score >= threshold and best_candidates:
                top = sorted(best_candidates, key=lambda c: c.score, reverse=True)[0]
                return self._finalize(track, top, all_evidence)

        # No match: store candidates for future resolution
        if best_candidates:
            self._store_unresolved(track, best_candidates, all_evidence)

        return None

    def resolve_playlist(self, tracks: list[TrackInput]) -> list[ResolutionResult | None]:
        """Resolve all tracks in a playlist. Stub for batch processing."""
        raise NotImplementedError(
            "resolve_playlist is planned for a future release. "
            "Use resolve() in a loop for now."
        )

    def _check_cache(self, track: TrackInput) -> ResolutionResult | None:
        """Check if we have a fresh, confident resolution cached."""
        cached = self._db.get_resolved_track(track.platform, track.platform_id)
        if cached is None:
            return None

        # Check freshness
        if cached.resolved_at:
            age = datetime.now(timezone.utc) - cached.resolved_at
            if age > timedelta(days=CACHE_FRESHNESS_DAYS):
                return None

        # Check confidence threshold
        threshold = VERIFIED_THRESHOLD if self._config.upgrade_mode else CONFIRMED_THRESHOLD
        if cached.confidence >= threshold:
            return cached

        return None

    def _finalize(
        self,
        track: TrackInput,
        candidate: RecordingCandidate,
        evidence: list[Evidence],
    ) -> ResolutionResult:
        """Create and store a resolved track."""
        score, tier = compute_confidence(evidence)

        resolved = ResolutionResult(
            platform=track.platform,
            platform_id=track.platform_id,
            title=candidate.title,
            artist=candidate.artist,
            mb_recording_id=candidate.mb_recording_id,
            confidence=score,
            tier=tier,
            evidence=evidence,
            resolved_at=datetime.now(timezone.utc),
        )

        self._db.store_resolved_track(resolved)
        return resolved

    def _store_unresolved(
        self,
        track: TrackInput,
        candidates: list[RecordingCandidate],
        evidence: list[Evidence],
    ) -> None:
        """Store unresolved candidates for future processing."""
        self._db.store_candidates(
            platform=track.platform,
            platform_id=track.platform_id,
            candidates=candidates[:self._config.max_candidates],
        )

    def _wait_for_rate_limit(self, source: str) -> None:
        """Wait if rate-limited for a source."""
        limiter = self._rate_limiters.get(source)
        if limiter and not limiter.acquire():
            wait_time = limiter.wait_time()
            if wait_time > 0:
                time.sleep(wait_time)
