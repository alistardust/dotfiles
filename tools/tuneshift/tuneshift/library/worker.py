"""Resumable resolution/enrichment worker (spec §4.1a, §4.3; AC-D7, AC-X2).

Library-first add lands tracks immediately and defers the (rate-limited,
network-bound) work of resolving a track to platform candidates. This worker is
the resumable engine that drains that backlog. It is deliberately I/O-free: the
actual candidate lookup is an injected ``resolver`` callable, so the *same* code
path serves the background drain and a foreground ``resolve`` command, and unit
tests never touch the network.

Failure handling (AC-X2 "rate-limited work is never lost"):

* ``ResolutionRateLimited`` -> the track stays ``pending`` with exponential
  backoff and an incremented attempt count. Rate limits are transient and never
  cause quarantine.
* any other exception -> retried with backoff up to ``max_attempts``, after
  which the track is quarantined with a machine-readable reason.
* resolver returns no candidates -> the track is quarantined immediately
  (nothing to resolve to).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from tuneshift.db import Database
from tuneshift.models import Track

logger = logging.getLogger(__name__)

# SQLite's datetime('now') format; next_attempt_at must be string-comparable
# with it (see Database.next_pending_resolution).
_SQLITE_TS_FMT = "%Y-%m-%d %H:%M:%S"


class ResolutionRateLimited(Exception):
    """Raised by a resolver when an upstream platform rate-limits the request.

    Distinct from a hard failure: the work is re-queued with backoff and is
    never counted toward the quarantine attempt ceiling.
    """


@dataclass(frozen=True)
class ResolvedCandidate:
    """A hydrated platform candidate produced by a resolver."""

    platform: str
    platform_track_id: str
    metadata: dict[str, Any] | None = field(default=None)


# A resolver takes a library Track and returns the platform candidates it found.
Resolver = Callable[[Track], Sequence[ResolvedCandidate]]


class ResolutionWorker:
    """Drains the resolution queue by resolving tracks to platform candidates."""

    def __init__(
        self,
        db: Database,
        resolver: Resolver,
        *,
        enricher: Callable[[Database, Track], None] | None = None,
        rate_limiter: Any | None = None,
        max_attempts: int = 5,
        base_backoff_seconds: float = 60.0,
    ) -> None:
        self._db = db
        self._resolver = resolver
        self._enricher = enricher
        self._rate_limiter = rate_limiter
        self._max_attempts = max_attempts
        self._base_backoff_seconds = base_backoff_seconds

    def enqueue(self, track_id: int) -> None:
        """Queue a track for resolution. Idempotent per track."""
        self._db.enqueue_resolution(track_id)

    def drain(self, limit: int | None = None) -> int:
        """Resolve due tracks until the queue is drained or ``limit`` is hit.

        Returns the number of tracks *successfully* resolved. Backed-off tracks
        (rate-limited or awaiting retry) are skipped this pass and remain queued,
        which is what makes a subsequent drain resumable.
        """
        resolved = 0
        processed = 0
        while limit is None or processed < limit:
            track_id = self._db.next_pending_resolution()
            if track_id is None:
                break
            processed += 1
            if self._resolve_one(track_id):
                resolved += 1
        return resolved

    def _resolve_one(self, track_id: int) -> bool:
        """Resolve a single track. Returns True only on success."""
        track = self._db.get_track(track_id)
        if track is None:
            # Track vanished (deleted) after enqueue; drop it from the queue.
            self._db.set_resolution_state(
                track_id, "quarantined", last_error="track_missing"
            )
            return False

        if self._rate_limiter is not None:
            self._rate_limiter.wait()

        try:
            candidates = list(self._resolver(track))
        except ResolutionRateLimited as exc:
            # Transient: re-queue with backoff, never quarantine.
            self._db.set_resolution_state(
                track_id,
                "pending",
                last_error=str(exc),
                next_attempt_at=self._backoff_at(track_id),
                increment_attempts=True,
            )
            logger.info("resolution rate-limited, backing off: track=%s", track_id)
            return False
        except Exception as exc:  # noqa: BLE001 - failure is classified below
            return self._handle_failure(track_id, exc)

        if not candidates:
            self._quarantine(track_id, "no_candidate: no platform match found")
            return False

        for cand in candidates:
            self._db.upsert_track_candidate(
                track_id, cand.platform, cand.platform_track_id, cand.metadata
            )
        self._db.set_resolution_state(track_id, "resolved", last_error=None)
        # Clear any prior quarantine now that the track resolved.
        if track.quarantine_state:
            self._db.set_track_fields(
                track_id,
                {"quarantine_state": None, "quarantine_reason": None},
                source="resolver",
            )
        # Async enrichment (AC-D7): classification + artist genres happen here,
        # out of the interactive add path. Failures are non-fatal.
        if self._enricher is not None:
            try:
                self._enricher(self._db, track)
            except Exception:  # noqa: BLE001 - enrichment is best-effort
                logger.warning(
                    "enrichment failed after resolve: track=%s", track_id,
                    exc_info=True,
                )
        return True

    def _handle_failure(self, track_id: int, exc: Exception) -> bool:
        """Retry a hard failure with backoff; quarantine once retries exhaust."""
        row = self._db.conn.execute(
            "SELECT attempts FROM resolution_queue WHERE track_id = ?", (track_id,)
        ).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        if attempts >= self._max_attempts:
            self._quarantine(
                track_id,
                f"max_attempts_exceeded: {type(exc).__name__}: {exc}",
                increment_attempts=True,
            )
            return False
        self._db.set_resolution_state(
            track_id,
            "pending",
            last_error=f"{type(exc).__name__}: {exc}",
            next_attempt_at=self._backoff_at(track_id, attempts=attempts),
            increment_attempts=True,
        )
        logger.warning(
            "resolution failed (attempt %s/%s): track=%s error=%s",
            attempts,
            self._max_attempts,
            track_id,
            exc,
        )
        return False

    def _quarantine(
        self, track_id: int, reason: str, *, increment_attempts: bool = False
    ) -> None:
        self._db.set_resolution_state(
            track_id,
            "quarantined",
            last_error=reason,
            increment_attempts=increment_attempts,
        )
        self._db.set_track_fields(
            track_id,
            {"quarantine_state": "unresolved", "quarantine_reason": reason},
            source="resolver",
        )
        logger.warning("track quarantined: track=%s reason=%s", track_id, reason)

    def _backoff_at(self, track_id: int, attempts: int | None = None) -> str:
        """Compute an exponential-backoff timestamp string (SQLite format)."""
        if attempts is None:
            row = self._db.conn.execute(
                "SELECT attempts FROM resolution_queue WHERE track_id = ?",
                (track_id,),
            ).fetchone()
            attempts = (row["attempts"] if row else 0) + 1
        delay = self._base_backoff_seconds * (2 ** max(0, attempts - 1))
        return (datetime.now(timezone.utc) + timedelta(seconds=delay)).strftime(
            _SQLITE_TS_FMT
        )
