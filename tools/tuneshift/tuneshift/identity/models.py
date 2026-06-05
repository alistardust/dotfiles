"""Data models for track identity resolution."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ConfidenceTier(enum.Enum):
    """Resolution confidence tiers."""

    VERIFIED = "VERIFIED"
    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    UNCERTAIN = "UNCERTAIN"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceTier:
        if score >= 0.95:
            return cls.VERIFIED
        if score >= 0.80:
            return cls.CONFIRMED
        if score >= 0.60:
            return cls.PROBABLE
        return cls.UNCERTAIN


class ResolutionStatus(enum.Enum):
    """Status of a resolution attempt."""

    RESOLVED = "RESOLVED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    UPGRADED = "UPGRADED"
    UNCHANGED = "UNCHANGED"


@dataclass
class Evidence:
    """A single piece of evidence from a resolution source."""

    source: str
    evidence_type: str
    confidence: float
    raw_data: str | None = None


@dataclass
class RecordingCandidate:
    """A candidate recording from a source search."""

    title: str
    artist: str
    mb_recording_id: str | None = None
    duration_ms: int | None = None
    score: float = 0.0
    release_groups: list[dict] = field(default_factory=list)


@dataclass
class SourceResult:
    """Result from a single source query."""

    recordings: list[RecordingCandidate]
    evidence: Evidence | None = None
    rate_limit_remaining: int | None = None


@dataclass
class TrackInput:
    """Input to the resolver pipeline (constructed from a TuneShift Track)."""

    title: str
    artist: str
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None


@dataclass
class ResolutionResult:
    """Result of resolving a single track."""

    track_id: int
    status: ResolutionStatus
    mb_recording_id: str | None = None
    mb_release_group_id: str | None = None
    confidence_score: float | None = None
    confidence_tier: ConfidenceTier | None = None
    evidence: list[Evidence] = field(default_factory=list)
    error: str | None = None
