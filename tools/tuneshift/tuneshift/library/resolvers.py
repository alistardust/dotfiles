"""Library-first platform resolver (spec §4.1a, AC-D7, AC-X3).

The :class:`ResolutionWorker` is deliberately I/O-free: it delegates the actual
candidate lookup to an injected ``resolver`` callable. This module provides the
production resolver — a thin, DRY bridge over the same multi-strategy platform
search that ``reconcile`` uses (:func:`tuneshift.reconcile.gather_candidates`),
converting each :class:`~tuneshift.models.TrackResult` into the worker's
:class:`~tuneshift.library.worker.ResolvedCandidate` contract.

Sharing the discovery pass with reconcile is what lets resolution *persist* the
exact candidate set selection will later score over (AC-X3 / AC-P4), instead of
maintaining a second, drift-prone search path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tuneshift.library.worker import ResolutionRateLimited, ResolvedCandidate
from tuneshift.matching.track import score_match_with_version
from tuneshift.reconcile import build_alias_resolver, gather_candidates

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tuneshift.db import Database
    from tuneshift.models import Track, TrackResult

# Platform errors that mean "temporarily throttled" — surfaced to the worker as
# a transient rate-limit so the track is re-queued with backoff, never lost or
# quarantined (AC-X2).
_RATE_LIMIT_MARKERS = ("rate limit", "429", "too many requests")


def _capture_metadata(candidate: TrackResult) -> dict[str, object]:
    """Snapshot every version-selection-relevant field off a search result.

    Persisted as ``track_candidates.captured_metadata`` so a later scoring pass
    (FL1b) can reconstruct the candidate without another live search.
    """
    return {
        "title": candidate.title,
        "artist": candidate.artist,
        "album": candidate.album,
        "duration_seconds": candidate.duration_seconds,
        "isrc": candidate.isrc,
        "available": candidate.available,
        "tier_restricted": candidate.tier_restricted,
        "audio_modes": candidate.audio_modes,
        "audio_quality": candidate.audio_quality,
        "tidal_version": candidate.tidal_version,
        "media_metadata_tags": candidate.media_metadata_tags,
        "album_artist": candidate.album_artist,
        "album_type": candidate.album_type,
        "recording_date": candidate.recording_date,
        "release_date": candidate.release_date,
        "remaster_year": candidate.remaster_year,
        "language": candidate.language,
        "composer": candidate.composer,
        "mb_work_id": candidate.mb_work_id,
    }


class PlatformResolver:
    """Resolve a library track to hydrated platform candidates.

    Reuses reconcile's multi-strategy search. Candidates are returned best-match
    first (by the source-aware version score with no preference bias) so the
    worker can hydrate the track from the strongest identity match; the full
    per-playlist version selection remains reconcile/selection's job.
    """

    def __init__(self, db: Database, client: object, *, max_candidates: int = 10) -> None:
        self._db = db
        self._client = client
        self._max_candidates = max_candidates
        # Built once per resolver so aliased artists are retrieved + scored under
        # every equivalent surface form (mirrors reconcile).
        self._alias_resolver = build_alias_resolver(db)

    @property
    def platform_name(self) -> str:
        return self._client.platform_name

    def __call__(self, track: Track) -> Sequence[ResolvedCandidate]:
        try:
            candidates, _strategies = gather_candidates(
                track, self._client, self._alias_resolver,
            )
        except Exception as exc:  # noqa: BLE001 - classify throttling vs hard error
            if _is_rate_limit(exc):
                raise ResolutionRateLimited(str(exc)) from exc
            raise

        if not candidates:
            return []

        all_durations = [c.duration_seconds for c in candidates if c.duration_seconds]

        def _score(candidate: TrackResult) -> int:
            return score_match_with_version(
                track.title, track.artist, track.album,
                candidate.title, candidate.artist, candidate.album,
                result_duration=candidate.duration_seconds,
                reference_duration=track.duration_seconds,
                all_durations=all_durations,
                alias_resolver=self._alias_resolver,
            )

        ranked = sorted(candidates, key=_score, reverse=True)[: self._max_candidates]
        platform = self._client.platform_name
        resolved: list[ResolvedCandidate] = []
        for candidate in ranked:
            metadata = _capture_metadata(candidate)
            # Attach the source-aware match score (0-100) so the worker can
            # derive a confidence tier for the hydrated track without recomputing.
            metadata["match_score"] = _score(candidate)
            resolved.append(
                ResolvedCandidate(
                    platform=platform,
                    platform_track_id=candidate.platform_id,
                    metadata=metadata,
                )
            )
        return resolved


def _is_rate_limit(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _RATE_LIMIT_MARKERS)
