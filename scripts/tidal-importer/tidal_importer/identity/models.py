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


@dataclass
class Artist:
    id: str
    name: str
    mb_artist_id: str | None = None
    discogs_artist_id: int | None = None
    sort_name: str | None = None


@dataclass
class Recording:
    id: str
    title: str
    artist_id: str
    duration_ms: int | None = None
    mb_recording_id: str | None = None


@dataclass
class Album:
    id: str
    title: str
    primary_type: str | None = None
    secondary_types: list[str] = field(default_factory=list)
    artist_id: str | None = None
    mb_release_group_id: str | None = None
    discogs_master_id: int | None = None
    release_year: int | None = None

    @property
    def is_compilation(self) -> bool:
        return "Compilation" in self.secondary_types

    @property
    def is_live(self) -> bool:
        return "Live" in self.secondary_types

    @property
    def is_soundtrack(self) -> bool:
        return "Soundtrack" in self.secondary_types


@dataclass
class Release:
    id: str
    album_id: str
    title: str
    release_year: int | None = None
    release_country: str | None = None
    is_remaster: bool = False
    is_deluxe: bool = False
    is_expanded: bool = False
    mb_release_id: str | None = None
    discogs_release_id: int | None = None
    label: str | None = None
    catalog_number: str | None = None

    @property
    def is_original(self) -> bool:
        return not self.is_remaster and not self.is_deluxe and not self.is_expanded


@dataclass
class PlatformTrack:
    id: str
    recording_id: str
    platform: str
    platform_track_id: str
    platform_album_id: str | None = None
    album_id: str | None = None
    release_id: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    quality_tier: str | None = None


@dataclass
class Evidence:
    id: str
    recording_id: str
    source: str
    evidence_type: str
    confidence: float
    raw_data: str | None = None
    is_current: bool = True
    superseded_by: str | None = None
    created_at: str | None = None


@dataclass
class RecordingCandidate:
    title: str
    artist: str
    mb_recording_id: str | None = None
    duration_ms: int | None = None
    score: float = 0.0
    release_groups: list[dict] = field(default_factory=list)


@dataclass
class SourceResult:
    recordings: list[RecordingCandidate]
    evidence: Evidence | None = None
    rate_limit_remaining: int | None = None


@dataclass
class ResolvedTrack:
    recording: Recording
    albums: list[Album]
    confidence: ConfidenceTier
    confidence_score: float
    best_album: Album | None = None
    evidence: list[Evidence] = field(default_factory=list)
    platform_tracks: list[PlatformTrack] = field(default_factory=list)


@dataclass
class TrackInput:
    """Input track for the resolver pipeline (not a DB entity)."""
    platform: str
    platform_id: str
    title: str
    artist: str
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    platform_artist_id: str | None = None


@dataclass
class ResolutionResult:
    """Result from the resolver pipeline."""
    platform: str
    platform_id: str
    title: str
    artist: str
    mb_recording_id: str | None = None
    confidence: float = 0.0
    tier: ConfidenceTier = ConfidenceTier.UNCERTAIN
    evidence: list[Evidence] = field(default_factory=list)
    resolved_at: "datetime | None" = None

